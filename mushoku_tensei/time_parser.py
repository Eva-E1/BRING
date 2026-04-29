"""
Parse temporal evidence from Mushoku Tensei into conservative story times.

The parser now distinguishes between:
- absolute anchors such as ages or calendar years
- named relative markers such as "the next morning"
- counted relative markers such as "two years later"

It also exposes a small `TimelineBuilder` that can carry state across segments,
which makes chronological reconstruction more accurate than segment-local
fallbacks alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

# Base epoch: Rudeus's birth
BASE_DATE = datetime(1, 1, 1)

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "couple": 2,
    "few": 3,
    "several": 4,
}
COUNT_TOKEN = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|couple|few|several)"

# Patterns
AGE_PATTERN = re.compile(
    rf"(?:rudeus|rudy|the boy|the child|the baby|he|she|i)?(?:\s+(?:is|was|turned|at))?\s*{COUNT_TOKEN}\s*(?:years?\s*old|yo)\b",
    re.IGNORECASE,
)
AGE_HYPHEN_PATTERN = re.compile(
    rf"\b{COUNT_TOKEN}\s*-\s*year\s*-\s*old\b|\b{COUNT_TOKEN}\s+year\s+old\b",
    re.IGNORECASE,
)
AGE_NARRATION = re.compile(
    rf"at\s+the\s+age\s+of\s+{COUNT_TOKEN}|when\s+(?:he|she|i|rudeus|rudy)\s+was\s+{COUNT_TOKEN}",
    re.IGNORECASE,
)
ARMORED_DRAGON_YEAR = re.compile(
    r"(?:(\d+)\s+of\s+the\s+Armored\s+Dragon\s+Calendar|(?:Armored\s*Dragon\s*Calendar|A\.?D\.?C\.?)\s*(\d+))",
    re.IGNORECASE,
)
CALENDAR_SHORTHAND = re.compile(r"\bK\s*[-:]?\s*(\d{1,4})\b", re.IGNORECASE)
RELATIVE_YEARS = re.compile(rf"{COUNT_TOKEN}\s*years?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_MONTHS = re.compile(rf"{COUNT_TOKEN}\s*months?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_WEEKS = re.compile(rf"{COUNT_TOKEN}\s*weeks?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_DAYS = re.compile(rf"{COUNT_TOKEN}\s*days?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_HOURS = re.compile(rf"{COUNT_TOKEN}\s*hours?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_MINUTES = re.compile(rf"{COUNT_TOKEN}\s*minutes?\s*(later|after|passed|ago)", re.IGNORECASE)
RELATIVE_SECONDS = re.compile(rf"{COUNT_TOKEN}\s*seconds?\s*(later|after|passed|ago)", re.IGNORECASE)

NAMED_RELATIVE_MARKERS = (
    (re.compile(r"\ba few seconds later\b|\bseconds later\b", re.IGNORECASE), timedelta(seconds=5)),
    (re.compile(r"\ba moment later\b|\ba few moments later\b", re.IGNORECASE), timedelta(minutes=1)),
    (re.compile(r"\bafter a while\b|\bafter awhile\b", re.IGNORECASE), timedelta(minutes=15)),
    (re.compile(r"\blater that day\b", re.IGNORECASE), timedelta(hours=6)),
    (re.compile(r"\bthe next day\b|\bnext day\b|\bthe following day\b", re.IGNORECASE), timedelta(days=1)),
    (re.compile(r"\bthat night\b|\bthat evening\b|\bduring the night\b", re.IGNORECASE), timedelta(hours=12)),
    (re.compile(r"\bthe next morning\b|\bthe following morning\b", re.IGNORECASE), timedelta(days=1, hours=6)),
    (re.compile(r"\bthe next week\b|\bthe following week\b", re.IGNORECASE), timedelta(days=7)),
    (re.compile(r"\bthe next month\b|\bthe following month\b", re.IGNORECASE), timedelta(days=30)),
)


@dataclass(frozen=True)
class CalendarReference:
    era: str
    year: int


@dataclass(frozen=True)
class TemporalSignal:
    absolute: timedelta | None = None
    relative: timedelta | None = None
    calendar: CalendarReference | None = None
    has_explicit_marker: bool = False


def parse_time_expressions(markers: List[str]) -> datetime:
    """Return the strongest time estimate available in the markers."""
    signal = extract_temporal_signal(markers)
    if signal.absolute is not None:
        return BASE_DATE + signal.absolute
    if signal.relative is not None:
        return BASE_DATE + signal.relative
    return BASE_DATE


def extract_temporal_signal(markers: Iterable[str]) -> TemporalSignal:
    """Extract absolute and relative time hints from one segment."""
    best_age_absolute = timedelta(0)
    best_calendar_absolute = timedelta(0)
    best_relative = timedelta(0)
    best_calendar: CalendarReference | None = None
    has_explicit_marker = False

    for marker in markers:
        normalized = str(marker or "").strip()
        if not normalized:
            continue
        has_explicit_marker = True

        years = _extract_age_years(normalized)
        if years is not None and 0 <= years <= 100:
            best_age_absolute = max(best_age_absolute, timedelta(days=years * 365))

        calendar = _extract_calendar_reference(normalized)
        if calendar is not None and 1 <= calendar.year <= 1000:
            best_calendar = calendar
            best_calendar_absolute = max(best_calendar_absolute, timedelta(days=calendar.year * 365))

        best_relative = max(best_relative, _extract_relative_delta(normalized))

    best_absolute = best_age_absolute or best_calendar_absolute

    return TemporalSignal(
        absolute=best_absolute or None,
        relative=best_relative or None,
        calendar=best_calendar,
        has_explicit_marker=has_explicit_marker,
    )


class TimelineBuilder:
    """Small state machine for sequential story-time reconstruction."""

    def __init__(self, *, base_time: datetime = BASE_DATE):
        self.base_time = base_time
        self.current_time: datetime | None = None

    def apply_segment(self, *, segment_index: int, markers: Iterable[str]) -> datetime:
        signal = extract_temporal_signal(markers)
        if signal.absolute is not None:
            self.current_time = self.base_time + signal.absolute
            return self.current_time

        if signal.relative is not None:
            anchor = self.current_time or (self.base_time + timedelta(days=segment_index))
            self.current_time = anchor + signal.relative
            return self.current_time

        if self.current_time is None:
            self.current_time = self.base_time + timedelta(days=segment_index)
        else:
            self.current_time = self.current_time + timedelta(days=1)
        return self.current_time


def estimate_story_time(segment_index: int, markers: List[str]) -> datetime:
    """Convert a segment's time markers into a datetime."""
    if markers:
        return parse_time_expressions(markers)
    return BASE_DATE + timedelta(days=segment_index)


def detect_large_timeline_jump(previous_time: datetime, current_time: datetime) -> bool:
    return (current_time - previous_time) > timedelta(days=366)


def _extract_age_years(marker: str) -> Optional[int]:
    for pattern in (AGE_PATTERN, AGE_HYPHEN_PATTERN, AGE_NARRATION):
        match = pattern.search(marker)
        if not match:
            continue
        for group in match.groups():
            value = _parse_count(group)
            if value is not None:
                return value
    return None


def _extract_calendar_reference(marker: str) -> Optional[CalendarReference]:
    ad_match = ARMORED_DRAGON_YEAR.search(marker)
    if ad_match:
        year = int(ad_match.group(1) or ad_match.group(2))
        return CalendarReference(era="Armored Dragon", year=year)

    shorthand_match = CALENDAR_SHORTHAND.search(marker)
    if shorthand_match:
        return CalendarReference(era="Armored Dragon", year=int(shorthand_match.group(1)))
    return None


def _extract_relative_delta(marker: str) -> timedelta:
    best = timedelta(0)

    for pattern, multiplier in (
        (RELATIVE_YEARS, 365),
        (RELATIVE_MONTHS, 30),
        (RELATIVE_WEEKS, 7),
        (RELATIVE_DAYS, 1),
    ):
        match = pattern.search(marker)
        if match:
            count = _parse_count(match.group(1))
            if count is not None:
                best = max(best, timedelta(days=_clamp_relative_count(count, multiplier) * multiplier))

    for pattern, seconds_per_unit in (
        (RELATIVE_HOURS, 3600),
        (RELATIVE_MINUTES, 60),
        (RELATIVE_SECONDS, 1),
    ):
        match = pattern.search(marker)
        if match:
            count = _parse_count(match.group(1))
            if count is not None:
                best = max(best, timedelta(seconds=count * seconds_per_unit))

    for pattern, delta in NAMED_RELATIVE_MARKERS:
        if pattern.search(marker):
            best = max(best, delta)

    return best


def _parse_count(value: object) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return NUMBER_WORDS.get(text)


def _clamp_relative_count(count: int, multiplier_days: int) -> int:
    if multiplier_days == 365:
        return min(count, 20)
    if multiplier_days == 30:
        return min(count, 24)
    if multiplier_days == 7:
        return min(count, 52)
    return min(count, 90)
