// Same cases as backend/tests/test_nlu.py: the browser rules (demo mode) must agree with the backend.
import assert from "node:assert/strict";
import { test } from "node:test";
import { isDenied, understand } from "../src/lib/understand";

const PLACES = new Set(["jaipur", "bhubaneswar", "cuttack", "puri", "new delhi", "delhi"]);
const known = (name: string) => PLACES.has(name.toLowerCase());

test("care and place in three languages, quotes verbatim", () => {
  for (const [text, care, place] of [
    ["My father needs dialysis near Bhubaneswar", "kidney-dialysis", "Bhubaneswar"],
    ["मेरी माँ को भुवनेश्वर के पास डायलिसिस चाहिए", "kidney-dialysis", "Bhubaneswar"],
    ["bas MRI karwana hai jaipur mein", "mri", "Jaipur"],
    ["kidney transplant in New Delhi", "kidney-transplant", "New Delhi"],
    ["dialysis Jaipur", "kidney-dialysis", "Jaipur"],
  ]) {
    const u = understand(text, known);
    assert.equal(u.care?.id, care, text);
    assert.equal(u.place?.text, place, text);
    const span = u.care!.span!;
    assert.equal(text.slice(span.start, span.end), span.quote);
  }
});

test("red flags open the emergency screen", () => {
  for (const [text, rule] of [
    ["He has chest pain and is sweating, we are in Cuttack", "chest-pain"],
    ["papa behosh ho gaye", "unresponsive"],
    ["सांप ने काट लिया", "snakebite"],
    ["She is pregnant and bleeding heavily", "bleeding"],
  ]) {
    const u = understand(text, known);
    assert.ok(u.urgency.emergency, text);
    assert.equal(u.urgency.rule, rule);
  }
  assert.equal(understand("chest pain near Cuttack", known).place?.text, "Cuttack");
});

test("denied symptoms do not trigger", () => {
  for (const text of [
    "no chest pain, just need an MRI in Jaipur",
    "seene me dard nahi hai, MRI chahiye",
    "he is breathing fine, no bleeding, needs x-ray in puri",
    "सीने में दर्द नहीं है",
  ]) {
    assert.equal(understand(text, known).urgency.emergency, false, text);
  }
  assert.ok(isDenied("no fever", 3, 8));
  assert.equal(isDenied("no cough but fever", 12, 17), false);
});

test("urgent, crisis and broad words", () => {
  const labour = understand("my wife is in labour, hospital near me", known);
  assert.deepEqual([labour.urgency.level, labour.urgency.score, labour.urgency.emergency], [3, 60, false]);
  assert.equal(labour.care?.id, "pregnancy-delivery");
  assert.ok(labour.place?.here);
  const crisis = understand("I want to kill myself", known);
  assert.ok(crisis.urgency.emergency && crisis.urgency.crisis);
  const tooth = understand("tooth pain near Puri", known);
  assert.equal(tooth.care, null);
  assert.ok(tooth.careOptions.some((o) => o.id === "root-canal"));
  assert.equal(understand("my son broke his leg, no fever", known).care?.id, "fracture-trauma");
});
