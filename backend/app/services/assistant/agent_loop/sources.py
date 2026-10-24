"""Source inclusion ledger rules for citations.

A source found by a tool is **not** automatically citable. Only refs with
``inclusion=sent_to_model`` (dispatched to the provider) may appear in the
citation validation passed-index.

Stage 4.3: ``mark_dispatched`` means handed to the test/scripted provider
payload — not proven HTTP. ``confirm_transport_sent`` is the future hook
when a real transport ACKs the wire send.

Exact quotes are never mid-truncated: whole quote fits, or quote + citable
basis are excluded together. ``status=truncated`` alone does not authorize
citing excluded text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.assistant.agent_loop.protocol import SourceInclusion, SourceRef


@dataclass(frozen=True, slots=True)
class ExactQuotePolicy:
    """Exact quote must fit entirely within the remaining result/context budget."""

    max_quote_chars: int = 2000

    def accept_exact_quote(self, text: str | None, *, remaining_chars: int) -> tuple[str | None, bool]:
        """Return ``(quote_or_none, excluded)``."""
        if text is None:
            return None, False
        if not isinstance(text, str):
            return None, True
        stripped = text.strip()
        if not stripped:
            return None, False
        limit = min(self.max_quote_chars, max(0, remaining_chars))
        if len(stripped) <= limit:
            return stripped, False
        return None, True


@dataclass
class SourceLedger:
    """Tracks provenance stages for one user-turn."""

    policy: ExactQuotePolicy = field(default_factory=ExactQuotePolicy)
    _by_key: dict[tuple[str, str, int | None], SourceRef] = field(default_factory=dict)
    # Rich payloads for citation validation (fragment_id → passed dict).
    _citation_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Prepared but not yet dispatched (full bank fragment dicts).
    _pending_citation_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    # First dispatched revision per (type, id) — conflicting later revisions not swapped.
    _dispatched_revision: dict[tuple[str, str], int | None] = field(default_factory=dict)
    revision_conflicts: list[dict[str, Any]] = field(default_factory=list)
    # Stateless: only fragment ids present in the **current** model request body
    # may be cited. Previously sent fragments that were packed out are not assumed
    # to remain in the model context. Server citation payloads stay pinned.
    _current_request_fragment_ids: set[str] | None = None
    # Server-side UI metadata (hrefs etc.) retained even when omitted from model body.
    _server_fragment_meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def _key(ref: SourceRef) -> tuple[str, str, int | None]:
        return (ref.type, ref.id, ref.revision)

    @staticmethod
    def _id_key(ref: SourceRef) -> tuple[str, str]:
        return (ref.type, ref.id)

    def record_obtained(self, ref: SourceRef) -> SourceRef:
        stored = ref.model_copy(update={"inclusion": "tool_result_obtained"})
        self._by_key[self._key(stored)] = stored
        return stored

    def mark_prepared(
        self,
        ref: SourceRef,
        *,
        citation_payload: dict[str, Any] | None = None,
    ) -> SourceRef:
        key = self._key(ref)
        base = self._by_key.get(key, ref)
        stored = base.model_copy(update={"inclusion": "prepared_for_context"})
        self._by_key[key] = stored
        if citation_payload and ref.type == "bank_fragment" and not stored.exact_quote_excluded:
            self._pending_citation_payloads[ref.id] = dict(citation_payload)
            self._retain_server_meta(ref.id, citation_payload)
        return stored

    def _retain_server_meta(self, fragment_id: str, payload: dict[str, Any]) -> None:
        """Keep href / SHA / diagnostics for final UI — not for model context."""
        keys = (
            "document_href",
            "fragment_href",
            "content_href",
            "sha256",
            "content_sha256",
            "diagnostics",
            "document_title",
            "publication_date",
            "publication_date_precision",
            "page_number",
            "source_role",
            "qa_method",
            "content_type",
            "revision",
            "text_kind",
            "text_plain_for_validation",
        )
        meta = {k: payload[k] for k in keys if k in payload and payload[k] is not None}
        if meta:
            prev = self._server_fragment_meta.get(fragment_id) or {}
            self._server_fragment_meta[fragment_id] = {**prev, **meta}

    def begin_request_cite_scope(self, fragment_ids: set[str]) -> None:
        """Restrict citations to fragments actually present in this request body."""
        self._current_request_fragment_ids = set(fragment_ids)

    def clear_request_cite_scope(self) -> None:
        self._current_request_fragment_ids = None

    def server_meta_for(self, fragment_id: str) -> dict[str, Any] | None:
        return self._server_fragment_meta.get(fragment_id)

    def mark_sent(self, ref: SourceRef) -> SourceRef:
        """Alias used by 4.2 tests — same as ``mark_dispatched`` without payload."""
        stored, _conflict = self.mark_dispatched(ref)
        return stored

    def mark_dispatched(
        self,
        ref: SourceRef,
        *,
        citation_payload: dict[str, Any] | None = None,
    ) -> tuple[SourceRef, bool]:
        """Mark source as included in the provider payload (test or future HTTP).

        Returns ``(ref, conflict)``. On revision conflict with an already
        dispatched id, keeps the earlier revision and does **not** replace it.
        """
        id_key = self._id_key(ref)
        if id_key in self._dispatched_revision:
            prev = self._dispatched_revision[id_key]
            if prev != ref.revision:
                self.revision_conflicts.append(
                    {
                        "type": ref.type,
                        "id": ref.id,
                        "kept_revision": prev,
                        "ignored_revision": ref.revision,
                    }
                )
                # Keep earlier dispatched entry for citations.
                existing = self._find_dispatched(ref.type, ref.id)
                return (existing or ref, True)

        key = self._key(ref)
        base = self._by_key.get(key, ref)
        stored = base.model_copy(update={"inclusion": "sent_to_model"})
        self._by_key[key] = stored
        self._dispatched_revision[id_key] = ref.revision
        payload = citation_payload
        if payload is None and ref.type == "bank_fragment":
            payload = self._pending_citation_payloads.get(ref.id)
        if payload and ref.type == "bank_fragment" and not stored.exact_quote_excluded:
            self._citation_payloads[ref.id] = dict(payload)
            self._retain_server_meta(ref.id, payload)
            self._pending_citation_payloads.pop(ref.id, None)
        elif stored.exact_quote_excluded and ref.type == "bank_fragment":
            self._citation_payloads.pop(ref.id, None)
            self._pending_citation_payloads.pop(ref.id, None)
        return stored, False

    def confirm_transport_sent(
        self,
        ref: SourceRef,
        *,
        citation_payload: dict[str, Any] | None = None,
    ) -> SourceRef:
        """Confirm sources actually present in a successful HTTP request body.

        Call only after the transport receives a response (2xx body). Do **not**
        call on timeout / connection failure (delivery unknown). Successful HTTP
        does not prove the model read or understood the source.
        """
        stored, _ = self.mark_dispatched(ref, citation_payload=citation_payload)
        return stored

    def _find_dispatched(self, type_: str, id_: str) -> SourceRef | None:
        for ref in self._by_key.values():
            if ref.type == type_ and ref.id == id_ and ref.inclusion == "sent_to_model":
                return ref
        return None

    def attach_exact_quote(
        self,
        ref: SourceRef,
        quote: str | None,
        *,
        remaining_chars: int,
    ) -> SourceRef:
        """Attach quote or exclude both quote and citable status for that text."""
        text, excluded = self.policy.accept_exact_quote(quote, remaining_chars=remaining_chars)
        if excluded:
            stored = ref.model_copy(
                update={"exact_quote": None, "exact_quote_excluded": True}
            )
            self._by_key[self._key(stored)] = stored
            self._citation_payloads.pop(ref.id, None)
            return stored
        stored = ref.model_copy(
            update={"exact_quote": text, "exact_quote_excluded": False}
        )
        self._by_key[self._key(stored)] = stored
        return stored

    def citable_refs(self) -> list[SourceRef]:
        out: list[SourceRef] = []
        for ref in self._by_key.values():
            if ref.inclusion != "sent_to_model":
                continue
            if ref.exact_quote_excluded and ref.type == "bank_fragment":
                continue
            out.append(ref)
        return out

    def passed_index_for_citations(self) -> dict[str, dict[str, Any]]:
        """Index for ``validate_bank_evidence_citations`` — only dispatched bank frags.

        When a request cite-scope is active, fragments packed out of the current
        body are not citable (stateless model — no memory of prior requests).
        """
        index: dict[str, dict[str, Any]] = {}
        scope = self._current_request_fragment_ids
        for ref in self.citable_refs():
            if ref.type != "bank_fragment":
                continue
            if scope is not None and ref.id not in scope:
                continue
            payload = self._citation_payloads.get(ref.id)
            if payload:
                index[ref.id] = dict(payload)
                continue
            # Prefer pinned server meta for exact quote validation
            server = self._server_fragment_meta.get(ref.id)
            if server and server.get("text_plain_for_validation"):
                index[ref.id] = {
                    "fragment_id": ref.id,
                    "revision": server.get("revision", ref.revision),
                    "text_kind": server.get("text_kind")
                    or ("exact_quote" if ref.exact_quote else "paraphrase"),
                    "text_plain_for_validation": server["text_plain_for_validation"],
                }
                continue
            # Minimal fallback when only SourceRef fields exist
            index[ref.id] = {
                "fragment_id": ref.id,
                "revision": ref.revision,
                "text_kind": "exact_quote" if ref.exact_quote else "paraphrase",
                "text_plain_for_validation": ref.exact_quote or "",
            }
        return index

    def list_by_inclusion(self, inclusion: SourceInclusion) -> list[SourceRef]:
        return [r for r in self._by_key.values() if r.inclusion == inclusion]
