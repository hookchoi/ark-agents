"""
ARK Point Agent Telegram Bot
HS비서 + HS인텔리 Telegram 연동
"""

import os
import subprocess
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# 환경변수에서 로드 (.env 파일)
HS_BISEO_TOKEN = os.environ.get("HS_BISEO_TOKEN")   # HS비서 봇 토큰
HS_INTELLI_TOKEN = os.environ.get("HS_INTELLI_TOKEN")  # HS인텔리 봇 토큰
HS_CHAT_ID = os.environ.get("HS_CHAT_ID")             # HS 개인 chat_id

BISEO_WORKSPACE = os.path.expanduser("~/workspace/ai/hs-biseo")
INTELLI_WORKSPACE = os.path.expanduser("~/workspace/ai/hs-intelli")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """HS의 메시지를 받아 Claude Code로 처리"""
    user_id = str(update.effective_chat.id)

    # HS 본인만 허용
    if user_id != HS_CHAT_ID:
        await update.message.reply_text("접근 권한이 없습니다.")
        return

    message = update.message.text
    bot_name = context.application.bot_data.get("name", "hs-biseo")
    workspace = BISEO_WORKSPACE if bot_name == "hs-biseo" else INTELLI_WORKSPACE

    await update.message.reply_text("⚙️ 처리 중...")

    # Claude Code CLI 호출
    result = subprocess.run(
        ["claude", "-p", message, "--output-format", "text"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120
    )

    response = result.stdout.strip() if result.stdout else "처리 실패: " + result.stderr
    await update.message.reply_text(response)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_name = context.application.bot_data.get("name", "hs-biseo")
    name = "HS비서 (비서실장)" if bot_name == "hs-biseo" else "HS인텔리 (인텔리전스)"
    await update.message.reply_text(f"안녕하세요, HS. {name}입니다. 무엇을 도와드릴까요?")


def run_bot(token: str, name: str):
    app = Application.builder().token(token).build()
    app.bot_data["name"] = name
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"{name} 봇 시작...")
    app.run_polling()


if __name__ == "__main__":
    import sys
    bot_type = sys.argv[1] if len(sys.argv) > 1 else "biseo"

    if bot_type == "biseo":
        run_bot(HS_BISEO_TOKEN, "hs-biseo")
    elif bot_type == "intelli":
        run_bot(HS_INTELLI_TOKEN, "hs-intelli")
