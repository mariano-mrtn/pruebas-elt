#!/usr/bin/env python3
"""
Monitor de estabilidad de data-api.binance.vision (ticket #2).

A diferencia de tools/probe_rate_limits.py (que mide cuanto aguanta el host
en una corrida corta y escalonada), este script hace UN solo chequeo por
ejecucion: pega una vez al endpoint real que va a usar el adaptador de
Binance, mide status HTTP + latencia, y APENDA una fila a un log CSV.

Esta pensado para correr disparado por un cron de GitHub Actions cada 1-2
horas durante 7 (o 14) dias. El log acumulado despues se analiza con
tools/analyze_binance_stability.py para decidir si el ticket se cierra.

Uso:
    python tools/monitor_binance_stability.py
    python tools/monitor_binance_stability.py --log-path docs/monitoring/binance_stability_log.csv
"""
import argparse
import csv
import os
import time
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "elt-taller-stability-monitor/0.1"}
DEFAULT_LOG_PATH = "docs/monitoring/binance_stability_log.csv"
FIELDNAMES = ["timestamp_utc", "status", "http_code", "latency_ms", "retry_after", "note"]

# Mismo endpoint/params que va a usar el adaptador real (klines de 1h), pero
# con limit=1 para no gastar cuota: nos interesa la salud del host, no los
# datos.
URL = "https://data-api.binance.vision/api/v3/klines"
PARAMS = {"symbol": "BTCUSDT", "interval": "1h", "limit": 1}


def classify(response, elapsed_ms):
    """Devuelve (status, note) segun la misma logica de estados que
    probe_rate_limits.py, para que ambos scripts sean comparables."""
    code = response.status_code
    if code in (429, 418):
        return "THROTTLED", ""
    if code in (403, 451):
        return "BLOCKED", ""
    if code != 200:
        return f"HTTP_{code}", response.text[:200]
    try:
        body = response.json()
    except ValueError:
        return "BAD_BODY", "respuesta no-JSON con HTTP 200"
    if not isinstance(body, list) or not body:
        return "BAD_BODY", "cuerpo vacio o con forma inesperada"
    return "OK", ""


def run_check():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = time.perf_counter()
    try:
        r = requests.get(URL, params=PARAMS, headers=UA, timeout=15)
    except requests.RequestException as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "timestamp_utc": ts,
            "status": "ERROR",
            "http_code": "",
            "latency_ms": latency_ms,
            "retry_after": "",
            "note": str(e)[:200],
        }
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    status, note = classify(r, latency_ms)
    return {
        "timestamp_utc": ts,
        "status": status,
        "http_code": r.status_code,
        "latency_ms": latency_ms,
        "retry_after": r.headers.get("Retry-After", ""),
        "note": note,
    }


def append_row(row, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    file_exists = os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH,
                         help=f"Ruta del CSV de log (default: {DEFAULT_LOG_PATH})")
    args = parser.parse_args()

    row = run_check()
    append_row(row, args.log_path)

    print(f"[{row['timestamp_utc']}] status={row['status']} "
          f"http={row['http_code']} latency_ms={row['latency_ms']} "
          f"note={row['note']!r}")

    if row["status"] not in ("OK",):
        # No hacemos fallar el job por un solo chequeo malo (una corrida
        # aislada no dice nada sobre estabilidad); el veredicto se saca
        # analizando la serie completa con analyze_binance_stability.py.
        print("Aviso: chequeo no-OK, pero esto es esperable de forma aislada; "
              "se evalua en agregado.")


if __name__ == "__main__":
    main()
