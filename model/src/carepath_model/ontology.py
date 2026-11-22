from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OboTerm:
    id: str
    name: str = ""
    synonyms: list[str] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    obsolete: bool = False


SYNONYM_RE = re.compile(r'^synonym:\s+"((?:[^"\\]|\\.)*)"')


def read_text(path: str | Path) -> str:
    file_path = Path(path)
    if file_path.suffix == ".gz":
        with gzip.open(file_path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return file_path.read_text(encoding="utf-8")


def parse_obo(text: str) -> list[OboTerm]:
    terms: list[OboTerm] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        if not block.lstrip().startswith("[Term]"):
            continue
        term = OboTerm(id="")
        for line in block.splitlines():
            if line.startswith("id: "):
                term.id = line[4:].strip()
            elif line.startswith("name: "):
                term.name = line[6:].strip()
            elif line.startswith("is_a: "):
                parent = line[6:].split("!", 1)[0].strip()
                if parent:
                    term.parents.append(parent)
            elif line.startswith("xref: "):
                term.xrefs.append(line[6:].strip())
            elif line.startswith("is_obsolete: true"):
                term.obsolete = True
            else:
                match = SYNONYM_RE.match(line)
                if match:
                    term.synonyms.append(match.group(1).replace('\\"', '"'))
        if term.id:
            terms.append(term)
    return terms


def term_aliases(term: OboTerm) -> tuple[str, ...]:
    aliases = []
    for value in (term.name, *term.synonyms):
        cleaned = re.sub(r"\s+", " ", value).strip()
        if cleaned and cleaned not in aliases:
            aliases.append(cleaned)
    return tuple(aliases)
