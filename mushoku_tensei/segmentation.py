"""
Semantic segmentation for Mushoku Tensei.

The ingester performs best when each extraction request covers one coherent
scene or beat, while still preserving chapter context. This splitter builds a
two-level structure:

- section boundaries from volume/chapter/interlude headers
- scene-sized extraction units from paragraph/dialogue blocks and sentences
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

HEADING_PATTERN = re.compile(
    r"(?im)^(?:\s*)(Volume\s+\d+|Chapter\s+\d+|Prologue|Epilogue|Interlude|Extra(?:\s+Chapter)?)\b.*$"
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?\"'])\s+(?=[A-Z0-9\"'])")


async def segment_text(
    full_text: str,
    gateway: Optional[object] = None,
    min_chunk_chars: int = 350,
    max_chunk_chars: int = 900,
) -> List[dict]:
    """
    Split a novel into semantically coherent extraction units.

    The optional gateway is unused for now, but kept to avoid breaking callers.
    """
    del gateway

    sections = _split_into_sections(full_text)
    segments: List[dict] = []
    current_volume: Optional[int] = None
    current_chapter: Optional[int] = None

    for section_index, section in enumerate(sections):
        heading_meta = _guess_meta(section["heading"])
        current_volume = heading_meta.get("volume", current_volume)
        current_chapter = heading_meta.get("chapter", current_chapter)

        scene_units = _split_section_into_units(
            section["body"],
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
        )
        for local_index, unit in enumerate(scene_units):
            segment_text = _compose_segment_text(section["heading"], unit)
            segments.append(
                {
                    "index": len(segments),
                    "section_index": section_index,
                    "scene_index": local_index,
                    "heading": section["heading"],
                    "text": segment_text.strip(),
                    "clean_text": unit.strip(),
                    "volume": current_volume,
                    "chapter": current_chapter,
                    "segment_kind": _infer_segment_kind(section["heading"]),
                }
            )

    logger.info("Segmented text into %d semantic chunks.", len(segments))
    return segments


def _split_into_sections(full_text: str) -> List[dict]:
    matches = list(HEADING_PATTERN.finditer(full_text))
    if not matches:
        return [{"heading": None, "body": full_text.strip()}] if full_text.strip() else []

    sections: List[dict] = []
    if matches[0].start() > 0 and full_text[: matches[0].start()].strip():
        sections.append({"heading": None, "body": full_text[: matches[0].start()].strip()})

    pending_headings: List[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        heading = match.group(0).strip()
        pending_headings = _rollup_headings(pending_headings, heading)
        if body:
            sections.append({"heading": "\n".join(pending_headings).strip(), "body": body})

    return sections


def _split_section_into_units(
    text: str,
    *,
    min_chunk_chars: int,
    max_chunk_chars: int,
) -> List[str]:
    paragraphs = _paragraph_blocks(text)
    if not paragraphs:
        return []

    units: List[str] = []
    buffer: List[str] = []
    buffer_len = 0

    for paragraph in paragraphs:
        pieces = [paragraph]
        if len(paragraph) > max_chunk_chars:
            pieces = _split_long_paragraph(paragraph, max_chunk_chars)

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue

            projected_len = buffer_len + len(piece) + (2 if buffer else 0)
            if buffer and projected_len > max_chunk_chars:
                units.append("\n\n".join(buffer).strip())
                buffer = [piece]
                buffer_len = len(piece)
                continue

            buffer.append(piece)
            buffer_len = projected_len

            if buffer_len >= min_chunk_chars and _is_scene_boundary(piece):
                units.append("\n\n".join(buffer).strip())
                buffer = []
                buffer_len = 0

    if buffer:
        buffered_text = "\n\n".join(buffer).strip()
        if units and len(buffered_text) < min_chunk_chars:
            merged = f"{units.pop()}\n\n{buffered_text}".strip()
            units.extend(_rebalance_oversized_unit(merged, max_chunk_chars))
        else:
            units.append(buffered_text)

    return [unit for unit in units if unit]


def _paragraph_blocks(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n+", text)
    normalized = [re.sub(r"\s+\n", "\n", block).strip() for block in blocks]
    return [block for block in normalized if block]


def _split_long_paragraph(paragraph: str, max_chunk_chars: int) -> List[str]:
    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()]
    if len(sentences) <= 1:
        return _hard_wrap_text(paragraph, max_chunk_chars)

    units: List[str] = []
    current: List[str] = []
    current_len = 0
    for sentence in sentences:
        if len(sentence) > max_chunk_chars:
            if current:
                units.append(" ".join(current).strip())
                current = []
                current_len = 0
            units.extend(_hard_wrap_text(sentence, max_chunk_chars))
            continue

        projected = current_len + len(sentence) + (1 if current else 0)
        if current and projected > max_chunk_chars:
            units.append(" ".join(current).strip())
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len = projected
    if current:
        units.append(" ".join(current).strip())
    return units


def _hard_wrap_text(text: str, max_chunk_chars: int) -> List[str]:
    words = text.split()
    if not words:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        if len(word) > max_chunk_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            chunks.extend(word[index : index + max_chunk_chars] for index in range(0, len(word), max_chunk_chars))
            continue

        projected = current_len + len(word) + (1 if current else 0)
        if current and projected > max_chunk_chars:
            chunks.append(" ".join(current).strip())
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


def _rebalance_oversized_unit(text: str, max_chunk_chars: int) -> List[str]:
    if len(text) <= max_chunk_chars:
        return [text]
    pieces: List[str] = []
    for paragraph in _paragraph_blocks(text):
        pieces.extend(_split_long_paragraph(paragraph, max_chunk_chars))
    return pieces


def _compose_segment_text(heading: Optional[str], body: str) -> str:
    if heading:
        return f"{heading}\n\n{body.strip()}".strip()
    return body.strip()


def _infer_segment_kind(heading: Optional[str]) -> str:
    if not heading:
        return "scene"
    lowered = heading.lower()
    if "prologue" in lowered:
        return "prologue"
    if "epilogue" in lowered:
        return "epilogue"
    if "interlude" in lowered:
        return "interlude"
    if "extra" in lowered:
        return "extra"
    if "chapter" in lowered:
        return "chapter_scene"
    if "volume" in lowered:
        return "volume_scene"
    return "scene"


def _is_scene_boundary(text: str) -> bool:
    lowered = text.lower()
    boundary_signals = (
        lowered.endswith('"'),
        lowered.endswith("'"),
        lowered.endswith("..."),
        lowered.endswith("?!"),
        bool(re.search(r"\b(later|afterward|afterwards|the next day|that night|the following morning)\b", lowered)),
    )
    return any(boundary_signals)


def _guess_meta(text_snippet: Optional[str]) -> dict:
    meta = {}
    if not text_snippet:
        return meta
    vol_match = re.search(r"Volume\s+(\d+)", text_snippet, re.IGNORECASE)
    if vol_match:
        meta["volume"] = int(vol_match.group(1))
    ch_match = re.search(r"Chapter\s+(\d+)", text_snippet, re.IGNORECASE)
    if ch_match:
        meta["chapter"] = int(ch_match.group(1))
    return meta


def _rollup_headings(pending_headings: List[str], heading: str) -> List[str]:
    lowered = heading.lower()
    if lowered.startswith("volume"):
        return [heading]
    if lowered.startswith("chapter") and pending_headings:
        return [item for item in pending_headings if item.lower().startswith("volume")] + [heading]
    return pending_headings + [heading]


def iter_segment_texts(segments: Iterable[dict]) -> List[str]:
    return [str(segment.get("text", "")).strip() for segment in segments if segment.get("text")]
