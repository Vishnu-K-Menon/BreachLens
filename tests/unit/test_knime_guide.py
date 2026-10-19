"""The numbers in docs/KNIME_GUIDE.md, recomputed with pandas on the same file.

Each step mirrors one KNIME node. If the corpus is regenerated and a number changes,
this test fails and the guide must be updated. Skipped when the corpus is absent.
"""

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PAYROLL = ROOT / "data/raw/corpus_v1/docs/sheets/payroll_export.csv"
GUIDE = ROOT / "docs/KNIME_GUIDE.md"
DEPT = {
    "#N/A": "UNKNOWN",
    "OPS": "Operations",
    "SLS": "Sales",
    "FIN": "Finance",
    "IT": "IT",
    "CS": "Customer Service",
    "WHS": "Warehouse",
}

pytestmark = pytest.mark.skipif(not PAYROLL.is_file(), reason="corpus_v1 not generated")


@pytest.fixture(scope="module")
def nodes() -> dict:
    out = {}
    raw = PAYROLL.read_bytes()
    out["latin1_is_cp1252"] = raw.decode("latin-1") == raw.decode("cp1252")
    # 1 CSV Reader: skip 1 line, ';', ISO-8859-1, '#N/A' stays text, bank columns excluded
    df = pd.read_csv(
        PAYROLL, sep=";", encoding="latin-1", skiprows=1, dtype=str, keep_default_na=False
    ).drop(columns=["Bank Routing", "Account No"])
    out["reader"] = df.shape
    # 3-4 side branch: SSN -> digit count -> GroupBy
    out["digits"] = df["SS#"].str.len().value_counts().to_dict()
    out["short_employees"] = df.loc[df["SS#"].str.len() == 8, "Emp No"].nunique()
    # 2 padLeft(9, "0") then mask
    df["SS#"] = df["SS#"].map(lambda s: "***-**-" + s.zfill(9)[5:9])
    out["masked_head"] = df["SS#"].head(3).tolist()
    # 5-7 rename, names
    df = df.rename(columns={"Employee Name": "employee_name", "SS#": "ssn_masked"})
    name = df["employee_name"]
    df["last_name"] = name.map(lambda s: s[: s.index(",")].strip().upper())
    df["given_names"] = name.map(lambda s: s[s.index(",") + 1 :].strip().upper())
    out["names_head"] = df[["last_name", "given_names"]].head(3).values.tolist()
    # 8 Rule Engine
    df["dept"] = df["Dept"].map(lambda d: DEPT.get(d, d))
    out["dept"] = df["dept"].value_counts().to_dict()
    # 9 String to Date&Time, 10 Duplicate Row Filter (max pay_date)
    df["pay_date"] = pd.to_datetime(df["Pay Date"], format="%m/%d/%Y")
    out["unknown_by_date"] = (
        df[df["dept"] == "UNKNOWN"]["pay_date"].dt.strftime("%m/%d").value_counts().to_dict()
    )
    dd = df.sort_values("pay_date").drop_duplicates("Emp No", keep="last").sort_index()
    out["dedupe"] = len(dd)
    out["dedupe_dates"] = dd["pay_date"].dt.date.astype(str).unique().tolist()
    # 11 SSN check, 12 review list, 13 GroupBy by state
    out["ssn_digit_runs"] = int(dd["ssn_masked"].str.contains(r"[0-9]{5,}").sum())
    out["review"] = sorted(dd.loc[dd["dept"] == "UNKNOWN", "Emp No"].tolist())
    g = dd.assign(gross=dd["Gross Pay"].str.replace(",", ".").astype(float)).groupby("State")
    out["by_state"] = {
        st: (int(n), round(float(s), 2))
        for st, n, s in zip(g.size().index, g.size(), g["gross"].sum(), strict=True)
    }
    out["nj_zips"] = dd.loc[dd["State"] == "NJ", "Zip"].tolist()
    return out


def test_guide_numbers(nodes):
    assert nodes["latin1_is_cp1252"]
    assert nodes["reader"] == (80, 11)
    assert nodes["digits"] == {9: 72, 8: 8} and nodes["short_employees"] == 4
    assert nodes["masked_head"] == ["***-**-2648", "***-**-3751", "***-**-2089"]
    assert nodes["names_head"] == [["FOWLER", "EDWIN"], ["GRAY", "ANTHONY"], ["HERNANDEZ", "LEE K"]]
    assert nodes["dept"] == {
        "IT": 15,
        "Customer Service": 15,
        "Operations": 14,
        "Warehouse": 12,
        "Sales": 10,
        "Finance": 8,
        "UNKNOWN": 6,
    }
    assert nodes["unknown_by_date"] == {"09/15": 4, "09/30": 2}
    assert nodes["dedupe"] == 40 and nodes["dedupe_dates"] == ["2026-09-30"]
    assert nodes["ssn_digit_runs"] == 0
    assert nodes["review"] == ["503447", "955744"]
    assert nodes["by_state"] == {
        "CA": (6, 27172.28),
        "FL": (6, 28516.22),
        "MA": (2, 7173.99),
        "NJ": (2, 10473.2),
        "NY": (6, 24132.46),
        "PA": (6, 27873.69),
        "TX": (6, 30774.03),
        "VA": (6, 25580.96),
    }
    assert nodes["nj_zips"] == ["07102", "08608"]


def test_guide_text_states_the_same_numbers():
    text = GUIDE.read_text(encoding="utf-8")
    for s in (
        "**80 rows × 11 columns**",
        "`9` → **72**, `8` → **8**",
        "`***-**-2648`",
        "**80 → 40 rows**",
        "**0 rows**",
        "**2 rows**: emp_no `503447`",
        "| CA | 6 | 27,172.28 |",
        "181,696.83",
        'padLeft($SS#$, 9, "0")',
    ):
        assert s in text, s
    assert "Python Script" not in text.replace("no Python Script", "")
