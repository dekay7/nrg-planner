"""Invented AC cycles and constrained-power opportunities, never equipment traces."""
import json

import pytest

from custom_components.nrg.battery_learning import BatteryLearning, MAX_AGE
from custom_components.nrg.config import settings
from custom_components.nrg.statistics import Statistics
from conftest import NOW


def config(**changes):
    return settings({"has_battery": True, "battery_learning": True, **changes})


def observation(power=0, soc=40, **changes):
    return {"battery_kw": power, "battery_soc": soc, "battery_learning_valid": True, **changes}


def cycle(learner, start=NOW, efficiency=.88, counters=False, reverse=False, **changes):
    # Two one-hour legs over the same 40 SOC points. Charge/discharge energy
    # need not be translated into assumed stored capacity to measure their ratio.
    for minute in range(121):
        if reverse:
            power = 6 * efficiency if minute < 60 else -6 if minute < 120 else 0
            soc = 80 - 40 * minute / 60 if minute <= 60 else 40 + 40 * (minute - 60) / 60
            charged = max(minute - 60, 0) * .1
            discharged = min(minute, 60) * .1 * efficiency
        else:
            power = -6 if minute < 60 else 6 * efficiency if minute < 120 else 0
            soc = 40 + 40 * minute / 60 if minute <= 60 else 80 - 40 * (minute - 60) / 60
            charged = min(minute, 60) * .1
            discharged = max(minute - 60, 0) * .1 * efficiency
        values = observation(power, soc, battery_energy_counters=counters,
                             battery_charge_energy=100 + charged, battery_discharge_energy=200 + discharged)
        learner.observe(start + minute * 60, values | changes, True)


def opportunity(learner, start=NOW, direction="charge", kw=4, minutes=20, eligible=True, spike=False):
    sign = -1 if direction == "charge" else 1
    for minute in range(minutes + 1):
        power = sign * (20 if spike and minute == 5 else kw)
        learner.observe(start + minute * 60, observation(power, 50 - sign * minute * .1,
                        **{"battery_" + direction + "_opportunity": eligible}), True)
    learner.observe(start + (minutes + 1) * 60, observation(0, 50 - sign * minutes * .1), True)


@pytest.mark.parametrize("counters", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_efficiency_needs_three_closed_cycles_and_not_configured_capacity(counters, reverse):
    learner = BatteryLearning()
    for index in range(3):
        cycle(learner, NOW + index * 7260, counters=counters, reverse=reverse)
        result = learner.quality(config(), NOW + index * 7260 + 7200)["estimates"]
        assert result["round_trip_efficiency"]["samples"] == index + 1
        assert result["round_trip_efficiency"]["source"] == ("learned" if index == 2 else "configured")
    now = NOW + 3 * 7260
    assert learner.model(config(battery_capacity=1), now)["round_trip_efficiency"] == pytest.approx(88)
    assert learner.model(config(battery_capacity=200), now)["round_trip_efficiency"] == pytest.approx(88)
    assert learner.model(config(), now)["battery_charge_kw"] == 5


def test_selected_counters_are_used_instead_of_sampled_power():
    learner = BatteryLearning()
    # Instantaneous power can miss changes between samples; the counters measure
    # 88% even though these sampled powers integrate to 100%.
    for index in range(3):
        for minute in range(121):
            values = observation(-6 if minute < 60 else 6 if minute < 120 else 0,
                                 40 + 40 * min(minute, 120 - minute) / 60,
                                 battery_energy_counters=True,
                                 battery_charge_energy=100 + min(minute, 60) * .1,
                                 battery_discharge_energy=200 + max(minute - 60, 0) * .088)
            learner.observe(NOW + index * 7260 + minute * 60, values, True)
    assert learner.model(config(), NOW + 22000)["round_trip_efficiency"] == pytest.approx(88)


@pytest.mark.parametrize("failure", ["gap", "missing", "balance", "soc_jump", "disabled", "counter_reset", "counter_missing", "counter_jump"])
def test_broken_observations_cannot_complete_a_cycle(failure):
    learner = BatteryLearning()
    for minute in range(121):
        values = observation(-6 if minute < 60 else 5.28 if minute < 120 else 0,
                             40 + 40 * min(minute, 120 - minute) / 60)
        if failure.startswith("counter"):
            values |= {"battery_energy_counters": True, "battery_charge_energy": 100 + min(minute, 60) * .1,
                       "battery_discharge_energy": 200 + max(minute - 60, 0) * .088}
        if minute == 70:
            if failure == "gap":
                continue
            if failure == "missing":
                values["battery_kw"] = None
            if failure == "balance":
                values["battery_learning_valid"] = False
            if failure == "soc_jump":
                values["battery_soc"] = 10
            if failure == "counter_reset":
                values["battery_charge_energy"] = 0
            if failure == "counter_missing":
                values["battery_discharge_energy"] = None
            if failure == "counter_jump":
                values["battery_discharge_energy"] += 10
        # A gap must exceed the existing 180-second observation tolerance.
        if failure == "gap" and 71 <= minute <= 73:
            continue
        learner.observe(NOW + minute * 60, values, not (failure == "disabled" and minute == 70))
    assert learner.cycles == []


def test_small_soc_loops_and_impossible_efficiency_do_not_become_calibration():
    learner = BatteryLearning()
    for minute in range(121):
        learner.observe(NOW + minute * 60, observation(-6 if minute < 60 else 5.28,
                        40 + 10 * min(minute, 120 - minute) / 60), True)
    assert learner.cycles == []
    cycle(learner, NOW + 7260, efficiency=1.1)
    assert learner.cycles == []


@pytest.mark.parametrize("direction", ["charge", "discharge"])
def test_power_needs_three_independent_sustained_opportunities(direction):
    learner = BatteryLearning()
    for index, kw in enumerate((3, 4, 5)):
        opportunity(learner, NOW + index * 3600, direction, kw, minutes=30)
        assert len(learner.powers[direction]) == index + 1  # Not three samples from one half-hour event.
        expected = 4 if index == 2 else 5
        assert learner.model(config(), NOW + index * 3600 + 2000)["battery_" + direction + "_kw"] == expected
    opposite = "discharge" if direction == "charge" else "charge"
    assert learner.model(config(), NOW + 10000)["battery_" + opposite + "_kw"] == 5
    assert learner.model(config(), NOW + 10000)["round_trip_efficiency"] == 90


def test_low_load_short_events_spikes_and_gaps_do_not_establish_power_limits():
    learner = BatteryLearning()
    opportunity(learner, eligible=False)
    opportunity(learner, NOW + 3600, minutes=9)
    assert learner.powers["charge"] == []
    opportunity(learner, NOW + 7200, spike=True)
    assert learner.powers["charge"] == [{"kw": 4, "ended": NOW + 7200 + 1260}]
    for minute in range(21):
        learner.observe(NOW + 10800 + minute * 60,
                        observation(-4, 50 + minute * .1, battery_charge_opportunity=True), True)
    learner.observe(NOW + 10800 + 2000, observation(), True)
    assert len(learner.powers["charge"]) == 1  # A gap discards the unfinished event, even its completed blocks.


def test_off_and_absent_use_fallbacks_without_deleting_saved_calibration():
    learner = BatteryLearning()
    for index in range(3):
        cycle(learner, NOW + index * 7260)
    for index in range(3):
        opportunity(learner, NOW + 22000 + index * 2000)
    saved = learner.export()
    now = NOW + 30000
    assert learner.model(config(battery_learning=False), now) == {
        "round_trip_efficiency": 90, "battery_charge_kw": 5, "battery_discharge_kw": 5}
    assert learner.model(config(has_battery=False), now)["round_trip_efficiency"] == 90
    learner.observe(now, observation(), False)
    assert learner.export() == saved
    assert learner.previous is None and learner.cycle is None


def test_storage_is_bounded_restart_breaks_candidates_and_old_samples_expire():
    saved = {"cycles": [{"charge_kwh": 5, "discharge_kwh": 4.4, "ended": NOW}] * 20,
             "powers": {"charge": [{"kw": 4, "ended": NOW}] * 20}}
    stats = Statistics({"battery": saved, "ledger": {"day": {"import_cost": 1}}})
    exported = json.loads(json.dumps(stats.export()))
    restored = Statistics(exported)
    assert len(restored.battery.cycles) == len(restored.battery.powers["charge"]) == 12
    assert restored.battery.previous is None and restored.battery.cycle is None
    assert restored.battery.model(config(), NOW)["round_trip_efficiency"] == pytest.approx(88)
    assert restored.battery.model(config(), NOW + MAX_AGE + 1)["round_trip_efficiency"] == 90
    assert restored.ledger == stats.ledger
    assert Statistics({"hours": [], "ev_sessions": []}).battery.cycles == []


def test_configuration_changes_reset_only_battery_and_manual_assumptions_do_not():
    stats = Statistics({"hours": [{"house_kwh": 1}], "ev_sessions": [{"kwh_per_percent": .7}],
                        "ledger": {"day": {"import_cost": 2}}})
    mappings = {"battery_power": "sensor.example_ac_battery", "battery_soc": "sensor.example_battery_soc"}
    stats.battery.configure(config(), mappings)
    cycle(stats.battery)
    stats.battery.configure(config(battery_capacity=200, round_trip_efficiency=80, battery_charge_kw=10), mappings)
    assert len(stats.battery.cycles) == 1
    restored = Statistics(stats.export())
    restored.battery.configure(config(), mappings)
    assert len(restored.battery.cycles) == 1
    restored.battery.configure(config(battery_power_inverted=True), mappings)
    assert restored.battery.cycles == []
    assert restored.hours == stats.hours and restored.ev_sessions == stats.ev_sessions and restored.ledger == stats.ledger


def test_soc_crossing_uses_only_energy_until_the_starting_soc():
    learner = BatteryLearning()
    for minute in range(120):
        power = -6 if minute < 60 else 5.28
        soc = 40 + 40 * minute / 60 if minute <= 60 else 80 - 40 * (minute - 60) / 60
        learner.observe(NOW + minute * 60, observation(power, soc), True)
    # A permitted three-minute interval crosses the anchor by more than a point.
    # Only its first minute belongs to the closed cycle; the other two must not
    # inflate discharge energy or cause a spurious SOC-jump rejection.
    learner.observe(NOW + 122 * 60, observation(0, 80 - 40 * 62 / 60), True)
    assert len(learner.cycles) == 1
    assert learner.cycles[0]["charge_kwh"] == pytest.approx(6)
    assert learner.cycles[0]["discharge_kwh"] == pytest.approx(5.28)


def test_long_idle_discards_cycle_instead_of_learning_standby_as_conversion_loss():
    learner = BatteryLearning()
    for minute in range(61):
        learner.observe(NOW + minute * 60, observation(-6 if minute < 60 else 0, 40 + 40 * minute / 60), True)
    for minute in range(61, 182):
        learner.observe(NOW + minute * 60, observation(0, 80), True)
    assert learner.cycle is None
    for minute in range(182, 243):
        learner.observe(NOW + minute * 60, observation(5.28 if minute < 242 else 0,
                        80 - 40 * (minute - 182) / 60), True)
    assert learner.cycles == []


def test_restart_cannot_complete_an_unfinished_cycle_or_power_opportunity():
    learner = BatteryLearning()
    for minute in range(61):
        learner.observe(NOW + minute * 60, observation(-6, 40 + 40 * minute / 60,
                        battery_charge_opportunity=True), True)
    assert learner.cycle is not None and learner.episodes["charge"]["best"] == 6
    restored = BatteryLearning(learner.export())
    for minute in range(61):
        restored.observe(NOW + 3600 + minute * 60, observation(5.28 if minute < 60 else 0,
                         80 - 40 * minute / 60), True)
    assert restored.cycles == [] and restored.powers["charge"] == []


def test_efficiency_outliers_do_not_override_consistent_cycles():
    learner = BatteryLearning({"cycles": [
        {"charge_kwh": 5, "discharge_kwh": out, "ended": NOW} for out in (4.4, 4.4, 4.4, 2.6)]})
    assert learner.model(config(), NOW)["round_trip_efficiency"] == pytest.approx(88)
    assert learner.quality(config(), NOW)["estimates"]["round_trip_efficiency"]["samples"] == 3
