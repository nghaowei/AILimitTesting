"""Settings loaded from environment / .env. See .env.example for documentation."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .parsing import MEALS


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    channel: str | int
    bot_username: str
    meals: tuple[str, ...]
    dry_run: bool
    max_claims_per_meal_per_day: int
    max_attempts_per_meal_per_day: int
    min_seconds_between_sends: float
    max_sends_per_hour: int
    claim_delay_min: float
    claim_delay_max: float
    reply_timeout: float
    max_post_age: float
    notify_saved_messages: bool
    session_name: str
    state_file: Path
    timezone: str

    @classmethod
    def from_env(cls, require_channel: bool = True) -> "Config":
        load_dotenv()
        api_id = os.getenv("TG_API_ID", "").strip()
        api_hash = os.getenv("TG_API_HASH", "").strip()
        if not api_id or not api_hash:
            raise SystemExit("TG_API_ID and TG_API_HASH must be set (get them at https://my.telegram.org).")

        channel_raw = os.getenv("CHANNEL", "").strip()
        if require_channel and not channel_raw:
            raise SystemExit("CHANNEL must be set. Run `python -m credit_sniper --list-chats` to find it.")
        channel: str | int = int(channel_raw) if channel_raw.lstrip("-").isdigit() else channel_raw

        meals = tuple(m.strip().lower() for m in os.getenv("MEALS", "breakfast,dinner").split(",") if m.strip())
        bad = [m for m in meals if m not in MEALS]
        if bad or not meals:
            raise SystemExit(f"MEALS must be a comma list of {MEALS}, got {bad or 'nothing'}.")

        cfg = cls(
            api_id=int(api_id),
            api_hash=api_hash,
            channel=channel,
            bot_username=os.getenv("BOT_USERNAME", "rccredits_bot").strip().lstrip("@"),
            meals=meals,
            dry_run=_bool("DRY_RUN", True),
            max_claims_per_meal_per_day=_int("MAX_CLAIMS_PER_MEAL_PER_DAY", 1),
            max_attempts_per_meal_per_day=_int("MAX_ATTEMPTS_PER_MEAL_PER_DAY", 6),
            min_seconds_between_sends=_float("MIN_SECONDS_BETWEEN_SENDS", 4.0),
            max_sends_per_hour=_int("MAX_SENDS_PER_HOUR", 15),
            claim_delay_min=_float("CLAIM_DELAY_MIN", 0.4),
            claim_delay_max=_float("CLAIM_DELAY_MAX", 1.2),
            reply_timeout=_float("REPLY_TIMEOUT", 20.0),
            max_post_age=_float("MAX_POST_AGE_SECONDS", 90.0),
            notify_saved_messages=_bool("NOTIFY_SAVED_MESSAGES", True),
            session_name=os.getenv("SESSION_NAME", "credit_sniper").strip(),
            state_file=Path(os.getenv("STATE_FILE", "state.json").strip()),
            timezone=os.getenv("TIMEZONE", "Asia/Singapore").strip(),
        )
        if cfg.min_seconds_between_sends < 2:
            raise SystemExit("MIN_SECONDS_BETWEEN_SENDS below 2 is not allowed (ban risk).")
        if not 0 <= cfg.claim_delay_min <= cfg.claim_delay_max:
            raise SystemExit("Need 0 <= CLAIM_DELAY_MIN <= CLAIM_DELAY_MAX.")
        if cfg.max_claims_per_meal_per_day < 1 or cfg.max_attempts_per_meal_per_day < 1:
            raise SystemExit("Daily caps must be at least 1.")
        return cfg
