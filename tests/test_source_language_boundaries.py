"""Prevent new player-facing language from leaking into executable source."""
from __future__ import annotations

from pathlib import Path


SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".gd", ".h", ".hpp", ".js", ".py", ".sh", ".ts",
}
IGNORED_PARTS = {".git", ".venv"}

# Temporary migration debt. Counts may decrease but must never increase.
LEGACY_CJK_LIMITS = {
    "desktop/godot/scripts/main.gd": 11_553,
    "desktop/godot/tests/test_main_menu_return.gd": 12,
    "desktop/godot/tests/test_panel_catalog.gd": 33,
    "macro_sim/desktop/runtime.py": 257,
    "tests/test_desktop_runtime.py": 23,
}


def _is_cjk_ideograph(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"


def test_executable_source_does_not_add_cjk_language_debt():
    root = Path(__file__).resolve().parents[1]
    counts: dict[str, int] = {}
    for path in root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix not in SOURCE_SUFFIXES
            or IGNORED_PARTS.intersection(path.parts)
        ):
            continue
        count = sum(_is_cjk_ideograph(char) for char in path.read_text())
        if count:
            counts[path.relative_to(root).as_posix()] = count

    unexpected = set(counts) - set(LEGACY_CJK_LIMITS)
    assert not unexpected, f"new CJK text in executable source: {sorted(unexpected)}"
    increased = {
        path: (count, LEGACY_CJK_LIMITS[path])
        for path, count in counts.items()
        if count > LEGACY_CJK_LIMITS[path]
    }
    assert not increased, f"CJK migration debt increased: {increased}"
