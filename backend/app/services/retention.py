"""Evidence retention (NFR4 / DATA-3): delete evidence images older than N days.

Incident rows are kept for the audit trail; only the image and its key are removed.
Run ad hoc with `python -m app.services.retention`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import ProctoringIncident

log = logging.getLogger(__name__)


def purge_evidence(db: Session, storage, retention_days: int, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    old = (
        db.query(ProctoringIncident)
        .filter(ProctoringIncident.timestamp < cutoff, ProctoringIncident.evidence_key.isnot(None))
        .all()
    )
    removed = 0
    for incident in old:
        try:
            storage.delete(incident.evidence_key)
        except Exception:
            log.exception("Failed to delete evidence %s", incident.evidence_key)
            continue
        incident.evidence_key = None
        removed += 1
    db.commit()
    log.info("Retention purge removed %d evidence images older than %s", removed, cutoff)
    return removed


async def retention_loop(interval_seconds: int = 24 * 3600) -> None:  # pragma: no cover
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.services import deps

    while True:
        try:
            with SessionLocal() as db:
                await deps.run_ml(
                    purge_evidence, db, deps.get_storage(), get_settings().evidence_retention_days
                )
        except Exception:
            log.exception("Retention job failed")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.services import deps

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        n = purge_evidence(session, deps.get_storage(), get_settings().evidence_retention_days)
    print(f"Removed {n} evidence images")
