import logging
import os
from threading import Lock

from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingsModelError(Exception):
    """Raised when embeddings model cannot be loaded or used."""


class EmbeddingsModelProvider:
    """
    Thread-safe lazy singleton provider for sentence-transformers model.

    One model instance is created per process and reused across requests.
    """

    _model = None
    _lock = Lock()
    _disabled_warning_emitted = False

    @classmethod
    def _warn_disabled_once(cls) -> None:
        if cls._disabled_warning_emitted:
            return
        message = (
            "Embeddings are disabled by EMBEDDINGS_ENABLED=false. "
            "Returning empty embedding result."
        )
        logger.warning(message)
        print(f"WARNING: {message}")
        cls._disabled_warning_emitted = True

    @classmethod
    def _resolve_load_target(cls) -> tuple[str, str | None]:
        model_path = getattr(settings, "EMBEDDINGS_MODEL_PATH", None)
        model_id = getattr(
            settings,
            "EMBEDDINGS_MODEL_ID",
            "BAAI/bge-m3",
        )

        if model_path and os.path.isdir(model_path):
            return model_path, None

        cache_dir = getattr(settings, "EMBEDDINGS_CACHE_DIR", None)
        return model_id, cache_dir

    @classmethod
    def get_model(cls):
        if not bool(getattr(settings, "EMBEDDINGS_ENABLED", True)):
            cls._warn_disabled_once()
            return None

        if cls._model is not None:
            return cls._model

        with cls._lock:
            if cls._model is not None:
                return cls._model

            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingsModelError(
                    "sentence-transformers is not installed. "
                    "Add it to requirements and reinstall dependencies."
                ) from exc

            target, cache_dir = cls._resolve_load_target()
            device = getattr(settings, "EMBEDDINGS_DEVICE", "cpu")
            trust_remote_code = bool(getattr(settings, "EMBEDDINGS_TRUST_REMOTE_CODE", False))

            kwargs = {"device": device, "trust_remote_code": trust_remote_code}
            if cache_dir:
                kwargs["cache_folder"] = cache_dir

            try:
                cls._model = SentenceTransformer(target, **kwargs)
                logger.info(
                    "Embeddings model loaded: target=%s device=%s cache_dir=%s",
                    target,
                    device,
                    cache_dir,
                )
            except Exception as exc:
                raise EmbeddingsModelError(
                    f"Failed to load embeddings model from '{target}': {exc}"
                ) from exc

            return cls._model

    @classmethod
    def encode(
        cls,
        texts: str | list[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        batch_size: int = 32,
    ):
        """
        Encode one string or list of strings into embeddings.
        """
        model = cls.get_model()
        if model is None:
            return []
        try:
            return model.encode(
                texts,
                normalize_embeddings=normalize_embeddings,
                convert_to_numpy=convert_to_numpy,
                batch_size=batch_size,
            )
        except Exception as exc:
            raise EmbeddingsModelError(f"Failed to encode text(s): {exc}") from exc

