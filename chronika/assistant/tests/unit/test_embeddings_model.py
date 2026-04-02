import types
from unittest import mock

from django.test import SimpleTestCase, override_settings

from assistant.integrations.embeddings_model import (
    EmbeddingsModelError,
    EmbeddingsModelProvider,
)


class EmbeddingsModelProviderTests(SimpleTestCase):
    def setUp(self):
        EmbeddingsModelProvider._model = None
        EmbeddingsModelProvider._disabled_warning_emitted = False

    def tearDown(self):
        EmbeddingsModelProvider._model = None
        EmbeddingsModelProvider._disabled_warning_emitted = False

    @override_settings(
        EMBEDDINGS_MODEL_PATH="/local/model",
        EMBEDDINGS_MODEL_ID="BAAI/bge-m3",
        EMBEDDINGS_CACHE_DIR="/tmp/hf-cache",
    )
    def test_resolve_load_target_uses_local_path_when_directory_exists(self):
        with mock.patch("assistant.integrations.embeddings_model.os.path.isdir", return_value=True):
            target, cache_dir = EmbeddingsModelProvider._resolve_load_target()

        self.assertEqual(target, "/local/model")
        self.assertIsNone(cache_dir)

    @override_settings(
        EMBEDDINGS_MODEL_PATH="/missing/model",
        EMBEDDINGS_MODEL_ID="custom/model-id",
        EMBEDDINGS_CACHE_DIR="/tmp/hf-cache",
    )
    def test_resolve_load_target_falls_back_to_model_id(self):
        with mock.patch("assistant.integrations.embeddings_model.os.path.isdir", return_value=False):
            target, cache_dir = EmbeddingsModelProvider._resolve_load_target()

        self.assertEqual(target, "custom/model-id")
        self.assertEqual(cache_dir, "/tmp/hf-cache")

    @override_settings(
        EMBEDDINGS_MODEL_PATH=None,
        EMBEDDINGS_MODEL_ID="custom/model-id",
        EMBEDDINGS_CACHE_DIR="/tmp/hf-cache",
        EMBEDDINGS_DEVICE="cpu",
        EMBEDDINGS_TRUST_REMOTE_CODE=False,
    )
    def test_get_model_loads_once_and_reuses_singleton(self):
        fake_model = object()
        fake_ctor = mock.Mock(return_value=fake_model)
        fake_module = types.SimpleNamespace(SentenceTransformer=fake_ctor)

        with mock.patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            first = EmbeddingsModelProvider.get_model()
            second = EmbeddingsModelProvider.get_model()

        self.assertIs(first, fake_model)
        self.assertIs(second, fake_model)
        fake_ctor.assert_called_once_with(
            "custom/model-id",
            device="cpu",
            trust_remote_code=False,
            cache_folder="/tmp/hf-cache",
        )

    @override_settings(
        EMBEDDINGS_MODEL_PATH=None,
        EMBEDDINGS_MODEL_ID="custom/model-id",
        EMBEDDINGS_CACHE_DIR=None,
        EMBEDDINGS_DEVICE="cuda",
        EMBEDDINGS_TRUST_REMOTE_CODE=True,
    )
    def test_get_model_passes_kwargs_without_cache_folder_when_cache_not_set(self):
        fake_ctor = mock.Mock(return_value=object())
        fake_module = types.SimpleNamespace(SentenceTransformer=fake_ctor)

        with mock.patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            EmbeddingsModelProvider.get_model()

        fake_ctor.assert_called_once_with(
            "custom/model-id",
            device="cuda",
            trust_remote_code=True,
        )

    def test_get_model_raises_custom_error_when_package_missing(self):
        with mock.patch.dict("sys.modules", {"sentence_transformers": None}):
            with self.assertRaises(EmbeddingsModelError) as exc:
                EmbeddingsModelProvider.get_model()

        self.assertIn("sentence-transformers is not installed", str(exc.exception))

    @override_settings(EMBEDDINGS_ENABLED=False)
    def test_get_model_returns_none_when_embeddings_disabled(self):
        with mock.patch("builtins.print") as print_mock:
            model = EmbeddingsModelProvider.get_model()

        self.assertIsNone(model)
        print_mock.assert_called_once()

    @override_settings(EMBEDDINGS_ENABLED=False)
    def test_encode_returns_empty_result_when_embeddings_disabled(self):
        with mock.patch("builtins.print") as print_mock:
            result = EmbeddingsModelProvider.encode(["hello"])

        self.assertEqual(result, [])
        print_mock.assert_called_once()

    def test_encode_passes_arguments_to_model(self):
        fake_model = mock.Mock()
        fake_model.encode.return_value = [[0.1, 0.2]]
        EmbeddingsModelProvider._model = fake_model

        result = EmbeddingsModelProvider.encode(
            ["hello"],
            normalize_embeddings=False,
            convert_to_numpy=False,
            batch_size=8,
        )

        self.assertEqual(result, [[0.1, 0.2]])
        fake_model.encode.assert_called_once_with(
            ["hello"],
            normalize_embeddings=False,
            convert_to_numpy=False,
            batch_size=8,
        )

    def test_encode_wraps_model_exception(self):
        fake_model = mock.Mock()
        fake_model.encode.side_effect = RuntimeError("boom")
        EmbeddingsModelProvider._model = fake_model

        with self.assertRaises(EmbeddingsModelError) as exc:
            EmbeddingsModelProvider.encode("hello")

        self.assertIn("Failed to encode text(s)", str(exc.exception))
