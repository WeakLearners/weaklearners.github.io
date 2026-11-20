#!/usr/bin/env python3
"""Refresh the Overwatch figures on index.html from the tracker database.

Usage:
  python3 tools/update_stats.py            rewrite the marked values and the as-of date
  python3 tools/update_stats.py --check    change nothing; exit 1 if the page differs from the DB

Exit codes: 0 ok, 1 page numbers differ (check) , 2 a conclusion sentence would
become false (nothing is written; a human must rewrite the text), 3 database missing.

Same queries and method as projects/overwatch-analysis/stats-snapshot.md in the vault:
competitive matches only, one-proportion z-test against the comp baseline,
Bonferroni over the groups actually tested (maps n>=30, hours n>=50).
Marks on the page: data-stat="KEY" spans, the STAT block in the script
(/* @stats:begin */ ... /* @stats:end */), and data-claim attributes.
"""
import datetime, math, os, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
DB = Path(os.environ.get("OW_DB", "~/Code/overwatch/data/overwatch.db")).expanduser()
COMP = "queue_mode IN ('comp_role','comp_open')"
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
LONG = ["January","February","March","April","May","June","July","August","September","October","November","December"]


def pval(k, n, p):
    z = (k / n - p) / math.sqrt(p * (1 - p) / n)
    return z, math.erfc(abs(z) / math.sqrt(2))


def compute():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n, w, first, last = c.execute(f"SELECT COUNT(*), SUM(win), MIN(date), MAX(date) FROM matches WHERE {COMP}").fetchone()
    p = w / n
    maps = {r[0]: (r[1], r[2]) for r in c.execute(f"SELECT map, COUNT(*), SUM(win) FROM matches WHERE {COMP} GROUP BY map HAVING COUNT(*)>=30")}
    hours = {int(r[0]): (r[1], r[2]) for r in c.execute(f"SELECT hour, COUNT(*), SUM(win) FROM matches WHERE {COMP} GROUP BY hour HAVING COUNT(*)>=50")}
    fy, fm = int(first[:4]), int(first[5:7]); ly, lm = int(last[:4]), int(last[5:7])
    today = datetime.date.today()
    gn, gw = maps["Watchpoint: Gibraltar"]
    hn, hw = hours[12]; tn, tw = hours[14]
    noon_p = pval(hw, hn, p)[1]
    fmt_p = (f"{noon_p:.2g}" if noon_p >= 0.0001 else "<0.0001")
    map_surv = [m for m, (a, b) in maps.items() if pval(b, a, p)[1] < 0.05 / len(maps)]
    hour_surv = [h for h, (a, b) in hours.items() if pval(b, a, p)[1] < 0.05 / len(hours)]
    stats = {
        "comp_matches": f"{n:,}", "comp_wins": f"{w:,}", "comp_losses": f"{n - w:,}",
        "comp_rate": f"{100 * p:.2f}", "comp_rate_1": f"{100 * p:.1f}",
        "months": str((ly - fy) * 12 + lm - fm),
        "range_end_mon": f"{MON[lm - 1]} {ly}",
        "asof_short": f"{MON[today.month - 1]} {today.day}, {today.year}",
        "asof_long": f"{LONG[today.month - 1]} {today.day}, {today.year}",
        "maps_tested": str(len(maps)),
        "gib_rate": f"{100 * gw / gn:.1f}", "gib_n": str(gn),
        "noon_rate": f"{100 * hw / hn:.1f}", "noon_n": str(hn), "noon_p": fmt_p,
        "hour14_rate": f"{100 * tw / tn:.1f}", "hour14_n": str(tn),
    }
    claims = {
        "gib_above_avg": gw / gn > p,
        "no_map_survives": not map_surv,
        "hour14_near_avg": abs(100 * tw / tn - 100 * p) <= 1.5,
        "noon_below_avg": hw / hn < p,
        "no_hour_survives": not hour_surv,
    }
    js = {"matches": n, "wins": w, "rate": f"{100 * p:.2f}"}
    return stats, claims, js, {"map_surv": map_surv, "hour_surv": hour_surv}


STAT_RE = r'(<(\w+)[^>]*\bdata-stat="%s"[^>]*>)(.*?)(</\2>)'
JS_RE = re.compile(r"(/\* @stats:begin[^\n]*\*/\nconst STAT = )\{[^}]*\}(;\n/\* @stats:end \*/)")


def main():
    check = "--check" in sys.argv
    if not DB.exists():
        print(f"database not found: {DB} (set OW_DB). Cannot check the numbers.")
        return 3
    stats, claims, js, extra = compute()
    html = PAGE.read_text()

    bad = []
    for m in re.finditer(r'data-claim(2?)="(\w+)" data-claim\1-value="(\w+)"', html):
        key, want = m.group(2), m.group(3) == "true"
        if claims[key] != want:
            bad.append(f"  claim {key}: page text assumes {want}, data now says {claims[key]}")
    if bad:
        print("A sentence on the page would become false. Nothing was changed. Rewrite the text, then update the data-claim values.")
        print("\n".join(bad))
        if extra["map_surv"]: print("  maps that survive correction:", extra["map_surv"])
        if extra["hour_surv"]: print("  hours that survive correction:", extra["hour_surv"])
        print("  current:", {k: stats[k] for k in ("gib_rate", "noon_rate", "noon_p", "hour14_rate", "comp_rate")})
        return 2

    changes, out = [], html
    for key, val in stats.items():
        found = False
        def rep(m):
            nonlocal found
            found = True
            if m.group(3) != val and not (check and key.startswith("asof")):
                changes.append(f"  {key}: {m.group(3)} -> {val}")
            return m.group(1) + (m.group(3) if check and key.startswith("asof") else val) + m.group(4)
        out = re.sub(STAT_RE % re.escape(key), rep, out, flags=re.S)
        if not found:
            print(f"marker data-stat=\"{key}\" not found on the page"); return 2
    m = JS_RE.search(out)
    if not m:
        print("STAT block not found in the script"); return 2
    new_js = "{matches: %d, wins: %d, rate: '%s'}" % (js["matches"], js["wins"], js["rate"])
    if f"{m.group(1)}{new_js}{m.group(2)}" != m.group(0):
        changes.append(f"  STAT block -> {new_js}")
        out = out[:m.start()] + m.group(1) + new_js + m.group(2) + out[m.end():]

    if check:
        if changes:
            print("index.html Overwatch numbers differ from the database:")
            print("\n".join(changes))
            print("Fix: python3 tools/update_stats.py   (then check the text, and commit)")
            return 1
        print("index.html numbers match the database.")
        return 0
    PAGE.write_text(out)
    print("updated:" if changes else "no change.")
    print("\n".join(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
