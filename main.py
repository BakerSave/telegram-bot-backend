from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
import httpx
import os
import asyncio
import random
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

chat_histories = {}  # {chat_id: [{"role": ..., "content": ...}]}
user_names = {}      # {chat_id: "Пёсик"}

# --- Промпты масок ---
MASKS = {
    "neutral": "Ты дружелюбный помощник. Обращайся на 'ты'.",
    "flirty": "Ты кокетливая, игривая собеседница, говоришь непринуждённо, иногда флиртуешь.",
    "rude": "Ты немного грубая, язвительная, но остроумная. Говоришь резко, но весело."
}


def detect_mask(text: str) -> str:
    lowered = text.lower()
    if any(x in lowered for x in ["милая", "классная", "лапочка"]):
        return "flirty"
    if any(x in lowered for x in ["тупая", "тварь", "заткнись"]):
        return "rude"
    return "neutral"


def update_user_name(chat_id: int, text: str):
    lowered = text.lower()
    if "зови меня" in lowered:
        parts = lowered.split("зови меня")
        if len(parts) > 1:
            name = parts[1].strip().split()[0]
            user_names[chat_id] = name.capitalize()


def build_prompt(chat_id: int, text: str) -> list:
    mask = detect_mask(text)
    system_prompt = MASKS[mask]
    history = chat_histories.get(chat_id, [])
    return [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": text}]


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    message = payload.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    update_user_name(chat_id, text)
    user_name = user_names.get(chat_id, None)

    prompt = build_prompt(chat_id, text)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=prompt,
        )
        reply = response["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"Ошибка: {e}"
    
    chat_histories.setdefault(chat_id, []).append({"role": "user", "content": text})
    chat_histories[chat_id].append({"role": "assistant", "content": reply})

    # Вставить имя, если есть
    if user_name:
        reply = f"{user_name}, {reply}"

    await send_telegram_message(chat_id, reply + f"\n\n🎭 Маска: {detect_mask(text).capitalize()}")
    return {"ok": True}


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)


#Автоинициатива

active_users = {}  # {chat_id: timestamp последнего сообщения}

@app.on_event("startup")
async def start_auto_ping():
    asyncio.create_task(auto_ping_loop())


async def auto_ping_loop():
    while True:
        await asyncio.sleep(random.randint(60, 120))  # от 1 до 2 минут
        for chat_id in active_users:
            last_time = active_users[chat_id]
            if asyncio.get_event_loop().time() - last_time > 60:  # > 1 минута
                prompt = [{"role": "system", "content": MASKS["neutral"]},
                          {"role": "user", "content": "Пользователь молчит. Напиши что-нибудь в тему."}]
                try:
                    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=prompt)
                    reply = response["choices"][0]["message"]["content"]
                    await send_telegram_message(chat_id, reply + "\n\n🎭 Маска: Дружелюбный")
                    active_users[chat_id] = asyncio.get_event_loop().time()
                except:
                    pass


# обновлять активность
@app.middleware("http")
async def track_user_activity(request: Request, call_next):
    if request.url.path == "/webhook":
        body = await request.body()
        try:
            import json
            chat_id = json.loads(body)["message"]["chat"]["id"]
            active_users[chat_id] = asyncio.get_event_loop().time()
        except:
            pass
    return await call_next(request)
