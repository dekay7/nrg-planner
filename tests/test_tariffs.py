from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.nrg.config import settings
from custom_components.nrg.forecast import price_at
from custom_components.nrg.tariffs import validate_periods, period_at, schedule_complete, external_intervals, boundaries
from conftest import NOW, ZONE


def schedule(rates=(10, 20, 15, 5)):
    return [{"label": label, "start": a, "end": b, "rate_cents": rate, "days": ["mon","tue","wed","thu","fri","sat","sun"]}
            for (label,a,b),rate in zip((("Morning","06:00","13:00"),("Mid-Day Peak","13:00","19:00"),
                                        ("Evening","19:00","21:00"),("Overnight","21:00","06:00")),rates)]


def stamp(hour, minute=0, day=19):
    return datetime(2026, 10, day, hour, minute, tzinfo=ZONE).timestamp()


def test_supply_and_delivery_periods_are_independent_and_half_open():
    config = settings({"supply_plan":"Time-of-use supply", "delivery_plan":"Time-of-use delivery",
                       "supply_periods":schedule((8,3,8,6)),"delivery_periods":schedule((4,15,6,2))})
    validate_periods(config["supply_periods"])
    assert schedule_complete(config["delivery_periods"])
    noon = price_at(stamp(12), NOW, config, [], None)
    peak = price_at(stamp(13), NOW, config, [], None)
    overnight = price_at(stamp(2), NOW, config, [], None)
    assert noon["import_price"] == pytest.approx(.12)
    assert peak["import_price"] == pytest.approx(.18)
    assert peak["supply_period"] == "Mid-Day Peak"
    assert overnight["import_price"] == pytest.approx(.08)
    assert overnight["price_known"] is True


def test_overnight_start_day_week_wrap_overlap_and_missing_rates():
    monday_night = [{"label":"Monday night","start":"21:00","end":"06:00","rate_cents":2,"days":["mon"]}]
    assert period_at(stamp(5, day=20), monday_night, ZONE)[0] == .02
    assert period_at(stamp(5, day=19), monday_night, ZONE)[0] is None
    assert not schedule_complete(monday_night)
    with pytest.raises(ValueError, match="overlap"):
        validate_periods(schedule()+[{"label":"Sunday extra","start":"23:00","end":"01:00","rate_cents":1,"days":["sun"]}])
    unfinished = schedule((1,None,3,4))
    validate_periods(unfinished)
    assert not schedule_complete(unfinished)
    config = settings({"supply_plan":"Time-of-use supply","supply_periods":unfinished})
    missing = price_at(stamp(14), NOW, config, [], None)
    assert missing["import_price"] is None and not missing["price_known"]
    assert missing["price_source"] == "missing"


def test_dst_repeated_clock_hour_gets_same_contract_rate():
    zone=ZoneInfo("America/Chicago")
    first=datetime(2026,11,1,1,30,tzinfo=zone,fold=0).timestamp()
    second=datetime(2026,11,1,1,30,tzinfo=zone,fold=1).timestamp()
    assert second-first == 3600
    assert period_at(first,schedule(),zone) == period_at(second,schedule(),zone)


def test_exact_tariff_boundary_and_external_prices_with_units():
    periods=[{"label":"all day","start":"06:07","end":"06:07","rate_cents":5,"days":["mon","tue","wed","thu","fri","sat","sun"]}]
    config=settings({"supply_plan":"Time-of-use supply","supply_periods":periods})
    assert stamp(6,7,day=20) in boundaries(NOW,NOW+48*3600,config,ZONE)
    rows=external_intervals([{"valid_from":"2026-10-20T06:00:00-05:00","valid_to":"2026-10-20T07:00:00-05:00","value_inc_vat":14}],"c/kWh")
    config=settings({"supply_plan":"External supply entity","delivery_cents":3}) | {"_external_supply":rows}
    assert price_at(stamp(6,day=20),NOW,config,[],None)["import_price"] == pytest.approx(.17)
    assert price_at(stamp(7,day=20),NOW,config,[],None)["import_price"] is None
    with pytest.raises(ValueError, match="timezones"):
        external_intervals([{"start":"2026-10-20T06:00:00","end":"2026-10-20T07:00:00","price":.1}],"USD/kWh")


def test_current_external_observation_does_not_overwrite_a_future_interval():
    config=settings({"supply_plan":"External supply entity"}) | {"_external_supply":[{"start":NOW+900,"end":NOW+1800,"price":.3}]}
    assert price_at(NOW,NOW,config,[],.1)["supply_price"]==.1
    assert price_at(NOW+900,NOW,config,[],.1)["supply_price"]==.3
    assert price_at(NOW+1800,NOW,config,[],.1)["supply_price"] is None
