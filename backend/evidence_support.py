"""Conservative clause-level guards; text support is not real-world verification.

Only explicit, locally scoped exclusions are applied. Unknown services inherit the
upstream policy. The original text/reference must always remain in the audit.
"""
from __future__ import annotations
import re

SERVICE_PATTERNS = {
    'kidney-dialysis': r'\b(?:ha?emodialysis|dialysis|capd)\b',
    'mri': r'\bmri\b|magnetic resonance',
    'nicu': r'\bnicu\b|neonatal intensive care',
    'c-section': r'c[ -]?section|c(?:ae|e)sarean',
    'emergency-c-section': r'c[ -]?section|c(?:ae|e)sarean',
    'cardiac-surgery': r'cardiac surg|heart surg|cardiothoracic surg',
    'burns': r'\bburn(?:s)?\b',
}


def claim_status(text, service, pattern=None, recognize_referral_centers=True):
    """Assess only clauses containing the service; unrelated negation must not leak.

    States are operational linguistic flags, not an NLI probability. Multiple
    conflicting clauses remain conflict; no entity identification is invented.
    """
    expr = pattern or SERVICE_PATTERNS.get(service)
    if not expr:
        return 'unreviewed'
    matcher = re.compile(expr, re.I) if isinstance(expr, str) else expr
    states = []
    for clause in re.split(r'[.;\n]|\bbut\b|\bhowever\b', text, flags=re.I):
        for match in matcher.finditer(clause):
            before = clause[max(0, match.start()-90):match.start()]
            after = clause[match.end():match.end()+90]
            local = before + match.group() + after
            exemption = re.search(
                r'\b(?:not only(?:\s+\w+){0,3}|no[ -](?:cost|charges?|fees?)|'
                r'no (?:appointments?|waiting|waits?|referrals?)(?:\s+\w+){0,4})\s*$', before, re.I)
            if (not exemption and re.search(r'\b(?:not|no|without|never)\s+(?:\w+[ -]+){0,4}$', before, re.I)) or re.search(
                r'\b(?:discontinued|suspended|unavailable|ceased|not (?:available|offered|provided))\b', local, re.I):
                states.append('negative')
            elif re.search(r'\b(?:planned|planning|proposed|future|coming soon|will (?:offer|open|provide)|used to|formerly)\b', local, re.I):
                states.append('planned_or_historical')
            elif re.search(r'\b(?:refer(?:red|ral|ring)?|awareness|counsell?ing|education(?:al)?|training|trained|worked at)\b', local, re.I):
                # A referral center RECEIVES patients; it is not an outgoing referral claim.
                # Found in the repository's real burns-unit example. This only resolves
                # that wording, not the identity/availability of the described facility.
                incoming = re.search(r'\breferral[ -]+(?:cent(?:er|re)|hospital|unit)\b', local, re.I)
                outgoing = re.search(r'\b(?:elsewhere|another (?:hospital|institution)|referred (?:out|to))\b', local, re.I)
                other_indirect = re.search(r'\b(?:awareness|counsell?ing|education(?:al)?|training|trained|worked at)\b', local, re.I)
                states.append('support' if recognize_referral_centers and incoming and not outgoing and not other_indirect else 'indirect')
            elif re.search(r'\b(?:unknown|not specified|not mentioned|no explicit|unclear)\b', local, re.I):
                states.append('uncertain')
            else:
                states.append('support')
    if 'support' in states and any(s in states for s in ('negative', 'planned_or_historical')):
        return 'conflict'
    if 'support' in states:
        return 'support'
    for state in ('conflict', 'negative', 'planned_or_historical', 'indirect', 'uncertain'):
        if state in states:
            return state
    return 'unreviewed'


def supported_items(evidence, service, policy="strict"):
    """Return usable items and auditable exclusions, without relabeling raw records."""
    if policy not in {"off", "explicit", "strict"}:
        raise ValueError("Unknown claim guard policy")
    blocked = {"negative", "planned_or_historical", "conflict"}
    if policy == "strict":
        blocked |= {"indirect", "uncertain"}
    if policy == "off":
        blocked = set()
    kept, rejected = [], []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        if item.get('evidence_status') != 'usable' or not isinstance(item.get('text'), str) or not item['text'].strip():
            continue
        status = claim_status(item['text'], service)
        if status in blocked:
            rejected.append({**item, 'guard_status': status})
        else:
            kept.append(item)
    # A positive claim must not erase a separate explicit contradiction.
    if any(e['guard_status'] in {'negative','conflict'} for e in rejected):
        return [], rejected
    return kept, rejected
