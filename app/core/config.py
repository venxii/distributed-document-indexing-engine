from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Incremental Document Indexing Engine"
    database_url: str = "postgresql+psycopg://indexflow:indexflow@localhost:5432/indexflow"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
