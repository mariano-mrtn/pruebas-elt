# Pipeline ELT y Dashboard de Cotizaciones

Pipeline ELT (Binance, OKX, Coinbase) + dbt + API FastAPI + dashboard.

## Estado
- [x] Fase 0: esqueleto del repo y sonda de rate limits
- [ ] Capa 1: cañería de datos (extracción, bronce, staging, backfill)

## Puesta en marcha
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python tools/probe_rate_limits.py
```
