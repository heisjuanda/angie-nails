import config
from availability import to_minutes


def test_no_duplicate_ids():
    ids = [s["id"] for s in config.ALL_SERVICES]
    assert len(ids) == len(set(ids))


def test_every_category_exists():
    known = {c["id"] for c in config.CATEGORIES}
    assert all(s["category"] in known for s in config.ALL_SERVICES)


def test_lookup_covers_everything():
    assert config.SERVICES_BY_ID == {s["id"]: s for s in config.ALL_SERVICES}


def test_durations_are_positive_minutes():
    for s in config.ALL_SERVICES:
        assert isinstance(s["duration"], int), s["id"]
        assert s["duration"] > 0, s["id"]
        if s["category"] == "combos":
            assert s["duration"] <= config.DURACION_X * 3, s["id"]
            assert s["duration"] >= config.DURACION_X, s["id"]


def test_bundles_come_first_so_they_are_offered_first():
    assert [s["id"] for s in config.ALL_SERVICES[: len(config.BUNDLES)]] == \
        [s["id"] for s in config.BUNDLES]


def test_every_open_day_can_fit_at_least_one_service():
    """Si un combo no cabe en un día hábil, ese día queda imposible de agendar."""
    for weekday, spans in config.BUSINESS_HOURS.items():
        for open_hhmm, close_hhmm in spans:
            open_minutes = (to_minutes(close_hhmm) - to_minutes(open_hhmm))
            for s in config.ALL_SERVICES:
                assert s["duration"] <= open_minutes, f"{s['id']} no cabe en el día {weekday}"
