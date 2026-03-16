from __future__ import annotations

from datetime import datetime, timezone

import httpx


class AlpacaBrokerAdapter:
    """Minimal Alpaca connectivity tester."""

    name = "alpaca"

    @staticmethod
    def _trading_base_url(base_url: str) -> str:
        normalized_base_url = base_url.rstrip("/")
        if normalized_base_url.endswith("/v2"):
            return normalized_base_url[:-3]
        return normalized_base_url

    @staticmethod
    def _data_base_url(base_url: str) -> str:
        trading_base = AlpacaBrokerAdapter._trading_base_url(base_url)
        if "paper-api.alpaca.markets" in trading_base:
            return "https://data.alpaca.markets"
        if "api.alpaca.markets" in trading_base:
            return "https://data.alpaca.markets"
        return trading_base

    @staticmethod
    def _headers(api_key: str, secret_key: str) -> dict:
        return {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

    @staticmethod
    def _isoformat(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    async def test_connection(self, api_key: str, secret_key: str, base_url: str) -> dict:
        if not api_key or not secret_key or not base_url:
            return {
                "ok": False,
                "provider": self.name,
                "message": "Alpaca credentials are incomplete.",
                "sample_data": None,
            }

        headers = self._headers(api_key, secret_key)
        url = f"{self._trading_base_url(base_url)}/v2/account"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            return {
                "ok": True,
                "provider": self.name,
                "message": "Alpaca connection test succeeded.",
                "sample_data": {
                    "account_number": payload.get("account_number"),
                    "status": payload.get("status"),
                    "currency": payload.get("currency"),
                    "buying_power": payload.get("buying_power"),
                    "cash": payload.get("cash"),
                    "portfolio_value": payload.get("portfolio_value"),
                },
            }
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "provider": self.name,
                "message": f"Alpaca request failed with status {exc.response.status_code}.",
                "sample_data": {"response": exc.response.text[:500]},
            }
        except Exception as exc:  # pragma: no cover - network variability
            return {
                "ok": False,
                "provider": self.name,
                "message": f"Alpaca test failed: {exc}",
                "sample_data": None,
            }

    async def list_active_assets(self, api_key: str, secret_key: str, base_url: str) -> list[dict]:
        if not api_key or not secret_key or not base_url:
            raise ValueError("Alpaca credentials are incomplete.")

        url = f"{self._trading_base_url(base_url)}/v2/assets"
        params = {
            "status": "active",
            "asset_class": "us_equity",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers(api_key, secret_key), params=params)
            response.raise_for_status()
            payload = response.json()

        assets = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if not item.get("symbol"):
                continue
            if item.get("tradable") is False:
                continue
            assets.append(item)
        return assets

    async def get_stock_bars(
        self,
        api_key: str,
        secret_key: str,
        base_url: str,
        *,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment: str = "raw",
        feed: str = "iex",
        limit: int = 10000,
    ) -> dict[str, list[dict]]:
        if not api_key or not secret_key or not base_url:
            raise ValueError("Alpaca credentials are incomplete.")
        if not symbols:
            return {}

        url = f"{self._data_base_url(base_url)}/v2/stocks/bars"
        headers = self._headers(api_key, secret_key)
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": self._isoformat(start),
            "end": self._isoformat(end),
            "adjustment": adjustment,
            "feed": feed,
            "limit": str(limit),
            "sort": "asc",
        }

        all_bars: dict[str, list[dict]] = {symbol: [] for symbol in symbols}
        next_page_token = None

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                request_params = dict(params)
                if next_page_token:
                    request_params["page_token"] = next_page_token
                response = await client.get(url, headers=headers, params=request_params)
                response.raise_for_status()
                payload = response.json()
                for symbol, bars in payload.get("bars", {}).items():
                    all_bars.setdefault(symbol, []).extend(bars)
                next_page_token = payload.get("next_page_token")
                if not next_page_token:
                    break

        return {symbol: bars for symbol, bars in all_bars.items() if bars}

