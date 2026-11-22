"""Understand a free-text request: what care, where, and how urgent.

The flow is fixed in code; a model only fills in one step (after the pre-consultation agent in
Americium3/ai-medical-demo):

1. screen   Red-flag rules over the person's own words, with negation ("no chest pain" does not trigger).
            A level 1/2 hit routes straight to the emergency screen: no model call, no search.
2. extract  Care and place from the shared lexicon (web/src/data/lexicon.json): whole-word phrases,
            longest first, in English, Hindi and Hinglish. A broad word ("kidney", "दाँत") becomes a
            question with options, never a guess.
3. model    Optional. With CAREPATH_LLM_ENDPOINT set (a Databricks model serving endpoint), one chat call
            fills what the rules left open (care described in other words, a place, an urgency level).
            Everything it returns is kept only if it quotes the message verbatim and the quote is not
            denied; care ids must be in the catalogue. Model urgency can only raise the rule level.
            If the call fails, the rules result stands and the response says so (`llm.error`).

Urgency → emergency score: level 1 = 100, 2 = 85, 3 = 60, 4 = 15. A score of 80 or more opens the
emergency screen. Level 3 halves the travel distance the ranking allows, so nearer hospitals count more.
Nothing here is a diagnosis.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import config

_HERE = Path(__file__).resolve().parent
_LEXICON_PATHS = [_HERE / "lexicon.json", _HERE.parent / "web" / "src" / "data" / "lexicon.json"]

URGENCY_SCORE = {1: 100, 2: 85, 3: 60, 4: 15}
URGENCY_LABEL = {1: "life-threatening", 2: "emergency", 3: "urgent", 4: "not urgent"}

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
CLAUSE_BREAK = re.compile(r"[.,;:!?।\n]|\bbut\b|\bhowever\b|\balthough\b|\bthough\b|\blekin\b|लेकिन|मगर", re.I)
# English: a denial cue right before the symptom, with at most a few filler words between.
EN_DENIAL = re.compile(
    r"(?:\bno|\bnot|\bwithout|\bdenies|\bdenied|n't|\bnever|\bnone)"
    r"(?:\s+(?:any|a|an|the|signs?|of|more|longer|real|other|having|experiencing|feeling|have|has|had|been|is|was|"
    r"felt|got|much|serious|major|really))*\s*$", re.I)
# Hindi / Hinglish: the denial comes after the symptom ("सीने में दर्द नहीं है", "seene me dard nahi").
HI_DENIAL_AFTER = re.compile(r"^\s*(?:(?:है|था|थी|हैं|तो|बिल्कुल|कोई|hai|tha|thi|to)\s*)?(?:नहीं|नही|nahi|nahin|nai\b)", re.I)


def load_lexicon() -> dict:
    for p in _LEXICON_PATHS:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("lexicon.json not found next to nlu.py or in web/src/data/")


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    lo = 0
    for m in CLAUSE_BREAK.finditer(text, 0, start):
        lo = m.end()
    nxt = CLAUSE_BREAK.search(text, end)
    return lo, (nxt.start() if nxt else len(text))


def is_denied(text: str, start: int, end: int) -> bool:
    """True when the person explicitly denies what text[start:end] says, in its own clause."""
    lo, hi = _clause_bounds(text, start, end)
    return bool(EN_DENIAL.search(text[lo:start]) or HI_DENIAL_AFTER.match(text[end:hi]))


def _phrase_regex(phrase: str) -> re.Pattern:
    p = re.escape(phrase.lower()).replace(r"\ ", r"\s+")
    if DEVANAGARI.search(phrase):
        return re.compile(p)
    return re.compile(rf"(?<![a-z0-9]){p}(?![a-z0-9])")


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s.lower())


def grounded(quote: str, text: str) -> tuple[int, int] | None:
    """Where the quote sits in the message, or None: it must appear verbatim (ignoring case and spacing),
    be at least 3 characters unless it is the whole message, and not be denied there."""
    q = (quote or "").strip()
    if not q:
        return None
    m = re.search(re.escape(q).replace(r"\ ", r"\s+"), text, re.I)
    if not m:
        return None
    if len(_norm(q)) < 3 and _norm(q) != _norm(text):
        return None
    if is_denied(text, m.start(), m.end()):
        return None
    return m.start(), m.end()


@dataclass
class Span:
    quote: str
    start: int
    end: int

    def dict(self):
        return {"quote": self.quote, "start": self.start, "end": self.end}


@dataclass
class Understanding:
    text: str
    level: int = 4
    urgency_rule: str | None = None
    urgency_span: Span | None = None
    urgency_source: str = "none"
    crisis: bool = False
    care_id: str | None = None
    care_span: Span | None = None
    care_source: str | None = None
    care_options: list[str] = field(default_factory=list)
    options_span: Span | None = None
    place_text: str | None = None
    place_here: bool = False
    place_span: Span | None = None
    place_source: str | None = None
    llm: dict = field(default_factory=lambda: {"used": False})

    @property
    def score(self) -> int:
        return URGENCY_SCORE[self.level]

    @property
    def emergency(self) -> bool:
        return self.score >= config.EMERGENCY_SCORE_MIN

    def dict(self, names: dict[str, dict]) -> dict:
        care = lambda i: {"id": i, "name": names.get(i, {}).get("en", i), "nameHi": names.get(i, {}).get("hi", i)}
        return {
            "text": self.text,
            "method": "rules+llm" if self.llm.get("used") else "rules",
            "llm": self.llm,
            "urgency": {"level": self.level, "score": self.score, "label": URGENCY_LABEL[self.level],
                        "rule": self.urgency_rule, "source": self.urgency_source, "crisis": self.crisis,
                        "emergency": self.emergency, **({"span": self.urgency_span.dict()} if self.urgency_span else {})},
            "care": ({**care(self.care_id), "source": self.care_source,
                      **({"span": self.care_span.dict()} if self.care_span else {})} if self.care_id else None),
            "careOptions": [care(i) for i in self.care_options],
            **({"careOptionsSpan": self.options_span.dict()} if self.options_span else {}),
            "place": ({"text": self.place_text, "here": self.place_here, "source": self.place_source,
                       **({"span": self.place_span.dict()} if self.place_span else {})}
                      if (self.place_text or self.place_here) else None),
        }


class LlmClient:
    """Chat completion on a Databricks model serving endpoint (OpenAI-style payload)."""

    def __init__(self, endpoint: str, timeout: float = 8.0):
        import sys
        sys.path.insert(0, str(_HERE.parent / "pipeline"))
        from databricks_sql import DatabricksSQL  # host + token (personal token or the app's OAuth identity)
        self.endpoint, self.timeout = endpoint, timeout
        self._db = DatabricksSQL(warehouse_id=os.environ.get("DATABRICKS_WAREHOUSE_ID") or "unused")

    def complete(self, messages: list[dict]) -> str:
        body = json.dumps({"messages": messages, "max_tokens": 400, "temperature": 0}).encode()
        req = urllib.request.Request(f"{self._db.host}/serving-endpoints/{self.endpoint}/invocations", data=body,
                                     method="POST", headers={"Authorization": f"Bearer {self._db.token}",
                                                             "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]


SYSTEM_PROMPT = """You help people in India find a hospital. Read the person's message (English, Hindi or Hinglish) \
and reply with JSON only, no prose:
{"care": [{"id": "<id from the list>", "quote": "<exact words from the message>"}],
 "place": {"text": "<city, district or PIN in English>", "quote": "<exact words>"} or null,
 "near_me": true or false,
 "urgency": {"level": 1, 2, 3 or 4, "quote": "<exact words, or empty>"}}
Rules:
- Do not diagnose. Choose care only if the message names it or plainly describes needing it; otherwise "care": [].
  At most 2 care items, best first.
- Every quote must be copied exactly from the message. Never quote words the person denied ("no fever").
- Urgency: 1 = life-threatening now (unconscious, not breathing); 2 = emergency (chest pain, severe breathing \
trouble, stroke signs, heavy bleeding, poisoning, snakebite, seizure now, wants to die); 3 = needs care today \
(labour, fracture, high fever, accident without danger signs); 4 = not urgent. If unsure between two levels, \
choose the more urgent.
Care ids:
"""


class Understander:
    def __init__(self, lexicon: dict | None = None, llm=None, known_place=None):
        self.lex = lexicon or load_lexicon()
        self.names = {t["id"]: {"en": t["en"], "hi": t["hi"]} for t in self.lex["terms"]}
        self.flags = [(f["id"], f["level"], bool(f.get("crisis")), [re.compile(p, re.I) for p in f["patterns"]])
                      for f in self.lex["redFlags"]]
        self.terms = sorted(((t["id"], ph, _phrase_regex(ph)) for t in self.lex["terms"] for ph in t["say"]),
                            key=lambda x: -len(x[1]))
        self.broad = sorted(((b["options"], ph, _phrase_regex(ph)) for b in self.lex["broad"] for ph in b["say"]),
                            key=lambda x: -len(x[1]))
        self.here = [re.compile(p, re.I) for p in self.lex["placeCuesHere"]]
        self.places_hi = sorted(self.lex["placesHi"].items(), key=lambda kv: -len(kv[0]))
        self.stop = set(self.lex["placeStopwords"]) | {t for _, ph, _ in self.terms for t in ph.split() if ph.isascii()}
        self.hi_non_places = set(self.lex["hiNonPlaces"])
        self.known_place = known_place or (lambda name: False)
        if llm is None and os.environ.get("CAREPATH_LLM_ENDPOINT"):
            llm = LlmClient(os.environ["CAREPATH_LLM_ENDPOINT"])
        self.llm = llm

    def info(self) -> dict:
        return {"rules": True, "llm": getattr(self.llm, "endpoint", None) if self.llm else None}

    # ------------------------------------------------------------------ 1. screen
    def screen(self, text: str, u: Understanding):
        for rule, level, crisis, patterns in self.flags:
            for p in patterns:
                for m in p.finditer(text):
                    if is_denied(text, m.start(), m.end()):
                        continue
                    if level < u.level:
                        u.level, u.urgency_rule, u.urgency_source = level, rule, "rules"
                        u.urgency_span = Span(m.group(0), m.start(), m.end())
                    u.crisis = u.crisis or crisis
                    break

    # ------------------------------------------------------------------ 2. extract
    def _matches(self, text: str, table):
        low = text.lower()
        hits, taken = [], []
        for key, phrase, rx in table:
            for m in rx.finditer(low):
                s, e = m.start(), m.end()
                if any(s < te and ts < e for ts, te in taken) or is_denied(text, s, e):
                    continue
                taken.append((s, e))
                hits.append((key, Span(text[s:e], s, e)))
        return hits

    def extract_care(self, text: str, u: Understanding):
        hits = self._matches(text, self.terms)
        if hits:
            # Longest phrase first (the table is sorted), so "kidney transplant" beats "kidney".
            hits.sort(key=lambda h: -(h[1].end - h[1].start))
            u.care_id, u.care_span, u.care_source = hits[0][0], hits[0][1], "rules"
            return
        broad = self._matches(text, self.broad)
        if broad:
            u.care_options, u.options_span = list(broad[0][0]), broad[0][1]

    _PREP = re.compile(r"(?<![a-z])(?:near|in|at|around|close to|from|next to|nearest to)\s+"
                       r"([a-z][a-z .'-]{1,40}?)(?=\s*(?:[,.;!?।]|$|\b(?:for|with|who|which|that|because|please|asap|"
                       r"urgently|today|tomorrow|tonight|now|and|hospital|hospitals|area|district|city)\b))", re.I)
    _HINGLISH = re.compile(r"([a-z]+(?:\s[a-z]+)?)\s+(?:ke paas|ke pass|ke nazdeek|ke najdeek|ke aas ?paas|mein|me)\b", re.I)
    _HINDI = re.compile(r"([ऀ-ॿ]+(?:\s[ऀ-ॿ]+)?)\s+(?:के पास|के नज़दीक|के नजदीक|के आसपास|के आस-पास|में|से)")
    _PIN = re.compile(r"(?<!\d)\d{6}(?!\d)")

    def _clean_place(self, cand: str) -> str | None:
        words = [w for w in re.split(r"\s+", cand.strip(" .'-")) if w]
        while words and words[0].lower() in self.stop:
            words.pop(0)
        while words and words[-1].lower() in self.stop:
            words.pop()
        return " ".join(words) if words else None

    def extract_place(self, text: str, u: Understanding):
        m = self._PIN.search(text)
        if m:
            u.place_text, u.place_span, u.place_source = m.group(0), Span(m.group(0), m.start(), m.end()), "rules"
            return
        for hi, en in self.places_hi:
            i = text.find(hi)
            if i >= 0:
                u.place_text, u.place_span, u.place_source = en, Span(hi, i, i + len(hi)), "rules"
                return
        for rx in (self._PREP, self._HINGLISH):
            for m in rx.finditer(text):
                cand = self._clean_place(m.group(1))
                if not cand:
                    continue
                words = cand.split()
                # Explicit "near X": keep X (the search will check it). Hinglish "X mein": only a known place.
                for n in range(len(words), 0, -1):
                    name = " ".join(words[:n])
                    if self.known_place(name) or (rx is self._PREP and n == len(words)):
                        s = m.start(1) + m.group(1).find(words[0])
                        e = m.start(1) + m.group(1).find(words[n - 1]) + len(words[n - 1])
                        u.place_text, u.place_span, u.place_source = name, Span(text[s:e], s, e), "rules"
                        return
        for m in self._HINDI.finditer(text):
            words = [w for w in m.group(1).split() if w not in self.hi_non_places]
            if words and self.known_place(" ".join(words)):
                u.place_text, u.place_span, u.place_source = " ".join(words), Span(m.group(1), m.start(1), m.end(1)), "rules"
                return
        # A bare known place ("dialysis Jaipur"): any one or two words the catalogue knows as a city or district.
        tokens = list(re.finditer(r"[A-Za-z][A-Za-z.'-]+", text))
        for n in (2, 1):
            for i in range(len(tokens) - n + 1):
                group = tokens[i:i + n]
                name = " ".join(t.group(0) for t in group)
                if name.lower() not in self.stop and self.known_place(name):
                    s, e = group[0].start(), group[-1].end()
                    u.place_text, u.place_span, u.place_source = name, Span(text[s:e], s, e), "rules"
                    return
        for rx in self.here:
            m = rx.search(text)
            if m and not is_denied(text, m.start(), m.end()):
                u.place_here, u.place_span, u.place_source = True, Span(m.group(0), m.start(), m.end()), "rules"
                return

    # ------------------------------------------------------------------ 3. model
    def _ask_model(self, text: str, u: Understanding):
        catalogue = "\n".join(f"{t['id']}: {t['en']}" for t in self.lex["terms"])
        try:
            raw = self.llm.complete([{"role": "system", "content": SYSTEM_PROMPT + catalogue},
                                     {"role": "user", "content": text}])
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0) if m else raw)
        except Exception as exc:  # the rules result stands; say why the model did not help
            u.llm = {"used": False, "endpoint": getattr(self.llm, "endpoint", None), "error": type(exc).__name__}
            return
        kept, dropped = [], []
        if not u.care_id:
            for item in (data.get("care") or [])[:2]:
                cid, where = item.get("id"), grounded(item.get("quote", ""), text)
                if cid in self.names and where and (not u.care_options or cid in u.care_options or not kept):
                    u.care_id, u.care_span, u.care_source = cid, Span(text[where[0]:where[1]], *where), "llm"
                    u.care_options, u.options_span = [], None
                    kept.append("care")
                    break
            else:
                if data.get("care"):
                    dropped.append("care")
        place = data.get("place") or None
        if not (u.place_text or u.place_here) and isinstance(place, dict) and place.get("text"):
            where = grounded(place.get("quote", ""), text)
            if where:
                u.place_text, u.place_span, u.place_source = place["text"], Span(text[where[0]:where[1]], *where), "llm"
                kept.append("place")
            else:
                dropped.append("place")
        if not (u.place_text or u.place_here) and data.get("near_me") is True:
            u.place_here, u.place_source = True, "llm"
            kept.append("near_me")
        urg = data.get("urgency") or {}
        try:
            level = int(urg.get("level", 4))
        except (TypeError, ValueError):
            level = 4
        if 1 <= level < u.level:
            where = grounded(urg.get("quote", ""), text)
            if where:  # model urgency only raises the rule level, and only with the person's own words behind it
                u.level, u.urgency_source, u.urgency_rule = level, "llm", None
                u.urgency_span = Span(text[where[0]:where[1]], *where)
                kept.append("urgency")
            else:
                dropped.append("urgency")
        u.llm = {"used": True, "endpoint": getattr(self.llm, "endpoint", None), "kept": kept, "dropped": dropped}

    def understand(self, text: str) -> Understanding:
        text = (text or "").strip()
        u = Understanding(text=text)
        self.screen(text, u)
        self.extract_place(text, u)  # rules only; also tells the emergency screen where to look
        if u.place_text and u.place_text.isascii() and u.place_text.islower():
            u.place_text = u.place_text.title()
        if u.emergency:  # rules first: an emergency needs no model and no search
            return u
        self.extract_care(text, u)
        if self.llm and (not u.care_id or not (u.place_text or u.place_here) or u.level == 4):
            self._ask_model(text, u)
        return u
