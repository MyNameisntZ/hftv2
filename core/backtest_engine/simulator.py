from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta


SMALL_CAP_UNIVERSE = [
    {"symbol": "KULR", "price": 2.45, "float_millions": 17.2, "avg_volume": 8_400_000, "market_cap_millions": 210.0, "is_halted": False},
    {"symbol": "BBAI", "price": 4.85, "float_millions": 28.4, "avg_volume": 5_600_000, "market_cap_millions": 620.0, "is_halted": False},
    {"symbol": "RGTI", "price": 7.15, "float_millions": 16.8, "avg_volume": 12_200_000, "market_cap_millions": 950.0, "is_halted": False},
    {"symbol": "QBTS", "price": 3.65, "float_millions": 26.0, "avg_volume": 9_700_000, "market_cap_millions": 480.0, "is_halted": False},
    {"symbol": "SOUN", "price": 13.25, "float_millions": 240.0, "avg_volume": 21_000_000, "market_cap_millions": 4300.0, "is_halted": False},
    {"symbol": "AEMD", "price": 3.18, "float_millions": 9.6, "avg_volume": 2_700_000, "market_cap_millions": 41.0, "is_halted": False},
    {"symbol": "SNDL", "price": 2.12, "float_millions": 185.0, "avg_volume": 4_300_000, "market_cap_millions": 520.0, "is_halted": False},
    {"symbol": "HSDT", "price": 9.8, "float_millions": 6.4, "avg_volume": 1_200_000, "market_cap_millions": 55.0, "is_halted": False},
]


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


def _deterministic_ratio(key: str) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _filter_universe(scanner_settings: dict) -> list[dict]:
    min_price = float(scanner_settings.get("min_price", 2.0))
    max_price = float(scanner_settings.get("max_price", 20.0))
    max_float = float(scanner_settings.get("max_float_millions", 20.0))
    min_avg_volume = int(scanner_settings.get("min_avg_volume", 0))
    max_market_cap = float(scanner_settings.get("max_market_cap_millions", 1000.0))
    exclude_halted = bool(scanner_settings.get("exclude_halted", True))

    filtered = []
    for item in SMALL_CAP_UNIVERSE:
        if not (min_price <= item["price"] <= max_price):
            continue
        if item["float_millions"] > max_float:
            continue
        if item["avg_volume"] < min_avg_volume:
            continue
        if item["market_cap_millions"] > max_market_cap:
            continue
        if exclude_halted and item["is_halted"]:
            continue
        filtered.append(item)
    return filtered


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


def _simulate_variant(
    strategy_id: str,
    parameters: dict,
    selected_universe: list[dict],
    simulation_days: int,
    starting_capital: float,
    account_type: str,
    settlement_days: int,
) -> VariantResult:
    cash = starting_capital
    unsettled: list[tuple[date, float]] = []
    equity_curve: list[float] = [starting_capital]
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    total_trades = 0
    current_day = date.today() - timedelta(days=simulation_days)
    capital_fraction = 0.22

    for day_offset in range(simulation_days):
        current_day = current_day + timedelta(days=1)
        settled_today = [amount for settle_date, amount in unsettled if settle_date <= current_day]
        unsettled = [(settle_date, amount) for settle_date, amount in unsettled if settle_date > current_day]
        cash += sum(settled_today)

        for symbol_data in selected_universe:
            symbol = symbol_data["symbol"]
            decision_key = f"{strategy_id}:{symbol}:{current_day.isoformat()}:{parameters}"
            signal_ratio = _deterministic_ratio(decision_key)
            if signal_ratio < 0.58:
                continue

            available_cash = cash if account_type == "Cash Account" else cash + sum(amount for _, amount in unsettled)
            risk_budget = max(0.0, available_cash * capital_fraction)
            position_size = min(risk_budget, cash if account_type == "Cash Account" else risk_budget)
            if position_size < 100:
                continue

            stop_loss_pct = float(parameters.get("stop_loss_pct", 2.5))
            take_profit_pct = float(parameters.get("take_profit_pct", 5.0))
            reward_multiplier = take_profit_pct / max(stop_loss_pct, 0.5)
            performance_bias = (_deterministic_ratio(f"perf:{decision_key}") - 0.5) * 0.06
            pnl_pct = performance_bias + (reward_multiplier - 1.5) * 0.004
            pnl = round(position_size * pnl_pct, 2)
            proceeds = position_size + pnl

            cash -= position_size
            if account_type == "Cash Account" and settlement_days > 0:
                unsettled.append((current_day + timedelta(days=settlement_days), proceeds))
            else:
                cash += proceeds

            total_trades += 1
            if pnl >= 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)

        ending_equity = cash + sum(amount for _, amount in unsettled)
        equity_curve.append(ending_equity)

    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    ending_equity = cash + sum(amount for _, amount in unsettled)
    net_profit = round(ending_equity - starting_capital, 2)
    win_rate = round((wins / total_trades) * 100, 2) if total_trades else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else round(gross_profit, 2)

    return VariantResult(
        parameters=parameters,
        net_profit=net_profit,
        ending_equity=round(ending_equity, 2),
        win_rate=win_rate,
        total_trades=total_trades,
        profit_factor=profit_factor,
        max_drawdown=round(max_drawdown * 100, 2),
        settled_cash_end=round(cash, 2),
    )


def run_accelerated_backtest(
    *,
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
    data_source: str,
) -> dict:
    selected_universe = _filter_universe(scanner_settings)
    variants = _parameter_variants(strategy_id, base_parameters, mode)

    if not selected_universe:
        return {
            "strategy_name": strategy_name,
            "simulation_model": "accelerated_replay",
            "replay_speed": replay_speed,
            "data_source": data_source,
            "note": "No symbols matched the active universe filters.",
            "universe_size": 0,
            "anchor_days_old": anchor_days_old,
            "simulation_days": simulation_days,
            "account_type": account_type,
            "settlement_days": settlement_days,
            "variants_tested": 0,
        }

    results = [
        _simulate_variant(
            strategy_id,
            variant,
            selected_universe,
            simulation_days,
            starting_capital,
            account_type,
            settlement_days,
        )
        for variant in variants
    ]
    best = max(results, key=lambda result: result.net_profit)

    return {
        "strategy_name": strategy_name,
        "simulation_model": "accelerated_replay",
        "replay_speed": replay_speed,
        "data_source": data_source,
        "anchor_days_old": anchor_days_old,
        "simulation_days": simulation_days,
        "account_type": account_type,
        "settlement_days": settlement_days,
        "universe_size": len(selected_universe),
        "universe_symbols": [item["symbol"] for item in selected_universe],
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
        },
        "suggestion": (
            f"Best variant for {strategy_name} used stop {best.parameters.get('stop_loss_pct')}% "
            f"and target {best.parameters.get('take_profit_pct')}%."
        ),
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

