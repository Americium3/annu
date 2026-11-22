from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO_ROOT / "backend"), str(REPO_ROOT / "model" / "src")]

from carepath_model.ontology import parse_obo, read_text, term_aliases  # noqa: E402
from carepath_model.service_catalog import (  # noqa: E402
    ACTION_ALIAS_OVERRIDES,
    TAG_ACTION_OVERRIDES,
    infer_service_urgency,
)
from carepath_model.taxonomy import normalize_text  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        default=str(REPO_ROOT / "backend" / ".cache" / "snapshot.pkl"),
    )
    parser.add_argument("--maxo-obo", required=True)
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "model" / "artifacts"),
    )
    args = parser.parse_args()

    with Path(args.snapshot).open("rb") as handle:
        snapshot = pickle.load(handle)
    tags = snapshot.tags[snapshot.tags["kind"] == "service"].copy()

    terms = [
        term
        for term in parse_obo(read_text(args.maxo_obo))
        if term.id.startswith("MAXO:") and not term.obsolete
    ]
    action_labels = {term.id: term.name for term in terms}
    alias_index: dict[str, set[str]] = {}
    for term in terms:
        for alias in term_aliases(term) + ACTION_ALIAS_OVERRIDES.get(term.id, ()):
            normalized = normalize_text(alias)
            if normalized:
                alias_index.setdefault(normalized, set()).add(term.id)

    service_rows = []
    map_rows = []
    for tag in tags.itertuples():
        aliases = list(dict.fromkeys([tag.label, *(tag.synonyms or [])]))
        action_ids = set()
        for alias in aliases:
            action_ids.update(alias_index.get(normalize_text(alias), set()))
        for action_id in TAG_ACTION_OVERRIDES.get(tag.tag_id, []):
            action_ids.add(action_id)
        action_ids = sorted(action_ids)
        primary_action_id = action_ids[0] if action_ids else None

        service_id = f"tag:{tag.tag_id}"
        service_rows.append(
            {
                "service_id": service_id,
                "service_label": tag.label,
                "aliases": aliases,
                "service_type": "reference_service_tag",
                "service_group": tag.group_name,
                "facility_count": int(tag.facility_count),
                "reference_kind": tag.kind,
                "parent_action_ids": [],
                "primary_action_id": primary_action_id,
                "urgency_level": infer_service_urgency(tag.label, aliases),
                "service_contexts": ["reference_service_tag"],
                "action_mapping_status": (
                    "mapped" if primary_action_id else "capability_only_or_unmapped"
                ),
                "source": "ref_service_tags",
            }
        )
        for action_id in action_ids:
            relation = (
                "manual_override"
                if action_id in TAG_ACTION_OVERRIDES.get(tag.tag_id, [])
                else "exact_alias"
            )
            map_rows.append(
                {
                    "service_id": service_id,
                    "action_id": action_id,
                    "action_label": action_labels.get(action_id, action_id),
                    "relation_type": relation,
                    "priority": 1 if relation == "manual_override" else 2,
                    "confidence": 0.9 if relation == "manual_override" else 0.95,
                }
            )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "service_catalog.preview.json").write_text(
        json.dumps(service_rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "service_action_map.preview.json").write_text(
        json.dumps(map_rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "services": len(service_rows),
                "service_action_links": len(map_rows),
                "mapped_services": len({row["service_id"] for row in map_rows}),
                "capability_only_or_unmapped": sum(
                    not row["primary_action_id"] for row in service_rows
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
