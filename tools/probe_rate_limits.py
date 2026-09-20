#!/usr/bin/env python3
"""
Sonda de rate limits: Binance, OKX y Coinbase (velas horarias de BTC).

Pagina hacia atras igual que el backfill (5.3) y sube el ritmo de a poco:
1, 2, 4 y 8 req/s, 6 segundos por escalon (~90 llamadas por exchange).
Se DETIENE en la primera senal de throttling o bloqueo. No insiste: en
Binance seguir despues de un 429 escala a 418 (ban temporal de IP).

Uso:  pip install requests && python tools/probe_rate_limits.py
"""
import json
import time
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "elt-taller-probe/0.1"}  # Coinbase exige User-Agent
HOUR_MS = 3_600_000
SECONDS_PER_LEVEL = 6
LEVELS = (1, 2, 4, 8)  # req/s objetivo
CB_WINDOW_H = 290  # margen bajo el tope de ~300 velas por llamada
BACKFILL_CALLS = {"binance": 79, "coinbase": 314, "okx": 763}  # segun el doc (5.3)
HEADER_HINTS = ("limit", "weight", "retry", "remaining")
BINANCE_BASE = "https://data-api.binance.vision"  # api.binance.com da 451 desde Actions

def now_ms():
    return int(time.time() * 1000)


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- una funcion por exchange: recibe el cursor (ms) y devuelve la respuesta ---
def fetch_binance(cursor):
    return requests.get(
        f"{BINANCE_BASE}/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 1000, "endTime": cursor},
        headers=UA, timeout=15,
    )


def fetch_okx(cursor):
    return requests.get(
        "https://www.okx.com/api/v5/market/history-candles",
        params={"instId": "BTC-USDT", "bar": "1H", "limit": 100, "after": cursor},
        headers=UA, timeout=15,
    )


def fetch_coinbase(cursor):
    return requests.get(
        "https://api.exchange.coinbase.com/products/BTC-USD/candles",
        params={
            "granularity": 3600,
            "start": iso(cursor - CB_WINDOW_H * HOUR_MS),
            "end": iso(cursor),
        },
        headers=UA, timeout=15,
    )


def parse(name, r, cursor):
    """Devuelve (estado, cantidad_de_velas, cursor_siguiente)."""
    if r.status_code in (429, 418):
        return "THROTTLED", 0, cursor
    if r.status_code in (403, 451):
        return "BLOCKED", 0, cursor  # geo/IP bloqueada, o WAF
    if r.status_code != 200:
        return f"HTTP_{r.status_code}", 0, cursor
    body = r.json()
    if name == "okx":
        code = body.get("code")
        if code == "50011":  # Too Many Requests
            return "THROTTLED", 0, cursor
        if code != "0":
            return f"OKX_{code}", 0, cursor
        rows = body["data"]
        return "OK", len(rows), (min(int(x[0]) for x in rows) if rows else cursor)
    if not isinstance(body, list):
        return "BAD_BODY", 0, cursor
    if name == "binance":
        return "OK", len(body), (min(int(x[0]) for x in body) - 1 if body else cursor)
    return "OK", len(body), cursor - CB_WINDOW_H * HOUR_MS  # coinbase


def run_exchange(name, fetch):
    print(f"\n=== {name.upper()} ===")
    res = {"exchange": name, "verdict": "OK", "page_size": 0, "levels": [], "rate_headers": {}}
    cursor = now_ms()
    for target in LEVELS:
        n_calls = target * SECONDS_PER_LEVEL
        t_start = time.time()
        for i in range(n_calls):
            wait = t_start + i / target - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                r = fetch(cursor)
            except requests.RequestException as e:
                res["verdict"] = "ERROR"
                res["stop_at"] = {"target_rps": target, "call": i + 1, "error": str(e)[:200]}
                print(f"  ERROR de red en {target} req/s, llamada {i + 1}: {e}")
                return res
            state, n, cursor = parse(name, r, cursor)
            for k, v in r.headers.items():
                if any(h in k.lower() for h in HEADER_HINTS):
                    res["rate_headers"][k] = v
            if state != "OK":
                res["verdict"] = state
                res["stop_at"] = {
                    "target_rps": target,
                    "call": i + 1,
                    "http": r.status_code,
                    "retry_after": r.headers.get("Retry-After"),
                    "body": r.text[:200],
                }
                print(f"  {state} a {target} req/s (llamada {i + 1}): HTTP {r.status_code}, "
                      f"Retry-After={r.headers.get('Retry-After')}")
                return res
            res["page_size"] = max(res["page_size"], n)
        achieved = n_calls / (time.time() - t_start)
        res["levels"].append({"target_rps": target, "achieved_rps": round(achieved, 2)})
        print(f"  {target} req/s objetivo -> {achieved:.2f} logrado, sin throttling")
    return res


def main():
    exchanges = [("binance", fetch_binance), ("okx", fetch_okx), ("coinbase", fetch_coinbase)]
    results = []
    for name, fetch in exchanges:
        results.append(run_exchange(name, fetch))
        time.sleep(2)

    print("\n=== RESUMEN ===")
    for res in results:
        clean = res["levels"][-1]["achieved_rps"] if res["levels"] else 0.0
        res["max_clean_rps"] = clean
        if clean:
            minutes = BACKFILL_CALLS[res["exchange"]] / (clean * 0.5) / 60
            res["backfill_minutes_at_50pct"] = round(minutes, 1)
        print(f"{res['exchange']:9} veredicto={res['verdict']:10} "
              f"velas/llamada={res['page_size']:5} "
              f"ritmo limpio max={clean} req/s "
              f"backfill al 50%: {res.get('backfill_minutes_at_50pct', 'n/d')} min")
    print("\n--- JSON (copialo tal cual) ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
