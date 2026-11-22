"""LLM judge of hospital records: grounded verdicts can lower proof and reorder; nothing else is kept."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from judge import EvidenceJudge  # noqa: E402
from recommender import Recommender  # noqa: E402
from tests.test_serving_cross_encoder import snapshot  # noqa: E402


class FakeLlm:
    endpoint = "fake-llm"

    def __init__(self, verdicts):
        self.verdicts, self.calls, self.payloads = verdicts, 0, []

    def complete(self, messages):
        self.calls += 1
        payload = json.loads(messages[1]["content"])
        self.payloads.append(payload)
        if isinstance(self.verdicts, Exception):
            raise self.verdicts
        by_name = {h["name"]: h["id"] for h in payload["hospitals"]}
        return json.dumps({"hospitals": [{**v, "id": by_name.get(name, name)} for name, v in self.verdicts.items()]})


def rec(verdicts):
    r = Recommender(snapshot(), ranking_method="rules")
    r.judge = EvidenceJudge(FakeLlm(verdicts))
    return r


class JudgeTest(unittest.TestCase):
    # These tests are about the judge, not the search radius: keep the pool to the first step with a provider,
    # so the far-away "outside" record is not pulled in by MIN_POOL_SIZE (tested in test_serving_cross_encoder).
    def setUp(self):
        self._pool = config.MIN_POOL_SIZE
        config.MIN_POOL_SIZE = 1

    def tearDown(self):
        config.MIN_POOL_SIZE = self._pool

    def test_grounded_verdict_lowers_proof_and_reorders(self):
        r = rec({"Near": {"verdict": "equipment_only", "quote": "We provide dialysis.", "reason": "only a machine"},
                 "Far": {"verdict": "offers", "quote": "specialized dialysis treatment unit", "reason": "a dialysis unit"}})
        plain = [f["id"] for f in r.recommend("dialysis", "26.9,75.8")["results"]]
        out = r.recommend("dialysis", "26.9,75.8", judge=True)
        self.assertEqual(plain, ["near", "far"])
        self.assertEqual([f["id"] for f in out["results"]], ["far", "near"])  # equipment_only is weak proof
        near = next(f for f in out["results"] if f["id"] == "near")
        self.assertEqual(near["judgement"]["verdict"], "equipment_only")
        self.assertEqual(near["judgement"]["line"], "We provide dialysis.")
        self.assertEqual(near["judgement"]["field"], "procedure")
        self.assertFalse(near["rankFactors"]["solidProof"])
        self.assertEqual(out["metadata"]["judge"], {"used": True, "available": True, "model": "fake-llm",
                                                    "asked": 2, "judged": 2})

    def test_only_usable_lines_are_shown_to_the_model(self):
        r = rec({})
        r.recommend("dialysis", "26.9,75.8", judge=True)
        lines = [ln["text"] for h in r.judge.llm.payloads[0]["hospitals"] for ln in h["lines"]]
        self.assertNotIn("unusable specialized dialysis text", lines)

    def test_ungrounded_or_invalid_verdicts_are_dropped(self):
        r = rec({"Near": {"verdict": "not_supported", "quote": "they closed the dialysis unit"},
                 "Far": {"verdict": "excellent", "quote": "specialized dialysis treatment unit"}})
        out = r.recommend("dialysis", "26.9,75.8", judge=True)
        self.assertEqual([f["id"] for f in out["results"]], ["near", "far"])
        self.assertTrue(all("judgement" not in f for f in out["results"]))
        self.assertEqual(out["metadata"]["judge"]["judged"], 0)

    def test_verdict_never_raises_proof(self):
        r = rec({"Far": {"verdict": "offers", "quote": "specialized dialysis treatment unit"}})
        plain = {f["id"]: f["rankFactors"]["proof"] for f in r.recommend("dialysis", "26.9,75.8")["results"]}
        judged = {f["id"]: f["rankFactors"]["proof"] for f in r.recommend("dialysis", "26.9,75.8", judge=True)["results"]}
        self.assertEqual(judged["far"], plain["far"])

    def test_failure_keeps_rules_ranking_and_says_so(self):
        r = rec(TimeoutError())
        out = r.recommend("dialysis", "26.9,75.8", judge=True)
        self.assertEqual([f["id"] for f in out["results"]], ["near", "far"])
        self.assertEqual(out["metadata"]["judge"]["error"], "TimeoutError")

    def test_verdicts_are_cached_per_care_and_hospital(self):
        r = rec({"Near": {"verdict": "offers", "quote": "We provide dialysis."}})
        r.recommend("dialysis", "26.9,75.8", judge=True)
        r.recommend("haemodialysis", "26.91,75.8", judge=True)
        self.assertEqual(r.judge.llm.calls, 2)  # "far" was not judged the first time, so it is asked again
        self.assertEqual([h["name"] for h in r.judge.llm.payloads[1]["hospitals"]], ["Far"])

    def test_without_a_model_the_flag_is_harmless(self):
        r = Recommender(snapshot(), ranking_method="rules")
        out = r.recommend("dialysis", "26.9,75.8", judge=True)
        self.assertEqual(out["metadata"]["judge"], {"used": False, "available": False})
        self.assertIn("equipment_only", config.JUDGE_WEAK)


if __name__ == "__main__":
    unittest.main()
