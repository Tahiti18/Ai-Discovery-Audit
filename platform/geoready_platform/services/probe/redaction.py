"""Server-side redaction of paid report content for free-tier orgs.

The free report is a complete, honest taste: the verdict, the gap, the
competitor list, the misinformation FINDINGS (so the user sees AI is saying
something false about them), and the first few ranked positions. What's held
back to create upgrade pressure:

- the **Fix** text under each misinformation finding (findings visible, fixes
  locked) — "we found the wound; the bandage is $29"
- ranked positions past the first three in each answer's ranking list

This MUST run server-side. If we only blurred in React, a free user could read
the full JSON in devtools. These helpers rewrite the API response payloads so
the paid content never leaves the server for a gated plan.

Pure functions. Never mutate the ORM rows — they operate on the already-built
Pydantic output objects' plain fields.
"""

from __future__ import annotations

from typing import Any

# How many ranked positions a free user may see per answer. Enough to grasp
# "I'm not in the top 3", not enough to hand them the full competitive map.
FREE_RANK_LIMIT = 3

_MISINFO_SOURCE = "llm_misinformation"


def redact_flags(flags: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Strip the ``fix`` text from misinformation findings and mark them locked.

    The finding itself (issue_type, severity, description, evidence) stays fully
    visible — that's the hook. Only the actionable fix is withheld. Non-
    misinformation flags are returned untouched."""
    if not flags:
        return flags
    out: list[dict[str, Any]] = []
    for flag in flags:
        if isinstance(flag, dict) and flag.get("source") == _MISINFO_SOURCE and flag.get("fix"):
            redacted = dict(flag)
            redacted["fix"] = None
            redacted["fix_locked"] = True
            out.append(redacted)
        else:
            out.append(flag)
    return out


def redact_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    """Truncate a Perception's ranked-name list to the free limit and flag it.

    Sets ``ranked_locked: true`` only when names were actually removed, so the
    frontend shows the "unlock the rest" overlay only where there IS a rest."""
    if not details:
        return details
    ranked = details.get("ranked_names")
    if not isinstance(ranked, list) or len(ranked) <= FREE_RANK_LIMIT:
        return details
    redacted = dict(details)
    redacted["ranked_names"] = ranked[:FREE_RANK_LIMIT]
    redacted["ranked_total"] = len(ranked)  # so the UI can say "+7 more"
    redacted["ranked_locked"] = True
    # A ``you_position`` beyond the visible window would itself leak ranking
    # depth ("you're #6" tells them at least 6 were returned). Keep it only when
    # it falls inside the free window.
    if isinstance(redacted.get("you_position"), int) and redacted["you_position"] > FREE_RANK_LIMIT:
        redacted["you_position"] = None
        redacted["you_position_locked"] = True
    return redacted
