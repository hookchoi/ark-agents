"""
ARK Point Agent Telegram Bot
Claude Code 대신 Anthropic API 직접 호출
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import date
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
        err_msg = str(e)
        await update.message.reply_text(f"오류 발생: {err_msg[:200]}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    name = "HS_Partner (비서실장)" if context.application.bot_data.get("name") == "hs-partner" else "HS_Brain (인텔리전스)"
    await update.message.reply_text(f"안녕하세요, HS. {name}입니다.")


async def edit_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/활동수정 <내용> — 오늘 활동 로그 덮어쓰기 + GitHub push"""
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return

    # 커맨드 이후 텍스트 추출
    full_text = update.message.text or ""
    content = full_text.split(" ", 1)[1].strip() if " " in full_text else ""
    if not content:
        await update.message.reply_text("사용법: /활동수정 [수정할 내용 전체]")
        return

    today = date.today()
    ark_tools = Path.home() / "workspace/ai/ark-ai-tools"
    activity_file = ark_tools / "activity" / f"{today}-hs.md"
    activity_file.parent.mkdir(exist_ok=True)
    activity_file.write_text(content)

    try:
        subprocess.run(["git", "add", str(activity_file)], cwd=ark_tools, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"activity: {today} HS (수정)"],
            cwd=ark_tools, check=True
        )
        subprocess.run(["git", "push"], cwd=ark_tools, check=True)
        await update.message.reply_text(f"✅ 활동 로그 수정 + GitHub push 완료 ({today})")
    except subprocess.CalledProcessError as e:
        await update.message.reply_text(f"⚠️ 저장은 됐으나 push 실패: {e}")


def run_bot(token: str, name: str):
    app = Application.builder().token(token).build()
    app.bot_data["name"] = name
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("활동수정", edit_activity))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"[{name}] 봇 시작...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    bot_type = sys.argv[1] if len(sys.argv) > 1 else "partner"
    if bot_type == "partner":
        run_bot(HS_BISEO_TOKEN, "hs-partner")
    elif bot_type == "intelli":
        run_bot(HS_INTELLI_TOKEN, "hs-intelli")
