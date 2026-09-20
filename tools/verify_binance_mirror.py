#!/usr/bin/env python3
"""
Compara velas horarias de api.binance.com vs data-api.binance.vision.
Correr desde tu maquina (api.binance.com esta bloqueada en GitHub Actions).

Uso:  python tools/verify_binance_mirror.py
"""
import time

import requests

A = "https://api.binance.com"
B = "https://data-api.binance.vision"
UA = {"User-Agent": "elt-taller-probe/0.1"}


def klines(host, **params):
    p = {"symbol": "BTCUSDT", "interval": "1h", **params}
    r = requests.get(f"{host}/api/v3/klines", params=p, headers=UA, timeout=20)
    r.raise_for_status()
    return r.json()


def ts(ms):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


def compare(label, **params):
    a, b = klines(A, **params), klines(B, **params)
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    estado = "PASS" if a == b else "FAIL"
    print(f"[{estado}] {label}: {len(a)} vs {len(b)} velas, filas distintas={diffs}")
    return a, b


def main():
    a, b = compare("Primera vela de la serie (startTime=0)", startTime=0, limit=1)
    if a and b:
        print(f"   api.binance.com -> {ts(a[0][0])} | data-api -> {ts(b[0][0])}")

    compare("1000 velas hasta 2020-01-01", endTime=1577836800000, limit=1000)

    # Ultima hora ya cerrada (evita comparar la vela en curso)
    cur = int(time.time() // 3600 * 3600 * 1000) - 1
    compare("1000 velas cerradas mas recientes", endTime=cur, limit=1000)

    row = klines(B, endTime=cur, limit=1)[0]
    print(f"\nEstructura en data-api: {len(row)} campos (esperado 12)")
    print(row)


if __name__ == "__main__":
    main()
