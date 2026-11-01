from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.nrg.runtime import NRGRuntime
from custom_components.nrg.config import settings
from conftest import NOW, ZONE


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


@pytest.mark.parametrize("now, label", [
    (datetime(2026, 11, 1, 10, 15, tzinfo=ZONE).timestamp(), "Today"),
    (datetime(2026, 10, 31, 18, tzinfo=ZONE).timestamp(), "Tomorrow"),
])
async def test_dst_forecast_refresh_keeps_valid_hours_and_explains_omissions(now, label):
    today = datetime.fromtimestamp(now, ZONE).date()

    async def get_text(url, params):
        kind = params["type"]
        if kind == "hasdaynexttomorrow":
            return "true" if label == "Tomorrow" else "false"
        day = today + timedelta(days=kind == "daynexttomorrow")
        return " ".join(f"Date.UTC({day.year},{day.month - 1},{day.day},{h},0,0),{h - 8}" for h in range(24))

    runtime = SimpleNamespace(config=settings({"supply_plan": "Hourly ComEd"}), entry=SimpleNamespace(options={}),
        prices=[], forecast_status={}, get_text=get_text, last_fetch=0)
    with patch("custom_components.nrg.runtime.time.time", return_value=now):
        await NRGRuntime.refresh_forecasts(runtime)
    assert len(runtime.prices) == (23 if label == "Today" else 47)
    midday = datetime(2026, 11, 1, 11, tzinfo=ZONE).timestamp()
    assert next(row for row in runtime.prices if row["start"] == midday)["supply"] == .04
    assert f"{label}: 23 published hours loaded" in runtime.forecast_status["comed"]
    assert "DST labels omitted" in runtime.forecast_status["comed"]
