from __future__ import annotations

from typing import Iterable


class CandidateRanker:
    """Rank grasp candidates deterministically for runtime use."""

    def rank(self, candidates: Iterable[dict]) -> list[dict]:
        """Return ranked candidates.

        Args:
            candidates: Candidate iterable.

        Returns:
            list[dict]: Ranked candidates.

        Raises:
            ValueError: If a candidate entry is not a dictionary.
        """
        normalized: list[dict] = []
        for item in candidates:
            if not isinstance(item, dict):
                raise ValueError('candidate entries must be dictionaries')
            normalized.append(dict(item))
        return sorted(
            normalized,
            key=lambda item: (
                -float(item.get('score', 0.0)),
                item.get('approach', ''),
                item.get('target_id', ''),
                item.get('candidate_id', ''),
            ),
        )
