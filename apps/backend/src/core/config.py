from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEFAULT_LLM_MODEL: ClassVar[str] = "openai/gpt-oss-120b"

    MAX_CONTEXT_MESSAGES: int = 20
    MODEL_NAME: str | None = None
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str | None = None
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 1
    LLM_FAKE_MODE: bool = False
    GROQ_API_KEY: str = ""

    @property
    def llm_model(self) -> str:
        if self.LLM_MODEL is not None:
            model = self.LLM_MODEL
        elif self.MODEL_NAME is not None:
            model = self.MODEL_NAME
        else:
            model = self.DEFAULT_LLM_MODEL

        model = model.strip()
        if not model:
            raise ValueError("LLM model is not configured.")
        return model

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",

    )


settings = Settings()
