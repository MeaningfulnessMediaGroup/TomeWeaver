"""Tests for engine config merge/save (prose lint persistence)."""

from config import ENGINE_CONFIG, save_engine_config


def test_save_engine_config_preserves_unrelated_keys(monkeypatch, tmp_path):
    from config import ROOT_DIR

    original = dict(ENGINE_CONFIG)
    try:
        configs = tmp_path / "configs"
        configs.mkdir()
        config_path = configs / "engine_config.json"
        monkeypatch.setattr("config.ROOT_DIR", tmp_path)

        ENGINE_CONFIG.clear()
        ENGINE_CONFIG.update(
            {
                "inline_prose_edit": True,
                "spelling_locale": "british",
                "custom_dictionary_scope": "universe",
                "temperature_base": 0.9,
            }
        )

        save_engine_config({"temperature_base": 0.7})

        assert ENGINE_CONFIG["inline_prose_edit"] is True
        assert ENGINE_CONFIG["spelling_locale"] == "british"
        assert ENGINE_CONFIG["custom_dictionary_scope"] == "universe"
        assert ENGINE_CONFIG["temperature_base"] == 0.7

        import json

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["spelling_locale"] == "british"
        assert saved["custom_dictionary_scope"] == "universe"
    finally:
        ENGINE_CONFIG.clear()
        ENGINE_CONFIG.update(original)
