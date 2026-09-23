#!/usr/bin/env python3
"""
Analiza el log de tools/monitor_binance_stability.py y aplica el criterio
de "estable" del ticket #2:

  - >= 99% de llamadas exitosas en la ventana
  - sin ningun 451/5xx inexplicado
  - latencia sin picos sostenidos

Uso:
    python tools/analyze_binance_stability.py
    python tools/analyze_binance_stability.py --log-path docs/monitoring/binance_stability_log.csv --days 7
"""
import argparse
import csv
import statistics
from datetime import datetime, timedelta, timezone

DEFAULT_LOG_PATH = "docs/monitoring/binance_stability_log.csv"
SUCCESS_THRESHOLD = 0.99
# Un "pico sostenido" = N chequeos seguidos por encima de este multiplo de
# la mediana de latencia de la ventana.
SPIKE_STREAK_LEN = 3
SPIKE_MULTIPLIER = 3.0


def load_rows(log_path, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    with open(log_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                row["_ts"] = ts
                row["latency_ms"] = float(row["latency_ms"]) if row["latency_ms"] else None
                rows.append(row)
    rows.sort(key=lambda r: r["_ts"])
    return rows


def find_latency_spikes(rows):
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    if len(latencies) < SPIKE_STREAK_LEN:
        return []
    median = statistics.median(latencies)
    threshold = median * SPIKE_MULTIPLIER
    spikes, streak = [], []
    for r in rows:
        if r["latency_ms"] is not None and r["latency_ms"] > threshold:
            streak.append(r)
        else:
            if len(streak) >= SPIKE_STREAK_LEN:
                spikes.append((streak[0]["timestamp_utc"], streak[-1]["timestamp_utc"], len(streak)))
            streak = []
    if len(streak) >= SPIKE_STREAK_LEN:
        spikes.append((streak[0]["timestamp_utc"], streak[-1]["timestamp_utc"], len(streak)))
    return spikes, median, threshold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    parser.add_argument("--days", type=int, default=7, help="Tamano de la ventana a evaluar (default: 7)")
    args = parser.parse_args()

    rows = load_rows(args.log_path, args.days)
    total = len(rows)
    if total == 0:
        print(f"No hay chequeos en los ultimos {args.days} dias todavia en {args.log_path}.")
        return

    ok = sum(1 for r in rows if r["status"] == "OK")
    success_rate = ok / total

    unexplained = [r for r in rows if r["status"] in ("BLOCKED",) or r["status"].startswith("HTTP_5")]
    throttled = [r for r in rows if r["status"] == "THROTTLED"]
    errors = [r for r in rows if r["status"] == "ERROR"]

    spikes, median, threshold = find_latency_spikes(rows)

    first_ts, last_ts = rows[0]["timestamp_utc"], rows[-1]["timestamp_utc"]
    span_days = (rows[-1]["_ts"] - rows[0]["_ts"]).total_seconds() / 86400

    print(f"=== Estabilidad de data-api.binance.vision (ticket #2) ===")
    print(f"Ventana solicitada: {args.days} dias | datos cubren: {span_days:.1f} dias ({first_ts} -> {last_ts})")
    print(f"Chequeos totales: {total}")
    print(f"Exitosos (OK): {ok} ({success_rate:.2%})")
    print(f"Throttled (429/418): {len(throttled)}")
    print(f"Bloqueados/5xx inexplicados: {len(unexplained)}")
    print(f"Errores de red/timeout: {len(errors)}")
    print(f"Latencia mediana: {median:.0f} ms | umbral de pico ({SPIKE_MULTIPLIER}x): {threshold:.0f} ms")
    if spikes:
        print(f"Picos sostenidos detectados ({SPIKE_STREAK_LEN}+ chequeos seguidos por encima del umbral):")
        for start, end, n in spikes:
            print(f"  - {start} -> {end} ({n} chequeos)")
    else:
        print("Sin picos de latencia sostenidos.")

    is_stable = (
        success_rate >= SUCCESS_THRESHOLD
        and len(unexplained) == 0
        and len(spikes) == 0
        and span_days >= (args.days - 0.5)  # que la ventana ya se haya completado
    )

    print()
    if is_stable:
        print(f"VEREDICTO: ESTABLE — se cumple el criterio de {SUCCESS_THRESHOLD:.0%} exito, "
              "sin 451/5xx inexplicados y sin picos sostenidos. Ticket #2 puede cerrarse.")
    elif span_days < (args.days - 0.5):
        print(f"VEREDICTO: EN CURSO — todavia no se completan los {args.days} dias de ventana, seguir esperando.")
    else:
        print("VEREDICTO: REVISAR — no se cumple alguno de los criterios. "
              "Si son señales aisladas, extender la ventana a 14 dias; "
              "si el host falla de forma consistente, evaluar el plan B "
              "(correr la extraccion de Binance desde otro servicio con IP habilitada).")


if __name__ == "__main__":
    main()
