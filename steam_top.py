import os
import sys
import time

import requests

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"].strip()
ID_FILE = "message_id.txt"
SHOW = 10  # how many games to display
HEADERS = {"User-Agent": "steam-top-games-bot/1.0"}


def get_top_appids(n=25):
    url = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    ranks = r.json()["response"]["ranks"]
    return [item["appid"] for item in ranks[:n]]


def get_current_players(appid):
    url = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
    r = requests.get(url, params={"appid": appid}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["response"].get("player_count", 0)


def get_names(appids):
    import json

    payload = {
        "ids": [{"appid": a} for a in appids],
        "context": {"language": "english", "country_code": "US"},
        "data_request": {},
    }
    url = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
    r = requests.get(url, params={"input_json": json.dumps(payload)}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json()["response"].get("store_items", [])
    return {i["appid"]: i.get("name", f"App {i['appid']}") for i in items}


def build_message():
    appids = get_top_appids()
    counts = {}
    for a in appids:
        try:
            counts[a] = get_current_players(a)
        except Exception as e:
            print(f"player count failed for {a}: {e}", file=sys.stderr)
        time.sleep(0.2)

    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:SHOW]
    names = get_names([a for a, _ in top])

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for i, (appid, players) in enumerate(top, start=1):
        name = names.get(appid, f"App {appid}")
        label = medals.get(i, f"**{i}.**")
        lines.append(f"{label} [{name}](https://store.steampowered.com/app/{appid}) — {players:,} playing")

    embed = {
        "title": "🎮 Top Games on Steam Right Now",
        "description": "\n".join(lines),
        "color": 0x1B2838,
        "footer": {"text": "Live player counts from Steam • updates every ~15 min"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return {"embeds": [embed]}


def main():
    body = build_message()

    message_id = None
    if os.path.exists(ID_FILE):
        message_id = open(ID_FILE).read().strip() or None

    if message_id:
        r = requests.patch(f"{WEBHOOK}/messages/{message_id}", json=body, headers=HEADERS, timeout=30)
        if r.status_code == 404:  # message was deleted, post a new one
            message_id = None
        else:
            r.raise_for_status()
            print("Edited existing message")
            return

    r = requests.post(WEBHOOK, params={"wait": "true"}, json=body, headers=HEADERS, timeout=30)
    r.raise_for_status()
    with open(ID_FILE, "w") as f:
        f.write(r.json()["id"])
    print("Posted new message")


if __name__ == "__main__":
    main()
