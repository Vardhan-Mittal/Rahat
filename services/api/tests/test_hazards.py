from rahat import hazards
from rahat.llm import intake_fallback


def test_rain_thresholds_follow_imd():
    assert hazards.rain_rule(10)["level"] == "green"
    assert hazards.rain_rule(64.5)["level"] == "yellow"
    assert hazards.rain_rule(115.6)["level"] == "orange"
    assert hazards.rain_rule(204.5)["level"] == "red"


def test_heat_uses_departure_from_normal():
    assert hazards.heat_rule(41.0, normal=36.0)["level"] == "orange"  # +5.0 ≥ 4.5
    assert hazards.heat_rule(41.0, normal=34.0)["level"] == "red"  # +7.0 ≥ 6.5
    assert hazards.heat_rule(41.0, normal=39.0)["level"] == "green"
    assert hazards.heat_rule(45.5)["level"] == "orange"  # absolute, no normal


def test_river_rule_skips_small_cells():
    assert hazards.river_rule(120, 10)["level"] == "green"
    assert hazards.river_rule(3100, 1000)["level"] == "red"
    assert hazards.river_rule(None, None)["level"] == "green"


def test_official_alert_cannot_be_averaged_away():
    rules = [hazards.rain_rule(0), {"level": "red", "text": "x", "why": "", "source": "SACHET", "kind": "official", "value": "Flood"}]
    assert hazards.combine(rules)["level"] == "red"


def test_no_data_is_unknown_not_safe():
    assert hazards.combine([])["level"] == "unknown"


def test_intake_fallback_reads_hindi():
    info = intake_fallback("पानी घर में घुस गया है, 4 लोग फँसे हैं")
    assert info["language"] == "hi"
    assert info["need"] == "rescue"
