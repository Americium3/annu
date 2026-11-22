"""Shared pair scorer. Scores are relevance signals, not clinical probabilities."""
from __future__ import annotations

from collections import OrderedDict
from threading import RLock

import numpy as np

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


class CrossEncoderError(RuntimeError):
    """Model/dependency failures must be visible, never replaced by rule scores."""


class CrossEncoderScorer:
    def __init__(self, model_name=DEFAULT_MODEL, revision=None, device="cpu", batch_size=32,
                 max_length=512, cache_size=50000, model=None):
        if min(batch_size, max_length, cache_size) < 1:
            raise ValueError("Cross-encoder batch, sequence and cache sizes must be positive")
        self.model_name, self.revision, self.device = model_name, revision, device
        self.batch_size, self.max_length, self.cache_size = batch_size, max_length, cache_size
        self._model = model  # injected test models must return raw single-label logits
        self._cache = OrderedDict()
        self._lock = RLock()

    def _load(self):
        if self._model is None:
            try:
                import torch
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    self.model_name, revision=self.revision, device=self.device,
                    max_length=self.max_length, activation_fn=torch.nn.Identity(), trust_remote_code=False,
                )
            except Exception as exc:
                raise CrossEncoderError(
                    "Cross-encoder could not load. Install the neural requirements and make the "
                    "configured Hugging Face checkpoint or local model directory available."
                ) from exc
        return self._model

    def warmup(self):
        self.score("MRI imaging", ["This facility lists MRI imaging services."])

    def info(self):
        return {"method": "cross_encoder", "model": self.model_name, "revision": self.revision,
                "device": self.device, "batchSize": self.batch_size, "maxLengthTokens": self.max_length,
                "loaded": self._model is not None, "cachedPairs": len(self._cache),
                "scoreMeaning": "sigmoid of raw relevance logit; not calibrated availability or quality"}

    def score(self, query, passages):
        if not passages:
            return []
        if not isinstance(query, str) or not query.strip() or any(not isinstance(p, str) or not p.strip() for p in passages):
            raise ValueError("Cross-encoder needs nonempty query and passage strings")
        keys = [(query, text) for text in passages]
        # Serialize CPU inference and model initialization across FastAPI request threads.
        with self._lock:
            missing = list(dict.fromkeys(k for k in keys if k not in self._cache))
            values = {k: self._cache[k] for k in keys if k in self._cache}
            if missing:
                try:
                    logits = np.asarray(self._load().predict(
                        missing, batch_size=self.batch_size, show_progress_bar=False, convert_to_numpy=True,
                    ), dtype=float)
                    if logits.shape not in {(len(missing),), (len(missing), 1)} or not np.isfinite(logits).all():
                        raise ValueError("Expected one finite logit per query/passage pair")
                    logits = logits.reshape(-1)
                    # Numerically stable sigmoid; explicitly applied exactly once.
                    z = np.exp(-np.abs(logits))
                    scores = np.where(logits >= 0, 1 / (1 + z), z / (1 + z))
                    values.update(zip(missing, map(float, scores)))
                except CrossEncoderError:
                    raise
                except Exception as exc:
                    raise CrossEncoderError("Cross-encoder inference failed; no alternative ranking was substituted.") from exc
            for key in dict.fromkeys(keys):
                self._cache[key] = values[key]
                self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return [values[k] for k in keys]
