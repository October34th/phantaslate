"""
Relay tests that need no API key and make no network calls.
Run:  pip install pytest && pytest -q
"""

from fastapi.testclient import TestClient

import main
from main import app, build_system_prompt, parse_auto_reply, code_from_name, is_mismatch

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["stateless"] is True


def test_empty_text_rejected():
    r = client.post("/translate", json={"text": "", "source_lang": "auto", "target_lang": "en"})
    assert r.status_code == 422  # fails min_length


def test_too_long_rejected():
    r = client.post("/translate", json={"text": "x" * 5001, "target_lang": "en"})
    assert r.status_code == 422  # exceeds max_length


def test_target_auto_rejected(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "test-key")
    r = client.post("/translate", json={"text": "hello", "target_lang": "auto"})
    assert r.status_code == 400


def test_missing_key_reports_config_error(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "")
    r = client.post("/translate", json={"text": "hello", "target_lang": "fr"})
    assert r.status_code == 500


def test_prompt_handles_auto_and_named():
    assert "Detect the language" in build_system_prompt("auto", "ja")
    named = build_system_prompt("en", "ja")
    assert "into Japanese" in named
    assert "English" in named


def test_named_source_prompt_still_requests_detection():
    """A stated source must not stop the model reporting the real language."""
    named = build_system_prompt("zh-Hant", "ko")
    assert "LANG:" in named
    assert "genuinely written in" in named


def test_auto_prompt_requests_english_language_name():
    prompt = build_system_prompt("auto", "en")
    assert "LANG:" in prompt
    assert "English" in prompt


def test_parse_auto_reply_well_formed():
    assert parse_auto_reply("LANG: Japanese\n---\nGood morning") == ("Japanese", "Good morning")


def test_parse_auto_reply_multiline_translation_preserved():
    detected, text = parse_auto_reply("LANG: German\n---\nline1\nline2")
    assert detected == "German"
    assert text == "line1\nline2"


def test_parse_auto_reply_falls_back_when_format_ignored():
    assert parse_auto_reply("Good morning") == (None, "Good morning")


def test_parse_auto_reply_falls_back_on_empty_language():
    assert parse_auto_reply("LANG: \n---\nHello") == (None, "Hello")


def test_mismatch_detects_wrong_source():
    """The reported bug: source set to Traditional Chinese, text is English."""
    mismatch, code = is_mismatch("zh-Hant", "English")
    assert mismatch is True
    assert code == "en"


def test_no_mismatch_when_source_is_correct():
    assert is_mismatch("ja", "Japanese") == (False, "ja")


def test_no_false_alarm_on_ambiguous_chinese():
    """Bare 'Chinese' must not fight either Chinese variant."""
    assert is_mismatch("zh-Hans", "Chinese") == (False, None)
    assert is_mismatch("zh-Hant", "Chinese") == (False, None)


def test_no_false_alarm_on_unknown_language():
    assert is_mismatch("en", "Klingon") == (False, None)


def test_simplified_and_traditional_are_distinguished():
    mismatch, code = is_mismatch("zh-Hans", "Traditional Chinese")
    assert mismatch is True
    assert code == "zh-Hant"


def test_code_from_name_handles_formatting_variants():
    assert code_from_name("Chinese (Simplified)") == "zh-Hans"
    assert code_from_name("japanese") == "ja"
    assert code_from_name("Japanese.") == "ja"


def test_parse_reply_without_separator():
    """Models frequently drop the separator line — the tag must still parse."""
    detected, text = parse_auto_reply("LANG: English\n\n你如何評價我的設置?")
    assert detected == "English"
    assert text == "你如何評價我的設置?"


def test_parse_reply_with_code_fence():
    assert parse_auto_reply("```\nLANG: Spanish\n---\nHola\n```") == ("Spanish", "Hola")


def test_parse_reply_with_fullwidth_colon():
    detected, text = parse_auto_reply("LANG： Japanese\n---\nおはよう")
    assert detected == "Japanese"
    assert text == "おはよう"


def test_parse_reply_keeps_dashes_inside_translation():
    detected, text = parse_auto_reply("LANG: English\n---\nA - B - C")
    assert detected == "English"
    assert text == "A - B - C"


def test_parse_reply_untagged_is_returned_whole():
    assert parse_auto_reply("Just the translation") == (None, "Just the translation")
