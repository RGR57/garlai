import unittest

from src.core.config import Settings


class LLMConfigurationTests(unittest.TestCase):
    def test_llm_model_prefers_new_field_over_legacy_model_name(self):
        settings = Settings(
            LLM_MODEL="groq/openai/gpt-oss-20b",
            MODEL_NAME="groq/old-model",
            GROQ_API_KEY="secret",
            _env_file=None,
        )

        self.assertEqual(settings.llm_model, "groq/openai/gpt-oss-20b")

    def test_llm_model_accepts_legacy_model_name_during_migration(self):
        settings = Settings(
            MODEL_NAME="groq/legacy-model",
            GROQ_API_KEY="secret",
            _env_file=None,
        )

        self.assertEqual(settings.llm_model, "groq/legacy-model")

    def test_llm_model_defaults_to_blessed_groq_model_when_unconfigured(self):
        settings = Settings(GROQ_API_KEY="secret", _env_file=None)

        self.assertEqual(settings.llm_model, "openai/gpt-oss-120b")

    def test_blank_explicit_llm_model_uses_legacy_model_name(self):
        settings = Settings(
            LLM_MODEL="",
            MODEL_NAME="groq/legacy-model",
            GROQ_API_KEY="secret",
            _env_file=None,
        )

        self.assertEqual(settings.llm_model, "groq/legacy-model")

    def test_whitespace_explicit_llm_model_uses_legacy_model_name(self):
        settings = Settings(
            LLM_MODEL="   ",
            MODEL_NAME="groq/legacy-model",
            GROQ_API_KEY="secret",
            _env_file=None,
        )

        self.assertEqual(settings.llm_model, "groq/legacy-model")

    def test_real_groq_provider_keeps_credential_boundary_explicit(self):
        settings = Settings(
            LLM_MODEL="groq/openai/gpt-oss-20b",
            GROQ_API_KEY="",
            _env_file=None,
        )

        self.assertEqual(settings.LLM_PROVIDER, "groq")
        self.assertEqual(settings.GROQ_API_KEY, "")
