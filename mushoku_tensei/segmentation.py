"""
Intelligently segment an English light novel into logical chunks (scenes)
based on chapter/volume headings. Optimised for smaller chunks (max 1500 chars).
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Patterns for English light novel headings
CHAPTER_PATTERN = re.compile(
    r"(?im)^(?:\s*)(Chapter\s+\d+|Volume\s+\d+|Prologue|Epilogue|Interlude|Extra(?:\s+Chapter)?)\b.*$",
    re.IGNORECASE,
)


async def segment_text(
    full_text: str,
    gateway: Optional[object] = None,
    min_chunk_chars: int = 300,
    max_chunk_chars: int = 1500,  # reduced from 4000
) -> List[dict]:
    """
    Split the text into logical segments based on chapter/volume markers.
    """
    break_points = [m.start() for m in CHAPTER_PATTERN.finditer(full_text)]
    if not break_points:
        logger.info("No chapter markers found; falling back to fixed‑length chunks.")
        segments = _chunk_by_length(full_text, max_chunk_chars)
    else:
        segments = _split_by_markers(full_text, break_points, min_chunk_chars, max_chunk_chars)

    result = []
    for i, seg_text in enumerate(segments):
        meta = _guess_meta(seg_text[:200])
        result.append({
            "index": i,
            "text": seg_text.strip(),
            "volume": meta.get("volume"),
            "chapter": meta.get("chapter"),
        })

    logger.info("Segmented text into %d chunks.", len(result))
    return result


def _chunk_by_length(text: str, chunk_size: int) -> List[str]:
    chunks: List[str] = []
    cursor = 0
    while cursor < len(text):
        window = text[cursor:cursor + chunk_size]
        if len(window) < chunk_size:
            chunks.append(window)
            break
        split_at = max(window.rfind("\n\n"), window.rfind(". "))
        if split_at <= 0:
            split_at = len(window)
        chunks.append(text[cursor:cursor + split_at].strip())
        cursor += split_at
    return [chunk for chunk in chunks if chunk]


def _split_by_markers(
    text: str,
    break_points: List[int],
    min_chars: int,
    max_chars: int,
) -> List[str]:
    segments = []
    prev = 0
    for bp in break_points:
        chunk = text[prev:bp].strip()
        if len(chunk) >= min_chars:
            segments.append(chunk)
        prev = bp
    chunk = text[prev:].strip()
    if chunk:
        segments.append(chunk)
    return _merge_small_segments(segments, min_chars, max_chars)


def _merge_small_segments(segments: List[str], min_chars: int, max_chars: int) -> List[str]:
    merged = []
    buf = ""
    for seg in segments:
        if not buf:
            buf = seg
            continue
        if len(buf) < min_chars or len(buf) + len(seg) < max_chars:
            buf = f"{buf}\n\n{seg}".strip()
        else:
            merged.append(buf.strip())
            buf = seg
    if buf.strip():
        merged.append(buf.strip())
    return merged


def _guess_meta(text_snippet: str) -> dict:
    meta = {}
    vol_match = re.search(r"Volume\s+(\d+)", text_snippet, re.IGNORECASE)
    if vol_match:
        meta["volume"] = int(vol_match.group(1))
    ch_match = re.search(r"Chapter\s+(\d+)", text_snippet, re.IGNORECASE)
    if ch_match:
        meta["chapter"] = int(ch_match.group(1))
    return meta
