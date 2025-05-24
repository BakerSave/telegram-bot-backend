from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import openai
import httpx
import os
import asyncio
import random
import time
import json
from pymorphy2 import MorphAnalyzer

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

morph = MorphAnalyzer()

# Память чатов
chat_states = {}

# Маски
masks = {
    "friendly": {"emoji": "😊", "prompt": "Ты дружелюбный помощник."},
    "flirty": {"emoji": "😉", "prompt": "Ты флиртующий собеседник."},
    "rude": {"emoji": "😒", "prompt": "Ты немного грубый и дерзкий собеседник."},
}

# Дефолтный стиль общения (пример переписки)
DEFAULT_STYLE_EXAMPLE = """[
    {"role": "user", "content": "ну че ты там"},
    {"role": "assistant", "content": "да ниче лол"},
    {"role": "user", "content": "опять пропал капец"},
    {"role": "assistant", "content": "сорян канеш, ща тут"},
    {"role": "user", "content": "че как с ботом там?"},
    {"role": "assistant", "content": "ну работает норм вроде"}
]"""

# Таймеры для инициатив
last_user_activity = {}
last_bot_ping = {}
PING_MIN_DELAY = 60
PING_MAX_DELAY = 120

# Максимальный объём истории в символах
MAX_HISTORY_CHARS = 20000

def inflect_name(name):
    parsed = morph.parse(name)[0]
    return {
        "nomn": parsed.inflect({"nomn"}).word if parsed.inflect({"nomn"}) else name,
        "accs": parsed.inflect({"accs"}).word if parsed.inflect({"accs"}) else name,
        "ablt": parsed.inflect({"ablt"}).word if parsed.inflect({"ablt"}) else name
    }

def insert_name(chat_id, template: str) -> str:
    user = chat_states.get(chat_id)
    if not user or not user.get("inflections"):
        return template
    f = user["inflections"]
    return template.format(
        name=f.get("nomn", ""),
        acc=f.get("accs", ""),
        ins=f.get("ablt", "")
    )

def apply_style(messages, style_json: str):
    try:
        parsed = json.loads(style_json)
        messages.append({"role": "system", "content": "Ты ведёшь переписку в мессенджере. Продолжай диалог в том же стиле, что в примере ниже: без заглавных букв, с разговорной лексикой, с эмодзи, с 'лол', 'капец', 'канеш', 'ну'. Не отвечай как ассистент. Не будь официальным."})
        messages.extend(parsed)
    except Exception as e:
        print("⚠️ Ошибка парсинга style:", e)

def trim_history(chat_id, max_chars=MAX_HISTORY_CHARS):
    history = chat_states[chat_id]["history"]
    total = 0
    trimmed = []
    for msg in reversed(history):
        total += len(msg.get("content", ""))
        trimmed.append(msg)
        if total > max_chars:
            break
    trimmed = list(reversed(trimmed[:-1])) if total > max_chars else list(reversed(trimmed))
    chat_states[chat_id]["history"] = trimmed

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("📩 INCOMING from Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"].get("text", "")

        now = time.time()
        last_user_activity[chat_id] = now
        chat_states.setdefault(chat_id, {
            "history": [],
            "mask": "friendly",
            "name": None,
            "inflections": None,
            "style_learned": None
        })
        last_bot_ping.pop(chat_id, None)

        # Имя
        lowered = text.lower()
        if any(p in lowered for p in ["меня зовут", "зови меня"]):
            words = text.split()
            name = None
            for i, word in enumerate(words):
                if word.lower() in ["зовут", "меня"]:
                    if i + 1 < len(words):
                        name = words[i + 1]
                        break
            if name:
                chat_states[chat_id]["name"] = name
                chat_states[chat_id]["inflections"] = inflect_name(name)

        # Обновить историю
        history = chat_states[chat_id]["history"]
        history.append({"role": "user", "content": text})

        # Ограничение длины истории
        trim_history(chat_id)

        # Определить маску
        if any(word in lowered for word in ["дура", "тупая", "тварь", "идиот"]):
            chat_states[chat_id]["mask"] = "rude"
        elif any(word in lowered for word in ["милая", "лапочка", "секси", "красотка", "классная"]):
            chat_states[chat_id]["mask"] = "flirty"
        else:
            chat_states[chat_id]["mask"] = "friendly"

        mask = chat_states[chat_id]["mask"]
        style = chat_states[chat_id].get("style_learned") or DEFAULT_STYLE_EXAMPLE

        messages = []
        apply_style(messages, style)
        messages += chat_states[chat_id]["history"]

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        reply = insert_name(chat_id, reply)

        history.append({"role": "assistant", "content": reply})
        full_reply = f"{reply}\n\n{masks[mask]['emoji']} Маска: {mask.capitalize()}"
        await send_telegram_message(chat_id, full_reply)

    except Exception as e:
        print("❌ Ошибка:", e)

    return {"ok": True} ...
