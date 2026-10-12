"""End-to-end claim flow against a fake Telegram client (no network)."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from telethon.errors import FloodWaitError

from credit_sniper.bot import Sniper
from credit_sniper.config import Config

POST = "🍽️ Someone is giving away 2 DINNER credits at RVRC!\n\nCredits available now: 🍽️ 2 dinner"


def make_cfg(tmp_path, **kw):
    cfg = Config(api_id=1, api_hash="x", channel="chan", bot_username="rccredits_bot",
                 meals=("breakfast", "dinner"), dry_run=False, max_claims_per_meal_per_day=1,
                 max_attempts_per_meal_per_day=3, min_seconds_between_sends=2, max_sends_per_hour=15,
                 claim_delay_min=0, claim_delay_max=0, reply_timeout=0.3, max_post_age=90,
                 notify_saved_messages=True, session_name="t", state_file=Path(tmp_path) / "state.json",
                 timezone="Asia/Singapore")
    return replace(cfg, **kw)


class FakeClient:
    def __init__(self, reply=None, flood=False):
        self.sent = []
        self.reply = reply
        self.flood = flood
        self.sniper = None

    async def send_message(self, to, text):
        if self.flood and to != "me":
            req = SimpleNamespace()
            raise FloodWaitError(request=req, capture=30)
        self.sent.append((to, text))
        if to != "me" and self.reply is not None:
            asyncio.get_running_loop().call_later(
                0.01, lambda: asyncio.ensure_future(self.sniper.on_bot_message(SimpleNamespace(raw_text=self.reply))))


def post_event(msg_id=1, text=POST, age=0):
    return SimpleNamespace(message=SimpleNamespace(
        id=msg_id, raw_text=text, date=datetime.now(timezone.utc) - timedelta(seconds=age)))


def make(tmp_path, reply=None, flood=False, **kw):
    client = FakeClient(reply, flood)
    s = Sniper(make_cfg(tmp_path, **kw), client)
    s.bot = "BOT"
    client.sniper = s
    return s, client


def claims(client):
    return [t for to, t in client.sent if to == "BOT"]


@pytest.mark.asyncio
async def test_success_claims_once_then_capped(tmp_path):
    s, c = make(tmp_path, reply="✅ You claimed 1 dinner credit!")
    await s.on_post(post_event(1))
    assert claims(c) == ["/claim dinner"]
    assert any(to == "me" for to, _ in c.sent)  # notified
    await s.on_post(post_event(2, "Credits still available: 🍽️ 1 dinner"))
    assert claims(c) == ["/claim dinner"]  # daily cap, no second claim


@pytest.mark.asyncio
async def test_duplicate_and_stale_posts_ignored(tmp_path):
    s, c = make(tmp_path, reply="😔 No dinner credits available right now.")
    await s.on_post(post_event(1))
    await s.on_post(post_event(1))
    await s.on_post(post_event(2, age=600))
    assert claims(c) == ["/claim dinner"]


@pytest.mark.asyncio
async def test_sold_out_then_rate_limited(tmp_path):
    s, c = make(tmp_path, reply="😔 No dinner credits available right now.")
    await s.on_post(post_event(1))
    await s.on_post(post_event(2, "Credits still available: 🍽️ 1 dinner"))  # waits out 2s min interval
    assert claims(c) == ["/claim dinner", "/claim dinner"]
    assert s.ledger.claims == {} and s.ledger.attempts == {"dinner": 2}


@pytest.mark.asyncio
async def test_no_reply_counts_as_claimed(tmp_path):
    s, c = make(tmp_path, reply=None)
    await s.on_post(post_event(1))
    assert s.ledger.claims == {"dinner": 1}


@pytest.mark.asyncio
async def test_login_needed_pauses_and_resumes(tmp_path):
    s, c = make(tmp_path, reply="Your session has expired, please log in again")
    await s.on_post(post_event(1))
    assert s.paused_reason
    await s.on_post(post_event(2))
    assert claims(c) == ["/claim dinner"]
    await s.on_bot_message(SimpleNamespace(raw_text="✅ You're in! Logged in as X (RVRC)."))
    assert s.paused_reason is None


@pytest.mark.asyncio
async def test_flood_wait_stops_all_sending(tmp_path):
    s, c = make(tmp_path, reply="x", flood=True)
    await s.on_post(post_event(1))
    assert s.limiter.wait_time() is None
    assert s.limiter.cooldown_remaining() > 60


@pytest.mark.asyncio
async def test_dry_run_sends_nothing(tmp_path):
    s, c = make(tmp_path, reply="✅ claimed", dry_run=True)
    await s.on_post(post_event(1))
    assert c.sent == [] and s.ledger.attempts == {}


@pytest.mark.asyncio
async def test_unwanted_meal_ignored(tmp_path):
    s, c = make(tmp_path, reply="✅ claimed", meals=("breakfast",))
    await s.on_post(post_event(1))
    assert c.sent == []
