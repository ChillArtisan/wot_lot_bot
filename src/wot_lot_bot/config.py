from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(default="", repr=False)
    admin_telegram_ids: str = Field(default="")
    telegram_proxy: str = Field(default="", repr=False)

    lolz_api_token: str = Field(default="", repr=False)
    lolz_api_base: str = Field(default="https://prod-api.lzt.market")

    watermark: str = Field(default="")
    chromium_path: str = Field(default="")
    data_dir: Path = Field(default=Path("data"))

    @property
    def admin_ids(self) -> set[int]:
        ids = set()
        for raw in self.admin_telegram_ids.split(","):
            raw = raw.strip()
            if raw.lstrip("-").isdigit():
                ids.add(int(raw))
        return ids

    @property
    def tank_cache_dir(self) -> Path:
        return self.data_dir / "tanks"


@lru_cache
def get_settings() -> Settings:
    return Settings()
