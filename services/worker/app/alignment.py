"""Baseline word and phrase alignment inspired by Needleman-Wunsch.

Provides token-level alignment with configurable scoring.
Limitations are explicitly documented.
"""

from __future__ import annotations

import re
from typing import Any


class AlignmentResult:
    """Result of a token-level alignment."""

    def __init__(
        self,
        source_tokens: list[str] | None = None,
        target_tokens: list[str] | None = None,
        matches: list[tuple[int, int, str]] | None = None,
        score: float = 0.0,
        differing_spans: list[tuple[str, str]] | None = None,
        slot_candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.source_tokens = source_tokens or []
        self.target_tokens = target_tokens or []
        self.matches = matches or []  # (src_idx, tgt_idx, match_type)
        self.score = score
        self.differing_spans = differing_spans or []
        self.slot_candidates = slot_candidates or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_tokens": self.source_tokens,
            "target_tokens": self.target_tokens,
            "matches": self.matches,
            "score": self.score,
            "differing_spans": self.differing_spans,
            "slot_candidates": self.slot_candidates,
        }


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenization."""
    return re.findall(r"[A-Za-z0-9_]+|[^\s\w]", text)


def align_texts(
    source: str,
    target: str,
    match_score: float = 2.0,
    substitution_penalty: float = -1.0,
    gap_penalty: float = -0.5,
) -> AlignmentResult:
    """Align source and target texts using a Needleman-Wunsch-inspired approach.

    Args:
        source: Source text.
        target: Target text.
        match_score: Score for an exact match.
        substitution_penalty: Penalty for a substitution (mismatch).
        gap_penalty: Penalty for inserting a gap.

    Returns:
        An ``AlignmentResult`` with token-level matches and differing spans.

    Limitations:
        - Uses only surface-level token equality.
        - No lemmatization, stemming, or synonym resolution.
        - No phrase-level (n:m) matching.
        - No multilingual support.
        - Gap and substitution penalties are simple constants.
        - May produce suboptimal alignments for very long texts.
    """
    src_tokens = _tokenize(source)
    tgt_tokens = _tokenize(target)
    n, m = len(src_tokens), len(tgt_tokens)

    # DP matrix
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i * gap_penalty
    for j in range(m + 1):
        dp[0][j] = j * gap_penalty

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score = match_score if src_tokens[i - 1].lower() == tgt_tokens[j - 1].lower() else substitution_penalty
            dp[i][j] = max(
                dp[i - 1][j - 1] + score,
                dp[i - 1][j] + gap_penalty,
                dp[i][j - 1] + gap_penalty,
            )

    # Traceback
    i, j = n, m
    matches: list[tuple[int, int, str]] = []
    diff_spans: list[tuple[str, str]] = []
    slot_candidates: list[dict[str, Any]] = []

    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (match_score if src_tokens[i - 1].lower() == tgt_tokens[j - 1].lower() else substitution_penalty):
            if src_tokens[i - 1].lower() == tgt_tokens[j - 1].lower():
                matches.append((i - 1, j - 1, "match"))
            else:
                matches.append((i - 1, j - 1, "substitution"))
                diff_spans.append((src_tokens[i - 1], tgt_tokens[j - 1]))
                slot_candidates.append({
                    "source": src_tokens[i - 1],
                    "target": tgt_tokens[j - 1],
                    "type": "term",
                })
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1] + gap_penalty):
            matches.append((-1, j - 1, "insertion"))
            diff_spans.append(("", tgt_tokens[j - 1]))
            j -= 1
        else:
            matches.append((i - 1, -1, "deletion"))
            diff_spans.append((src_tokens[i - 1], ""))
            i -= 1

    matches.reverse()
    diff_spans.reverse()

    return AlignmentResult(
        source_tokens=src_tokens,
        target_tokens=tgt_tokens,
        matches=matches,
        score=dp[n][m],
        differing_spans=diff_spans if len(diff_spans) <= 50 else diff_spans[:50],
        slot_candidates=slot_candidates if len(slot_candidates) <= 20 else slot_candidates[:20],
    )