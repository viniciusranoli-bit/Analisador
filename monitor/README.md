# Monitoramento sintético — camadas L1 a L4

Monitoramento separado por disponibilidade, readiness, autenticação e fluxo caro
de análise para o Analisador de LinkedIn.

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
| `MONITOR_RETRY_BACKOFF_BASE_MS` | Backoff inicial entre tentativas | `500` |
| `MONITOR_RETRY_BACKOFF_MAX_MS` | Backoff máximo | `30000` |
| `MONITOR_RETRY_JITTER_FACTOR` | Jitter proporcional do backoff | `0.2` |
| `MONITOR_ALERT_FAILURE_THRESHOLD` | Falhas antes de alerta | `3` |
| `MONITOR_ALERT_RECOVERY_NOTIFY` | Emite recuperação após sucesso | `true` |
| `MONITOR_ALERT_WEBHOOK_URL` | Webhook de alerta (secret) | — |
| `MONITOR_E2E_EMAIL` | Conta de teste | — |
| `MONITOR_E2E_PASSWORD` | Senha da conta | — |
| `MONITOR_E2E_CRON` | Cron da camada E2E | `*/30 * * * *` |
| `MONITOR_DEEP_CRON` | Cron do fluxo caro | `0 8,20 * * *` |
| `MONITOR_DEEP_ENABLED` | Habilita L4 | `false` |
| `MONITOR_DEEP_ZIP_PATH` | ZIP de teste da análise | — |

### Cron no GitHub Actions

O GitHub exige cron literal no workflow. Ao alterar `MONITOR_SMOKE_CRON`, atualize
também `.github/workflows/synthetic-smoke.yml` e valide:

```bash
python monitor/scripts/check_schedule_sync.py
```

O workflow carrega os valores por `export_github_env.py`, sem executar `source`.
O estado de alertas é salvo na variável de repositório `MONITOR_ALERT_STATE`
quando `GITHUB_TOKEN` está disponível; localmente usa `.state/alert_state.json`.

## Execução local

```bash
cd monitor
pip install -r requirements.txt
cp monitor.config.env monitor.config.local.env
# preencha MONITOR_E2E_EMAIL e MONITOR_E2E_PASSWORD em monitor.config.local.env
python scripts/run_smoke.py
# ou uma camada isolada:
python scripts/run_smoke.py --layer availability
python scripts/run_smoke.py --layer readiness
python scripts/run_smoke.py --layer auth
```

## CI (GitHub Actions)

Configure estes secrets no repositório:

- `MONITOR_E2E_EMAIL`
- `MONITOR_E2E_PASSWORD`

Workflow: `.github/workflows/synthetic-smoke.yml`

O fluxo caro L4 é executado somente pelo workflow dedicado
`.github/workflows/synthetic-deep.yml` e exige credenciais E2E e um ZIP de teste.

## Endpoints de saúde (Fase 0)

| Endpoint | Uso |
|----------|-----|
| `GET /health` | Liveness — processo ativo |
| `GET /ready` | Readiness — OpenAI, Supabase (se configurado) |

## Camadas e política de falhas

1. **Disponibilidade:** processo HTTP, páginas públicas e latência.
2. **Readiness:** dependências necessárias para operar, sem chamar LLM.
3. **Autenticação:** login, sessão e rota protegida.
4. **Fluxo caro:** upload e análise completa com IA, em baixa frequência.

Cada camada possui retry próprio com backoff exponencial e jitter. O pipeline
interrompe as camadas seguintes quando uma camada anterior falha. O alerta só é
emitido após três execuções consecutivas com falha, é deduplicado enquanto o
incidente permanece ativo e uma recuperação é enviada no primeiro sucesso.
