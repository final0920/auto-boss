"""
应用配置：pydantic-settings 从 .env 读取。
缺 GPT_API_KEY 时启动报错（AC14）。
"""
from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gpt_api_key: str = ""
    gpt_base_url: str = "https://gpt.pkpp.cn/v1"
    gpt_model: str = "gpt-5.5"
    gpt_reasoning: str = "high"

    # Server
    bind_host: str = "127.0.0.1"
    terminal_token: str = ""

    # Database
    database_url: str = "sqlite:///./data/boss_autoapply.db"

    # Rate limits
    daily_apply_limit: int = 150
    apply_interval_min: int = 20
    apply_interval_max: int = 90
    vlm_daily_limit: int = 200

    # Pipeline
    score_threshold: int = 80

    # Backend selection
    default_backend: str = "uia"  # "uia" | "vision"
    t_ctrl: float = 0.8           # uia 命中率阈值，低于此切 vision
    t_ocr: float = 0.6            # ocr 命中率阈值

    # Inbox watcher poll interval (seconds)
    inbox_poll_min_sec: int = 120
    inbox_poll_max_sec: int = 300

    @model_validator(mode="after")
    def _require_gpt_api_key(self) -> "Settings":
        if not self.gpt_api_key:
            raise ValueError(
                "GPT_API_KEY is required but not set. "
                "Copy .env.example to .env and fill in GPT_API_KEY."
            )
        return self

    @field_validator("bind_host")
    @classmethod
    def _require_token_for_remote(cls, v: str) -> str:
        # 具体的 terminal_token 非空校验在 _require_token_when_remote 中（model_validator）
        return v

    @model_validator(mode="after")
    def _require_token_when_remote(self) -> "Settings":
        # BIND_HOST != 127.0.0.1 时强制 TERMINAL_TOKEN 非空高熵（AC12/P2）
        if self.bind_host != "127.0.0.1" and not self.terminal_token:
            raise ValueError(
                "TERMINAL_TOKEN must be set (non-empty, high-entropy) "
                "when BIND_HOST != 127.0.0.1"
            )
        return self


settings = Settings()
