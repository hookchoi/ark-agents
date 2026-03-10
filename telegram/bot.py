"""
ARK Point Agent Telegram Bot
Claude Code 대신 Anthropic API 직접 호출
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

load_dotenv(Path(__file__).parent / ".env")

HS_BISEO_TOKEN = os.environ["HS_BISEO_TOKEN"]
HS_INTELLI_TOKEN = os.environ["HS_INTELLI_TOKEN"]
HS_CHAT_ID = os.environ["HS_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

PARTNER_WORKSPACE = Path.home() / "workspace/ai/hs-partner"
INTELLI_WORKSPACE = Path.home() / "workspace/ai/hs-intelli"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def load_system_prompt(workspace: Path) -> str:
    """CLAUDE.md + MEMORY.md + 오늘 일기를 시스템 프롬프트로 로드"""
    parts = []

    for fname in ["SOUL.md", "CLAUDE.md", "MEMORY.md"]:
        fpath = workspace / fname
        if fpath.exists():
            parts.append(fpath.read_text())

    # 오늘/어제 일기
    from datetime import date, timedelta
    for delta in [0, 1]:
        day = date.today() - timedelta(days=delta)
        diary = workspace / "memory" / f"{day}.md"
        if diary.exists():
            parts.append(diary.read_text())

    return "\n\n---\n\n".join(parts)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return

    message = update.message.text
    bot_name = context.application.bot_data.get("name", "hs-partner")
    workspace = PARTNER_WORKSPACE if bot_name == "hs-partner" else INTELLI_WORKSPACE
    agent_name = "HS_Partner" if bot_name == "hs-partner" else "HS_Brain"

    await update.message.reply_text(f"⚙️ {agent_name} 처리 중...")

    try:
        system_prompt = load_system_prompt(workspace)
        print(f"[{agent_name}] 메시지 수신: {message[:50]}")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": message}]
        )

        reply = response.content[0].text
        if len(reply) > 4000:
            reply = reply[:4000] + "\n...(생략)"

        print(f"[{agent_name}] 응답 완료 ({len(reply)}자)")
        await update.message.reply_text(reply)

    except Exception as e:
        print(f"[{agent_name}] 오류: {e}")
        await update.message.reply_text(f"오류 발생: {str(e)[:200]}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    name = "HS_Partner (비서실장)" if context.application.bot_data.get("name") == "hs-partner" else "HS_Brain (인텔리전스)"
    await update.message.reply_text(f"안녕하세요, HS. {name}입니다.")


def run_bot(token: str, name: str):
    app = Application.builder().token(token).build()
    app.bot_data["name"] = name
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"[{name}] 봇 시작...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    bot_type = sys.argv[1] if len(sys.argv) > 1 else "partner"
    if bot_type == "partner":
        run_bot(HS_BISEO_TOKEN, "hs-partner")
    elif bot_type == "intelli":
        run_bot(HS_INTELLI_TOKEN, "hs-intelli")
