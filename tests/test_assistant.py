from backend.app.assistant import guard_ok, numbers, parse, rs
from backend.app.store import get_store


def test_rupee_format():
    assert rs(1900) == "₹1,900" and rs(170800) == "₹1,70,800" and rs(-46) == "-₹46"


def test_numbers_and_guard():
    assert numbers("₹1,900 and 8.0% on 2026-11-03") == {"1900", "8", "2026", "11", "3"}
    facts = {"price": {"modal": 1900, "date": "2026-11-03"}}
    assert guard_ok("Price is ₹1,900 today", "Price ₹1,900", facts)
    assert not guard_ok("Price is ₹2,100 today", "Price ₹1,900", facts)  # an invented number is rejected


def test_parse_telugu_and_romanised():
    s = get_store()
    p = parse("మదనపల్లెలో టమాటా ధర ఎంత?", s)
    assert (p.intent, p.crop, p.market, p.lang) == ("price", "tomato", "madanapalle", "te")
    p = parse("Kurnool lo ullipaya dhara entha?", s)
    assert (p.intent, p.crop, p.market, p.lang) == ("price", "onion", "kurnool", "te")
    p = parse("Where should I sell 10 tonnes of onion?", s)
    assert p.intent == "best_market" and p.quantity_qtl == 100 and p.lang == "en"
