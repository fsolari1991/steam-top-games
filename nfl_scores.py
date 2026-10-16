import json
import os
from datetime import datetime

import requests

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
FAVORITES = {"PHI", "GB", "MIA"}  # Eagles, Packers, Dolphins
ID_FILE = "nfl_message_id.txt"
STATE_FILE = "nfl_state.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", "Accept": "application/json"}


def parse_game(event):
    comp = event["competitions"][0]
    status = event["status"]["type"]
    teams = {}
    for c in comp["competitors"]:
        abbr = c["team"]["abbreviation"]
        teams[c["homeAway"]] = {
            "abbr": abbr,
            "name": c["team"].get("shortDisplayName", abbr),
            "score": int(c.get("score") or 0),
        }
    kickoff = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    return {
        "id": str(event["id"]),
        "state": status["state"],  # pre / in / post
        "detail": status.get("shortDetail", ""),
        "ts": int(kickoff.timestamp()),
        "home": teams["home"],
        "away": teams["away"],
        "fav": bool({teams["home"]["abbr"], teams["away"]["abbr"]} & FAVORITES),
    }


def side(team, bold):
    text = f"{team['abbr']} {team['score']}"
    return f"**{text}**" if bold else text


def format_line(g):
    star = "⭐ " if g["fav"] else ""
    a, h = g["away"], g["home"]
    if g["state"] == "pre":
        return f"{star}🕐 {a['abbr']} @ {h['abbr']} — <t:{g['ts']}:f>"
    icon = "🔴" if g["state"] == "in" else "✅"
    a_lead = a["score"] > h["score"]
    h_lead = h["score"] > a["score"]
    return f"{star}{icon} {side(a, a_lead)} @ {side(h, h_lead)} — {g['detail']}"


def build_embed(games, week):
    ordered = sorted(games, key=lambda g: (not g["fav"], g["ts"]))
    lines = [format_line(g) for g in ordered] or ["No games found."]
    title = "🏈 NFL Scoreboard"
    if week:
        title += f" — Week {week}"
    return {
        "title": title,
        "description": "\n".join(lines),
        "color": 0x013369,
        "footer": {"text": "⭐ = our teams • 🔴 live • ✅ final • updates every few minutes"},
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def build_alerts(games, old_state):
    """Messages for favorite-team kickoffs and finals. old_state None = first run."""
    if old_state is None:
        return []
    out = []
    for g in games:
        if not g["fav"]:
            continue
        prev = old_state.get(g["id"])
        if prev is None:
            continue
        a, h = g["away"], g["home"]
        if g["state"] == "in" and prev != "in" and prev != "post":
            out.append(f"🏈 **KICKOFF!** ⭐ {a['name']} @ {h['name']} is underway.")
        elif g["state"] == "post" and prev != "post":
            if a["score"] == h["score"]:
                result = "It ended in a tie."
            else:
                w = a if a["score"] > h["score"] else h
                result = f"**{w['name']}** win!"
            out.append(
                f"🏁 **FINAL:** ⭐ {a['name']} {a['score']}, {h['name']} {h['score']} — {result}"
            )
    return out


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def main():
    webhook = os.environ["DISCORD_NFL_WEBHOOK_URL"].strip()

    r = requests.get(SCOREBOARD, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    games = [parse_game(e) for e in data.get("events", [])]
    week = (data.get("week") or {}).get("number")

    body = {"embeds": [build_embed(games, week)]}

    # 1) update (or create) the self-editing scoreboard message
    message_id = None
    if os.path.exists(ID_FILE):
        message_id = open(ID_FILE).read().strip() or None

    edited = False
    if message_id:
        p = requests.patch(f"{webhook}/messages/{message_id}", json=body, headers=HEADERS, timeout=30)
        if p.status_code != 404:
            p.raise_for_status()
            edited = True
    if not edited:
        p = requests.post(webhook, params={"wait": "true"}, json=body, headers=HEADERS, timeout=30)
        p.raise_for_status()
        with open(ID_FILE, "w") as f:
            f.write(p.json()["id"])
        print("Posted new scoreboard message")
    else:
        print("Edited scoreboard message")

    # 2) kickoff / final alerts for favorite teams
    old_state = load_state()
    for text in build_alerts(games, old_state):
        a = requests.post(webhook, json={"content": text}, headers=HEADERS, timeout=30)
        a.raise_for_status()
        print("Alert:", text)

    # 3) remember game states for next run
    with open(STATE_FILE, "w") as f:
        json.dump({g["id"]: g["state"] for g in games}, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
