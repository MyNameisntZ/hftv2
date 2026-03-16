from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean

from adapters.brokers.alpaca.client import AlpacaBrokerAdapter
from sqlalchemy import select

from database.models import TickerMetadata
from database.session import SessionLocal


UNIVERSE_CHUNK_SIZE = 100
QUALIFICATION_LOOKBACK_DAYS = 20
CONCURRENT_BAR_REQUESTS = 6


@dataclass
class QualifiedSymbol:
    symbol: str
    price: float
    avg_volume: float
    float_millions: float | None
    market_cap_millions: float | None
    is_halted: bool


@dataclass
class CandidateTrade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl_pct: float
    confidence: float
    exit_reason: str
    setup: dict


@dataclass
class VariantResult:
    parameters: dict
    net_profit: float
    ending_equity: float
    win_rate: float
    total_trades: int
    profit_factor: float
    max_drawdown: float
    settled_cash_end: float
    trade_log: list[dict]


def _utc_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _chunked(items: list[str], chunk_size: int) -> list[list[str]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _parse_bar_timestamp(bar: dict) -> datetime:
    raw_value = str(bar.get("t"))
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(UTC)


def _normalize_bar(bar: dict) -> dict:
    timestamp = _parse_bar_timestamp(bar)
    return {
        "time": timestamp,
        "open": float(bar.get("o", 0.0)),
        "high": float(bar.get("h", 0.0)),
        "low": float(bar.get("l", 0.0)),
        "close": float(bar.get("c", 0.0)),
        "volume": int(bar.get("v", 0)),
    }


def _load_cached_metadata(symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}

    with SessionLocal() as db:
        rows = db.scalars(select(TickerMetadata).where(TickerMetadata.symbol.in_(symbols))).all()

    return {
        row.symbol: {
            "float_millions": None if row.float_shares is None else round(row.float_shares / 1_000_000, 2),
            "market_cap_millions": None if row.market_cap is None else round(row.market_cap / 1_000_000, 2),
            "is_halted": bool(row.is_halted),
        }
        for row in rows
    }


async def _fetch_bar_batches(
    adapter: AlpacaBrokerAdapter,
    credentials: dict,
    *,
    symbols: list[str],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> dict[str, list[dict]]:
    semaphore = asyncio.Semaphore(CONCURRENT_BAR_REQUESTS)

    async def fetch_chunk(chunk: list[str]) -> dict[str, list[dict]]:
        async with semaphore:
            return await adapter.get_stock_bars(
                credentials.get("alpaca_api_key", ""),
                credentials.get("alpaca_secret_key", ""),
                credentials.get("alpaca_base_url", ""),
                symbols=chunk,
                timeframe=timeframe,
                start=start,
                end=end,
            )

    results = await asyncio.gather(*[fetch_chunk(chunk) for chunk in _chunked(symbols, UNIVERSE_CHUNK_SIZE)])
    merged: dict[str, list[dict]] = {}
    for payload in results:
        for symbol, bars in payload.items():
            merged[symbol] = [_normalize_bar(bar) for bar in bars]
    return merged


def _qualifies(scanner_settings: dict, symbol_data: QualifiedSymbol) -> bool:
    min_price = float(scanner_settings.get("min_price", 0.0))
    max_price = float(scanner_settings.get("max_price", 1_000_000.0))
    min_avg_volume = int(scanner_settings.get("min_avg_volume", 0))
    max_float = float(scanner_settings.get("max_float_millions", 1_000_000.0))
    max_market_cap = float(scanner_settings.get("max_market_cap_millions", 1_000_000.0))
    exclude_halted = bool(scanner_settings.get("exclude_halted", True))

    if not (min_price <= symbol_data.price <= max_price):
        return False
    if symbol_data.avg_volume < min_avg_volume:
        return False
    if symbol_data.float_millions is not None and symbol_data.float_millions > max_float:
        return False
    if symbol_data.market_cap_millions is not None and symbol_data.market_cap_millions > max_market_cap:
        return False
    if exclude_halted and symbol_data.is_halted:
        return False
    return True


def _build_qualified_universe(
    scanner_settings: dict,
    daily_bars: dict[str, list[dict]],
    metadata_map: dict[str, dict],
    qualification_date: date,
) -> tuple[list[QualifiedSymbol], list[str]]:
    notes: list[str] = []
    qualified: list[QualifiedSymbol] = []
    missing_float = 0
    missing_market_cap = 0

    for symbol, bars in daily_bars.items():
        eligible_bars = [bar for bar in bars if bar["time"].date() <= qualification_date]
        if len(eligible_bars) < 5:
            continue
        recent_bars = eligible_bars[-5:]
        latest_bar = recent_bars[-1]
        avg_volume = mean(bar["volume"] for bar in recent_bars)

        metadata = metadata_map.get(symbol, {})
        symbol_data = QualifiedSymbol(
            symbol=symbol,
            price=round(latest_bar["close"], 4),
            avg_volume=round(avg_volume, 2),
            float_millions=metadata.get("float_millions"),
            market_cap_millions=metadata.get("market_cap_millions"),
            is_halted=bool(metadata.get("is_halted", False)),
        )
        if symbol_data.float_millions is None:
            missing_float += 1
        if symbol_data.market_cap_millions is None:
            missing_market_cap += 1
        if _qualifies(scanner_settings, symbol_data):
            qualified.append(symbol_data)

    qualified.sort(key=lambda item: (-item.avg_volume, item.price, item.symbol))

    if missing_float:
        notes.append(
            f"Float metadata was unavailable for {missing_float} symbols, so max-float filtering only applied where cached metadata existed."
        )
    if missing_market_cap:
        notes.append(
            f"Market-cap metadata was unavailable for {missing_market_cap} symbols, so max-market-cap filtering only applied where cached metadata existed."
        )

    return qualified, notes


def _confidence_score(parameters: dict, impulse_pct: float, pullback_pct: float, volume_ratio: float) -> float:
    impulse_component = min(1.0, impulse_pct / max(float(parameters.get("flagpole_min_pct", 6.0)), 0.1))
    pullback_component = 1.0 - min(
        1.0,
        pullback_pct / max(float(parameters.get("pullback_max_pct", 2.2)), 0.1),
    )
    volume_component = min(1.0, volume_ratio / max(float(parameters.get("volume_spike_ratio", 2.0)), 0.1))
    confidence = 0.45 * impulse_component + 0.25 * max(0.0, pullback_component) + 0.30 * volume_component
    return round(max(0.0, min(0.99, confidence)), 2)


def _generate_bull_flag_candidates(
    bars_by_symbol: dict[str, list[dict]],
    parameters: dict,
    simulation_start: date,
) -> list[CandidateTrade]:
    candidates: list[CandidateTrade] = []
    flagpole_min_pct = float(parameters.get("flagpole_min_pct", 6.0))
    pullback_max_pct = float(parameters.get("pullback_max_pct", 2.2))
    breakout_buffer_pct = float(parameters.get("breakout_buffer_pct", 0.35))
    volume_spike_ratio = float(parameters.get("volume_spike_ratio", 2.0))
    confidence_threshold = float(parameters.get("confidence_threshold", 0.67))
    stop_loss_pct = float(parameters.get("stop_loss_pct", 2.7)) / 100
    take_profit_pct = float(parameters.get("take_profit_pct", 6.5)) / 100

    for symbol, bars in bars_by_symbol.items():
        usable_bars = [bar for bar in bars if bar["time"].date() >= simulation_start]
        if len(usable_bars) < 12:
            continue

        index = 8
        while index < len(usable_bars) - 1:
            current = usable_bars[index]
            impulse_window = usable_bars[max(0, index - 8) : index - 2]
            consolidation_window = usable_bars[max(0, index - 3) : index]
            volume_window = usable_bars[max(0, index - 8) : index]
            if len(impulse_window) < 4 or len(consolidation_window) < 3 or len(volume_window) < 5:
                index += 1
                continue

            pole_low = min(bar["low"] for bar in impulse_window)
            pole_high = max(bar["high"] for bar in impulse_window)
            if pole_low <= 0:
                index += 1
                continue

            impulse_pct = ((pole_high - pole_low) / pole_low) * 100
            if impulse_pct < flagpole_min_pct:
                index += 1
                continue

            pullback_low = min(bar["low"] for bar in consolidation_window)
            pullback_pct = ((pole_high - pullback_low) / pole_high) * 100 if pole_high > 0 else 0.0
            if pullback_pct > pullback_max_pct:
                index += 1
                continue

            consolidation_high = max(bar["high"] for bar in consolidation_window)
            breakout_price = consolidation_high * (1 + breakout_buffer_pct / 100)
            average_volume = mean(bar["volume"] for bar in volume_window)
            current_volume_ratio = current["volume"] / average_volume if average_volume > 0 else 0.0
            if current_volume_ratio < volume_spike_ratio:
                index += 1
                continue

            if current["close"] < breakout_price and current["high"] < breakout_price:
                index += 1
                continue

            confidence = _confidence_score(parameters, impulse_pct, pullback_pct, current_volume_ratio)
            if confidence < confidence_threshold:
                index += 1
                continue

            entry_price = max(current["close"], breakout_price)
            stop_price = entry_price * (1 - stop_loss_pct)
            target_price = entry_price * (1 + take_profit_pct)

            exit_price = usable_bars[-1]["close"]
            exit_time = usable_bars[-1]["time"]
            exit_reason = "window_close"
            exit_index = len(usable_bars) - 1
            for forward_index in range(index + 1, len(usable_bars)):
                future_bar = usable_bars[forward_index]
                stop_hit = future_bar["low"] <= stop_price
                target_hit = future_bar["high"] >= target_price
                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_time = future_bar["time"]
                    exit_reason = "stop_before_target"
                    exit_index = forward_index
                    break
                if stop_hit:
                    exit_price = stop_price
                    exit_time = future_bar["time"]
                    exit_reason = "stop_loss"
                    exit_index = forward_index
                    break
                if target_hit:
                    exit_price = target_price
                    exit_time = future_bar["time"]
                    exit_reason = "take_profit"
                    exit_index = forward_index
                    break

            candidates.append(
                CandidateTrade(
                    symbol=symbol,
                    entry_time=current["time"],
                    exit_time=exit_time,
                    entry_price=round(entry_price, 4),
                    exit_price=round(exit_price, 4),
                    pnl_pct=round(((exit_price - entry_price) / entry_price) * 100, 4),
                    confidence=confidence,
                    exit_reason=exit_reason,
                    setup={
                        "impulse_pct": round(impulse_pct, 2),
                        "pullback_pct": round(pullback_pct, 2),
                        "volume_ratio": round(current_volume_ratio, 2),
                    },
                )
            )
            index = max(index + 1, exit_index + 1)

    candidates.sort(key=lambda candidate: (candidate.entry_time, -candidate.confidence, candidate.symbol))
    return candidates


def _simulate_account(
    candidates: list[CandidateTrade],
    parameters: dict,
    starting_capital: float,
    account_type: str,
    settlement_days: int,
) -> VariantResult:
    cash = starting_capital
    unsettled: list[tuple[date, float]] = []
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    equity_curve = [starting_capital]
    trade_log: list[dict] = []
    capital_fraction = 0.22

    for candidate in candidates:
        current_day = candidate.entry_time.date()
        settled_today = [amount for settle_day, amount in unsettled if settle_day <= current_day]
        unsettled = [(settle_day, amount) for settle_day, amount in unsettled if settle_day > current_day]
        cash += sum(settled_today)

        available_cash = cash if account_type == "Cash Account" else cash + sum(amount for _, amount in unsettled)
        risk_budget = max(0.0, available_cash * capital_fraction)
        position_budget = min(risk_budget, cash if account_type == "Cash Account" else risk_budget)
        if position_budget < candidate.entry_price:
            continue

        shares = int(position_budget / candidate.entry_price)
        if shares <= 0:
            continue

        cost_basis = round(shares * candidate.entry_price, 2)
        proceeds = round(shares * candidate.exit_price, 2)
        pnl = round(proceeds - cost_basis, 2)

        cash -= cost_basis
        if account_type == "Cash Account" and settlement_days > 0:
            unsettled.append((candidate.exit_time.date() + timedelta(days=settlement_days), proceeds))
        else:
            cash += proceeds

        if pnl >= 0:
            wins += 1
            gross_profit += pnl
        else:
            losses += 1
            gross_loss += abs(pnl)

        trade_log.append(
            {
                "symbol": candidate.symbol,
                "entry_time": candidate.entry_time.isoformat(),
                "exit_time": candidate.exit_time.isoformat(),
                "entry_price": candidate.entry_price,
                "exit_price": candidate.exit_price,
                "shares": shares,
                "pnl": pnl,
                "pnl_pct": candidate.pnl_pct,
                "confidence": candidate.confidence,
                "exit_reason": candidate.exit_reason,
                "setup": candidate.setup,
            }
        )
        equity_curve.append(cash + sum(amount for _, amount in unsettled))

    ending_equity = round(cash + sum(amount for _, amount in unsettled), 2)
    total_trades = len(trade_log)
    win_rate = round((wins / total_trades) * 100, 2) if total_trades else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else round(gross_profit, 2)

    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    return VariantResult(
        parameters=parameters,
        net_profit=round(ending_equity - starting_capital, 2),
        ending_equity=ending_equity,
        win_rate=win_rate,
        total_trades=total_trades,
        profit_factor=profit_factor,
        max_drawdown=round(max_drawdown * 100, 2),
        settled_cash_end=round(cash, 2),
        trade_log=trade_log[:50],
    )


def _parameter_variants(strategy_id: str, parameters: dict, mode: str) -> list[dict]:
    if strategy_id != "bull_flag_breakout" or mode == "Simple Replay":
        return [parameters]

    stop_values = sorted(
        {
            round(max(0.5, float(parameters.get("stop_loss_pct", 2.7)) + delta), 2)
            for delta in (-0.75, 0.0, 0.75)
        }
    )
    target_values = sorted(
        {
            round(max(1.0, float(parameters.get("take_profit_pct", 6.5)) + delta), 2)
            for delta in (-1.5, 0.0, 1.5)
        }
    )

    variants = []
    for stop_loss_pct in stop_values:
        for take_profit_pct in target_values:
            variant = dict(parameters)
            variant["stop_loss_pct"] = stop_loss_pct
            variant["take_profit_pct"] = take_profit_pct
            variants.append(variant)
    return variants


async def run_alpaca_historical_backtest(
    *,
    adapter: AlpacaBrokerAdapter,
    credentials: dict,
    strategy_id: str,
    strategy_name: str,
    base_parameters: dict,
    scanner_settings: dict,
    mode: str,
    anchor_days_old: int,
    simulation_days: int,
    starting_capital: float,
    settlement_days: int,
    account_type: str,
    replay_speed: str,
) -> dict:
    simulation_end = datetime.now(UTC).date() - timedelta(days=max(anchor_days_old, 1))
    simulation_start = simulation_end - timedelta(days=max(simulation_days - 1, 0))
    qualification_start = simulation_start - timedelta(days=QUALIFICATION_LOOKBACK_DAYS)

    assets = await adapter.list_active_assets(
        credentials.get("alpaca_api_key", ""),
        credentials.get("alpaca_secret_key", ""),
        credentials.get("alpaca_base_url", ""),
    )
    symbols = sorted({asset["symbol"] for asset in assets if asset.get("symbol")})

    historical_daily_bars = await _fetch_bar_batches(
        adapter,
        credentials,
        symbols=symbols,
        timeframe="1Day",
        start=_utc_midnight(qualification_start),
        end=_utc_midnight(simulation_end + timedelta(days=1)),
    )
    metadata_map = _load_cached_metadata(list(historical_daily_bars))
    qualified_universe, notes = _build_qualified_universe(
        scanner_settings,
        historical_daily_bars,
        metadata_map,
        simulation_start,
    )

    if not qualified_universe:
        return {
            "strategy_name": strategy_name,
            "simulation_model": "alpaca_historical_daily_replay",
            "replay_speed": replay_speed,
            "data_source": "Alpaca Historical Data",
            "note": "No symbols matched the active universe filters.",
            "notes": notes,
            "universe_size": 0,
            "anchor_days_old": anchor_days_old,
            "simulation_days": simulation_days,
            "account_type": account_type,
            "settlement_days": settlement_days,
            "variants_tested": 0,
            "assets_considered": len(symbols),
        }

    qualified_symbols = [item.symbol for item in qualified_universe]
    qualified_daily_bars = {
        symbol: historical_daily_bars.get(symbol, [])
        for symbol in qualified_symbols
    }

    variants = _parameter_variants(strategy_id, base_parameters, mode)
    results = []
    for variant in variants:
        candidates = _generate_bull_flag_candidates(qualified_daily_bars, variant, simulation_start)
        results.append(
            _simulate_account(
                candidates,
                variant,
                starting_capital,
                account_type,
                settlement_days,
            )
        )

    best = max(results, key=lambda item: item.net_profit)
    top_ranked = [
        {
            "symbol": item.symbol,
            "price": item.price,
            "avg_volume": item.avg_volume,
            "float_millions": item.float_millions,
            "market_cap_millions": item.market_cap_millions,
            "is_halted": item.is_halted,
        }
        for item in qualified_universe[:50]
    ]

    return {
        "strategy_name": strategy_name,
        "simulation_model": "alpaca_historical_daily_replay",
        "replay_speed": replay_speed,
        "data_source": "Alpaca Historical Data",
        "anchor_days_old": anchor_days_old,
        "simulation_days": simulation_days,
        "account_type": account_type,
        "settlement_days": settlement_days,
        "assets_considered": len(symbols),
        "universe_size": len(qualified_universe),
        "universe_symbols": qualified_symbols[:250],
        "universe_ranked": top_ranked,
        "qualification_date": simulation_start.isoformat(),
        "variants_tested": len(results),
        "best_variant": {
            "parameters": best.parameters,
            "net_profit": best.net_profit,
            "ending_equity": best.ending_equity,
            "win_rate": best.win_rate,
            "total_trades": best.total_trades,
            "profit_factor": best.profit_factor,
            "max_drawdown": best.max_drawdown,
            "settled_cash_end": best.settled_cash_end,
            "trade_log": best.trade_log,
        },
        "suggestion": (
            f"Best variant for {strategy_name} used stop {best.parameters.get('stop_loss_pct')}% "
            f"and target {best.parameters.get('take_profit_pct')}% across {len(qualified_universe)} qualified symbols in the daily historical scan."
        ),
        "notes": notes,
        "all_variants": [
            {
                "parameters": result.parameters,
                "net_profit": result.net_profit,
                "ending_equity": result.ending_equity,
                "win_rate": result.win_rate,
                "total_trades": result.total_trades,
                "profit_factor": result.profit_factor,
                "max_drawdown": result.max_drawdown,
            }
            for result in sorted(results, key=lambda item: item.net_profit, reverse=True)
        ][:10],
    }
