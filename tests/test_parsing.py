from credit_sniper.parsing import Reply, classify_reply, parse_available

GIVEAWAY = """🍞 Someone is giving away 3 BREAKFAST credits at RVRC! 🎉

Credits available now: 🍞 3 breakfast

First to claim wins — tap here to DM me:
https://t.me/rccredits_bot
Then send: /claim breakfast"""


def test_giveaway_post():
    assert parse_available(GIVEAWAY) == {"breakfast": 3}


def test_still_available_post():
    assert parse_available("✅ 1 breakfast credit claimed!\n\nCredits still available: 🍞 2 breakfast") == {"breakfast": 2}


def test_none_left():
    assert parse_available("✅ 1 breakfast credit claimed!\n\nCredits still available: none right now") == {}


def test_both_meals():
    assert parse_available("Credits still available: 🍞 1 breakfast, 🍽️ 2 dinner") == {"breakfast": 1, "dinner": 2}


def test_request_post_is_ignored():
    text = ("🙏 Someone at RVRC is looking for 🍽️ DINNER credits!\n\nIf you have extras, tap here to DM me:\n"
            "https://t.me/rccredits_bot\nThen send: /give to help them out 💛")
    assert parse_available(text) == {}


def test_headline_only_fallback():
    assert parse_available("Someone is giving away 2 DINNER credits at RVRC!") == {"dinner": 2}


def test_empty():
    assert parse_available("") == {}


def test_classify_replies_from_screenshots():
    assert classify_reply("😔 No dinner credits available right now.\nI'll put out a request in the group for you! 📢") is Reply.SOLD_OUT
    assert classify_reply("Tell me the meal type — e.g. /give breakfast or /claim dinner") is Reply.BAD_COMMAND
    assert classify_reply("⏳ Logging you in...") is Reply.PROGRESS
    assert classify_reply("✅ You're in! Logged in as X (RVRC).\n🔄 Your session will auto-refresh — you only need to log in once.") is Reply.LOGGED_IN


def test_classify_other():
    assert classify_reply("✅ You claimed 1 dinner credit!") is Reply.SUCCESS
    assert classify_reply("Your session has expired, please log in again") is Reply.LOGIN_NEEDED
    assert classify_reply("something new") is Reply.UNKNOWN
