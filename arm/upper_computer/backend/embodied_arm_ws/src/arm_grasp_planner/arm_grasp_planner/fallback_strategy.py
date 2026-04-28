from __future__ import annotations

from typing import Iterable


class FallbackStrategy:
    """Choose the first candidate that has not failed yet."""

    def next_candidate(self, ranked: Iterable[dict], failed_ids: Iterable[str] | None = None) -> dict | None:
        """Return the next usable candidate.

        Args:
            ranked: Ranked candidate iterable.
            failed_ids: Candidate identifiers to skip.

        Returns:
            dict | None: Selected candidate or ``None``.

        Raises:
            Does not raise.
        """
        failed = {str(item) for item in (failed_ids or ())}
        for candidate in ranked:
            candidate_id = str(candidate.get('candidate_id', candidate.get('target_id', '')))
            if candidate_id not in failed:
                return dict(candidate)
        return None
