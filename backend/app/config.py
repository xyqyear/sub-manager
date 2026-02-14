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

    admin_token: str = "change-me"
    refresh_loop_tick_sec: int = 15
    default_test_url: str = "https://www.gstatic.com/generate_204"
    default_test_interval: int = 300

    request_timeout_sec: float = 30.0
    min_refresh_interval_sec: int = 60
    max_refresh_interval_sec: int = 86400


settings = Settings()
