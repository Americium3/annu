"""LLM judge: does each candidate hospital's own record support the care the person needs?

The pipeline decided offline which records *mention* a kind of care (regex + TF-IDF evidence tiers). Mentioning
is not offering: "dialysis machine", "refer to X for dialysis" and "Department of Nephrology" all mention dialysis.
Here a language model reads the top candidates' record lines (procedure, capability, equipment, specialty,
description) for the care requested and gives one verdict per hospital, after the pre-consultation agent in
Americium3/ai-medical-demo: the flow is fixed in code, the model does one bounded task, and nothing it says is
kept unless it is grounded.

- Verdicts: offers (a line says the hospital provides it), likely (a department or specialty that provides it is
  listed), mentions_only (named in passing: a list, a referral, a plan), equipment_only (only a machine), and
  not_supported (the lines are about something else). Each must quote the exact line that decided it; a verdict
  whose quote is not in that hospital's lines is dropped and the rules ranking stands for that hospital.
- Effect: proof strength x JUDGE_MULTIPLIER[verdict]. The judge can lower proof, never raise it above the rules'
  evidence tier; equipment_only and not_supported also count as weak proof (listed after solid proof).
- One batched call per search for at most JUDGE_TOP_K hospitals; verdicts are cached per (care, hospital) because
  they do not depend on who asks. If the call fails, the rules ranking stands and the response says so.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from threading import RLock

import config

SYSTEM_PROMPT = """You check hospital records for one kind of care. For each hospital, read ONLY its record lines \
(no outside knowledge about the hospital) and decide one verdict:
- "offers": a line says this hospital provides this care.
- "likely": a department or specialty that normally provides this care is listed, but the care itself is not stated.
- "mentions_only": the care is named only in passing (a long list, a referral elsewhere, a plan, a camp, a past event).
- "equipment_only": only a machine or equipment is mentioned, not the service.
- "not_supported": the lines are about something else, another institution, or say it is not available.
Quote the ONE line (exact words, copied) that decided it. Reply with JSON only:
{"hospitals": [{"id": "h1", "verdict": "...", "quote": "...", "reason": "<= 15 words, plain language"}]}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


class EvidenceJudge:
    def __init__(self, llm, cache_size: int = 20000):
        self.llm, self.cache_size = llm, cache_size
        self.model = getattr(llm, "endpoint", None)
        self._cache: OrderedDict[tuple[str, str], dict] = OrderedDict()
        self._lock = RLock()

    def info(self) -> dict:
        return {"model": self.model, "topK": config.JUDGE_TOP_K, "cached": len(self._cache)}

    @staticmethod
    def lines(evidence: list[dict]) -> list[dict]:
        """The record lines the judge may read: usable evidence, distinct text, at most JUDGE_MAX_LINES."""
        out, seen = [], set()
        for e in evidence or []:
            text = e.get("text")
            if e.get("evidence_status") != "usable" or not isinstance(text, str) or not text.strip() or text in seen:
                continue
            seen.add(text)
            out.append({"field": e.get("field") or "record", "text": text.strip()})
        return out[:config.JUDGE_MAX_LINES]

    def judge(self, tag_id: str, care: str, synonyms: list[str], hospitals: list[tuple[str, str, list[dict]]]) -> dict:
        """hospitals: (unique_id, name, evidence). Returns {unique_id: verdict dict}; raises on a failed call."""
        with self._lock:
            done = {uid: self._cache[(tag_id, uid)] for uid, _, _ in hospitals if (tag_id, uid) in self._cache}
        todo = [(uid, name, self.lines(ev)) for uid, name, ev in hospitals if uid not in done]
        todo = [h for h in todo if h[2]]
        if not todo:
            return done
        short = {f"h{i + 1}": h for i, h in enumerate(todo)}
        payload = {"care": care, "also_called": synonyms[:6],
                   "hospitals": [{"id": sid, "name": name, "lines": lines} for sid, (_, name, lines) in short.items()]}
        raw = self.llm.complete([{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        for item in data.get("hospitals") or []:
            hit = short.get(str(item.get("id")))
            verdict = item.get("verdict")
            if not hit or verdict not in config.JUDGE_MULTIPLIER:
                continue
            uid, _, lines = hit
            quote = _norm(item.get("quote", ""))
            line = next((ln for ln in lines if len(quote) >= 3 and quote in _norm(ln["text"])), None)
            if line is None:  # not grounded in this hospital's own record: the rules ranking stands
                continue
            done[uid] = {"verdict": verdict, "field": line["field"], "quote": item["quote"].strip(),
                         "line": line["text"], "reason": str(item.get("reason") or "")[:160], "model": self.model}
            with self._lock:
                self._cache[(tag_id, uid)] = done[uid]
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        return done
