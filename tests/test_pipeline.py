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
    rows.append(["Andhra Pradesh", "Kurnool", "KARNOOL", "ONION", "Big", days[5], 1500, 2500, 2000, 300.0, "quintal", "X"])  # duplicate
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
