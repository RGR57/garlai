from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MAX_CONTEXT_MESSAGES: int = 20
    MODEL_NAME: str
    GROQ_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",

    )


settings = Settings()
