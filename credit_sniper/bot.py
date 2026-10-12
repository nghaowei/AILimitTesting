"""Telegram userbot: watches the credits channel and DMs /claim to the credits bot."""

import asyncio
import logging
import random
from collections import deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

from .config import Config
from .limits import Ledger, RateLimiter
from .parsing import Reply, classify_reply, parse_available

log = logging.getLogger("credit_sniper")


class Sniper:
    def __init__(self, cfg: Config, client: TelegramClient):
        self.cfg = cfg
        self.client = client
        tz = ZoneInfo(cfg.timezone)
        self.ledger = Ledger(cfg.state_file, cfg.max_claims_per_meal_per_day,
                             cfg.max_attempts_per_meal_per_day,
                             today=lambda: datetime.now(tz).date())
        self.limiter = RateLimiter(cfg.min_seconds_between_sends, cfg.max_sends_per_hour)
        self.paused_reason: str | None = None
        self._paused_for_login = False
        self._lock = asyncio.Lock()  # one claim in flight at a time, ever
        self._awaiting_reply = False
        self._replies: asyncio.Queue[tuple[Reply, str]] = asyncio.Queue()
        self._seen: deque[int] = deque(maxlen=500)
        self.bot = None

    async def setup(self) -> None:
        channel = await self.client.get_entity(self.cfg.channel)
        self.bot = await self.client.get_entity(self.cfg.bot_username)
        self.client.add_event_handler(self.on_post, events.NewMessage(chats=channel))
        self.client.add_event_handler(self.on_bot_message, events.NewMessage(chats=self.bot, incoming=True))
        log.info("Watching channel %r, claiming via @%s, meals=%s, dry_run=%s, today's ledger: claims=%s attempts=%s",
                 getattr(channel, "title", self.cfg.channel), self.cfg.bot_username, ",".join(self.cfg.meals),
                 self.cfg.dry_run, self.ledger.claims, self.ledger.attempts)

    # ---- incoming events -------------------------------------------------

    async def on_bot_message(self, event) -> None:
        text = event.raw_text or ""
        kind = classify_reply(text)
        if kind is Reply.LOGIN_NEEDED:
            self._paused_for_login = True
            await self._pause("the credits bot says you need to log in again. Log in via the bot; "
                              "claiming resumes automatically once it says \"You're in\".")
        elif kind is Reply.LOGGED_IN and self._paused_for_login:
            self._paused_for_login = False
            self.paused_reason = None
            log.info("Bot login confirmed - claiming resumed.")
        if self._awaiting_reply:
            self._replies.put_nowait((kind, text))
        else:
            log.debug("Bot message (not awaiting): %s", text)

    async def on_post(self, event) -> None:
        msg = event.message
        if msg.id in self._seen:
            return
        self._seen.append(msg.id)

        available = parse_available(msg.raw_text or "")
        wanted = [m for m in self.cfg.meals if available.get(m, 0) > 0]
        if not wanted:
            log.debug("Post %s: nothing to claim (%r)", msg.id, (msg.raw_text or "")[:60])
            return
        age = (datetime.now(timezone.utc) - msg.date).total_seconds()
        if age > self.cfg.max_post_age:
            log.info("Ignoring stale post %s (%.0fs old): %s", msg.id, age, available)
            return
        log.info("Post %s: available %s", msg.id, available)

        async with self._lock:
            for meal in wanted:
                if self.paused_reason:
                    log.warning("Paused (%s) - not claiming %s.", self.paused_reason, meal)
                    return
                if not self.ledger.can_claim(meal):
                    log.info("Daily cap reached for %s (claims=%s, attempts=%s) - skipping.",
                             meal, self.ledger.claims.get(meal, 0), self.ledger.attempts.get(meal, 0))
                    continue
                await self._claim(meal)

    # ---- claiming ----------------------------------------------------------

    async def _claim(self, meal: str) -> None:
        await asyncio.sleep(random.uniform(self.cfg.claim_delay_min, self.cfg.claim_delay_max))

        wait = self.limiter.wait_time()
        if wait is None:
            log.warning("Rate limit/cooldown active (%.0fs left) - skipping %s claim.",
                        self.limiter.cooldown_remaining(), meal)
            return
        if wait > 0:
            await asyncio.sleep(wait)
            if self.limiter.wait_time() != 0:
                return

        command = f"/claim {meal}"
        if self.cfg.dry_run:
            log.info("[DRY RUN] would send %r to @%s", command, self.cfg.bot_username)
            self.limiter.record_send()
            return

        while not self._replies.empty():
            self._replies.get_nowait()
        self._awaiting_reply = True
        try:
            try:
                await self.client.send_message(self.bot, command)
            except FloodWaitError as e:
                self.limiter.cooldown(e.seconds + 60)
                log.error("Telegram FloodWait %ss - all sending paused for %ss.", e.seconds, e.seconds + 60)
                return
            except RPCError as e:
                log.error("Failed to send %r: %s", command, e)
                return
            self.limiter.record_send()
            self.ledger.record_attempt(meal)
            log.info("Sent %r", command)
            kind, text = await self._await_reply()
        finally:
            self._awaiting_reply = False

        if kind is Reply.SUCCESS:
            self.ledger.record_claim(meal)
            log.info("Claimed %s: %s", meal, text)
            await self._notify(f"✅ Auto-claimed 1 {meal} credit.\n\nBot said: {text}")
        elif kind is Reply.SOLD_OUT:
            log.info("Lost the race for %s: %s", meal, text)
        elif kind is Reply.BAD_COMMAND:
            await self._pause(f"the bot didn't understand {command!r} - its command format may have changed.")
        elif kind is Reply.LOGIN_NEEDED:
            pass  # on_bot_message already paused and notified
        else:
            # Unknown reply or no reply: count it as a claim so we never hammer the bot
            # with retries for something that might already have succeeded.
            self.ledger.record_claim(meal)
            log.warning("Unrecognised/no reply for %s (%r) - counting as claimed to be safe.", meal, text)
            await self._notify(f"⚠️ Sent {command} but couldn't tell if it worked. "
                               f"Bot said: {text or '(nothing within timeout)'}\n"
                               f"Counted it as claimed - no more {meal} claims today.")

    async def _await_reply(self) -> tuple[Reply, str]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.cfg.reply_timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                kind, text = await asyncio.wait_for(self._replies.get(), remaining)
            except asyncio.TimeoutError:
                break
            if kind in (Reply.PROGRESS, Reply.LOGGED_IN):
                continue  # bot is auto-refreshing the session; the real answer follows
            return kind, text
        return Reply.UNKNOWN, ""

    # ---- helpers -------------------------------------------------------------

    async def _pause(self, reason: str) -> None:
        if self.paused_reason == reason:
            return
        self.paused_reason = reason
        log.error("PAUSED: %s", reason)
        await self._notify(f"⏸️ Credit sniper paused: {reason}")

    async def _notify(self, text: str) -> None:
        if not self.cfg.notify_saved_messages or self.cfg.dry_run:
            return
        if self.limiter.cooldown_remaining() > 0:
            return
        try:
            await self.client.send_message("me", text)
        except FloodWaitError as e:
            self.limiter.cooldown(e.seconds + 60)
            log.error("FloodWait on notification - sending paused for %ss.", e.seconds + 60)
        except RPCError as e:
            log.warning("Could not send notification: %s", e)


def make_client(cfg: Config) -> TelegramClient:
    # flood_sleep_threshold=0: surface every FloodWait to our own handler instead of
    # silently sleeping, so the limiter can stop *all* sends for the cooldown.
    return TelegramClient(cfg.session_name, cfg.api_id, cfg.api_hash,
                          flood_sleep_threshold=0, sequential_updates=False)


async def list_chats(cfg: Config) -> None:
    async with make_client(cfg) as client:
        async for d in client.iter_dialogs():
            if d.is_channel or getattr(d.entity, "bot", False):
                username = getattr(d.entity, "username", None)
                print(f"{d.id:>16}  @{username or '-':<24}  {d.name}")


async def run(cfg: Config) -> None:
    client = make_client(cfg)
    await client.start()
    try:
        sniper = Sniper(cfg, client)
        await sniper.setup()
        if cfg.dry_run:
            log.warning("DRY_RUN is on - nothing will be sent. Set DRY_RUN=false in .env to go live.")
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
