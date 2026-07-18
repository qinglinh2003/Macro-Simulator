"""v25 P0: the classification inventory is CI-enforced.

Any new field added to any manifest source without a classification entry fails
this test — completeness is a standing property, not a one-off audit claim."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from policy_inventory import verify, discover


def test_every_source_field_classified_exactly_once():
    errors = verify()
    assert not errors, "\n".join(errors)


def test_source_counts_documented():
    fields = discover()
    assert len(fields["Config"]) == 364
    assert len(fields["Policy"]) == 54   # 46 + 8 B4c migrations
    assert len(fields["World"]) == 31
    assert len(fields["Social"]) == 35
    assert len(fields["Relationship"]) == 12
