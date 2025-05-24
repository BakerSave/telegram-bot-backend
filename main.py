from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import openai
import httpx
import os
import asyncio
import random
import time
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
DEFAULT_STYLE_EXAMPLE = """
хммм а раньше ж ты находил ее покупки
ну лан
да канеш
капец сорян канеш
такс, че как там у тебя с ботом
ну там денег стоит. нууу каких-то
"""

# Таймеры для инициатив
last_user_activity = {}
last_bot_ping = {}
PING_MIN_DELAY = 60
PING_MAX_DELAY = 120

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

        # Определить маску
        if any(word in lowered for word in ["дура", "тупая", "тварь", "идиот"]):
            chat_states[chat_id]["mask"] = "rude"
        elif any(word in lowered for word in ["милая", "лапочка", "секси", "красотка", "классная"]):
            chat_states[chat_id]["mask"] = "flirty"
        else:
            chat_states[chat_id]["mask"] = "friendly"

        mask = chat_states[chat_id]["mask"]
        system_prompt = masks[mask]["prompt"]
        style = chat_states[chat_id].get("style_learned") or DEFAULT_STYLE_EXAMPLE

        messages = [{"role": "system", "content": system_prompt}]

        if style:
            for line in style.strip().splitlines():
                if line.strip():
                    messages.append({"role": "user", "content": line.strip()})

        messages += history

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        reply = insert_name(chat_id, reply)

        history.append({"role": "assistant", "content": reply})
        full_reply = f"{reply}\n\n{masks[mask]['emoji']} Маска: {mask.capitalize()}"
        await send_telegram_message(chat_id, full_reply)

    except Exception as e:
        print("❌ Ошибка:", e)

    return {"ok": True}

async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def ping_loop():
    while True:
        await asyncio.sleep(random.randint(5, 10))

        now = time.time()
        for chat_id, last_time in last_user_activity.items():
            if chat_id in last_bot_ping:
                continue
            since_last_msg = now - last_time
            if since_last_msg > random.randint(PING_MIN_DELAY, PING_MAX_DELAY):
                history = chat_states[chat_id]["history"]
                mask = chat_states[chat_id]["mask"]
                system_prompt = masks[mask]["prompt"]
                name = chat_states[chat_id].get("inflections", {}).get("nomn", "друг")

                style = chat_states[chat_id].get("style_learned") or DEFAULT_STYLE_EXAMPLE
                messages = [{"role": "system", "content": system_prompt}]
                if style:
                    for line in style.strip().splitlines():
                        if line.strip():
                            messages.append({"role": "user", "content": line.strip()})
                messages += history
                messages.append({
                    "role": "user",
                    "content": f"Ты давно молчишь с {name}. Напиши что-нибудь!"
                })
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages
                    )
                    reply = response["choices"][0]["message"]["content"]
                    reply = insert_name(chat_id, reply)
                    full_reply = f"{reply}\n\n{masks[mask]['emoji']} Маска: {mask.capitalize()}"
                    await send_telegram_message(chat_id, full_reply)
                    last_bot_ping[chat_id] = now
                    chat_states[chat_id]["history"].append({"role": "assistant", "content": reply})
                except Exception as e:
                    print(f"❌ Ошибка при пинге {chat_id}: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ping_loop())
