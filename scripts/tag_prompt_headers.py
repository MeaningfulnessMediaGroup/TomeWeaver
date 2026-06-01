"""One-shot: add :JSON|:TEXT suffixes to [PROMPT:KEY] headers in system_prompts.txt."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = ROOT / "configs" / "system_prompts.txt"

TEXT_KEYS = {
    "SYS_RECAP",
    "USER_RECAP",
    "SYS_BRIDGE",
    "USER_BRIDGE",
    "SYS_FIELD_GEN",
    "USER_FIELD_REROLL",
    "USER_FIELD_INSPIRE",
    "SYS_BRIDGE_EDIT",
    "USER_BRIDGE_POLISH",
    "USER_BRIDGE_CONDENSE",
    "USER_BRIDGE_EXPAND",
    "SYS_SPELL_AI",
    "USER_SPELL_AI",
    "SYS_MEMORY_PLOT",
    "USER_MEMORY_PLOT",
    "SYS_LOCATION_INFER",
    "USER_LOCATION_INFER",
}

HEADER = re.compile(r"^\[PROMPT:([A-Z0-9_]+)(?::(JSON|TEXT))?\]\s*$", re.I)


def main():
    lines = PROMPTS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.strip()
        m = HEADER.match(stripped)
        if m:
            key = m.group(1)
            kind = "TEXT" if key in TEXT_KEYS else "JSON"
            out.append(f"[PROMPT:{key}:{kind}]\n")
        else:
            out.append(line)
    PROMPTS_FILE.write_text("".join(out), encoding="utf-8")
    print(f"Tagged headers in {PROMPTS_FILE}")


if __name__ == "__main__":
    main()
