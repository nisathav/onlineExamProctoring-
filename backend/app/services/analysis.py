"""Temporal analysis of incidents (Phase 7). Flags are decision support only."""
from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from app.models import IncidentType, ProctoringIncident


def flag_reasons(
    incidents: Sequence[ProctoringIncident],
    away_count: int = 3,
    window_seconds: int = 30,
    long_away_seconds: int = 15,
    capture_interval_seconds: int = 3,
) -> list[str]:
    """Return human-readable reasons a student should be looked at by staff.

    * burst: `away_count`+ face-away incidents within `window_seconds`
    * long away: consecutive away captures (each <= ~1.5 intervals apart)
      spanning at least `long_away_seconds`
    """
    reasons: list[str] = []
    away = sorted(
        (i.timestamp for i in incidents if i.incident_type == IncidentType.looking_away)
    )

    window = timedelta(seconds=window_seconds)
    start = 0
    for end in range(len(away)):
        while away[end] - away[start] > window:
            start += 1
        if end - start + 1 >= away_count:
            reasons.append(f"{away_count}+ looking-away incidents within {window_seconds}s")
            break

    gap_limit = timedelta(seconds=capture_interval_seconds * 1.5)
    absent = sorted(
        i.timestamp
        for i in incidents
        if i.incident_type in (IncidentType.looking_away, IncidentType.no_face)
    )
    run_start = None
    for prev, cur in zip([None] + absent[:-1], absent):
        if prev is None or cur - prev > gap_limit:
            run_start = cur
        if run_start is not None and cur - run_start >= timedelta(seconds=long_away_seconds):
            reasons.append(f"Away from screen for {long_away_seconds}s or longer")
            break

    if any(i.incident_type == IncidentType.multiple_faces for i in incidents):
        reasons.append("Multiple faces detected")
    return reasons
