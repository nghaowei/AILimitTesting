from datetime import date

from credit_sniper.limits import Ledger, RateLimiter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_min_interval():
    c = Clock()
    rl = RateLimiter(min_interval=4, max_per_hour=10, clock=c)
    assert rl.wait_time() == 0
    rl.record_send()
    c.t += 1
    assert rl.wait_time() == 3
    c.t += 3
    assert rl.wait_time() == 0


def test_hourly_cap_skips_then_recovers():
    c = Clock()
    rl = RateLimiter(min_interval=4, max_per_hour=2, clock=c)
    rl.record_send(); c.t += 10
    rl.record_send(); c.t += 10
    assert rl.wait_time() is None
    c.t += 3600
    assert rl.wait_time() == 0


def test_flood_cooldown():
    c = Clock()
    rl = RateLimiter(min_interval=4, max_per_hour=10, clock=c)
    rl.cooldown(100)
    assert rl.wait_time() is None
    c.t += 101
    assert rl.wait_time() == 0


def test_ledger_caps_and_persists(tmp_path):
    day = [date(2026, 10, 12)]
    path = tmp_path / "state.json"
    led = Ledger(path, max_claims=1, max_attempts=3, today=lambda: day[0])
    assert led.can_claim("dinner")
    led.record_attempt("dinner"); led.record_claim("dinner")
    assert not led.can_claim("dinner")
    assert led.can_claim("breakfast")

    # survives restart
    led2 = Ledger(path, max_claims=1, max_attempts=3, today=lambda: day[0])
    assert not led2.can_claim("dinner")

    # resets next day
    day[0] = date(2026, 10, 13)
    assert led2.can_claim("dinner")


def test_ledger_attempt_cap(tmp_path):
    led = Ledger(tmp_path / "s.json", max_claims=1, max_attempts=2, today=lambda: date(2026, 1, 1))
    led.record_attempt("breakfast"); led.record_attempt("breakfast")
    assert not led.can_claim("breakfast")


def test_ledger_ignores_corrupt_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("not json")
    assert Ledger(p, 1, 2, today=lambda: date(2026, 1, 1)).can_claim("dinner")
