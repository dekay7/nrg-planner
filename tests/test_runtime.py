from types import SimpleNamespace
from unittest.mock import patch

from custom_components.nrg.runtime import NRGRuntime
from custom_components.nrg.config import settings
from conftest import NOW


async def test_today_forecast_survives_tomorrow_endpoint_failure():
    text = " ".join(f"Date.UTC(2026,9,20,{h},0,0),4" for h in range(24))
    async def get_text(url, params):
        if params["type"] == "daynexttoday":
            return text
        raise TimeoutError("tomorrow temporarily unavailable")
    runtime = SimpleNamespace(config=settings({"supply_plan": "Hourly ComEd"}), entry=SimpleNamespace(options={}),
        prices=[], forecast_status={}, get_text=get_text, last_fetch=0)
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW):
        await NRGRuntime.refresh_forecasts(runtime)
    assert len(runtime.prices) == 24
    assert runtime.prices[0]["fetched_at"] == NOW
    assert "Tomorrow" in runtime.forecast_status["comed"]
