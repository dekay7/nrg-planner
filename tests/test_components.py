from itertools import product

import pytest

from conftest import fixture,NOW,ZONE
from custom_components.nrg.planner import plan


@pytest.mark.parametrize("solar,battery,ev",list(product((False,True),repeat=3)))
def test_all_optional_hardware_combinations(solar,battery,ev):
    config,prices,outlook,telemetry,stats=fixture(has_solar=solar,has_battery=battery,has_ev=ev)
    result=plan(NOW,config,ZONE,telemetry,stats,prices,outlook,.15)
    assert result["household"]["windows"]
    if not solar:
        assert all(s["solar_known"] and s["solar_kwh"] == 0 for s in result["slots"])
    if not battery:
        assert result["effective_capacity_kwh"] == 0
        assert all(s["battery_action"] == "hold" and s["battery_soc"] is None for s in result["slots"])
    if not ev:
        assert result["ev_status"] == "not_installed" and result["deadline"] is None
        assert all(s["ev_kwh"] == 0 for s in result["slots"])


def test_grid_only_flat_home_has_normal_advice_without_missing_equipment_warnings():
    config,_,_,_,stats=fixture(has_solar=False,has_battery=False,has_ev=False,supply_plan="Flat supply",flat_supply_cents=10,delivery_cents=4)
    result=plan(NOW,config,ZONE,{},stats,[],{})
    assert result["household"]["category"] == "normal"
    assert result["household"]["confidence"] == "forecast"
    assert "battery" not in result["household"]["reason"].lower()


def test_monitoring_does_not_invent_ev_or_battery_commands():
    config,prices,outlook,telemetry,stats=fixture(ev_control=False,battery_control=False)
    telemetry["ev_kw"]=9
    result=plan(NOW,config,ZONE,telemetry,stats,prices,outlook,.15)
    assert result["ev_status"] == "monitor_only" and result["ev_amps"] == 0
    assert result["completion"] is None
    assert any(s["ev_kwh"]>0 for s in result["slots"])
    assert all(s["battery_action"] == "hold" for s in result["slots"])
