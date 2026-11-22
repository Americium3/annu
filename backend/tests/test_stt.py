"""Voice input: 16 kHz PCM in, transcript out; no model download (the pipeline is faked)."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stt import HINTS, Transcriber, TranscriptionError  # noqa: E402


class FakeProcessor:
    def get_prompt_ids(self, text, return_tensors=None):
        return text


class FakePipe:
    def __init__(self, text):
        self.text, self.calls = text, []

    def __call__(self, audio, generate_kwargs):
        self.calls.append((len(audio["raw"]), audio["sampling_rate"], generate_kwargs))
        return {"text": self.text}


def transcriber(text):
    t = Transcriber("fake-whisper")
    t._pipe, t._processor = FakePipe(text), FakeProcessor()
    return t


def pcm(seconds):
    return (np.sin(np.linspace(0, 440 * seconds, int(16000 * seconds))) * 8000).astype("<i2").tobytes()


class TranscriberTest(unittest.TestCase):
    def test_transcribes_with_language_and_place_name_hint(self):
        t = transcriber(" My father needs dialysis near Cuttack. ")
        out = t.transcribe(pcm(2), "en")
        self.assertEqual(out["transcript"], "My father needs dialysis near Cuttack.")
        n, rate, kwargs = t._pipe.calls[0]
        self.assertEqual((n, rate, kwargs["language"], kwargs["prompt_ids"]), (32000, 16000, "english", HINTS["en"]))
        t.transcribe(pcm(1), "hi")
        self.assertEqual(t._pipe.calls[1][2]["language"], "hindi")

    def test_too_short_is_empty_without_running_the_model(self):
        t = transcriber("anything")
        self.assertEqual(t.transcribe(pcm(0.1), "en")["transcript"], "")
        self.assertEqual(t._pipe.calls, [])

    def test_an_echoed_hint_is_not_a_transcript(self):
        self.assertEqual(transcriber("कटक, भुवनेश्वर").transcribe(pcm(1), "hi")["transcript"], "")

    def test_long_recordings_are_cut(self):
        t = transcriber("ok")
        t.transcribe(pcm(35), "en")
        self.assertEqual(t._pipe.calls[0][0], 30 * 16000)

    def test_loading_or_broken_model_answers_at_once(self):
        t = Transcriber("fake-whisper")
        t._loading = True
        with self.assertRaises(TranscriptionError) as e:
            t.transcribe(pcm(1), "en")
        self.assertIn("warming up", str(e.exception))
        t._loading, t._error = False, "OSError: no space left on device"
        with self.assertRaises(TranscriptionError) as e:
            t.transcribe(pcm(1), "en")
        self.assertIn("no space left", str(e.exception))

    def test_off_means_off(self):
        t = Transcriber("off")
        self.assertFalse(t.enabled)
        with self.assertRaises(TranscriptionError):
            t.transcribe(pcm(1), "en")


class EndpointTest(unittest.TestCase):
    def call(self, stt, body=b"", lang="en"):
        import main

        class Req:
            async def body(self):
                return body

        with patch.dict(main.STATE, {"stt": stt}):
            return asyncio.run(main.transcribe(Req(), lang))

    def test_returns_transcript(self):
        self.assertEqual(self.call(transcriber("dialysis in Puri"), pcm(1))["transcript"], "dialysis in Puri")

    def test_voice_off_is_503(self):
        import main
        with self.assertRaises(main.HTTPException) as e:
            self.call(Transcriber("off"), pcm(1))
        self.assertEqual(e.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
