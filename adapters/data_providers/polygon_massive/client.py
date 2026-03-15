from __future__ import annotations

import httpx


class PolygonMassiveAdapter:
    """Minimal Polygon/Massive connectivity tester."""

    name = "polygon_massive"
    base_url = "https://api.polygon.io"

    async def test_connection(self, api_key: str) -> dict:
        if not api_key:
            return {
                "ok": False,
                "provider": self.name,
                "message": "Polygon API key is missing.",
                "sample_data": None,
            }

        url = f"{self.base_url}/v3/reference/tickers/AAPL"
        params = {"apiKey": api_key}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            result = payload.get("results", {})
            return {
                "ok": True,
                "provider": self.name,
                "message": "Polygon connection test succeeded.",
                "sample_data": {
                    "symbol": result.get("ticker"),
                    "name": result.get("name"),
                    "market": result.get("market"),
                    "locale": result.get("locale"),
                    "primary_exchange": result.get("primary_exchange"),
                    "active": result.get("active"),
                },
            }
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "provider": self.name,
                "message": f"Polygon request failed with status {exc.response.status_code}.",
                "sample_data": {"response": exc.response.text[:500]},
            }
        except Exception as exc:  # pragma: no cover - network variability
            return {
                "ok": False,
                "provider": self.name,
                "message": f"Polygon test failed: {exc}",
                "sample_data": None,
            }

