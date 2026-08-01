"""
Telegram Webhook API Endpoint
Accepts incoming Telegram updates and routes them through TelegramBotV3Handler.
"""
from fastapi import APIRouter, Request, HTTPException, status
from typing import Dict, Any
from app.telegram_bot.bot import bot_handler

router = APIRouter()


@router.post("/webhook", response_model=Dict[str, Any])
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    """Process incoming Telegram Bot API updates via Webhook."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id") or 0
    text = message.get("text", "").strip()
    username = message.get("from", {}).get("username")

    if text.startswith("/start"):
        response = await bot_handler.handle_start(user_id=chat_id, username=username)
        return {"status": "ok", "action": "start_handled", "response": response}

    elif text.startswith("/checkin"):
        response = await bot_handler.handle_checkin(user_id=chat_id)
        return {"status": "ok", "action": "checkin_handled", "response": response}

    elif text.startswith("/workout"):
        response = await bot_handler.handle_workout(user_id=chat_id)
        return {"status": "ok", "action": "workout_handled", "response": response}

    elif text.startswith("/stats"):
        response = await bot_handler.handle_stats(user_id=chat_id)
        return {"status": "ok", "action": "stats_handled", "response": response}

    elif text.startswith("/sync"):
        response = await bot_handler.handle_sync(user_id=chat_id)
        return {"status": "ok", "action": "sync_handled", "response": response}

    elif text.startswith("/redflag"):
        parts = text.split(" ", 1)
        symptom = parts[1] if len(parts) > 1 else None
        response = await bot_handler.handle_redflag(user_id=chat_id, symptom=symptom)
        return {"status": "ok", "action": "redflag_handled", "response": response}

    elif text.startswith("/help"):
        response = await bot_handler.handle_help(user_id=chat_id)
        return {"status": "ok", "action": "help_handled", "response": response}

    return {"status": "ok", "action": "ignored"}


@router.get("/status")
async def telegram_status() -> Dict[str, Any]:
    """Get Telegram Bot integration status and configuration details."""
    return {
        "status": "online",
        "bot_version": "v3.0",
        "webapp_url": bot_handler.webapp_url,
        "supported_commands": list(ALLOWED_COMMANDS if 'ALLOWED_COMMANDS' in globals() else ["/start", "/checkin", "/workout", "/stats", "/sync", "/redflag", "/help"]),
    }

