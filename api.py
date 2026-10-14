import requests

_HEADERS = {"User-Agent": "SteamTrackerApp/1.0 (student-project)"}


def steam_search(term):
    """Searches the Steam store by game name."""
    response = requests.get(
        "https://store.steampowered.com/api/storesearch/",
        params={"term": term, "cc": "tr", "l": "english"},
        headers=_HEADERS, timeout=10)
    return response.json().get("items", [])


def steam_details(appid):
    """Fetches a game's details (developer, genre, price…)."""
    response = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": appid, "cc": "tr"},
        headers=_HEADERS, timeout=10)
    data = response.json()
    key = str(appid)
    if data and key in data and data[key]["success"]:
        return data[key]["data"]
    return None


def steam_player_count(appid):
    """Returns the game's current number of players."""
    response = requests.get(
        "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
        params={"appid": appid},
        headers=_HEADERS, timeout=10)
    return response.json()["response"]["player_count"]


def itad_game_id(api_key, appid):
    """Returns the IsThereAnyDeal game UUID for a Steam AppID."""
    response = requests.get(
        "https://api.isthereanydeal.com/games/lookup/v1",
        params={"key": api_key, "appid": str(appid)},
        headers=_HEADERS, timeout=10)
    response.raise_for_status()
    game = response.json().get("game")
    return game["id"] if game else None


def itad_price_info(api_key, appid):
    """Fetches the current Steam price in TRY and the historical lows from ITAD.

    Returns:
    {
        "current":  float (₺),
        "regular":  float (₺),
        "discount": int (%),
        "lows":     {"all_time": float, "one_year": float, "three_months": float}
    }
    or None (game not on ITAD, or not listed on Steam).
    """
    game_id = itad_game_id(api_key, appid)
    if not game_id:
        return None

    response = requests.post(
        "https://api.isthereanydeal.com/games/prices/v3",
        params={"key": api_key, "country": "TR"},
        json=[game_id], timeout=20)
    response.raise_for_status()

    results = response.json()
    if not results:
        return None

    data = results[0]
    # Steam's shop ID on ITAD is 61
    steam = next((d for d in data.get("deals", []) if d["shop"]["id"] == 61), None)

    lows = data.get("historyLow", {})
    return {
        "current":  steam["price"]["amount"]   if steam else None,
        "regular":  steam["regular"]["amount"] if steam else None,
        "discount": steam["cut"]               if steam else 0,
        "lows": {
            "all_time":     lows.get("all", {}).get("amount"),
            "one_year":     lows.get("y1",  {}).get("amount"),
            "three_months": lows.get("m3",  {}).get("amount"),
        },
    }


def steamcharts_history(appid):
    """Fetches the monthly average player history from SteamCharts.
    Format: [[timestamp_ms, avg_players], ...]
    """
    response = requests.get(
        f"https://steamcharts.com/app/{appid}/chart-data.json",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://steamcharts.com/app/{appid}",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=20)
    response.raise_for_status()
    return response.json()


def usd_to_try_rate():
    """Current USD → TRY exchange rate from the Frankfurter API."""
    response = requests.get(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": "TRY"},
        timeout=10)
    return response.json()["rates"]["TRY"]


if __name__ == "__main__":
    # Quick manual check: a game's Steam price converted from dollars to lira
    details = steam_details(1237950)  # Star Wars Battlefront II
    price_usd = details["price_overview"]["final"] / 100
    rate = usd_to_try_rate()
    price_try = round(price_usd * rate, 2)
    print(f"Price in USD: ${price_usd}")
    print(f"Rate: {rate}")
    print(f"Price in TRY: {price_try} ₺")
