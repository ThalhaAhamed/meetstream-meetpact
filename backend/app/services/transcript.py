"""Turn MeetStream transcript payloads (several shapes) into speaker turns."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


def _num(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        value = value.get("relative")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _speaker_of(item: Dict[str, Any]) -> str:
    participant = item.get("participant")
    if isinstance(participant, dict):
        name = participant.get("full_name") or participant.get("name")
        if name:
            return str(name)
    for key in ("speakerName", "speaker_name", "speaker", "name"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (int, float)):
            return f"Speaker {int(val)}"
    return "Unknown speaker"


def _text_of(item: Dict[str, Any]) -> str:
    for key in ("transcript", "text", "sentence"):  # MeetStream uses "transcript"
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    words = item.get("words")
    if isinstance(words, list):
        return " ".join(str(w.get("text") or w.get("word") or "") for w in words if isinstance(w, dict)).strip()
    return ""


def _times_of(item: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    start = _num(item.get("start_time") if "start_time" in item else item.get("start"))
    end = _num(item.get("end_time") if "end_time" in item else item.get("end"))
    words = item.get("words")
    if (start is None or end is None) and isinstance(words, list) and words:
        first, last = words[0] or {}, words[-1] or {}
        start = start if start is not None else _num(first.get("start_timestamp") or first.get("start"))
        end = end if end is not None else _num(last.get("end_timestamp") or last.get("end"))
    return start, end


def _items(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("segments", "transcript", "results", "data", "utterances"):
            val = payload.get(key)
            if isinstance(val, list):
                return [i for i in val if isinstance(i, dict)]
        if "words" in payload or "text" in payload:
            return [payload]
    return []


def normalize_transcript(payload: Any, max_gap: float = 8.0) -> List[Dict[str, Any]]:
    """Return [{speaker, text, start, end}] with consecutive same-speaker
    segments merged into one turn (unless separated by more than max_gap s)."""
    raw: List[Dict[str, Any]] = []
    for item in _items(payload):
        text = _text_of(item)
        if text:
            start, end = _times_of(item)
            raw.append({"speaker": _speaker_of(item), "text": text, "start": start, "end": end})
    # Drop silence artifacts per segment, before merging glues them into real speech.
    turns: List[Dict[str, Any]] = []
    for seg in drop_noise(raw):
        prev = turns[-1] if turns else None
        start = seg["start"]
        if (
            prev
            and prev["speaker"] == seg["speaker"]
            and (start is None or prev["end"] is None or start - prev["end"] <= max_gap)
        ):
            prev["text"] = f"{prev['text']} {seg['text']}"
            prev["end"] = seg["end"] if seg["end"] is not None else prev["end"]
            continue
        turns.append(dict(seg))
    return turns


_WORD = re.compile(r"[a-z0-9']+")


def drop_noise(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove speech-to-text artifacts from silence.

    Seen in a live Google Meet test: segments that are only punctuation, and a
    short phrase ("Thank you.") emitted every ~30 s during silence. A short
    segment (<= 3 words) that repeats 3+ times in one meeting is dropped."""
    def key(t: Dict[str, Any]) -> str:
        return " ".join(_WORD.findall(t["text"].lower()))

    counts: Dict[str, int] = {}
    for t in turns:
        k = key(t)
        if k and len(k.split()) <= 3:
            counts[k] = counts.get(k, 0) + 1

    def filler_only(k: str) -> bool:
        # e.g. "thank you", "thank you thank you", "okay bye" - no work content.
        words = k.split()
        return 0 < len(words) <= 4 and all(w in _FILLER_WORDS for w in words)

    return [t for t in turns if key(t) and counts.get(key(t), 0) < 3 and not filler_only(key(t))]


_FILLER_WORDS = {"thank", "thanks", "you", "okay", "ok", "bye", "yeah", "yes", "um", "uh", "hmm", "mm", "right", "cool"}


_LINE = re.compile(r"^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?([^:\n]{1,80}):\s*(.+)$")


def parse_plain_transcript(text: str) -> List[Dict[str, Any]]:
    """Parse a pasted ``Speaker: words`` transcript (used by Import transcript)."""
    turns: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE.match(raw)
        if m:
            stamp, speaker, words = m.groups()
            start = None
            if stamp:
                parts = [int(p) for p in stamp.split(":")]
                start = float(parts[-1] + 60 * parts[-2] + (3600 * parts[0] if len(parts) == 3 else 0))
            turns.append({"speaker": speaker.strip(), "text": words.strip(), "start": start, "end": None})
        elif turns:
            turns[-1]["text"] += " " + raw.strip()
    return turns


def render_transcript(turns: List[Dict[str, Any]]) -> str:
    lines = []
    for t in turns:
        stamp = ""
        if t.get("start") is not None:
            s = int(t["start"])
            stamp = f"[{s // 60:02d}:{s % 60:02d}] "
        lines.append(f"{stamp}{t['speaker']}: {t['text']}")
    return "\n".join(lines)
