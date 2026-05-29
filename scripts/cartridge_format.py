"""Cartridge format versioning for ``setup.json``.

The author-editable ``version`` field in setup is story metadata (your cartridge
revision). ``cartridge_format_version`` is the **engine schema** revision used
for deterministic upgrades when TomeWeaver evolves on-disk layout.

**Policy:** any change to cartridge file structure or ``setup.json`` schema must
bump the format version (REFACTOR.MAJOR.MINOR semantics) and register a migration
in ``_MIGRATIONS`` below. See ``.cursor/rules/on-disk-format-versioning.mdc``.

Related but separate version stamps elsewhere:

* ``runs/manifest.json`` → ``version`` (run tree manifest)
* ``branch_pack.json`` → ``pack_version`` (branch pack export)
"""

from __future__ import annotations

from pathlib import Path

# Increment when setup.json (or coupled cartridge conventions) change incompatibly.
CURRENT_CARTRIDGE_FORMAT_VERSION = 1

# Human-readable link to the NSM systems spec (documentation only).
CARTRIDGE_FORMAT_SPEC = "MMG-NSM-1.0"

SETUP_FORMAT_KEY = "cartridge_format_version"
SETUP_SPEC_KEY = "cartridge_format_spec"


def read_cartridge_format_version(setup_data: dict) -> int:
    """Return the stored format version, or ``0`` for legacy cartridges."""
    if not isinstance(setup_data, dict):
        return 0
    raw = setup_data.get(SETUP_FORMAT_KEY)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _migrate_v0_to_v1(setup_data: dict) -> dict:
    """Baseline: legacy cartridges are treated as format 1 (no field renames)."""
    return dict(setup_data)


_MIGRATIONS = {
    0: _migrate_v0_to_v1,
}


def migrate_setup_format(setup_data: dict, from_version: int, to_version: int) -> dict:
    """Apply registered migrations from *from_version* up to *to_version*."""
    if from_version >= to_version:
        return dict(setup_data)
    data = dict(setup_data)
    version = from_version
    while version < to_version:
        step = _MIGRATIONS.get(version)
        if step is not None:
            data = step(data)
        version += 1
    return data


def ensure_cartridge_format(
    setup_data: dict,
    *,
    target_version: int | None = None,
) -> tuple[dict, bool]:
    """Normalize format keys and migrate upward when needed.

    Returns ``(setup_dict, changed)``. Does not write to disk.
    Newer-than-engine formats are loaded as-is (forward-compatible read).
    """
    if not isinstance(setup_data, dict):
        raise ValueError("setup.json must be a JSON object")

    target = target_version if target_version is not None else CURRENT_CARTRIDGE_FORMAT_VERSION
    current = read_cartridge_format_version(setup_data)

    if current > target:
        return setup_data, False

    if (
        current == target
        and setup_data.get(SETUP_FORMAT_KEY) == target
        and setup_data.get(SETUP_SPEC_KEY) == CARTRIDGE_FORMAT_SPEC
    ):
        return setup_data, False

    data = migrate_setup_format(setup_data, current, target)
    data[SETUP_FORMAT_KEY] = target
    data[SETUP_SPEC_KEY] = CARTRIDGE_FORMAT_SPEC
    return data, True


def load_cartridge_setup(path, *, auto_upgrade: bool = True) -> dict:
    """Load ``setup.json``, migrate/stamp format version, optionally persist."""
    from config import load_json_safely, save_json_atomically

    path = Path(path)
    raw = load_json_safely(path, "setup.json")
    normalized, changed = ensure_cartridge_format(raw)
    if changed and auto_upgrade:
        save_json_atomically(normalized, path)
    return normalized


def stamp_new_cartridge_setup(setup_data: dict) -> dict:
    """Apply current format keys to a newly created setup dict (in memory)."""
    normalized, _ = ensure_cartridge_format(setup_data)
    return normalized
