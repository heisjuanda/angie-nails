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
    for weekday, spans in config.BUSINESS_HOURS.items():
        for open_hhmm, close_hhmm in spans:
            open_minutes = (to_minutes(close_hhmm) - to_minutes(open_hhmm))
            for s in config.ALL_SERVICES:
                assert s["duration"] <= open_minutes, f"{s['id']} no cabe en el día {weekday}"


def test_last_slot_never_runs_past_midnight():
    for weekday, spans in config.BUSINESS_HOURS.items():
        for open_hhmm, close_hhmm in spans:
            last_start = to_minutes(close_hhmm) - config.SLOT_STEP_MIN
            for s in config.ALL_SERVICES:
                assert last_start + s["duration"] <= 24 * 60, (
                    f"{s['id']} el día {weekday} ocupa después de medianoche"
                )


def test_booking_limits_are_sane():
    """Los topes tienen que ser alcanzables por una clienta real y frenar a un script."""
    assert config.MAX_ACTIVE_PER_PHONE_DAY == 1

    per_day = min(
        (to_minutes(close) - to_minutes(open)) // s["duration"]
        for s in config.ALL_SERVICES for spans in config.BUSINESS_HOURS.values()
        for open, close in spans
    )
    assert config.MAX_ACTIVE_PER_PHONE_DAY < per_day

    slots_in_window = per_day * config.BOOKING_WINDOW_DAYS
    assert config.MAX_PER_IP_HOUR < slots_in_window
    assert config.MAX_PER_IP_HOUR >= 4        # una familia grande agendando a la vez
    assert config.MAX_PER_PHONE_DAY > config.MAX_ACTIVE_PER_PHONE_DAY


def test_studio_location_config():
    assert "La Flora" in config.ESTUDIO_BARRIO
    assert "Calle 56" in config.ESTUDIO_DIRECCION
    assert "Todos los Santos" in config.ESTUDIO_REFERENCIA
    assert config.ESTUDIO_MAPS_URL.startswith("https://maps.google.com")
    assert config.ESTUDIO_WAZE_URL.startswith("https://waze.com")


def test_only_bundles_have_components_and_savings_fields():
    assert len(config.BUNDLES) == 4
    for b in config.BUNDLES:
        assert isinstance(b.get("components"), list) and len(b["components"]) in (2, 3)
        assert "discount_cop" in b
        assert "duration_saved_min" in b
    for s in config.SERVICES:
        assert "components" not in s
        assert "discount_cop" not in s
        assert "duration_saved_min" not in s


def test_compute_combo_metrics_subtracts_discount_and_duration_saved():
    bundle = {
        "id": "combo-unas-cejas",
        "components": ["unas", "cejas"],
        "discount_cop": 15000,
        "duration_saved_min": 30,
    }
    subs = [
        {"id": "acrilicas", "category": "unas", "price": 90000, "duration": 120},
        {"id": "laminado-cejas", "category": "cejas", "price": 60000, "duration": 60},
    ]
    price, duration = config.compute_combo_metrics(bundle, subs)
    assert duration == (120 + 60) - 30
    assert price == (90000 + 60000) - 15000

    # Si algún sub-servicio aún no tiene precio numérico definido (None), el total queda None
    subs_no_price = [
        {"id": "acrilicas", "category": "unas", "price": None, "duration": 120},
        {"id": "laminado-cejas", "category": "cejas", "price": 60000, "duration": 60},
    ]
    price2, duration2 = config.compute_combo_metrics(bundle, subs_no_price)
    assert duration2 == 150
    assert price2 is None


def test_resolve_service_supports_composite_and_dict_combo_selections():
    by_composite = config.resolve_service("combo-unas-cejas:acrilicas+laminado-cejas")
    assert by_composite is not None
    assert by_composite["id"] == "combo-unas-cejas:acrilicas+laminado-cejas"
    assert by_composite["base_id"] == "combo-unas-cejas"
    assert by_composite["name"] == "Combo Uñas + Cejas (Uñas acrílicas + Laminado de cejas)"
    assert by_composite["sub_services"] == ["acrilicas", "laminado-cejas"]

    by_dict = config.resolve_service(
        "combo-unas-cejas",
        {"unas": "acrilicas", "cejas": "laminado-cejas"},
    )
    assert by_dict == by_composite

    # Categoría incorrecta o selección incompleta se rechaza
    assert config.resolve_service("combo-unas-cejas:lifting+laminado-cejas") is None
    assert config.resolve_service("combo-unas-cejas", {"unas": "acrilicas"}) is None
    assert config.resolve_service("combo-unas-cejas:acrilicas") is None
    # Cuando no se envían sub-servicios (compatibilidad base), devuelve el combo base
    preview = config.resolve_service("combo-unas-cejas")
    assert preview is not None and preview["id"] == "combo-unas-cejas"

