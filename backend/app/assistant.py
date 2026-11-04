"""Agent 3, Market Advisor: answers farmers' questions in Telugu or English.

Flow: understand the question (rules first, LLM only as a fallback) -> call read-only
tools (get_price, get_trend, get_forecast, compare_markets) -> write the answer from
fixed templates -> optionally let the LLM reword it, but only if every number in the
reworded text exists in the tool output (otherwise the template answer is used).
"""
from __future__ import annotations

import difflib
import json
import re
import urllib.request
from dataclasses import dataclass, field

from backend.app import settings
from backend.app.netprice import compare_markets
from backend.app.store import Store

TE_DIGITS = str.maketrans("౦౧౨౩౪౫౬౭౮౯", "0123456789")
TELUGU = re.compile(r"[ఀ-౿]")
ROMAN_TE = {"lo", "entha", "enta", "dhara", "dara", "ela", "undi", "undhi", "ammala", "aagala", "agala", "ekkada", "emiti",
            "repu", "ivala", "ivvala", "eroju", "vaaram", "varam", "perugutunda", "taggutunda", "cheppu", "cheppandi", "kavali",
            "naaku", "nenu", "nundi", "unnayi", "ammali", "ammalaa", "aagalaa", "inka", "saruku", "raaka", "ekkuva", "takkuva",
            "vachhe", "vache", "vachindi", "quintallu", "ammithe", "baagundi", "manchidi", "untundi", "dharalu", "dhara?", "ki", "ku"}

INTENTS: list[tuple[str, list[str]]] = [
    ("best_market", ["where", "which market", "best market", "better market", "more money", "highest price", "best price",
                     "ekkada", "ye market", "e market", "edi manchi market", "ekkuva dhara", "ఎక్కడ", "ఏ మార్కెట్", "ఎక్కువ ధర", "మంచి మార్కెట్"]),
    ("sell_or_wait", ["sell or wait", "sell now", "or wait", "should i wait", "should i sell", "hold", "wait", "ammala", "aagala", "agala",
                      "ammalaa", "aagalaa", "ammala aagala", "ippude ammali", "అమ్మాలా", "ఆగాలా", "ఇప్పుడే అమ్మ", "ఆగితే"]),
    ("forecast", ["next week", "forecast", "tomorrow", "coming days", "next 7", "next few days", "will", "predict", "expected", "expect",
                  "go up", "go down", "increase", "decrease", "perugutunda", "taggutunda", "perugutundi", "taggutundi", "vachhe vaaram",
                  "vache varam", "vacche vaaram", "repu", "ముందు రోజుల", "రేపు", "వచ్చే వారం", "వచ్చే రోజుల", "పెరుగుతుందా", "తగ్గుతుందా",
                  "పెరుగుతుంది", "తగ్గుతుంది", "అంచనా", "ఎలా ఉంటుంది"]),
    ("arrivals", ["arrival", "arrivals", "supply", "how much came", "how much stock", "saruku", "raaka", "aavaka", "సరుకు", "రాక", "ఆవక"]),
    ("trend", ["trend", "going up", "going down", "moving", "how are", "how is", "last week", "past week", "rising", "falling",
               "ela undi", "ela unnayi", "ఎలా ఉంది", "ఎలా ఉన్నాయి", "ధోరణి", "గత వారం"]),
    ("price", ["price", "prices", "rate", "rates", "dhara", "dara", "dharalu", "entha", "enta", "cost", "today", "ivala", "ivvala", "eroju",
               "bhav", "ధర", "ధరలు", "రేటు", "ఎంత", "ఈ రోజు", "ఇవాళ"]),
    ("help", ["help", "hello", "hi", "namaskaram", "namaste", "what can you do", "నమస్కారం", "సహాయం", "ఏమి చేయగలవు"]),
]
NEEDS_CROP = {"price", "trend", "forecast", "arrivals", "sell_or_wait", "best_market"}
CONF_TE = {"high": "ఎక్కువ", "medium": "మధ్యస్థం", "low": "తక్కువ"}
TREND_EN = {"rising": "rising", "falling": "falling", "steady": "steady"}
TREND_TE = {"rising": "పెరుగుతోంది", "falling": "తగ్గుతోంది", "steady": "స్థిరంగా ఉంది"}
DECISION_EN, DECISION_TE = "The decision is yours.", "నిర్ణయం మీదే."
GUIDE_EN, GUIDE_TE = "This is a guide, not a guaranteed price.", "ఇది ఒక సూచన మాత్రమే, హామీ ధర కాదు."


@dataclass
class Parsed:
    intent: str = "unknown"
    crop: str | None = None
    market: str | None = None
    place: str | None = None
    quantity_qtl: float | None = None
    lang: str = "en"
    extra: dict = field(default_factory=dict)


def rs(v) -> str:
    v = int(round(float(v)))
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if v < 0 else "") + "₹" + s


MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_TE = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జులై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"]


def fd(iso: str, te: bool = False) -> str:
    """2026-11-03 -> '3 Nov' / 'నవంబర్ 3' (easier to read and to speak)."""
    _y, m, d = (int(x) for x in str(iso)[:10].split("-"))
    return f"{MON_TE[m - 1]} {d}" if te else f"{d} {MON_EN[m - 1]}"


def signed(p) -> str:
    return "n/a" if p is None else f"{'+' if p > 0 else ''}{p:.1f}%"


# ---------------------------------------------------------------------------- understanding
def _contains(text: str, words: list[str], phrase: str) -> bool:
    if TELUGU.search(phrase):
        return phrase in text
    return re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text) is not None


def _find_entity(text: str, tokens: list[str], table: dict[str, list[str]]) -> str | None:
    best, best_pos = None, None
    for eid, names in table.items():
        for n in names:
            n = n.lower()
            if TELUGU.search(n):
                pos = text.find(n)
            else:
                m = re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", text)
                pos = m.start() if m else -1
            if pos >= 0 and (best_pos is None or pos < best_pos):
                best, best_pos = eid, pos
    if best:
        return best
    latin = {n.lower(): eid for eid, names in table.items() for n in names if not TELUGU.search(n) and len(n) >= 4}
    for t in tokens:
        if len(t) >= 5:
            close = difflib.get_close_matches(t, list(latin), n=1, cutoff=0.82)
            if close:
                return latin[close[0]]
    return None


def parse(question: str, store: Store) -> Parsed:
    text = " ".join(question.translate(TE_DIGITS).lower().split())
    tokens = re.findall(r"[a-z]+", text)
    p = Parsed()
    if TELUGU.search(text) or sum(t in ROMAN_TE for t in tokens) >= 1:
        p.lang = "te"
    crops = {c["id"]: [c["id"], c["en"], *c["aliases"]] for c in store.catalog["crops"]}
    markets = {m["id"]: [m["id"], m["en"], m["te"], *m["aliases"]] for m in store.catalog["markets"]}
    places = {pl["id"]: [pl["en"].split(" (")[0]] for pl in store.places}
    p.crop = _find_entity(text, tokens, crops)
    p.market = _find_entity(text, tokens, markets)
    p.place = _find_entity(text, tokens, places)
    q = re.search(r"(\d+(?:\.\d+)?)\s*(quintals?|qtls?|qtl|క్వింటా\w*|క్వింటాళ్ల\w*|tonnes?|tons?|టన్\w*)", text)
    if q:
        val = float(q.group(1))
        p.quantity_qtl = val * 10 if q.group(2).startswith(("ton", "టన్")) else val
    for intent, words in INTENTS:
        if any(_contains(text, tokens, w) for w in words):
            p.intent = intent
            break
    if p.intent in ("unknown", "help") and (p.crop or p.market):
        p.intent = "price"
    return p


def llm_parse(question: str, store: Store) -> Parsed | None:
    if not settings.LLM_ENABLED:
        return None
    prompt = ("Extract the farmer's request as JSON with keys intent (price|trend|forecast|best_market|sell_or_wait|arrivals|help), "
              f"crop ({'|'.join(store.crops)}|null), market ({'|'.join(store.markets)}|null). Reply with JSON only.")
    out = llm_chat([{"role": "system", "content": prompt}, {"role": "user", "content": question}], max_tokens=80)
    if not out:
        return None
    try:
        data = json.loads(out[out.find("{"): out.rfind("}") + 1])
    except ValueError:
        return None
    p = Parsed(lang="te" if TELUGU.search(question) else "en")
    p.intent = data.get("intent") if data.get("intent") in {i for i, _ in INTENTS} else "unknown"
    p.crop = data.get("crop") if data.get("crop") in store.crops else None
    p.market = data.get("market") if data.get("market") in store.markets else None
    return p


# ---------------------------------------------------------------------------- read-only tools
def get_price(store: Store, crop: str, market: str) -> dict | None:
    return store.latest(crop, market) if store.has(crop, market) else None


def get_trend(store: Store, crop: str, market: str) -> dict | None:
    return store.trend(crop, market) if store.has(crop, market) else None


def get_forecast(store: Store, crop: str, market: str) -> dict | None:
    return store.forecast(crop, market)


TOOLS = {"get_price": get_price, "get_trend": get_trend, "get_forecast": get_forecast, "compare_markets": compare_markets}


# ---------------------------------------------------------------------------- answers
def _names(store: Store, crop: str | None, market: str | None):
    c = store.crops.get(crop) if crop else None
    m = store.markets.get(market) if market else None
    return c, m


def _strip_decision(text: str) -> str:
    return text.replace(DECISION_EN, "").replace(DECISION_TE, "").strip()


def compose(p: Parsed, lang: str, store: Store, origin: tuple[float, float] | None = None) -> tuple[str, dict]:
    te = lang == "te"
    facts: dict = {}
    cat = store.catalog
    if p.intent == "help":
        n = len(cat["markets"])
        facts["market_count"] = n
        return (("నేను టమాటా, ఉల్లిపాయ, అరటి పంటలకు ఈ రోజు మార్కెట్ ధర, ధర ధోరణి, వచ్చే 7 రోజుల ధర అంచనా, "
                 f"ఖర్చులు పోగా ఏ మార్కెట్ మంచిదో చెప్పగలను ({n} మార్కెట్లు). ఉదాహరణ: \"మదనపల్లెలో టమాటా ధర ఎంత?\"") if te else
                ("I can tell you today's mandi price, the price trend, a 7-day price range and the best market after costs "
                 f"for tomato, onion and banana in {n} Andhra Pradesh markets. Try: \"Madanapalle lo tomato rate entha?\""), facts)
    if p.intent == "unknown" or (p.intent in NEEDS_CROP and not p.crop and not p.market):
        mk = ", ".join((m["te"] if te else m["en"]) for m in cat["markets"])
        return (f"క్షమించండి, మీ ప్రశ్న అర్థం కాలేదు. నేను టమాటా, ఉల్లిపాయ, అరటి ధరలు ఈ మార్కెట్లలో చెప్పగలను: {mk}. ఉదాహరణ: \"కర్నూలులో ఉల్లిపాయ ధర ఎంత?\""
                if te else f"Sorry, I could not understand. I cover tomato, onion and banana in {mk}. Try: \"Onion price in Kurnool today?\"", facts)

    # market given but no crop: show all crops there (price) or ask
    if not p.crop:
        c_list = [c for c in cat["crops"] if store.has(c["id"], p.market)]
        if p.intent == "price" and c_list:
            rows = [(c, get_price(store, c["id"], p.market)) for c in c_list]
            facts["prices"] = {c["id"]: r for c, r in rows}
            m = store.markets[p.market]
            day = rows[0][1]["date"]
            items = ", ".join(f"{(c['te'] if te else c['en'])} {rs(r['modal'])}" for c, r in rows)
            return ((f"{m['te']}లో {fd(day, te)}న ధరలు (క్వింటాల్‌కు): {items}." if te else f"Prices at {m['en']} on {fd(day, te)} (per quintal): {items}."), facts)
        return ("ఏ పంట? నేను టమాటా, ఉల్లిపాయ, అరటి గురించి చెప్పగలను." if te else "Which crop? I cover tomato, onion and banana.", facts)

    c = store.crops[p.crop]
    cname = c["te"] if te else c["en"]
    if p.market and not store.has(p.crop, p.market):
        m = store.markets[p.market]
        avail = ", ".join((store.markets[x]["te"] if te else store.markets[x]["en"]) for x in c["markets"])
        return ((f"{m['te']}లో {c['te']} ధరలు మా వద్ద లేవు. {c['te']} కోసం మార్కెట్లు: {avail}." if te else
                 f"{c['en']} is not tracked at {m['en']}. Markets for {c['en']}: {avail}."), facts)

    if p.intent == "best_market":
        origin_id = p.place or p.market or c["markets"][0]
        place = next((pl for pl in store.places if pl["id"] == origin_id), None)
        if origin:
            lat, lon, oname = origin[0], origin[1], ("మీ ప్రాంతం" if te else "your location")
        elif place:
            lat, lon = place["lat"], place["lon"]
            oname = store.markets[origin_id]["te"] if te and origin_id in store.markets else place["en"]
        else:
            mk = store.markets[origin_id]
            lat, lon, oname = mk["lat"], mk["lon"], (mk["te"] if te else mk["en"])
        qty = p.quantity_qtl or 10
        cmp = compare_markets(store, p.crop, qty, lat, lon)
        facts["compare"] = cmp
        top = cmp["rows"][:3]
        mn = lambda mid: store.markets[mid]["te"] if te else store.markets[mid]["en"]  # noqa: E731
        q = f"{qty:g}"
        if te:
            items = ", ".join(f"{i}. {mn(r['market'])} {rs(r['net_per_qtl'])} (మొత్తం {rs(r['net_total'])})" for i, r in enumerate(top, 1))
            text = f"{oname} నుండి {q} క్వింటాళ్ల {cname}: రవాణా, కమీషన్ పోగా క్వింటాల్‌కు చేతికి వచ్చే డబ్బు: {items}."
        else:
            items = ", ".join(f"{i}. {mn(r['market'])} {rs(r['net_per_qtl'])} (total {rs(r['net_total'])})" for i, r in enumerate(top, 1))
            text = f"For {q} quintals of {cname.lower()} from {oname}, money in hand per quintal after transport and commission: {items}."
        b = cmp["best_vs_nearest"]
        if b and b["best"] != b["nearest"] and b["extra_total"] > 0:
            text += (f" సమీప మార్కెట్ ({mn(b['nearest'])}) కంటే {mn(b['best'])}లో సుమారు {rs(b['extra_total'])} ఎక్కువ వస్తుంది."
                     if te else f" {mn(b['best'])} gives about {rs(b['extra_total'])} more than the nearest market ({mn(b['nearest'])}).")
        elif b:
            text += (f" సమీప మార్కెట్ {mn(b['nearest'])} ఖర్చుల తర్వాత కూడా మంచిది." if te else f" The nearest market, {mn(b['nearest'])}, is also the best after costs.")
        text += " రవాణా ఖర్చు అంచనా మాత్రమే." if te else " Transport cost is an estimate."
        return text, facts

    if not p.market:
        if p.intent == "price":
            rows = sorted(store.latest_rows(p.crop), key=lambda r: -r["modal"])
            facts["prices"] = rows
            day = max(r["date"] for r in rows)
            items = ", ".join(f"{(store.markets[r['market']]['te'] if te else store.markets[r['market']]['en'])} {rs(r['modal'])}" for r in rows)
            top = store.markets[rows[0]["market"]]
            return ((f"{fd(day, te)}న {cname} ధరలు (క్వింటాల్‌కు): {items}. ఎక్కువ ధర {top['te']}లో ఉంది." if te else
                     f"{cname} prices on {fd(day, te)} (per quintal): {items}. Highest at {top['en']}."), facts)
        p.market = c["markets"][0]
        p.extra["default_market"] = True

    m = store.markets[p.market]
    mname = m["te"] if te else m["en"]
    note = ""
    if p.extra.get("default_market"):
        note = (f" (మార్కెట్ చెప్పలేదు కాబట్టి ముఖ్య మార్కెట్ {m['te']} తీసుకున్నాను.)" if te else
                f" (No market given, so I used {m['en']}, the main market.)")
    price = get_price(store, p.crop, p.market)
    trend = get_trend(store, p.crop, p.market)
    facts.update({"price": price, "trend": trend})

    if p.intent == "price":
        c7 = trend["change_7d_pct"]
        if te:
            text = (f"{m['te']}లో {fd(price['date'], te)}న {c['te']} ధర క్వింటాల్‌కు {rs(price['modal'])} "
                    f"(కనిష్ఠం {rs(price['min'])}, గరిష్ఠం {rs(price['max'])}).")
            if c7 is None or abs(c7) < 1:
                text += " గత వారంతో పోలిస్తే ధర దాదాపు అదే ఉంది."
            else:
                text += f" గత వారంతో పోలిస్తే {abs(c7):.1f}% {'పెరిగింది' if c7 > 0 else 'తగ్గింది'}."
        else:
            text = (f"{c['en']} at {m['en']} on {fd(price['date'], te)}: {rs(price['modal'])} per quintal "
                    f"(min {rs(price['min'])}, max {rs(price['max'])}).")
            text += (" About the same as last week." if c7 is None or abs(c7) < 1 else
                     f" {'Up' if c7 > 0 else 'Down'} {abs(c7):.1f}% from last week.")
        return text + note, facts

    if p.intent == "trend":
        lab = trend["label"]
        if te:
            text = f"{m['te']}లో {c['te']} ధర {TREND_TE[lab]}. 7 రోజుల్లో మార్పు: {signed(trend['change_7d_pct'])}, 30 రోజుల్లో: {signed(trend['change_30d_pct'])}."
            if trend["down_days_last5"] >= 3:
                text += f" గత 5 మార్కెట్ రోజుల్లో {trend['down_days_last5']} రోజులు ధర తగ్గింది."
            elif trend["up_days_last5"] >= 3:
                text += f" గత 5 మార్కెట్ రోజుల్లో {trend['up_days_last5']} రోజులు ధర పెరిగింది."
            a = trend["arrivals_change_7d_pct"]
            if a is not None:
                text += f" సరుకు రాక గత వారం కంటే {abs(a):.1f}% {'పెరిగింది' if a > 0 else 'తగ్గింది'}."
        else:
            text = f"{c['en']} at {m['en']} is {TREND_EN[lab]}. Change in 7 days: {signed(trend['change_7d_pct'])}, in 30 days: {signed(trend['change_30d_pct'])}."
            if trend["down_days_last5"] >= 3:
                text += f" Price fell on {trend['down_days_last5']} of the last 5 market days."
            elif trend["up_days_last5"] >= 3:
                text += f" Price rose on {trend['up_days_last5']} of the last 5 market days."
            a = trend["arrivals_change_7d_pct"]
            if a is not None:
                text += f" Arrivals are {'up' if a > 0 else 'down'} {abs(a):.1f}% from last week."
        return text + note, facts

    if p.intent == "arrivals":
        arr, a = price.get("arrivals_t"), trend["arrivals_change_7d_pct"]
        if arr is None:
            return ("ఈ మార్కెట్‌కు సరుకు రాక సమాచారం అందుబాటులో లేదు." if te else "Arrival data is not available for this market.") + note, facts
        if te:
            text = f"{m['te']}లో {fd(price['date'], te)}న {c['te']} సరుకు రాక {arr:g} టన్నులు."
            if a is not None:
                text += f" గత వారంతో పోలిస్తే {abs(a):.1f}% {'పెరిగింది' if a > 0 else 'తగ్గింది'}."
        else:
            text = f"Arrivals of {c['en']} at {m['en']} on {fd(price['date'], te)}: {arr:g} tonnes."
            if a is not None:
                text += f" Last 7 days vs the week before: {signed(a)}."
        return text + note, facts

    fc = get_forecast(store, p.crop, p.market)
    facts["forecast"] = fc
    if not fc or not fc.get("available"):
        return ((fc or {}).get("reason_te" if te else "reason_en") or ("అంచనా అందుబాటులో లేదు." if te else "No forecast available.")) + note, facts
    s = fc["summary"]
    if p.intent == "forecast":
        reason = fc["reasons"][0]["te" if te else "en"] if fc["reasons"] else None
        if te:
            text = (f"{m['te']}లో {c['te']}: వచ్చే 7 రోజుల్లో ధర {rs(s['lo'])} నుండి {rs(s['hi'])} మధ్య ఉండే అవకాశం ఉంది, "
                    f"ఎక్కువగా {rs(s['point_mean'])} దగ్గర. నమ్మకం: {CONF_TE[fc['confidence']]}.")
            if reason:
                text += f" ముఖ్య కారణం: {reason}."
            text += " " + GUIDE_TE
        else:
            text = (f"{c['en']} at {m['en']}: in the next 7 days the price is likely to stay between {rs(s['lo'])} and {rs(s['hi'])}, "
                    f"most likely around {rs(s['point_mean'])}. Confidence: {fc['confidence']}.")
            if reason:
                text += f" Main reason: {reason}."
            text += " " + GUIDE_EN
        return text + note, facts

    # sell_or_wait
    adv = _strip_decision(fc["advice"]["te" if te else "en"])
    if origin:
        lat, lon = origin
    else:
        lat, lon = m["lat"], m["lon"]
    cmp = compare_markets(store, p.crop, p.quantity_qtl or 10, lat, lon)
    facts["compare"] = cmp
    here = next((r for r in cmp["rows"] if r["market"] == p.market), None)
    best = cmp["rows"][0] if cmp["rows"] else None
    hint = ""
    if best and here and best["market"] != p.market and best["net_per_qtl"] > here["net_per_qtl"]:
        extra = best["net_per_qtl"] - here["net_per_qtl"]
        bm = store.markets[best["market"]]
        hint = (f" వేచి ఉండలేకపోతే, ఖర్చులు పోగా {bm['te']}లో క్వింటాల్‌కు సుమారు {rs(extra)} ఎక్కువ వస్తుంది." if te else
                f" If you cannot wait, {bm['en']} gives about {rs(extra)} more per quintal after costs.")
    if te:
        text = (f"ఈ రోజు {m['te']}లో {c['te']} ధర క్వింటాల్‌కు {rs(price['modal'])} ({fd(price['date'], te)}). "
                f"ఈ వారం: {rs(s['lo'])} నుండి {rs(s['hi'])} మధ్య ఉండే అవకాశం. {adv}{hint} {DECISION_TE}")
    else:
        text = (f"Today {c['en']} at {m['en']} is {rs(price['modal'])} per quintal ({fd(price['date'], te)}). "
                f"This week: likely {rs(s['lo'])} to {rs(s['hi'])}. {adv}{hint} {DECISION_EN}")
    return text + note, facts


def suggestions(p: Parsed, lang: str, store: Store) -> list[str]:
    crop = store.crops.get(p.crop or "tomato")
    market = store.markets.get(p.market or crop["markets"][0])
    if lang == "te":
        return [f"{market['te']}లో {crop['te']} ధర వచ్చే వారం ఎలా ఉంటుంది?", f"{crop['te']} ఎక్కడ అమ్మితే మంచిది?",
                f"{market['te']}లో {crop['te']} ఇప్పుడే అమ్మాలా, ఆగాలా?"]
    return [f"Will {crop['en'].lower()} price rise at {market['en']} next week?", f"Where should I sell {crop['en'].lower()}?",
            f"Should I sell {crop['en'].lower()} at {market['en']} now or wait?"]


# ---------------------------------------------------------------------------- LLM + number guard
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    out = set()
    for n in NUM.findall(text.translate(TE_DIGITS)):
        n = n.replace(",", "").rstrip(".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n if "." in n else str(int(n)))
    return out


def guard_ok(candidate: str, reference: str, facts: dict) -> bool:
    """Every number in the LLM text must already be in the template answer or the tool output."""
    allowed = numbers(reference) | numbers(json.dumps(facts, ensure_ascii=False, default=str))
    return numbers(candidate) <= allowed


def llm_chat(messages: list[dict], max_tokens: int = 300) -> str | None:
    if not settings.LLM_ENABLED:
        return None
    body = json.dumps({"model": settings.LLM_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{settings.LLM_BASE_URL}/chat/completions", data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "api-subscription-key": settings.LLM_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except Exception as exc:
        print(f"LLM call failed: {exc}")
        return None


def llm_reword(template: str, question: str, lang: str) -> str | None:
    language = "simple Telugu in Telugu script" if lang == "te" else "simple English"
    system = (f"You reword market answers for farmers in Andhra Pradesh. Write in {language}. Keep every number, rupee amount, "
              "date and market name exactly as given. Never add, remove, round or change any number. At most 4 short sentences. "
              "Keep any note that this is a guide and that the decision is the farmer's. Reply with the answer only.")
    return llm_chat([{"role": "system", "content": system},
                     {"role": "user", "content": f"Farmer's question: {question}\n\nAnswer to reword:\n{template}"}])


def ask(question: str, lang: str, store: Store, origin: tuple[float, float] | None = None, quantity: float | None = None,
        use_llm: bool = True) -> dict:
    question = (question or "").strip()[:500]
    p = parse(question, store)
    if p.intent == "unknown" and use_llm:
        p = llm_parse(question, store) or p
    if quantity and not p.quantity_qtl:
        p.quantity_qtl = quantity
    out_lang = p.lang if lang not in ("te", "en") else lang
    text, facts = compose(p, out_lang, store, origin)
    used_llm, guard = False, "n/a"
    if use_llm and settings.LLM_ENABLED and p.intent not in ("help", "unknown"):
        reworded = llm_reword(text, question, out_lang)
        if reworded and guard_ok(reworded, text, facts):
            text, used_llm, guard = reworded, True, "passed"
        else:
            guard = "fallback"
    data_date = None
    if facts.get("price"):
        data_date = facts["price"]["date"]
    elif facts.get("compare") or facts.get("prices"):
        data_date = store.meta["data_as_of"]
    return {"answer": text, "lang": out_lang, "intent": p.intent, "crop": p.crop, "market": p.market,
            "data_date": data_date, "source_label": store.source["label_te" if out_lang == "te" else "label_en"],
            "used_llm": used_llm, "guard": guard, "suggestions": suggestions(p, out_lang, store), "_facts": facts}
