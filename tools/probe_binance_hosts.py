#!/usr/bin/env python3
"""Prueba qué hosts de Binance responden desde esta IP (una llamada de velas por host)."""
import requests

HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://data-api.binance.vision",
]
UA = {"User-Agent": "elt-taller-probe/0.1"}


def main():
    print("=== BINANCE: HOSTS ALTERNATIVOS ===")
    for host in HOSTS:
        try:
            r = requests.get(
                f"{host}/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": "1h", "limit": 3},
                headers=UA,
                timeout=15,
            )
            if r.status_code == 200:
                rows = r.json()
                detail = f"{len(rows)} velas, ultima open_time={rows[-1][0]}"
            else:
                detail = r.text[:80].replace("\n", " ")
            print(f"{host:34} HTTP {r.status_code}  {detail}")
        except requests.RequestException as e:
            print(f"{host:34} ERROR {str(e)[:80]}")


if __name__ == "__main__":
    main()
