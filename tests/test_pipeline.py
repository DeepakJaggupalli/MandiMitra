from datetime import date

import numpy as np
import pandas as pd

from pipeline.clean import clean
from pipeline.common import RunLog, load_catalog
from pipeline.forecast import conformal_q
from pipeline.sources.agmarknet import map_columns


def test_map_columns_handles_portal_exports():
    df = pd.DataFrame({"Sl no.": [1], "District Name": ["Annamayya"], "Market Name": ["Madanapalli"], "Commodity": ["TOMATO"],
                       "Variety": ["Local"], "Grade": ["FAQ"], "Min Price (Rs./Quintal)": [1200], "Max Price (Rs./Quintal)": [2400],
                       "Modal Price (Rs./Quintal)": [1900], "Price Date": ["03 Nov 2026"], "Arrivals (Qtl)": [5000]})
    out = map_columns(df)
    assert out.loc[0, "modal"] == 1900 and out.loc[0, "date"] == pd.Timestamp("2026-11-03")
    assert out.loc[0, "arrivals_t"] == 500  # quintals -> tonnes
    assert out.loc[0, "price_unit"] == "quintal"


def _raw(rows):
    return pd.DataFrame(rows, columns=["state", "district", "market_raw", "commodity_raw", "variety", "date", "min", "max",
                                       "modal", "arrivals_t", "price_unit", "source"])


def test_clean_rules():
    days = pd.date_range("2026-09-01", "2026-10-31")
    rows = [["Andhra Pradesh", "Kurnool", "Kurnool", "Onion", "Big", d, 1500, 2500, 2000, 300.0, "quintal", "X"] for d in days]
    rows.append(["Andhra Pradesh", "Kurnool", "Kurnool APMC", "ONION", "Big", days[5], 1500, 2500, 2000, 300.0, "quintal", "X"])  # same record, other spelling
    rows[10][6], rows[10][7] = 2600, 1500  # max below min
    rows[20][6:9] = [15, 25, 20]  # typed per kg
    rows.append(["Andhra Pradesh", "Kurnool", "Atlantis", "Onion", "Big", days[1], 1, 2, 1, 1.0, "quintal", "X"])  # unknown market
    out, rep = clean(_raw(rows), load_catalog(), date(2026, 10, 31), RunLog())
    assert rep["duplicates_removed"] >= 1 and rep["unit_fixes"] >= 1 and rep["unmatched_rows"] == 1
    assert any(f["rule"] == "max_below_min" for f in rep["flagged"])
    assert str(days[10].date()) not in set(out["date"].dt.strftime("%Y-%m-%d"))  # held back until reviewed
    assert out["modal"].between(1000, 3000).all()
    assert (out["crop"] == "onion").all() and (out["market"] == "kurnool").all()


def test_conformal_quantiles_cover():
    rng = np.random.default_rng(0)
    lo, hi = conformal_q(rng.normal(0, 1, (2000, 7)))
    test = rng.normal(0, 1, (5000, 7))
    cov = np.mean((test >= lo) & (test <= hi))
    assert 0.77 <= cov <= 0.83


def test_ogd_paging_and_filter_fallback(monkeypatch):
    from pipeline.sources import agmarknet as ag

    rows = [{"State": "Andhra Pradesh", "District": "Kurnool", "Market": "Kurnool", "Commodity": "Onion", "Variety": "Local",
             "Arrival_Date": f"{d:02d}/10/2026", "Min_Price": 1000, "Max_Price": 2000, "Modal_Price": 1500} for d in range(1, 26)]

    def fake_get(resource, key, filters, limit, offset):
        if "State" not in filters:  # only the title-case spelling works on this fake resource
            return {"records": [], "total": 0}
        limit = 10  # API caps page size below what we ask for
        return {"records": rows[offset: offset + limit], "total": len(rows)}

    monkeypatch.setattr(ag, "_ogd_get", fake_get)
    rows_got, used, total = ag._ogd_pull("x", "k", [{"state": "AP"}, {"State": "AP"}])
    assert used == {"State": "AP"} and len(rows_got) == 25 and total == 25
    out = ag.map_columns(pd.DataFrame(rows_got))
    assert out.loc[0, "modal"] == 1500 and out.loc[0, "date"] == pd.Timestamp("2026-10-01")


def test_build_extra_prices_only():
    from datetime import date as d_
    from pipeline.extra import build_extra
    raw = pd.DataFrame({"state": "Andhra Pradesh", "district": "Guntur", "market_raw": ["Guntur APMC"] * 3 + ["DIVI (HQ-AVANIGADDA APMC)"],
                        "commodity_raw": ["Dry Chillies", "Dry Chillies", "Dry Chillies", "Dry Chillies"],
                        "variety": ["Teja", "334", "Teja", "Teja"], "grade": "FAQ",
                        "date": pd.to_datetime(["2026-11-26", "2026-11-27", "2026-11-27", "2026-11-27"]),
                        "min": [20000, 18000, 0, 15000], "max": [27000, 24000, 26000, 17000], "modal": [25000, 21000, 25500, 16000],
                        "arrivals_t": None, "price_unit": "quintal", "source": "AGMARKNET"})
    cat = {"extra_crops": [{"id": "dry_chillies", "en": "Dry chillies", "te": "ఎండు మిర్చి", "group": "spice", "agmarknet": ["Dry Chillies"]}],
           "places": [{"id": "guntur", "en": "Guntur", "te": "గుంటూరు", "aliases": []}]}
    out = build_extra(raw, cat, d_(2026, 11, 27))
    crop = out["crops"][0]
    assert crop["n_markets"] == 2
    g = next(m for m in crop["markets"] if m["market"] == "Guntur")
    assert g["te"] == "గుంటూరు" and g["modal"] == 23250 and g["min"] == 18000 and set(g["varieties"]) == {"Teja", "334"}
    assert any(m["market"] == "Divi (Hq-Avanigadda)" for m in crop["markets"])
