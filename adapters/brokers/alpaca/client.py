from __future__ import annotations

import httpx


class AlpacaBrokerAdapter:
    """Minimal Alpaca connectivity tester."""

    name = "alpaca"

    async def test_connection(self, api_key: str, secret_key: str, base_url: str) -> dict:
        if not api_key or not secret_key or not base_url:
            return {
                "ok": False,
                "provider": self.name,
                "message": "Alpaca credentials are incomplete.",
                "sample_data": None,
            }

        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        normalized_base_url = base_url.rstrip("/")
        if normalized_base_url.endswith("/v2"):
            url = f"{normalized_base_url}/account"
        else:
            url = f"{normalized_base_url}/v2/account"

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

