# RVRC Credit Sniper

A Telegram userbot that watches the **RVRC Credit Bot Updates** channel and, the moment someone gives away
breakfast or dinner credits, DMs `/claim <meal>` to `@rccredits_bot` for you.

It runs as **your own Telegram account** (bots can't read channels or DM other bots), so it's built to stay
well clear of Telegram's limits:

- **One claim in flight at a time.** It waits for the bot's answer before doing anything else.
- **Rate limiter on every send:** at least 4s between messages and at most 15 per hour (configurable, and the
  gap can't go below 2s). Claims that would break the limit are skipped, not queued, so a backlog never bursts out later.
- **FloodWait handling:** if Telegram ever says "slow down", *all* sending stops for that long plus 60s.
- **Daily caps, kept across restarts** (`state.json`, resets at midnight Singapore time): by default 1 successful claim
  per meal and 6 `/claim` attempts per meal.
- **Never retries blindly:** if the bot gives a reply it doesn't recognise, or doesn't answer, that counts as a claim,
  so it won't hammer the bot.
- **Pauses itself** if the credits bot says your NUS login expired, or doesn't understand the command. It sends you a
  note in Saved Messages and starts again once the bot says "You're in!".
- Ignores request posts ("looking for…"), duplicate posts, and posts more than 90s old.
- A small random delay (0.4–1.2s) before each claim.
- **Dry-run mode is on by default.**

## Setup

Needs Python 3.10+ and a machine that stays online (a laptop, a Raspberry Pi, or a small VPS).

```bash
git clone <this repo> && cd AILimitTesting
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. Go to <https://my.telegram.org> → **API development tools**, create an app, and put `api_id` / `api_hash`
   in `.env`.
2. Make sure your account has joined the channel and you've logged in to `@rccredits_bot` once (you already have).
3. Find the channel ID:
   ```bash
   python -m credit_sniper --list-chats
   ```
   The first run asks for your phone number and the login code Telegram sends you. This creates
   `credit_sniper.session`. **Treat that file like a password**, because it gives full access to your account. Put the
   channel's `@username` or numeric id into `CHANNEL=` in `.env`.
4. Do a dry run and leave it running until a giveaway comes in:
   ```bash
   python -m credit_sniper
   ```
   You should see `[DRY RUN] would send '/claim dinner'`.
5. Set `DRY_RUN=false` in `.env` and restart. Keep it running with `tmux`/`screen`, `nohup`, or a systemd service.

## Things to know

- When you lose a race, `@rccredits_bot` posts a "looking for credits" request in the channel under your name
  (that's how the bot works). The attempt cap keeps this to at most 6 per meal per day.
- `MAX_CLAIMS_PER_MEAL_PER_DAY` defaults to 1, because a second dinner credit you can't eat is wasted food. Raise it
  only if you're claiming for friends.
- If you have credits you won't use, `/give` them. That's what actually stops food going to waste.
- No automation is completely ban-proof. These defaults keep you to a handful of messages a day, which is less
  than you'd send claiming by hand.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover parsing of the real channel/bot messages, the rate limiter, the daily ledger, and the full claim
flow against a fake Telegram client.
