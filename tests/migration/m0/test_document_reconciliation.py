from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_current_entry_documents_do_not_claim_obsolete_product_boundaries():
    paths = [
        ROOT / "README.md",
        ROOT / "docs/README.md",
        ROOT / "docs/design/README.md",
        ROOT / "docs/design/current/developer-brief.md",
        ROOT / "docs/design/current/module-map.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    obsolete = (
        "The latest documented frontier is **v12.4**",
        "The next major development direction is **v13",
        "The model is still a closed economy",
        "World is an empty v20 shell",
        "v13 labor search is the next major gap",
    )
    assert not [claim for claim in obsolete if claim in text]
    assert "v124 Python oracle" in text
    assert "C++" in text
