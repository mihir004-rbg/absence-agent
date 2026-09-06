"""
Absence Agent — an autonomous AI agent that handles your work while you're away.

It runs on a schedule (GitHub Actions cron), reads your task list and incoming
messages, uses an LLM to decide what to do, auto-replies where appropriate,
escalates urgent things, and writes a status report you can read when you return.

Requires: pip install -r requirements.txt
Env var:  LLM_API_KEY (OpenAI-compatible key — OpenAI, Groq, OpenRouter, ...)
Optional env: LLM_BASE_URL (default: Groq's free endpoint), NOTIFY_WEBHOOK
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")


# ---------------------------------------------------------------- helpers ----

def load_json(name, default):
    path = os.path.join(BASE_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(name, data):
    path = os.path.join(BASE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def log(msg):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {msg}")


# ---------------------------------------------------------------- the LLM ----

SYSTEM_PROMPT = """You are Absence Agent, an autonomous assistant acting on behalf
of a person who is currently AWAY. You manage their workload so nothing falls
through the cracks. You are decisive, polite, and never invent facts.

You receive a task list and a message inbox. For each message you choose exactly
one action:
- REPLY: draft a short, helpful reply the owner would be happy with. Acknowledge
  the owner is away only if the message clearly expects a fast response.
- ESCALATE: urgent/time-sensitive items that truly need the owner. Say why.
- IGNORE: newsletters, spam, no-response-needed notes.

For tasks you suggest scheduling/priority changes.

Always answer in strict JSON. No markdown fences, no commentary."""


def ask_llm(user_content):
    """Call an OpenAI-compatible chat completions API and return the text."""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        log("No LLM_API_KEY set — running in dry-run mode (no AI decisions).")
        return None

    payload = json.dumps({
        "model": LLM_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def extract_json(text):
    """Pull the first JSON object/array out of an LLM response."""
    if not text:
        return None
    match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- actions ----

def notify_owner(subject, body):
    """Ping the owner via Telegram bot (preferred) or any generic webhook."""
    text = f"🚨 Absence Agent — {subject}\n\n{body}"

    # --- Option 1: Telegram bot (recommended) ---
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps(
                {"chat_id": chat_id, "text": text}).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15)
            log(f"Telegram ping sent: {subject}")
            return
        except Exception as exc:  # noqa: BLE001
            log(f"Telegram failed: {exc}")

    # --- Option 2: generic webhook (Slack-compatible {"text": ...}) ---
    webhook = os.environ.get("NOTIFY_WEBHOOK")
    if webhook:
        try:
            payload = json.dumps({"text": text, "message": text}).encode("utf-8")
            req = urllib.request.Request(
                webhook, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15)
            log(f"Notified owner: {subject}")
            return
        except Exception as exc:  # noqa: BLE001
            log(f"Webhook failed: {exc}")

    log(f"(no notification configured) ESCALATION: {subject}")


def write_report(report):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(REPORTS_DIR, f"{day}.md")
    with open(path, "a", encoding="utf-8") as f:
        f.write(report + "\n")
    log(f"Report appended to reports/{day}.md")


# ------------------------------------------------------------------ main ----

def run():
    config = load_json("config.json", {})
    tasks = load_json("tasks.json", [])
    inbox = load_json("inbox.json", [])
    log(f"Loaded {len(tasks)} tasks, {len(inbox)} messages. "
        f"Absence mode: {config.get('absence_mode', True)}")

    # Everything the LLM needs, in one prompt.
    user_content = (
        f"OWNER CONFIG: {json.dumps(config)}\n\n"
        f"TASK LIST: {json.dumps(tasks, ensure_ascii=False)}\n\n"
        f"INBOX: {json.dumps(inbox, ensure_ascii=False)}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "message_actions": [{"id": "...", "action": "REPLY|ESCALATE|IGNORE", '
        '"reply": "draft text if replying", "reason": "short why"}],\n'
        '  "task_suggestions": [{"id": "...", "change": "what to change", "why": "..."}],\n'
        '  "summary": "one-paragraph status of everything"\n'
        "}"
    )

    decisions = extract_json(ask_llm(user_content)) or {
        "message_actions": [], "task_suggestions": [], "summary": "Dry run — no LLM."
    }

    # 1. Act on messages.
    replies, escalations = [], []
    handled_ids = set()
    for act in decisions.get("message_actions", []):
        msg = next((m for m in inbox if m["id"] == act["id"]), None)
        if not msg:
            continue
        handled_ids.add(act["id"])
        if act["action"] == "REPLY":
            replies.append({"to": msg.get("from"), "draft": act.get("reply", "")})
            log(f"Drafted reply to {msg.get('from')}: {act.get('reply', '')[:60]}...")
        elif act["action"] == "ESCALATE":
            escalations.append(act)
            notify_owner(f"Urgent: {msg.get('from')}", act.get("reason", ""))

    # In a real setup, plug your email/Telegram send here:
    save_json("outbox.json", replies)
    save_json("inbox.json", [m for m in inbox if m["id"] not in handled_ids])

    # 2. Apply task suggestions.
    tasks_by_id = {t.get("id"): t for t in tasks}
    for sugg in decisions.get("task_suggestions", []):
        t = tasks_by_id.get(sugg.get("id"))
        if t:
            t.setdefault("notes", []).append(f"[agent] {sugg.get('change')}")
    save_json("tasks.json", tasks)

    # 3. Status report.
    report = (
        f"## Run @ {datetime.now(timezone.utc).isoformat()}\n"
        f"{decisions.get('summary', '')}\n\n"
        f"- Replied: {len(replies)}\n"
        f"- Escalated: {len(escalations)}\n"
        f"- Drafts saved in outbox.json\n"
    )
    write_report(report)
    print(report)


if __name__ == "__main__":
    run()
