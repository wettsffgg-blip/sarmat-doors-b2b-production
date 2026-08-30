# SARMAT DOORS READY15 — Render

## Backend

- Start command: `python server.py`
- Health check: `/api/health`
- PDF engine: ReportLab
- Endpoints: `/api/pdf`, `/api/final-pdf`, `/api/order`, `/api/telegram-test`

## Environment variables

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Секреты не должны записываться в HTML или репозиторий.

## Проверка после Deploy

1. Откройте `/api/health`.
2. Проверьте `ok: true`.
3. Проверьте `telegramConfigured: true`.
4. На сайте проверьте сначала обычное КП без подписи/печати.
5. Затем проверьте отправку заказа в Telegram.
6. Только после успешной отправки проверьте финальное КП с подписью и печатью.
