"""Pure text parsing for channel posts and bot replies. No Telegram I/O here."""

import enum
import re

MEALS = ("breakfast", "dinner")

# "Someone is giving away 3 BREAKFAST credits at RVRC!"
_GIVEAWAY_RE = re.compile(r"giving away\s+(\d+)\s+(breakfast|dinner)\s+credits?", re.IGNORECASE)
# "Credits available now: 🍞 3 breakfast" / "Credits still available: 🍞 2 breakfast, 🍽️ 1 dinner"
_AVAILABLE_LINE_RE = re.compile(r"credits\s+(?:still\s+)?available(?:\s+now)?\s*:(.*)", re.IGNORECASE)
_COUNT_RE = re.compile(r"(\d+)\s*(breakfast|dinner)\b", re.IGNORECASE)


def parse_available(text: str) -> dict[str, int]:
    """Return {meal: count} of credits a channel post says are claimable right now.

    Request posts ("Someone ... is looking for ...") and "none right now" yield {}.
    """
    if not text:
        return {}
    found: dict[str, int] = {}
    match = _AVAILABLE_LINE_RE.search(text)
    if match:
        line = match.group(1).splitlines()[0] if match.group(1) else ""
        for count, meal in _COUNT_RE.findall(line):
            found[meal.lower()] = found.get(meal.lower(), 0) + int(count)
        return {m: n for m, n in found.items() if n > 0}
    # Fallback: a giveaway headline without an availability line.
    for count, meal in _GIVEAWAY_RE.findall(text):
        found[meal.lower()] = found.get(meal.lower(), 0) + int(count)
    return {m: n for m, n in found.items() if n > 0}


class Reply(enum.Enum):
    SUCCESS = "success"            # bot confirmed we got a credit
    SOLD_OUT = "sold_out"          # "No dinner credits available right now."
    LOGIN_NEEDED = "login_needed"  # session expired, user must log in again via the bot
    LOGGED_IN = "logged_in"        # "You're in! Logged in as ..."
    BAD_COMMAND = "bad_command"    # "Tell me the meal type ..." - our command was malformed
    PROGRESS = "progress"          # "Logging you in..." etc. - keep waiting
    UNKNOWN = "unknown"


def classify_reply(text: str) -> Reply:
    t = (text or "").lower()
    if re.search(r"no\s+(breakfast|dinner)\s+credits?\s+available", t):
        return Reply.SOLD_OUT
    if "you're in" in t or "you’re in" in t or "logged in as" in t:
        return Reply.LOGGED_IN
    if "logging you in" in t:
        return Reply.PROGRESS
    if re.search(r"(log ?in|sign ?in)\b.*\b(again|first|required|expired)|session (has )?expired|not logged in|please log ?in", t):
        return Reply.LOGIN_NEEDED
    if "tell me the meal type" in t:
        return Reply.BAD_COMMAND
    if re.search(r"claimed|you got|you've got|enjoy|success", t):
        return Reply.SUCCESS
    return Reply.UNKNOWN
