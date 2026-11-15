"""Pull cancer/screening indicators from THL Sotkanet for all wellbeing services counties.
Data: CC BY 4.0, credit "Sotkanet / THL, https://sotkanet.fi". The API is for non-regular queries,
so run once and cache the results in data/.

Usage:
  python ingest/sotkanet.py search syöpä        # list indicator ids whose title matches
  python ingest/sotkanet.py fetch 1234 5678     # download those ids for 2015-2025 -> data/sotkanet_<id>.csv
NOTE: Run this on a machine with internet access; sotkanet.fi must be reachable.
"""
import io
import sys

import pandas as pd
import requests

BASE = "https://sotkanet.fi/rest/1.1"


def search(term: str):
    inds = requests.get(f"{BASE}/indicators", timeout=60).json()
    hits = [(i["id"], i["title"].get("fi") or i["title"].get("en")) for i in inds
            if term.lower() in str(i.get("title", "")).lower()]
    for h in hits:
        print(*h, sep="\t")
    return hits


def regions():
    r = pd.DataFrame(requests.get(f"{BASE}/regions", timeout=60).json())
    r["name"] = r["title"].apply(lambda t: t.get("fi"))
    return r[["id", "category", "code", "name"]]


def fetch(indicator: int, years=range(2015, 2026)):
    params = [("indicator", indicator)] + [("years", y) for y in years] + [("genders", "total")]
    resp = requests.get(f"{BASE}/csv", params=params, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), sep=";")
    reg = regions()
    df = df.merge(reg, left_on="region", right_on="id", how="left")
    df = df[df.category.isin(["HYVINVOINTIALUE", "MAA"])]
    df["source_url"] = f"https://sotkanet.fi/sotkanet/fi/taulukko?indicator={indicator}"
    out = f"data/sotkanet_{indicator}.csv"
    df.to_csv(out, index=False)
    print("wrote", out, len(df), "rows")
    return df


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["search", "seulon"]
    if cmd == "search":
        search(" ".join(args))
    elif cmd == "fetch":
        for a in args:
            fetch(int(a))
