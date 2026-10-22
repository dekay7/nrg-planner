"""Invented price outages, recovery and fallback planning scenarios."""
import pytest

from conftest import NOW, ZONE, fixture
from custom_components.nrg.fallback import PriceFallback, live_valid
from custom_components.nrg.planner import plan


def test_brief_failure_only_degrades_and_long_failure_enters_fallback():
    state = PriceFallback()
    assert not state.update(NOW, enabled=True, known=True, degraded=True)
    assert state.state == "Degraded"
    assert state.update(NOW + 900, enabled=True, known=False)
    assert state.state == "Fallback"


def test_recovery_requires_stability_distinct_observation_and_coordinator():
    state = PriceFallback()
    state.update(NOW, enabled=True, known=False)
    assert state.update(NOW + 10, enabled=True, known=True, observation=1, allow_recovery=True)
    assert state.state == "Recovering"
    assert state.update(NOW + 130, enabled=True, known=True, observation=1, allow_recovery=True)
    assert state.update(NOW + 140, enabled=True, known=True, observation=2)
    assert not state.update(NOW + 141, enabled=True, known=True, observation=2, allow_recovery=True)
    assert state.state == "Healthy"


def test_recovery_flap_restarts_timer_and_backwards_clock_cannot_recover():
    state = PriceFallback()
    state.update(NOW, enabled=True, known=False)
    state.update(NOW + 10, enabled=True, known=True, observation=1)
    state.update(NOW + 100, enabled=True, known=False)
    assert state.update(NOW + 200, enabled=True, known=True, observation=2, allow_recovery=True)
    assert state.update(NOW + 150, enabled=True, known=True, observation=3, allow_recovery=True)
    assert state.recovery_since == NOW + 150
    assert state.update(NOW + 260, enabled=True, known=True, observation=4, allow_recovery=True)


def test_manual_stays_active_until_released_and_does_not_bypass_automatic():
    state = PriceFallback(manual=True)
    assert state.update(NOW, enabled=True, known=True)
    assert state.update(NOW + 1000, enabled=True, known=True, allow_recovery=True)
    state.manual = False
    assert not state.update(NOW + 1001, enabled=True, known=True, allow_recovery=True)
    assert state.update(NOW + 1002, enabled=True, known=False)
    state.manual = True
    state.update(NOW + 1003, enabled=True, known=False)
    state.manual = False
    assert state.update(NOW + 1004, enabled=True, known=False)


def test_legacy_defaults_do_not_activate_custom_fallback():
    state = PriceFallback(manual=True)
    assert not state.update(NOW, enabled=False, known=False)
    assert state.state == "Degraded"
    config, *_ = fixture()
    assert config["price_fallback"] == "Existing behavior"
    assert config["fallback_battery"] == "Preserve battery"
    assert not config["fallback_notifications"]


def test_live_price_age_hour_boundary_and_future_timestamps():
    assert live_valid(NOW + 10, NOW + 100, hourly=True)
    assert not live_valid(NOW - 1, NOW, hourly=True)
    assert live_valid(NOW - 1, NOW)  # External non-hourly observation.
    assert not live_valid(NOW, NOW + 900)
    assert not live_valid(NOW + 1, NOW)


@pytest.mark.parametrize("charge_now", [False, True])
def test_fallback_pause_beats_deadline_unless_charge_now(charge_now):
    config, prices, solar, telemetry, stats = fixture(
        _fallback_active=True, fallback_ev="Pause scheduled charging")
    # settings() intentionally excludes private model inputs.
    config["_fallback_active"] = True
    config["departure_override"] = "2026-10-19T18:15:00-05:00"
    result = plan(NOW, config, ZONE, telemetry, stats, prices, solar, None, charge_now=charge_now)
    if charge_now:
        assert result["ev_status"] == "charge_now"
        assert result["ev_amps"] > 0
    else:
        assert result["ev_status"] == "fallback_paused"
        assert result["ev_shortfall_kwh"] > 0
        assert result["completion"] is None
        assert all(s["ev_amps"] == 0 for s in result["slots"])
    assert result["household"]["category"] == "limited"


@pytest.mark.parametrize("policy,expected", [("Preserve battery", "hold"), ("Self-consumption", "serve")])
def test_fallback_battery_outlook_uses_baseline_not_unknown_price_arbitrage(policy, expected):
    config, _, solar, telemetry, stats = fixture(has_ev=False, fallback_battery=policy)
    config["_fallback_active"] = True
    result = plan(NOW, config, ZONE, telemetry, stats, [], solar, None)
    assert result["battery_action"] == expected
    assert all(s["battery_action"] != "charge" and s["cost"] is None for s in result["slots"])
    assert result["modeled_cost"] is None
    assert "fallback" in result["battery_reason"]
    assert min(s["battery_soc"] for s in result["slots"]) >= config["backup_reserve"]


def test_maintain_departure_readiness_charges_when_urgent_without_prices():
    config, _, solar, telemetry, stats = fixture(fallback_ev="Maintain departure readiness")
    config["_fallback_active"] = True
    config["departure_override"] = "2026-10-19T18:15:00-05:00"
    result = plan(NOW, config, ZONE, telemetry, stats, [], solar, None)
    assert result["ev_amps"] > 0
    assert result["ev_status"] == "deadline"
    assert result["battery_action"] == "hold"
