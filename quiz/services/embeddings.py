import hashlib
import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger("quiz")


def answer_digest(model_name: str, answer: str) -> str:
    payload = f"{model_name}\n{answer}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Embedder:
    def __init__(self):
        self._model = None
        self.device = ""
        self._lock = threading.Lock()

    def load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                self._model = self._build()
        return self._model

    def _build(self):
        import torch
        from sentence_transformers import SentenceTransformer

        name = settings.EMBEDDING_MODEL_SOURCE
        kwargs = {}
        if "jina" in name.lower():
            kwargs["trust_remote_code"] = True
        if os.path.isdir(name):
            kwargs["local_files_only"] = True
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("正在加载向量模型 %s（%s）", settings.EMBEDDING_MODEL, device)
        try:
            model = SentenceTransformer(name, device=device, **kwargs)
            self.device = device
            return model
        except Exception as exc:
            if device != "cuda":
                raise
            logger.warning("CUDA 加载失败，改用 CPU：%s", exc)
            model = SentenceTransformer(name, device="cpu", **kwargs)
            self.device = "cpu"
            return model

    def embed(self, texts, progress: bool = False) -> list[list[float]]:
        array = self.load().encode(
            list(texts),
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=progress,
        )
        return array.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


_embedder = Embedder()


def get_embedder() -> Embedder:
    return _embedder
