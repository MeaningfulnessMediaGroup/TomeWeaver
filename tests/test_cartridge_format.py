"""Tests for setup.json cartridge format versioning."""

import json

from cartridge_format import (
    CARTRIDGE_FORMAT_SPEC,
    CURRENT_CARTRIDGE_FORMAT_VERSION,
    ensure_cartridge_format,
    load_cartridge_setup,
    read_cartridge_format_version,
    stamp_new_cartridge_setup,
)
from config import create_boilerplate_files


def test_new_boilerplate_stamps_format_version(mock_adventure_dir):
    create_boilerplate_files(mock_adventure_dir, "sandbox")
    data = json.loads((mock_adventure_dir / "setup.json").read_text(encoding="utf-8"))
    assert data["cartridge_format_version"] == CURRENT_CARTRIDGE_FORMAT_VERSION
    assert data["cartridge_format_spec"] == CARTRIDGE_FORMAT_SPEC


def test_legacy_setup_upgraded_on_load(tmp_path):
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps({"mode": "sandbox", "title": "Legacy"}), encoding="utf-8")

    data = load_cartridge_setup(setup_path)
    assert read_cartridge_format_version(data) == CURRENT_CARTRIDGE_FORMAT_VERSION
    assert data["title"] == "Legacy"

    on_disk = json.loads(setup_path.read_text(encoding="utf-8"))
    assert on_disk["cartridge_format_version"] == CURRENT_CARTRIDGE_FORMAT_VERSION


def test_ensure_idempotent_when_already_current():
    setup = stamp_new_cartridge_setup({"mode": "sandbox", "title": "Ok"})
    again, changed = ensure_cartridge_format(setup)
    assert changed is False
    assert again["cartridge_format_version"] == CURRENT_CARTRIDGE_FORMAT_VERSION


def test_future_format_loads_without_downgrade():
    setup = {
        "mode": "sandbox",
        "cartridge_format_version": CURRENT_CARTRIDGE_FORMAT_VERSION + 1,
        "cartridge_format_spec": CARTRIDGE_FORMAT_SPEC,
    }
    out, changed = ensure_cartridge_format(setup)
    assert changed is False
    assert out["cartridge_format_version"] == CURRENT_CARTRIDGE_FORMAT_VERSION + 1
