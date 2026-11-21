"""Regex matcher for the curated tags; shared by build_tags.py and tfidf_classify.py."""
from __future__ import annotations

import re

from tag_dictionary import NEGATION_PATTERN, NEGATION_WINDOW_CHARS, TAGS, Tag


class TagMatcher:
    def __init__(self, tags: list[Tag] = TAGS):
        self.tags = tags
        self._negation = re.compile(NEGATION_PATTERN, re.I)
        self._compiled = [(tag.id, [re.compile(p, re.I) for p in tag.patterns]) for tag in tags]

    def match(self, text: str) -> tuple[list[str], list[str]]:
        """Return (matched tag ids, tag ids whose only mentions were negated or planned)."""
        matched, negated = [], []
        if not text:
            return matched, negated
        for tag_id, patterns in self._compiled:
            found = was_negated = False
            for p in patterns:
                for m in p.finditer(text):
                    if self._negation.search(text[max(0, m.start() - NEGATION_WINDOW_CHARS):m.start()]):
                        was_negated = True
                        continue
                    found = True
                    break
                if found:
                    break
            if found:
                matched.append(tag_id)
            elif was_negated:
                negated.append(tag_id)
        return matched, negated
