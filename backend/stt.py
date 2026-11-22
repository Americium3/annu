"""Speech to text for the ask box, after Sprout's voice input (record in the browser, transcribe on the server).

Sprout sends the recording to Groq's Whisper; CarePath must run on Databricks, so the same open Whisper model runs
inside the app instead (CPU, `CAREPATH_STT_MODEL`, default openai/whisper-small: it writes Hindi in Devanagari,
which the smaller checkpoints do not). The browser sends 16 kHz mono 16-bit PCM, so no audio decoder (ffmpeg) is
needed on the server. A short hint of Indian place names and kinds of care is passed as Whisper's prompt: on
sample audio it turned "near Kodak" into "near Cuttack" and recovered "भुवनेश्वर" and "डायलिसिस". The hint is a
plain list of names, because longer prompts were echoed back into the transcript.

The model loads in the background at start-up; a request that arrives first waits for it. Failures are visible
(the page falls back to the browser's own speech recognition or to typing), never a made-up transcript.
"""
from __future__ import annotations

import threading
import time

import numpy as np

import config

SAMPLE_RATE = 16000
HINTS = {
    "en": "Hospitals near Bhubaneswar, Cuttack, Puri, Jaipur, Delhi, Mumbai, Patna, Lucknow. "
          "Dialysis, MRI, CT scan, NICU, C-section, delivery, fracture, burns.",
    "hi": "कटक, भुवनेश्वर, पुरी, जयपुर, दिल्ली, पटना, डायलिसिस, एमआरआई, प्रसव",
}
LANGUAGE = {"en": "english", "hi": "hindi"}


class TranscriptionError(RuntimeError):
    pass


class Transcriber:
    def __init__(self, model_name: str = config.STT_MODEL):
        self.model_name = model_name
        self._pipe = None
        self._processor = None
        self._error: str | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.model_name.lower() not in {"", "off", "none"}

    def info(self) -> dict:
        return {"model": self.model_name if self.enabled else None, "loaded": self._pipe is not None,
                "error": self._error}

    def warmup_in_background(self):
        if self.enabled:
            threading.Thread(target=self._load, name="stt-warmup", daemon=True).start()

    def _load(self):
        with self._lock:
            if self._pipe is not None:
                return
            try:
                from transformers import WhisperProcessor, pipeline
                self._processor = WhisperProcessor.from_pretrained(self.model_name)
                self._pipe = pipeline("automatic-speech-recognition", model=self.model_name, device=-1)
                self._error = None
            except Exception as exc:  # reported by /api/health and as 503 on /api/transcribe
                self._error = type(exc).__name__
                raise TranscriptionError("The speech model could not load.") from exc

    def transcribe(self, pcm16: bytes, lang: str) -> dict:
        if not self.enabled:
            raise TranscriptionError("Voice input is turned off on this server.")
        samples = np.frombuffer(pcm16[: len(pcm16) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        seconds = len(samples) / SAMPLE_RATE
        if seconds < 0.3:
            return {"transcript": "", "seconds": round(seconds, 2), "model": self.model_name}
        if seconds > config.STT_MAX_SECONDS:
            samples = samples[: int(config.STT_MAX_SECONDS * SAMPLE_RATE)]
        self._load()
        lang = lang if lang in LANGUAGE else "en"
        t0 = time.time()
        kwargs = {"language": LANGUAGE[lang], "task": "transcribe",
                  "prompt_ids": self._processor.get_prompt_ids(HINTS[lang], return_tensors="pt")}
        out = self._pipe({"raw": samples, "sampling_rate": SAMPLE_RATE}, generate_kwargs=kwargs)
        text = (out.get("text") or "").strip()
        if text and text in HINTS[lang]:  # an echoed hint is not something the person said
            text = ""
        return {"transcript": text[:600], "seconds": round(seconds, 2), "model": self.model_name,
                "elapsedMs": int((time.time() - t0) * 1000)}
