"""Free-text understanding: rules first, model output kept only when grounded in the person's words."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nlu import Understander, grounded, is_denied  # noqa: E402

PLACES = {"jaipur", "bhubaneswar", "cuttack", "puri", "new delhi", "delhi"}


class FakeLlm:
    endpoint = "fake-endpoint"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, messages):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def nlu(llm=None):
    return Understander(llm=llm or False, known_place=lambda n: n.lower() in PLACES)


class RulesTest(unittest.TestCase):
    def test_care_and_place_in_three_languages(self):
        for text, care, place in [
            ("My father needs dialysis near Bhubaneswar", "kidney-dialysis", "Bhubaneswar"),
            ("मेरी माँ को भुवनेश्वर के पास डायलिसिस चाहिए", "kidney-dialysis", "Bhubaneswar"),
            ("bas MRI karwana hai jaipur mein", "mri", "Jaipur"),
            ("kidney transplant in New Delhi", "kidney-transplant", "New Delhi"),
            ("dialysis Jaipur", "kidney-dialysis", "Jaipur"),
        ]:
            u = nlu().understand(text)
            self.assertEqual((u.care_id, u.place_text), (care, place), text)
            self.assertEqual(text[u.care_span.start:u.care_span.end], u.care_span.quote)  # quotes are verbatim

    def test_red_flags_route_to_emergency_without_a_model_call(self):
        llm = FakeLlm({"care": [], "urgency": {"level": 4}})
        for text, rule in [("He has chest pain and is sweating, we are in Cuttack", "chest-pain"),
                           ("papa behosh ho gaye", "unresponsive"), ("सांप ने काट लिया", "snakebite"),
                           ("She is pregnant and bleeding heavily", "bleeding")]:
            u = nlu(llm).understand(text)
            self.assertTrue(u.emergency, text)
            self.assertEqual(u.urgency_rule, rule)
        self.assertEqual(llm.calls, 0)
        self.assertEqual(nlu().understand("chest pain near Cuttack").place_text, "Cuttack")  # for the emergency list

    def test_denied_symptoms_do_not_trigger(self):
        for text in ["no chest pain, just need an MRI in Jaipur", "seene me dard nahi hai, MRI chahiye",
                     "he is breathing fine, no bleeding, needs x-ray in puri", "सीने में दर्द नहीं है"]:
            self.assertFalse(nlu().understand(text).emergency, text)
        self.assertTrue(is_denied("no fever", 3, 8))
        self.assertFalse(is_denied("no cough but fever", 12, 17))

    def test_crisis_is_flagged(self):
        u = nlu().understand("I want to kill myself")
        self.assertTrue(u.emergency and u.crisis)

    def test_urgent_but_not_emergency(self):
        u = nlu().understand("my wife is in labour, hospital near me")
        self.assertEqual((u.level, u.score, u.emergency), (3, 60, False))
        self.assertEqual(u.care_id, "pregnancy-delivery")
        self.assertTrue(u.place_here)

    def test_broad_words_ask_instead_of_guessing(self):
        u = nlu().understand("tooth pain near Puri")
        self.assertIsNone(u.care_id)
        self.assertIn("root-canal", u.care_options)


class ModelTest(unittest.TestCase):
    def test_grounded_model_answers_fill_gaps(self):
        llm = FakeLlm({"care": [{"id": "kidney-dialysis", "quote": "his kidneys stopped working"}],
                       "place": {"text": "Cuttack", "quote": "Cuttack"}, "near_me": False,
                       "urgency": {"level": 3, "quote": "stopped working"}})
        u = nlu(llm).understand("his kidneys stopped working, we live in Cuttack")
        self.assertEqual((u.care_id, u.care_source), ("kidney-dialysis", "llm"))
        self.assertEqual(u.level, 3)
        self.assertEqual(llm.calls, 1)

    def test_ungrounded_or_unknown_answers_are_dropped(self):
        llm = FakeLlm({"care": [{"id": "cardiac-surgery", "quote": "needs bypass surgery"},
                                {"id": "made-up", "quote": "feels weak"}],
                       "urgency": {"level": 2, "quote": "collapsed"}})
        u = nlu(llm).understand("my grandmother feels weak")
        self.assertIsNone(u.care_id)
        self.assertEqual(u.level, 4)  # escalation without the person's words is not taken
        self.assertIn("urgency", u.llm["dropped"])

    def test_model_cannot_lower_rule_urgency_or_use_denied_quotes(self):
        llm = FakeLlm({"care": [{"id": "fever-infections", "quote": "fever"}], "urgency": {"level": 4, "quote": ""}})
        u = nlu(llm).understand("my son broke his leg, no fever")
        self.assertEqual(u.level, 3)
        self.assertEqual(u.care_id, "fracture-trauma")  # rules found it; the model is not needed for care
        self.assertIsNone(grounded("fever", "no fever"))

    def test_model_failure_keeps_rules_result_and_says_so(self):
        u = nlu(FakeLlm(TimeoutError())).understand("I need a scan")
        self.assertEqual(u.llm, {"used": False, "endpoint": "fake-endpoint", "error": "TimeoutError"})
        self.assertIn("mri", u.care_options)


class AskEndpointTest(unittest.TestCase):
    def setUp(self):
        import main
        from tests.test_serving_cross_encoder import FakeModel, snapshot
        from cross_encoder import CrossEncoderScorer
        from recommender import Recommender
        self.main = main
        rec = Recommender(snapshot(), scorer=CrossEncoderScorer(model=FakeModel()))
        self.state = patch.dict(main.STATE, {"rec": rec, "nlu": Understander(llm=False, known_place=rec.known_place)})
        self.state.start()

    def tearDown(self):
        self.state.stop()

    def ask(self, **body):
        return self.main.ask(self.main.AskRequest(**body))

    def test_results_emergency_and_questions(self):
        r = self.ask(text="my mother needs dialysis near Jaipur")
        self.assertEqual(r["next"], "results")
        self.assertEqual(r["care"]["id"], "kidney-dialysis")
        self.assertTrue(r["results"]["results"])
        self.assertEqual(self.ask(text="he collapsed and is not breathing")["next"], "emergency")
        self.assertEqual(self.ask(text="I need a scan in Jaipur")["next"], "ask_care")
        self.assertEqual(self.ask(text="dialysis please")["next"], "ask_place")
        saved = self.ask(text="dialysis please", locationText="Jaipur")
        self.assertEqual((saved["next"], saved["place"]["source"]), ("results", "saved"))

    def test_urgency_shrinks_travel_distance(self):
        calm = self.ask(text="dialysis near Jaipur")["results"]["queryContext"]["searchParameters"]
        urgent = self.ask(text="he missed his dialysis, near Jaipur")["results"]["queryContext"]["searchParameters"]
        self.assertEqual((calm["urgencyLevel"], urgent["urgencyLevel"]), (4, 3))
        self.assertEqual(urgent["travelKm"], calm["travelKm"] / 2)

    def test_device_outside_india_asks_for_a_place(self):
        r = self.ask(text="dialysis near me", coordinates={"latitude": 40.44, "longitude": -79.94})
        self.assertEqual(r["next"], "ask_place")
        self.assertIn("outside India", r["placeMessage"])


if __name__ == "__main__":
    unittest.main()
