"""Prepare a model-facing turn payload under a hard serialized-size limit.

Rules (stage 4.6.1):
- Keep the current question and mandatory task constraints.
- Shorten history only by whole messages (oldest first).
- Drop bank fragments wholly (never mid-cut exact quotes).
- Do not strip unknown/conflict / interpretation_limits to make data look stronger.
- Account for JSON serialization overhead — N×per_tool ≠ transcript budget.
- If the minimal safe payload still exceeds the limit → fail with context_limit
  (caller must stop; never invent a fake final).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.services.assistant.agent_loop.loop_projections import slim_source_refs_for_model
from app.services.assistant.agent_loop.pack import json_size


@dataclass
class PackResult:
    payload: dict[str, Any]
    fits: bool
    context_incomplete: bool = False
    history_incomplete: bool = False
    history_omitted_count: int = 0
    dropped_fragment_ids: list[str] = field(default_factory=list)
    dropped_observation_names: list[str] = field(default_factory=list)
    payload_chars: int = 0
    detail: str = ""


def _obs_name(obs: dict[str, Any]) -> str:
    return str(obs.get("name") or "")


def _bank_fragment_ids(obs: dict[str, Any]) -> list[str]:
    data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
    out: list[str] = []
    for f in data.get("fragments") or []:
        if isinstance(f, dict) and f.get("fragment_id"):
            out.append(str(f["fragment_id"]))
    return out


def _drop_last_bank_fragment(obs: dict[str, Any]) -> str | None:
    """Remove one whole fragment from the end; return dropped id."""
    data = obs.get("data") if isinstance(obs.get("data"), dict) else None
    if not data:
        return None
    frags = data.get("fragments")
    if not isinstance(frags, list) or not frags:
        return None
    dropped = frags.pop()
    data["fragments"] = frags
    data["context_incomplete"] = True
    data["fragments_excluded_from_context"] = list(
        data.get("fragments_excluded_from_context") or []
    ) + (
        [str(dropped.get("fragment_id"))]
        if isinstance(dropped, dict) and dropped.get("fragment_id")
        else []
    )
    # Slim source_refs to remaining fragments only
    remain = {str(f.get("fragment_id")) for f in frags if isinstance(f, dict)}
    refs = obs.get("source_refs")
    if isinstance(refs, list):
        obs["source_refs"] = [
            r
            for r in refs
            if not (
                isinstance(r, dict)
                and r.get("type") == "bank_fragment"
                and str(r.get("id")) not in remain
            )
        ]
    if isinstance(dropped, dict) and dropped.get("fragment_id"):
        return str(dropped["fragment_id"])
    return None


def _slim_observation_for_model(obs: dict[str, Any]) -> dict[str, Any]:
    """Strip quote duplication from source_refs; keep structured data as-is."""
    out = dict(obs)
    if "source_refs" in out:
        out["source_refs"] = slim_source_refs_for_model(out.get("source_refs") or [])
    # Drop server-only / UI fields that may have leaked into observations
    for k in ("role",):
        # keep role=tool_result_data — it's small and useful
        pass
    data = out.get("data")
    if isinstance(data, dict):
        cleaned = dict(data)
        # Never ship text_plain_for_validation alongside text_plain
        if "text_plain" in cleaned or (
            isinstance(cleaned.get("fragments"), list)
            and any(
                isinstance(f, dict) and f.get("text_plain")
                for f in cleaned.get("fragments") or []
            )
        ):
            for f in cleaned.get("fragments") or []:
                if isinstance(f, dict):
                    f.pop("text_plain_for_validation", None)
                    # hrefs / sha stay out of model projection (already stripped upstream)
                    for hk in (
                        "document_href",
                        "fragment_href",
                        "content_href",
                        "sha256",
                        "content_sha256",
                        "diagnostics",
                    ):
                        f.pop(hk, None)
        out["data"] = cleaned
    return out


def prepare_turn_payload(
    *,
    user_question: str,
    task: dict[str, Any],
    observations: list[dict[str, Any]],
    conversation_history: list[dict[str, Any]] | None,
    history_incomplete: bool,
    history_omitted_count: int,
    budget_meta: dict[str, Any],
    repair_note: str | None,
    revision_conflicts: list[Any] | None,
    max_chars: int,
    role: str = "agent_loop_turn",
) -> PackResult:
    """Build a payload that serializes to ≤ max_chars, or report context_limit."""
    history = list(conversation_history or [])
    obs = [_slim_observation_for_model(copy.deepcopy(o)) for o in observations if isinstance(o, dict)]

    payload: dict[str, Any] = {
        "role": role,
        "user_question": user_question,
        "conversation_history": history,
        "history_incomplete": bool(history_incomplete),
        "history_omitted_count": int(history_omitted_count),
        "task": task,
        "observations": obs,
        "budget": budget_meta,
        "repair_note": repair_note,
        "revision_conflicts": list(revision_conflicts or []),
        "context_incomplete": False,
    }

    size = json_size(payload)
    if size <= max_chars:
        return PackResult(payload=payload, fits=True, payload_chars=size)

    incomplete = False
    hist_incomplete = bool(history_incomplete)
    hist_omitted = int(history_omitted_count)
    dropped_frags: list[str] = []
    dropped_obs_names: list[str] = []

    # 1) Drop optional bulk keys first
    if payload.get("revision_conflicts"):
        payload["revision_conflicts"] = []
        incomplete = True
        size = json_size(payload)
        if size <= max_chars:
            payload["context_incomplete"] = True
            return PackResult(
                payload=payload,
                fits=True,
                context_incomplete=True,
                history_incomplete=hist_incomplete,
                history_omitted_count=hist_omitted,
                dropped_fragment_ids=dropped_frags,
                payload_chars=size,
            )

    if payload.get("repair_note") and size > max_chars:
        # Keep a short repair flag, not a long note
        note = payload.get("repair_note")
        if isinstance(note, str) and len(note) > 120:
            payload["repair_note"] = note[:80] + "…"
            incomplete = True
            size = json_size(payload)

    # 2) Drop whole history messages from the oldest end
    while (
        isinstance(payload.get("conversation_history"), list)
        and payload["conversation_history"]
        and json_size(payload) > max_chars
    ):
        payload["conversation_history"] = payload["conversation_history"][1:]
        hist_incomplete = True
        hist_omitted += 1
        incomplete = True
    payload["history_incomplete"] = hist_incomplete
    payload["history_omitted_count"] = hist_omitted

    if json_size(payload) <= max_chars:
        payload["context_incomplete"] = incomplete
        return PackResult(
            payload=payload,
            fits=True,
            context_incomplete=incomplete,
            history_incomplete=hist_incomplete,
            history_omitted_count=hist_omitted,
            dropped_fragment_ids=dropped_frags,
            payload_chars=json_size(payload),
        )

    # 3) Drop whole bank fragments (from the end of each bank observation)
    safety = 0
    while json_size(payload) > max_chars and safety < 64:
        safety += 1
        progressed = False
        for obs_i in payload.get("observations") or []:
            if not isinstance(obs_i, dict):
                continue
            if _obs_name(obs_i) != "get_bank_evidence":
                continue
            fid = _drop_last_bank_fragment(obs_i)
            if fid:
                dropped_frags.append(fid)
                incomplete = True
                progressed = True
                break
        if not progressed:
            break

    if json_size(payload) <= max_chars:
        payload["context_incomplete"] = True
        return PackResult(
            payload=payload,
            fits=True,
            context_incomplete=True,
            history_incomplete=hist_incomplete,
            history_omitted_count=hist_omitted,
            dropped_fragment_ids=dropped_frags,
            payload_chars=json_size(payload),
        )

    # 4) Drop whole observations from the oldest end — mark incompleteness.
    # Never invent replacements; remaining tools must not look more complete.
    while (
        isinstance(payload.get("observations"), list)
        and payload["observations"]
        and json_size(payload) > max_chars
    ):
        removed = payload["observations"].pop(0)
        name = _obs_name(removed) if isinstance(removed, dict) else "?"
        dropped_obs_names.append(name)
        for fid in _bank_fragment_ids(removed) if isinstance(removed, dict) else []:
            dropped_frags.append(fid)
        incomplete = True
        payload["observations_omitted"] = list(payload.get("observations_omitted") or []) + [name]

    if json_size(payload) <= max_chars:
        payload["context_incomplete"] = True
        return PackResult(
            payload=payload,
            fits=True,
            context_incomplete=True,
            history_incomplete=hist_incomplete,
            history_omitted_count=hist_omitted,
            dropped_fragment_ids=dropped_frags,
            dropped_observation_names=dropped_obs_names,
            payload_chars=json_size(payload),
        )

    # 5) Minimal safe: question + task + empty observations + incompleteness flags
    minimal = {
        "role": role,
        "user_question": user_question,
        "conversation_history": [],
        "history_incomplete": True,
        "history_omitted_count": hist_omitted + len(history),
        "task": task,
        "observations": [],
        "budget": budget_meta,
        "repair_note": repair_note if isinstance(repair_note, str) and len(repair_note) < 100 else None,
        "revision_conflicts": [],
        "context_incomplete": True,
        "observations_omitted": dropped_obs_names
        + [_obs_name(o) for o in obs if isinstance(o, dict)],
    }
    # Mark all prior bank frags dropped
    for o in obs:
        if isinstance(o, dict):
            dropped_frags.extend(_bank_fragment_ids(o))
    min_size = json_size(minimal)
    if min_size <= max_chars:
        return PackResult(
            payload=minimal,
            fits=True,
            context_incomplete=True,
            history_incomplete=True,
            history_omitted_count=minimal["history_omitted_count"],
            dropped_fragment_ids=list(dict.fromkeys(dropped_frags)),
            dropped_observation_names=minimal["observations_omitted"],
            payload_chars=min_size,
            detail="reduced_to_minimal_safe_context",
        )

    return PackResult(
        payload=minimal,
        fits=False,
        context_incomplete=True,
        history_incomplete=True,
        history_omitted_count=minimal["history_omitted_count"],
        dropped_fragment_ids=list(dict.fromkeys(dropped_frags)),
        dropped_observation_names=list(minimal["observations_omitted"]),
        payload_chars=min_size,
        detail="minimal_safe_context_exceeds_limit",
    )


def fragment_ids_in_payload(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for obs in payload.get("observations") or []:
        if not isinstance(obs, dict):
            continue
        data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
        for f in data.get("fragments") or []:
            if isinstance(f, dict) and f.get("fragment_id") and (
                f.get("text_plain") or f.get("text_plain_for_validation")
            ):
                ids.add(str(f["fragment_id"]))
    return ids
