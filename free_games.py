import json
import os
import time
from datetime import datetime, timezone

import requests

API = "https://www.gamerpower.com/api/giveaways"
STATE_FILE = "free_games_seen.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
FIRST_RUN_LIMIT = 8   # how many current deals to post the very first time
PER_RUN_LIMIT = 5     # safety cap on posts per run
KEEP_IDS = 300        # how many seen IDs to remember


def fetch_giveaways():
    r = requests.get(
        API,
        params={"platform": "pc", "type": "game", "sort-by": "date"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        return []
    # When nothing matches, the API returns an object instead of a list
    if not isinstance(data, list):
        return []
    return [g for g in data if g.get("status", "Active") == "Active"]


def to_unix(text):
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError):
        return None


def build_embed(g):
    worth = g.get("worth") or "N/A"
    price_line = f"~~{worth}~~ **FREE**" if worth not in ("N/A", "", None) else "**FREE**"
    lines = [
        price_line,
        f"🖥️ {g.get('platforms', 'PC')}",
    ]
    end = to_unix(g.get("end_date"))
    if end:
        lines.append(f"⏰ Ends <t:{end}:R>")
    instructions = (g.get("instructions") or "").strip()
    if instructions:
        lines.append("")
        lines.append(instructions[:400])

    embed = {
        "title": f"🎁 {g.get('title', 'Free game')}",
        "url": g.get("open_giveaway_url") or g.get("gamerpower_url"),
        "description": "\n".join(lines),
        "color": 0x2ECC71,
        "footer": {"text": "Free game alert • grab it before it's gone"},
    }
    if g.get("image"):
        embed["image"] = {"url": g["image"]}
    return embed


def load_seen():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(seen[-KEEP_IDS:], f)


def pick_new(giveaways, seen):
    """Return games to post, oldest first."""
    if seen is None:  # first run: seed the channel with the newest few
        chosen = giveaways[:FIRST_RUN_LIMIT]
    else:
        known = set(seen)
        chosen = [g for g in giveaways if g["id"] not in known][:PER_RUN_LIMIT]
    return list(reversed(chosen))  # newest ends up at the bottom


def main():
    webhook = os.environ["DISCORD_FREEGAMES_WEBHOOK_URL"].strip()

    giveaways = fetch_giveaways()
    seen = load_seen()
    to_post = pick_new(giveaways, seen)

    remembered = list(seen or [])
    # On first run, remember everything currently active so old deals never repost
    if seen is None:
        remembered = [g["id"] for g in reversed(giveaways)]

    try:
        for g in to_post:
            r = requests.post(webhook, json={"embeds": [build_embed(g)], "flags": 4096}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            if g["id"] not in remembered:
                remembered.append(g["id"])
            print("Posted:", g.get("title"))
            time.sleep(1.5)
    finally:
        save_seen(remembered)

    if not to_post:
        print("Nothing new")


if __name__ == "__main__":
    main()
