"""Unit tests for free-tier server-side redaction and plan gating.

These are the conversion mechanism: free users must see that paid content
EXISTS (findings, that they're not in the top ranks) without being handed the
paid content itself (the fix text, the full ranking). The redaction runs
server-side so the withheld data never reaches the browser."""

from __future__ import annotations

from geoready_platform.services.plans import is_gated, limits_for
from geoready_platform.services.probe import redaction as r


# ─── plan gating ─────────────────────────────────────────────────────────────


def test_free_is_gated_paid_is_not():
    assert is_gated("free") is True
    assert is_gated(None) is True          # unknown → free → gated
    assert is_gated("garbage") is True
    for paid in ("founding", "pro", "business", "agency", "owner"):
        assert is_gated(paid) is False


def test_free_has_lifetime_cap_paid_unlimited():
    assert limits_for("free").checks_total == 3
    assert limits_for("free").checks_per_day is None
    for paid in ("founding", "pro", "business", "owner"):
        assert limits_for(paid).checks_total is None


# ─── flag redaction (misinformation fixes) ──────────────────────────────────


def _misinfo(fix="Update your Google Business Profile.", **kw):
    base = {
        "source": "llm_misinformation", "issue_type": "wrong_brand",
        "severity": "high", "description": "AI says you carry Chopard.",
        "evidence": "…Chopard…", "fix": fix,
    }
    base.update(kw)
    return base


def test_redact_flags_strips_fix_and_marks_locked():
    out = r.redact_flags([_misinfo()])
    assert out[0]["fix"] is None
    assert out[0]["fix_locked"] is True
    # The finding itself stays fully visible — that's the hook.
    assert out[0]["description"] == "AI says you carry Chopard."
    assert out[0]["evidence"] == "…Chopard…"
    assert out[0]["severity"] == "high"


def test_redact_flags_leaves_non_misinfo_untouched():
    other = {"type": "claims_closed", "source": "heuristic", "detail": "x"}
    out = r.redact_flags([other])
    assert out[0] == other
    assert "fix_locked" not in out[0]


def test_redact_flags_does_not_mutate_input():
    original = _misinfo()
    r.redact_flags([original])
    assert original["fix"] == "Update your Google Business Profile."  # unchanged
    assert "fix_locked" not in original


def test_redact_flags_handles_none_and_empty():
    assert r.redact_flags(None) is None
    assert r.redact_flags([]) == []


def test_redact_flags_finding_with_no_fix_is_left_alone():
    """A misinfo flag that already has no fix shouldn't gain a lock marker."""
    out = r.redact_flags([_misinfo(fix=None)])
    assert "fix_locked" not in out[0]


# ─── details redaction (ranked positions) ───────────────────────────────────


def test_redact_details_truncates_ranking_and_flags_total():
    details = {"ranked_names": [f"Shop {i}" for i in range(1, 9)], "you_position": None}
    out = r.redact_details(details)
    assert out["ranked_names"] == ["Shop 1", "Shop 2", "Shop 3"]
    assert out["ranked_total"] == 8
    assert out["ranked_locked"] is True


def test_redact_details_short_list_untouched():
    details = {"ranked_names": ["A", "B"]}
    out = r.redact_details(details)
    assert out["ranked_names"] == ["A", "B"]
    assert "ranked_locked" not in out


def test_redact_details_hides_position_beyond_free_window():
    details = {"ranked_names": [f"S{i}" for i in range(10)], "you_position": 6}
    out = r.redact_details(details)
    assert out["you_position"] is None
    assert out["you_position_locked"] is True


def test_redact_details_keeps_position_inside_free_window():
    details = {"ranked_names": [f"S{i}" for i in range(10)], "you_position": 2}
    out = r.redact_details(details)
    assert out["you_position"] == 2
    assert "you_position_locked" not in out


def test_redact_details_does_not_mutate_input():
    details = {"ranked_names": [f"S{i}" for i in range(10)], "you_position": 6}
    r.redact_details(details)
    assert len(details["ranked_names"]) == 10  # original untouched
    assert details["you_position"] == 6


def test_redact_details_handles_none_and_missing_ranked():
    assert r.redact_details(None) is None
    assert r.redact_details({"error": "x"}) == {"error": "x"}
