# 🤖 Absence Agent — AI Agent That Handles Your Work While You're Away

An autonomous AI agent that runs on GitHub Actions (free, 24/7, no server needed).
When you're away, it:

- 📋 Manages and prioritizes your task list (from `tasks.json` or GitHub Issues)
- 💬 Auto-responds to incoming messages/emails with polite "I'm away" + AI-drafted replies
- 🚨 Escalates urgent items and sends you a notification (email/Telegram webhook)
- 📊 Writes a daily status report of everything it did in your absence

## How it works

```
        ┌─────────────────────────────┐
        │  GitHub Actions (cron)      │
        │  runs every hour / daily    │
        └──────────┬──────────────────┘
                   ▼
        ┌─────────────────────────────┐
        │  agent.py                   │
        │  1. Load tasks & messages   │
        │  2. LLM classifies/priority │
        │  3. Auto-reply what it can  │
        │  4. Escalate what it can't  │
        │  5. Write status report     │
        └──────────┬──────────────────┘
                   ▼
        ┌─────────────────────────────┐
        │  You return → read         │
        │  reports/ + notifications   │
        └─────────────────────────────┘
```

## Quick start

1. **Create a new GitHub repo** (e.g. `absence-agent`) and push these files.

2. **Get an LLM API key** — any OpenAI-compatible provider works (OpenAI, Groq, Together, OpenRouter).
   Groq has a generous free tier: https://console.groq.com

3. **Add your secrets** in the repo → Settings → Secrets and variables → Actions:
   - `LLM_API_KEY` — your API key
   - `TELEGRAM_BOT_TOKEN` — (optional) from @BotFather, for urgent pings to your phone
   - `TELEGRAM_CHAT_ID` — (optional) your chat ID (message @userinfobot to get it)
   - `NOTIFY_WEBHOOK` — (optional) any generic webhook URL (Slack-compatible)

4. **Telegram pings (recommended):** message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token. Then message your new bot once (press START), and message [@userinfobot](https://t.me/userinfobot) to get your chat ID. Add both as repo secrets.

5. **Add your tasks** in `tasks.json`.

6. **Turn on Actions** — the workflow in `.github/workflows/agent.yml` runs the agent
   every hour. Adjust the cron schedule to taste.

7. **Go on vacation.** The agent handles the rest. 🏖️

## Run locally

```bash
pip install -r requirements.txt
export LLM_API_KEY="sk-..."
python agent.py
```

## Files

| File | Purpose |
|---|---|
| `agent.py` | The agent brain — loads tasks/messages, calls the LLM, acts |
| `tasks.json` | Your task list (editable, the agent also updates it) |
| `inbox.json` | Sample incoming messages the agent responds to |
| `config.json` | Settings: absence dates, reply tone, escalation rules |
| `reports/` | Daily status reports the agent writes |
| `.github/workflows/agent.yml` | The 24/7 heartbeat (GitHub Actions cron) |

## Extending it

- Hook `inbox.json` up to a real source (Gmail API, Telegram bot, GitHub Issues)
- Add more actions in `agent.py` (the `ACT` functions are simple to extend)
- Multiple people? Add per-person configs

MIT licensed — do whatever you want with it.
