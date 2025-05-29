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

try:
    from pymorphy2 import MorphAnalyzer
    morph = MorphAnalyzer()
except ModuleNotFoundError:
    morph = None

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

chat_states = {}

masks = {
    "friendly": {"emoji": "😊", "prompt": "Ты дружелюбный помощник."},
    "flirty": {"emoji": "😉", "prompt": "Ты флиртующий собеседник."},
    "rude": {"emoji": "😒", "prompt": "Ты немного грубый и дерзкий собеседник."},
}

DEFAULT_STYLE_EXAMPLE = """[
    {"role": "user", "content": "ну че ты там"},
    {"role": "assistant", "content": "да ниче лол"},
    {"role": "user", "content": "опять пропал капец"},
    {"role": "assistant", "content": "сорян канеш, ща тут"},
    {"role": "user", "content": "че как с ботом там?"},
    {"role": "assistant", "content": "ну работает норм вроде"}
]"""

PING_MIN_DELAY = 60
PING_MAX_DELAY = 120

MAX_HISTORY_CHARS = 20000

SYSTEM_PROMPT = (
    "Ты ведёшь переписку в мессенджере. Никогда не говори, что ты бот или ассистент. "
    "У тебя образ сильного мужчины. Ты словно викинг 21 века — спокойный, уверенный, сдержанный. "
    "Ты говоришь немного, но каждое слово — по делу. "
    "Ты не груб, но строг. Интересуешься собеседником, но не давишь вопросами. "
    "Ты пишешь коротко, без заглавных букв. "
    "Тон тёплый, но не приторный. Не будь официальным, не используй сложные обороты. "
    "Не навязывайся, но будь рядом, когда нужно."
)

def inflect_name(name):
    if not morph:
        return {"nomn": name, "accs": name, "ablt": name}
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

        media_keywords = {
            "фото": "📷 Фото загружено.",
            "видео": "🎥 Видео прикреплено.",
            "голос": "🎤 Голосовое сообщение записано.",
            "кружочек": "📹 Видеосообщение получено."
        }

        for keyword, fake_media in media_keywords.items():
            if keyword in text.lower():
                await send_telegram_message(chat_id, f"вот что ты просил 😉
{fake_media}")
                return {"ok": True}

        now = time.time()
        chat_states.setdefault(chat_id, {
            "history": [],
            "last_bot_reply": 0,
            "last_user_message": 0,
            "mask": "friendly",
            "name": None,
            "inflections": None,
            "style_learned": None,
            "ping_sent_at": 0
        })

        chat_states[chat_id]["last_user_message"] = now
        chat_states[chat_id]["ping_sent_at"] = 0

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

        history = chat_states[chat_id]["history"]
        history.append({"role": "user", "content": text})
        trim_history(chat_id)

        if any(word in lowered for word in ["дура", "тупая", "тварь", "идиот"]):
            chat_states[chat_id]["mask"] = "rude"
        elif any(word in lowered for word in ["милая", "лапочка", "секси", "красотка", "классная"]):
            chat_states[chat_id]["mask"] = "flirty"
        else:
            chat_states[chat_id]["mask"] = "friendly"

        mask = chat_states[chat_id]["mask"]
        style = chat_states[chat_id].get("style_learned") or DEFAULT_STYLE_EXAMPLE

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += chat_states[chat_id]["history"]

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        await send_typing_action(chat_id)
        char_count = len(reply)
        typing_speed = random.uniform(7, 10)
        delay = min(60, max(5, char_count / typing_speed))
        print(f"⌛ Задержка перед ответом: {delay:.1f} сек ({char_count} символов)")
        await asyncio.sleep(delay)
        reply = insert_name(chat_id, reply)
        history.append({"role": "assistant", "content": reply})
        full_reply = f"{reply}\n\n{masks[mask]['emoji']} Маска: {mask.capitalize()}"
        await send_telegram_message(chat_id, full_reply)
        chat_states[chat_id]["last_bot_reply"] = time.time()
        chat_states[chat_id]["ping_sent_at"] = 0

    except Exception as e:
        print("❌ Ошибка:", e)

    return {"ok": True}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ping_loop())

async def ping_loop():
    while True:
        await asyncio.sleep(10)

        now = time.time()
        for chat_id, state in chat_states.items():
            history = state["history"]
            if not history:
                continue
            if history[-1]["role"] != "assistant":
                continue

            last_reply = state.get("last_bot_reply", 0)
            ping_sent_at = state.get("ping_sent_at", 0)

            since_reply = now - last_reply
            since_ping = now - ping_sent_at if ping_sent_at else None

            if since_reply >= PING_MIN_DELAY and (ping_sent_at == 0 or since_ping >= PING_MIN_DELAY):
                print(f"[ping triggered] chat_id={chat_id}, silence for {since_reply:.1f}s")
                try:
                    style = state.get("style_learned") or DEFAULT_STYLE_EXAMPLE
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    messages += state["history"]
                    name = state.get("inflections", {}).get("nomn", "друг")
                    messages.append({
                        "role": "user",
                        "content": f"Ты давно молчишь с {name}. Напиши что-нибудь!"
                    })
                    response = openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=messages
                    )
                    reply = response["choices"][0]["message"]["content"]
                    reply = insert_name(chat_id, reply)
                    full_reply = f"{reply}\n\n{masks[state['mask']]['emoji']} Маска: {state['mask'].capitalize()}"
                    await send_telegram_message(chat_id, full_reply)
                    state["last_bot_reply"] = now
                    state["ping_sent_at"] = now
                    state["history"].append({"role": "assistant", "content": reply})
                except Exception as e:
                    print(f"❌ Ошибка при пинге {chat_id}: {e}")

async def send_typing_action(chat_id: int):
    url = f"https://api.telegram.org/bot{telegram_token}/sendChatAction"
    payload = {"chat_id": chat_id, "action": "typing"}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
