from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sub Manager"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./db.sqlite3"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    sql_echo: bool = False


settings = Settings()
