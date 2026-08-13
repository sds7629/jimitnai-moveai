from __future__ import annotations

from app.models.candidate_review import CandidateReview
from app.repositories.base import AppendOnlyRepository

LENSES: tuple[str, ...] = ("cost", "feasibility", "risk")


class CandidateReviewRepository(AppendOnlyRepository[CandidateReview]):
    """append-only -- 다중 관점 교차검증 결과. Re-review always inserts new
    rows per lens; there is no update() method here (see
    app/repositories/base.py's module docstring) and the `moveai_app` DB
    role has no UPDATE/DELETE grant on candidate_reviews
    (db/init/004-permissions.sql)."""

    model = CandidateReview

    def for_candidate(self, candidate_id: int) -> list[CandidateReview]:
        """All review rows for one candidate -- every lens, every historical
        (re-)review, oldest first."""
        return (
            self.db.query(CandidateReview)
            .filter(CandidateReview.candidate_id == candidate_id)
            .order_by(CandidateReview.created_at.asc())
            .all()
        )

    def for_incident(self, incident_id: int) -> list[CandidateReview]:
        """All review rows across every candidate of one incident, oldest
        first -- mirrors SimulationResultRepository.for_incident()."""
        return (
            self.db.query(CandidateReview)
            .filter(CandidateReview.incident_id == incident_id)
            .order_by(CandidateReview.created_at.asc())
            .all()
        )

    def latest_by_lens_for_candidate(self, candidate_id: int) -> dict[str, CandidateReview]:
        """The current state of the review for each of the 3 lenses --
        since a re-review appends new rows instead of updating old ones, the
        "current" verdict per lens is whichever row is most recent. Iterates
        for_candidate()'s ascending-by-created_at result and lets later rows
        overwrite earlier ones per lens, so the last write per lens wins."""
        latest: dict[str, CandidateReview] = {}
        for review in self.for_candidate(candidate_id):
            latest[review.lens] = review
        return latest
