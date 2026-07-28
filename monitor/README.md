# Monitoramento sintético — Fase 0 + Fase 1

Smoke tests de disponibilidade (L1) e autenticação (L2) para o Analisador de LinkedIn.

## Configuração

Todos os parâmetros ficam em `monitor/monitor.config.env`. Para overrides locais:

```bash
cp monitor/monitor.config.env monitor/monitor.config.local.env
# edite monitor.config.local.env (não versionado)
```

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `MONITOR_SMOKE_CRON` | Reexecução periódica (UTC) | `*/5 * * * *` |
| `MONITOR_BASE_URL` | URL alvo | `https://analisadorlinkedin.com.br` |
| `MONITOR_HTTP_TIMEOUT_SECONDS` | Timeout HTTP | `15` |
| `MONITOR_L1_MAX_LATENCY_MS` | Latência máxima L1 | `10000` |
| `MONITOR_RETRY_COUNT` | Retentativas pytest | `1` |
| `MONITOR_ALERT_FAILURE_THRESHOLD` | Falhas antes de alerta | `3` |
| `MONITOR_E2E_EMAIL` | Conta de teste | — |
| `MONITOR_E2E_PASSWORD` | Senha da conta | — |

### Cron no GitHub Actions

O GitHub exige cron literal no workflow. Ao alterar `MONITOR_SMOKE_CRON`, atualize também `.github/workflows/synthetic-smoke.yml` e valide:

```bash
python monitor/scripts/check_schedule_sync.py
```

## Execução local

```bash
cd monitor
pip install -r requirements.txt
cp monitor.config.env monitor.config.local.env
# preencha MONITOR_E2E_EMAIL e MONITOR_E2E_PASSWORD em monitor.config.local.env
python scripts/run_smoke.py
```

## CI (GitHub Actions)

Configure estes secrets no repositório:

- `MONITOR_E2E_EMAIL`
- `MONITOR_E2E_PASSWORD`

Workflow: `.github/workflows/synthetic-smoke.yml`

## Endpoints de saúde (Fase 0)

| Endpoint | Uso |
|----------|-----|
| `GET /health` | Liveness — processo ativo |
| `GET /ready` | Readiness — OpenAI, Supabase (se configurado) |
