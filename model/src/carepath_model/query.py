from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

from .taxonomy import normalize_text


class Urgency(IntEnum):
    ROUTINE = 0
    URGENT = 1
    EMERGENCY = 2


@dataclass(frozen=True)
class QueryMention:
    text: str
    start: int
    end: int
    matched_label: str
    concept_id: str
    concept_type: str
    match_method: str
    confidence: float


@dataclass(frozen=True)
class AliasEntry:
    label: str
    concept_id: str
    concept_type: str
    normalized: str


EMERGENCY_PATTERNS = (
    r"\bemergenc(?:y|ies)\b",
    r"\blife[ -]?threatening\b",
    r"\bsevere chest pain\b",
    r"\bcrushing chest pain\b",
    r"\bheart attack\b",
    r"\bstroke\b",
    r"\bsudden weakness\b",
    r"\bcannot breathe\b",
    r"\bdifficulty breathing\b",
    r"\bshortness of breath\b",
    r"\bsevere bleeding\b",
    r"\buncontrolled bleeding\b",
    r"\bunconscious\b",
    r"\bnot breathing\b",
    r"\bseizure\b",
    r"\bsevere burns?\b",
    r"急诊|紧急情况|危及生命",
    r"剧烈胸痛",
    r"压榨性胸痛",
    r"心肌梗死|心梗",
    r"卒中|中风",
    r"呼吸困难",
    r"严重出血|大出血",
    r"昏迷|意识不清",
    r"抽搐|癫痫持续状态",
    r"严重烧伤",
)

URGENT_PATTERNS = (
    r"\burgent(?:ly)?\b",
    r"\bas soon as possible\b",
    r"\basap\b",
    r"\bchest pain\b",
    r"\bhigh fever\b",
    r"\bnewborn fever\b",
    r"\bsevere abdominal pain\b",
    r"\bdehydration\b",
    r"\bpregnancy bleeding\b",
    r"紧急|尽快",
    r"胸痛",
    r"高热",
    r"新生儿发热",
    r"严重腹痛",
    r"孕期出血",
)

NEGATION_WINDOW_RE = re.compile(
    r"\b(no|not|without|denies|denied|never|ruled out)\b|没有|无|否认|并非",
    re.IGNORECASE,
)

CLAUSE_BREAK_RE = re.compile(
    r"\b(and|but|or|while|also|with|plus)\b|并|和|以及|伴有",
    re.IGNORECASE,
)


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 35) : start]
    breaks = list(CLAUSE_BREAK_RE.finditer(prefix))
    if breaks:
        prefix = prefix[breaks[-1].end() :]
    return bool(NEGATION_WINDOW_RE.search(prefix))


def detect_urgency(text: str) -> Urgency:
    normalized = normalize_text(text)
    for pattern in EMERGENCY_PATTERNS:
        for match in re.finditer(pattern, normalized):
            if not _is_negated(normalized, match.start()):
                return Urgency.EMERGENCY
    for pattern in URGENT_PATTERNS:
        for match in re.finditer(pattern, normalized):
            if not _is_negated(normalized, match.start()):
                return Urgency.URGENT
    return Urgency.ROUTINE


class MentionExtractor:
    def __init__(self, aliases: list[AliasEntry]):
        deduped: dict[tuple[str, str], AliasEntry] = {}
        for entry in aliases:
            normalized = entry.normalized or normalize_text(entry.label)
            minimum_length = 2 if re.search(r"[^\x00-\x7f]", normalized) else 3
            if len(normalized) < minimum_length:
                continue
            deduped.setdefault((normalized, entry.concept_id), AliasEntry(
                label=entry.label,
                concept_id=entry.concept_id,
                concept_type=entry.concept_type,
                normalized=normalized,
            ))
        self.aliases = sorted(
            deduped.values(),
            key=lambda entry: len(entry.normalized),
            reverse=True,
        )

    def extract(self, text: str) -> list[QueryMention]:
        normalized = normalize_text(text)
        used_spans: list[tuple[int, int]] = []
        mentions: list[QueryMention] = []
        for entry in self.aliases:
            escaped = re.escape(entry.normalized)
            if re.search(r"[^\x00-\x7f]", entry.normalized):
                pattern = re.compile(escaped)
            else:
                pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")
            for match in pattern.finditer(normalized):
                if _is_negated(normalized, match.start()):
                    continue
                if any(match.start() < end and match.end() > start for start, end in used_spans):
                    continue
                used_spans.append((match.start(), match.end()))
                mentions.append(
                    QueryMention(
                        text=normalized[match.start() : match.end()],
                        start=match.start(),
                        end=match.end(),
                        matched_label=entry.label,
                        concept_id=entry.concept_id,
                        concept_type=entry.concept_type,
                        match_method="exact_or_synonym",
                        confidence=0.95 if entry.normalized == normalize_text(entry.label) else 0.9,
                    )
                )
        mentions.sort(key=lambda mention: (mention.start, mention.end))
        return mentions


def distance_weight(urgency: Urgency) -> float:
    return {
        Urgency.ROUTINE: 0.50,
        Urgency.URGENT: 0.75,
        Urgency.EMERGENCY: 0.90,
    }[urgency]
