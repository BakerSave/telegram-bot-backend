from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import openai
import httpx
import os
import asyncio
import random
import time

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Память чатов
chat_states = {}

# Маски (упрощены)
masks = {
    "friendly": {"emoji": "😊", "prompt": "Ты дружелюбный помощник."},
    "flirty": {"emoji": "😉", "prompt": "Ты флиртующий собеседник."},
    "rude": {"emoji": "😒", "prompt": "Ты немного грубый и дерзкий собеседник."},
}

# Таймеры для инициатив
last_user_activity = {}
last_bot_ping = {}

# Ограничение: 1–2 минуты
PING_MIN_DELAY = 60
PING_MAX_DELAY = 120


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("📩 INCOMING from Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"]["text"]

        now = time.time()
        last_user_activity[chat_id] = now
        chat_states.setdefault(chat_id, {"history": [], "mask": "friendly", "name": None})
        last_bot_ping.pop(chat_id, None)  # сбросить таймер пинга

        # Имя
        if not chat_states[chat_id]["name"]:
            if any(word.lower().startswith("меня зовут") for word in text.lower().split()):
                name = text.split("зовут")[-1].strip().split()[0]
                chat_states[chat_id]["name"] = name

        # Обновить историю
        history = chat_states[chat_id]["history"]
        history.append({"role": "user", "content": text})

        # Маску определим по содержимому
        lowered = text.lower()
        if any(word in lowered for word in ["дура", "тупая", "тварь", "идиот"]):
            chat_states[chat_id]["mask"] = "rude"
        elif any(word in lowered for word in ["милая", "лапочка", "секси", "красотка", "классная"]):
            chat_states[chat_id]["mask"] = "flirty"
        else:
            chat_states[chat_id]["mask"] = "friendly"

        mask = chat_states[chat_id]["mask"]
        system_prompt = masks[mask]["prompt"]

        # Запрос в GPT
        messages = [{"role": "system", "content": system_prompt}] + history
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": reply})

        mask_emoji = masks[mask]["emoji"]
        full_reply = f"{reply}\n\n{mask_emoji} Маска: {mask.capitalize()}"
        await send_telegram_message(chat_id, full_reply)

    except Exception as e:
        print("❌ Ошибка:", e)

    return {"ok": True}


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)


# Автопинг
async def ping_loop():
    while True:
        await asyncio.sleep(random.randint(5, 10))  # интервал между циклами проверки

        now = time.time()
        for chat_id, last_time in last_user_activity.items():
            if chat_id in last_bot_ping:
                continue  # уже пинговали, ждём ответа

            since_last_msg = now - last_time
            random_delay = random.randint(PING_MIN_DELAY, PING_MAX_DELAY)

            if since_last_msg > random_delay:
                history = chat_states[chat_id]["history"]
                mask = chat_states[chat_id]["mask"]
                system_prompt = masks[mask]["prompt"]
                name = chat_states[chat_id]["name"] or "друг"

                messages = [{"role": "system", "content": system_prompt}] + history
                messages.append({"role": "user", "content": f"Ты давно молчишь с {name}. Напиши что-нибудь!"})

                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages
                    )
                    reply = response["choices"][0]["message"]["content"]
                    full_reply = f"{reply}\n\n{masks[mask]['emoji']} Маска: {mask.capitalize()}"
                    await send_telegram_message(chat_id, full_reply)
                    last_bot_ping[chat_id] = now
                    chat_states[chat_id]["history"].append({"role": "assistant", "content": reply})
                except Exception as e:
                    print(f"❌ Ошибка при пинге {chat_id}: {e}")


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ping_loop())
