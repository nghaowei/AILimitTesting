"""Rate limiting and the persistent per-day claim ledger."""

import json
import os
import time
from collections import deque
from datetime import date
from pathlib import Path


class RateLimiter:
    """Guards every outgoing Telegram message.

    - at least `min_interval` seconds between sends
    - at most `max_per_hour` sends in any rolling hour
    - a hard cooldown after Telegram tells us to slow down (FloodWait)
    """

    def __init__(self, min_interval: float, max_per_hour: int, clock=time.monotonic):
        self.min_interval = min_interval
        self.max_per_hour = max_per_hour
        self._clock = clock
        self._sent: deque[float] = deque()
        self._cooldown_until = 0.0

    def _prune(self, now: float) -> None:
        while self._sent and now - self._sent[0] >= 3600:
            self._sent.popleft()

    def wait_time(self) -> float | None:
        """Seconds to wait before a send is allowed, or None if it must be skipped.

        Skipping (rather than queueing) is deliberate: a claim that has to wait
        minutes is stale anyway, and a backlog would burst once the limit lifts.
        """
        now = self._clock()
        if now < self._cooldown_until:
            return None
        self._prune(now)
        if len(self._sent) >= self.max_per_hour:
            return None
        if self._sent:
            return max(0.0, self._sent[-1] + self.min_interval - now)
        return 0.0

    def record_send(self) -> None:
        self._sent.append(self._clock())

    def cooldown(self, seconds: float) -> None:
        self._cooldown_until = max(self._cooldown_until, self._clock() + seconds)

    def cooldown_remaining(self) -> float:
        return max(0.0, self._cooldown_until - self._clock())


class Ledger:
    """Claims and attempts per meal for the current day, persisted across restarts."""

    def __init__(self, path: Path, max_claims: int, max_attempts: int, today=date.today):
        self.path = Path(path)
        self.max_claims = max_claims
        self.max_attempts = max_attempts
        self._today = today
        self._day = ""
        self.claims: dict[str, int] = {}
        self.attempts: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            self._day = data.get("day", "")
            self.claims = {k: int(v) for k, v in data.get("claims", {}).items()}
            self.attempts = {k: int(v) for k, v in data.get("attempts", {}).items()}
        except (FileNotFoundError, ValueError, AttributeError):
            pass
        self._roll()

    def _roll(self) -> None:
        today = self._today().isoformat()
        if self._day != today:
            self._day, self.claims, self.attempts = today, {}, {}
            self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"day": self._day, "claims": self.claims, "attempts": self.attempts}))
        os.replace(tmp, self.path)

    def can_claim(self, meal: str) -> bool:
        self._roll()
        return (self.claims.get(meal, 0) < self.max_claims
                and self.attempts.get(meal, 0) < self.max_attempts)

    def record_attempt(self, meal: str) -> None:
        self._roll()
        self.attempts[meal] = self.attempts.get(meal, 0) + 1
        self._save()

    def record_claim(self, meal: str) -> None:
        self._roll()
        self.claims[meal] = self.claims.get(meal, 0) + 1
        self._save()
