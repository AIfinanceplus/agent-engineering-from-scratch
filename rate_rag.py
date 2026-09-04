"""Deterministic RAG retrieval and provenance gates for the rate lesson.

The retriever is deliberately lexical.  It does not pretend to use embeddings.
Every selected chunk retains a stable content hash and source URL so the next
gate can prove what entered the model context.
"""

from dataclasses import dataclass
from hashlib import sha256
import re
from urllib.parse import urlparse

from rate_context_engineering import ContextItem, teaching_context_candidates


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
ALLOWED_SOURCE_DOMAINS = {"fred.stlouisfed.org", "federalreserve.gov", "www.federalreserve.gov"}


class RAGEvidenceInsufficient(RuntimeError):
    def __init__(self, message, *, decisions, missing_series):
        self.decisions = list(decisions)
        self.missing_series = list(missing_series)
        super().__init__(message)


@dataclass(frozen=True)
class RAGChunk:
    chunk_id: str
    source_id: str
    title: str
    text: str
    source_url: str | None
    as_of: str
    series: tuple[str, ...]
    tokens: int
    status: str = "active"

    def __post_init__(self):
        if not self.chunk_id or not self.source_id or not self.title or not self.text:
            raise ValueError("RAG chunk identity, source, title and text must be non-empty")
        if isinstance(self.tokens, bool) or not isinstance(self.tokens, int) or self.tokens < 1:
            raise ValueError("RAG chunk tokens must be a positive integer")
        if self.status not in {"active", "superseded"}:
            raise ValueError("RAG chunk status must be active or superseded")
        if not self.series or not all(item in {"DGS2", "DGS10", "OTHER"} for item in self.series):
            raise ValueError("RAG chunk series tags are invalid")

    @property
    def content_sha256(self):
        return sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def citation_id(self):
        return f"CIT-{self.content_sha256[:10]}"

    def public_record(self):
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "title": self.title,
            "text": self.text,
            "source_url": self.source_url,
            "as_of": self.as_of,
            "series": list(self.series),
            "tokens": self.tokens,
            "status": self.status,
            "content_sha256": self.content_sha256,
            "citation_id": self.citation_id,
        }


class LexicalRateRetriever:
    """Rank chunks by disclosed token overlap and return a bounded Top-K."""

    def __init__(self, top_k=3):
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        self.top_k = top_k

    def retrieve(self, query, chunks):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("retrieval query must be non-empty")
        query_terms = set(TOKEN_PATTERN.findall(query.lower()))
        ranked = []
        for chunk in chunks:
            document_terms = set(TOKEN_PATTERN.findall(
                f"{chunk.title} {chunk.text} {' '.join(chunk.series)}".lower()
            ))
            matched = sorted(query_terms & document_terms)
            score = round(len(matched) / len(query_terms), 4)
            ranked.append({
                "chunk": chunk,
                "lexical_score": score,
                "matched_terms": matched,
            })
        ranked.sort(key=lambda row: (-row["lexical_score"], row["chunk"].chunk_id))
        selected = [row for row in ranked if row["lexical_score"] > 0][:self.top_k]
        return {
            "algorithm": "deterministic_lexical_overlap",
            "query": query,
            "query_terms": sorted(query_terms),
            "top_k": self.top_k,
            "ranked": [
                {**row["chunk"].public_record(),
                 "rank": index + 1,
                 "lexical_score": row["lexical_score"],
                 "matched_terms": row["matched_terms"],
                 "selected_top_k": row in selected}
                for index, row in enumerate(ranked)
            ],
            "selected": [
                {**row["chunk"].public_record(),
                 "rank": index + 1,
                 "lexical_score": row["lexical_score"],
                 "matched_terms": row["matched_terms"]}
                for index, row in enumerate(selected)
            ],
        }


class CitationGate:
    """Reject unattributed, superseded or incomplete retrieved evidence."""

    def __init__(self, required_series=("DGS2", "DGS10"), allowed_domains=ALLOWED_SOURCE_DOMAINS):
        self.required_series = tuple(required_series)
        self.allowed_domains = frozenset(allowed_domains)

    def validate(self, selected):
        decisions = []
        accepted = []
        for chunk in selected:
            domain = urlparse(chunk.get("source_url") or "").hostname
            reasons = []
            if chunk.get("status") != "active":
                reasons.append("source_version_superseded")
            if domain not in self.allowed_domains:
                reasons.append("source_domain_not_allowed")
            if not chunk.get("citation_id") or not chunk.get("content_sha256"):
                reasons.append("provenance_missing")
            passed = not reasons
            decisions.append({
                "chunk_id": chunk["chunk_id"],
                "citation_id": chunk.get("citation_id"),
                "source_url": chunk.get("source_url"),
                "domain": domain,
                "status": chunk.get("status"),
                "series": list(chunk.get("series", [])),
                "passed": passed,
                "reasons": reasons,
            })
            if passed:
                accepted.append(chunk)
        coverage = sorted({series for chunk in accepted for series in chunk.get("series", [])
                           if series in self.required_series})
        missing = sorted(set(self.required_series) - set(coverage))
        if missing:
            raise RAGEvidenceInsufficient(
                f"retrieved evidence missing verified coverage for {', '.join(missing)}",
                decisions=decisions,
                missing_series=missing,
            )
        return {
            "artifact_type": "verified_rag_evidence",
            "passed": True,
            "required_series": list(self.required_series),
            "coverage": coverage,
            "accepted": accepted,
            "decisions": decisions,
        }


def teaching_rag_fixture(scenario):
    if scenario not in {"rag_topk", "rag_stale", "rag_insufficient"}:
        raise ValueError("unknown RAG teaching scenario")
    dgs2 = RAGChunk(
        "fred-dgs2-current", "FRED-DGS2", "DGS2 series definition",
        "DGS2 is the daily market yield on U.S. Treasury securities at 2-year constant maturity.",
        "https://fred.stlouisfed.org/series/DGS2", "2026-09-01", ("DGS2",), 35,
    )
    dgs10 = RAGChunk(
        "fred-dgs10-current", "FRED-DGS10", "DGS10 series definition",
        "DGS10 is the daily market yield on U.S. Treasury securities at 10-year constant maturity.",
        "https://fred.stlouisfed.org/series/DGS10", "2026-09-01", ("DGS10",), 35,
    )
    event_noise = RAGChunk(
        "event-market-noise", "OLD-EVENT-NOTES", "Event market workflow",
        "Kalshi and Polymarket contract matching needs settlement review.",
        "https://fred.stlouisfed.org/series/DGS2", "2026-07-01", ("OTHER",), 30,
    )
    stale = RAGChunk(
        "stale-direct-trading", "ARCHIVED-RATE-NOTE", "DGS2 DGS10 2s10s daily yield strategy",
        "Superseded note: treat DGS2 and DGS10 series as directly tradeable contracts.",
        "https://fred.stlouisfed.org/series/DGS2", "2024-01-01", ("DGS2", "DGS10"), 35,
        status="superseded",
    )
    unattributed_dgs10 = RAGChunk(
        "unknown-dgs10", "UNKNOWN", "DGS10 daily yield",
        "DGS10 is a 10-year constant maturity yield series.",
        None, "2026-09-01", ("DGS10",), 35,
    )
    if scenario == "rag_topk":
        return {"query": "DGS2 DGS10 daily 2s10s constant maturity yield", "top_k": 2,
                "chunks": [dgs2, event_noise, dgs10]}
    if scenario == "rag_stale":
        return {"query": "DGS2 DGS10 daily 2s10s constant maturity yield", "top_k": 3,
                "chunks": [stale, dgs2, event_noise, dgs10]}
    return {"query": "DGS2 DGS10 daily 2s10s constant maturity yield", "top_k": 2,
            "chunks": [dgs2, unattributed_dgs10, event_noise]}


def rag_context_candidates(verified_evidence):
    """Promote only citation-gated chunks into mandatory model context."""
    candidates = teaching_context_candidates("context_relevant")[:3]
    for chunk in verified_evidence["accepted"]:
        candidates.append(ContextItem(
            item_id=f"evidence_{chunk['chunk_id']}",
            source=f"retrieval:{chunk['source_id']}",
            text=f"[{chunk['citation_id']}] {chunk['title']}: {chunk['text']}",
            tokens=chunk["tokens"],
            relevance=min(1.0, 0.8 + chunk["lexical_score"] * 0.2),
            authority=0.95,
            freshness=0.95,
            mandatory=True,
        ))
    return candidates


def rag_snapshot(retrieval, gate):
    return {
        "retrieval_algorithm": retrieval["algorithm"],
        "top_k": retrieval["top_k"],
        "query_terms": retrieval["query_terms"],
        "selected_chunk_ids": [chunk["chunk_id"] for chunk in retrieval["selected"]],
        "citation_gate": {
            "required_series": gate["required_series"],
            "coverage": gate["coverage"],
            "accepted_citation_ids": [chunk["citation_id"] for chunk in gate["accepted"]],
        },
        "embedding_model": None,
        "network_access": False,
        "fixture_disclosed": True,
    }
