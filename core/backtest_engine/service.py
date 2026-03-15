from __future__ import annotations

from database.models import BacktestRun
from database.session import SessionLocal

from core.service_base import EngineService


class BacktestEngineService(EngineService):
    service_name = "backtest_engine"

    async def on_start(self) -> None:
        await super().on_start()
        with SessionLocal() as db:
            existing = db.query(BacktestRun).count()
            if existing == 0:
                db.add(
                    BacktestRun(
                        name="phase1_smoke_test",
                        strategy_id="vwap_strategy",
                        parameters={"lookback": 20},
                        status="ready",
                        result_summary={"note": "placeholder backtest run"},
                    )
                )
                db.commit()
        self._message = "ready for historical simulation"
        self._metrics["simulation_modes"] = 3

