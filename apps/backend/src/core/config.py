from typing import ClassVar

from pydantic import Field
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
    DURABLE_DB_PATH: str = Field(
        default="runtime/garl-durable.sqlite3",
        validation_alias="GARL_DURABLE_DB_PATH",
    )

    @property
    def llm_model(self) -> str:
        for configured_model in (
            self.LLM_MODEL,
            self.MODEL_NAME,
            self.DEFAULT_LLM_MODEL,
        ):
            if configured_model is None:
                continue

            model = configured_model.strip()
            if model:
                return model

        raise ValueError("LLM model is not configured.")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",

    )


settings = Settings()
