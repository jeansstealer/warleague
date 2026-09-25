"""War League ingest: store new top-50 snapshots and build data/league.json.

Run by the GitHub workflow after it downloads the tracker's league feed:
    python scripts/ingest.py feed.json

A snapshot is stored only when it is new (a later capture with identical
entries is ignored). Each snapshot is placed in a round from the season
calendar in data/calendar.json; the latest snapshot per round is compared with
the previous round's to build that round's report. Standard library only.
"""
import json
import os
import sys
from datetime import datetime, timezone

HOUR_MS = 3600 * 1000
DAY_MS = 24 * HOUR_MS
METALS = ["Iron", "Bronze", "Silver", "Gold", "Diamond"]
TIERS = ["I", "II", "III", "IV"]
FIELDS = ["rank", "guildId", "name", "tag", "trophies", "league", "guildLevel", "members", "country"]


# ---------------------------------------------------------------- calendar
def _ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def after_round(t, cal):
    """(season, rounds finished) at time t (ms). 0 = before war 1 ended; the
    14-day break after war 6 counts as 6. Seasons repeat every seasonDays."""
    anchor = _ms(cal["anchorStart"])
    length = cal["seasonDays"] * DAY_MS
    n = (t - anchor) // length
    start = anchor + n * length
    done = sum(1 for i in range(1, cal["warsPerSeason"] + 1)
               if start + (i - 1) * cal["warGapHours"] * HOUR_MS + cal["warHours"] * HOUR_MS <= t)
    return cal["anchorSeason"] + n, done


def league_name(n):
    n = int(n)
    return "Diamond I" if n >= 16 else METALS[n // 4] + " " + TIERS[n % 4]


# ---------------------------------------------------------------- diff
def _key(e):
    return e.get("guildId") or ("name:" + e.get("name", ""))


def diff(prev, cur):
    """What changed between two top-50 snapshots (lists of entries)."""
    before = {_key(e): e for e in prev}
    keys_now = {_key(e) for e in cur}
    table = []
    for e in sorted(cur, key=lambda x: x["rank"]):
        p = before.get(_key(e))
        row = {k: e.get(k) for k in FIELDS}
        row.update({
            "isNew": p is None,
            "dT": None if p is None else e["trophies"] - p["trophies"],
            "dR": None if p is None else p["rank"] - e["rank"],
            "prevLeague": None if p is None else p["league"],
            "prevName": p["name"] if p is not None and p["name"] != e["name"] else None,
        })
        table.append(row)
    won = sorted((r for r in table if (r["dT"] or 0) > 0), key=lambda r: -r["dT"])
    lost = sorted((r for r in table if (r["dT"] or 0) < 0), key=lambda r: r["dT"])
    promoted = [r for r in table if r["prevLeague"] is not None and r["league"] > r["prevLeague"]]
    demoted = [r for r in table if r["prevLeague"] is not None and r["league"] < r["prevLeague"]]
    entered = [r for r in table if r["isNew"]]
    left = [{k: e.get(k) for k in FIELDS} for e in sorted(prev, key=lambda x: x["rank"]) if _key(e) not in keys_now]
    moved = [r for r in table if r["dR"]]
    out = {
        "table": table, "won": won, "lost": lost,
        "idleCount": sum(1 for r in table if r["dT"] == 0),
        "promoted": promoted, "demoted": demoted, "entered": entered, "left": left,
        "climbers": sorted((r for r in moved if r["dR"] > 0), key=lambda r: -r["dR"])[:5],
        "fallers": sorted((r for r in moved if r["dR"] < 0), key=lambda r: r["dR"])[:5],
    }
    out["summary"] = summary(out)
    out["stats"] = {"won": len(won), "lost": len(lost), "promoted": len(promoted), "demoted": len(demoted),
                    "entered": len(entered), "left": len(left)}
    return out


def _names(rows, limit=3):
    names = [r["name"] for r in rows]
    if len(names) <= limit:
        return names
    return names[:limit] + ["%d more" % (len(names) - limit)]


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def summary(r, covers=None):
    """Sentence parts [{"t": text, "b": bold}] in the style of the Discord round posts.
    Always says "top 50": guilds outside it can't be seen."""
    s = []
    t = lambda text: s.append({"t": text, "b": False})
    b = lambda text: s.append({"t": text, "b": True})
    if covers:
        t("Across rounds %d–%d, " % tuple(covers))
    t("%d of the top 50 won their war" % len(r["won"]) if r["won"] else "No top-50 guild won")
    if not r["lost"]:
        t(" and no top-50 guild lost.")
    else:
        t(" and only 1 guild lost (" if len(r["lost"]) == 1 else " and %d guilds lost (" % len(r["lost"]))
        b(_join(_names(r["lost"])))
        t(").")
    for rows, verb in ((r["promoted"], "climbed into"), (r["demoted"], "dropped to")):
        if rows:
            t(" ")
            b(_join(_names(rows)))
            leagues = {row["league"] for row in rows}
            t(" %s %s." % (verb, league_name(rows[0]["league"])) if len(leagues) == 1
              else (" were promoted." if verb == "climbed into" else " were demoted."))
    if r["entered"]:
        t(" New in the top 50: ")
        b(_join(_names(r["entered"])))
        t(".")
    if r["left"]:
        t(" Left the top 50: " + _join(_names(r["left"])) + ".")
    # Guild names can end in their own punctuation ("… !"): don't add a second mark.
    for i in range(1, len(s)):
        if s[i]["t"].startswith(".") and s[i - 1]["t"].rstrip()[-1:] in ("!", "?", "."):
            s[i]["t"] = s[i]["t"][1:]
    for p in s:
        p["t"] = p["t"].replace("!.", "!").replace("?.", "?")
    return s


# ---------------------------------------------------------------- storage
def _valid(feed):
    if not isinstance(feed, dict) or feed.get("status") != "ok":
        return None
    snap = feed.get("snapshot")
    if not isinstance(snap, dict) or not isinstance(snap.get("capturedAt"), int) or snap["capturedAt"] <= 0:
        return None
    entries = snap.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
        return None
    clean = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str):
            return None
        if not all(isinstance(e.get(k), int) for k in ("rank", "trophies", "league")):
            return None
        clean.append({k: e.get(k, "" if k in ("guildId", "name", "tag", "country") else 0) for k in FIELDS})
    return {"capturedAt": snap["capturedAt"], "entries": clean}


def _snap_dir(root):
    return os.path.join(root, "data", "snapshots")


def load_snapshots(root):
    d = _snap_dir(root)
    snaps = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                snaps.append(json.load(fh))
    return sorted(snaps, key=lambda s: s["capturedAt"])


def ingest(feed, root):
    """Store the feed's snapshot if it's new; rebuild league.json. Returns True if stored."""
    snap = _valid(feed)
    if snap is None:
        return False
    existing = load_snapshots(root)
    if any(s["capturedAt"] == snap["capturedAt"] for s in existing):
        return False
    if existing and existing[-1]["entries"] == snap["entries"]:
        return False  # nothing changed since the last capture
    os.makedirs(_snap_dir(root), exist_ok=True)
    name = datetime.fromtimestamp(snap["capturedAt"] / 1000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(os.path.join(_snap_dir(root), name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=1)
    build(root)
    return True


def build(root):
    """data/league.json: one report per (season, round), newest capture per round."""
    with open(os.path.join(root, "data", "calendar.json"), encoding="utf-8") as fh:
        cal = json.load(fh)
    per_round = {}
    for s in load_snapshots(root):
        per_round[after_round(s["capturedAt"], cal)] = s  # later capture wins
    keys = sorted(per_round)
    reports, history, seasons = {}, {}, {}
    for i, key in enumerate(keys):
        snap = per_round[key]
        season, rnd = key
        seasons.setdefault(season, []).append(rnd)
        prev_key = keys[i - 1] if i else None
        if prev_key:
            r = diff(per_round[prev_key]["entries"], snap["entries"])
            covers = None
            if prev_key[0] == season and prev_key[1] < rnd - 1:
                covers = [prev_key[1] + 1, rnd]
            elif prev_key[0] != season and rnd > 1:
                covers = [1, rnd]
            r["summary"] = summary(r, covers)
            r.update({"comparedWith": {"season": prev_key[0], "round": prev_key[1]}, "covers": covers})
        else:
            r = diff(snap["entries"], snap["entries"])
            for k in ("won", "lost", "promoted", "demoted", "entered", "left", "climbers", "fallers"):
                r[k] = []
            for row in r["table"]:
                row.update({"dT": None, "dR": None, "prevLeague": None})
            r["idleCount"] = 0
            r["stats"] = {k: 0 for k in r["stats"]}
            r["summary"] = [{"t": "First capture: the top 50 as it stands. Changes appear after the next round.", "b": False}]
            r.update({"comparedWith": None, "covers": None})
        r.update({"season": season, "round": rnd, "capturedAt": snap["capturedAt"]})
        reports["%d-%d" % key] = r
        for e in snap["entries"]:
            history.setdefault(_key(e), []).append(
                {"season": season, "round": rnd, "rank": e["rank"], "trophies": e["trophies"], "league": e["league"]})
    out = {
        "generatedAt": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "latest": "%d-%d" % keys[-1] if keys else None,
        "seasons": [{"season": s, "rounds": r} for s, r in sorted(seasons.items())],
        "reports": reports,
        "history": history,
    }
    with open(os.path.join(root, "data", "league.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    return out


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(argv[1], encoding="utf-8") as fh:
            feed = json.load(fh)
    except (IndexError, OSError, ValueError) as err:
        print("No usable feed:", err)
        feed = None
    stored = feed is not None and ingest(feed, root)
    if not os.path.exists(os.path.join(root, "data", "league.json")):
        build(root)
    print("New snapshot stored." if stored else "No new snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
