"""
Parse temporal evidence from Mushoku Tensei into a conservative reference time.

The parser intentionally prefers plausible, text-grounded signals over aggressive
normalization. Weak or implausible markers are ignored.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Optional

# Base epoch: Rudeus's birth
BASE_DATE = datetime(1, 1, 1)

# Patterns
AGE_PATTERN = re.compile(
    r"(?:Rudeus|Rudy|the boy|he)(?:\s(?:is|was|turned))?\s*(\d+)\s*(?:years?\s*old|yo)",
    re.IGNORECASE,
)
ARMORED_DRAGON_YEAR = re.compile(
    r"(?:(\d+)\s+of\s+the\s+Armored\s+Dragon\s+Calendar|(?:Armored\s*Dragon\s*Calendar|A\.?D\.?C\.?)\s*(\d+))",
    re.IGNORECASE,
)
RELATIVE_YEARS = re.compile(
    r"(\d+)\s*years?\s*(later|after|passed|ago)",
    re.IGNORECASE,
)
RELATIVE_MONTHS = re.compile(
    r"(\d+)\s*months?\s*(later|after|passed|ago)",
    re.IGNORECASE,
)
RELATIVE_DAYS = re.compile(
    r"(\d+)\s*days?\s*(later|after|passed|ago)",
    re.IGNORECASE,
)
AGE_NARRATION = re.compile(
    r"at\s+the\s+age\s+of\s+(\d+)|when\s+(?:he|rudeus|rudy)\s+was\s+(\d+)",
    re.IGNORECASE,
)


def parse_time_expressions(markers: List[str]) -> datetime:
    """Return the latest plausible datetime found in the markers."""
    best_absolute = timedelta(days=0)
    best_relative = timedelta(days=0)
    for marker in markers:
        # Age
        years = _extract_age_years(marker)
        if years is not None and 0 <= years <= 100:
            delta = timedelta(days=years * 365)
            if delta > best_absolute:
                best_absolute = delta
        # Armored Dragon Calendar year
        ad_match = ARMORED_DRAGON_YEAR.search(marker)
        if ad_match:
            adc_year = int(ad_match.group(1) or ad_match.group(2))
            if 1 <= adc_year <= 1000:
                delta = timedelta(days=adc_year * 365)
                if delta > best_absolute:
                    best_absolute = delta
        # Relative markers are weaker signals; only use them when no absolute time exists.
        rel_match = RELATIVE_YEARS.search(marker)
        if rel_match:
            years = int(rel_match.group(1))
            delta = timedelta(days=min(years, 20) * 365)
            if delta > best_relative:
                best_relative = delta
        month_match = RELATIVE_MONTHS.search(marker)
        if month_match:
            months = int(month_match.group(1))
            delta = timedelta(days=min(months, 24) * 30)
            if delta > best_relative:
                best_relative = delta
        day_match = RELATIVE_DAYS.search(marker)
        if day_match:
            days = int(day_match.group(1))
            delta = timedelta(days=min(days, 90))
            if delta > best_relative:
                best_relative = delta
    return BASE_DATE + (best_absolute or best_relative)


def estimate_story_time(segment_index: int, markers: List[str]) -> datetime:
    """Convert a segment's time markers into a datetime."""
    if markers:
        return parse_time_expressions(markers)
    # Fallback: each segment approx 1 day later (keeps chronological order)
    return BASE_DATE + timedelta(days=segment_index)


def _extract_age_years(marker: str) -> Optional[int]:
    age_match = AGE_PATTERN.search(marker)
    if age_match:
        return int(age_match.group(1))
    narration_match = AGE_NARRATION.search(marker)
    if narration_match:
        return int(narration_match.group(1) or narration_match.group(2))
    return None
