from __future__ import annotations
"""
ARK Point Multi-Agent Telegram Bot

Commands:
    /brain   [msg] — Brain Food 글쓰기
    /venture [msg] — 사업 기회 분석
    /atlas   [msg] — Personal Ops
    /ai      [msg] — AI Native 조직
    /archive       — 아카이브 조회

Brain Food 채널 포스트 → writing_samples/telegram/ 자동 저장
"""

import os
import re
import json
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)

load_dotenv(Path(__file__).parent / ".env")

HS_ORCHESTRATOR_TOKEN      = os.environ["HS_ORCHESTRATOR_TOKEN"]
HS_CHAT_ID            = os.environ["HS_CHAT_ID"]
BRAIN_FOOD_CHANNEL_ID = os.environ.get("BRAIN_FOOD_CHANNEL_ID", "")
ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]

BASE_DIR    = Path(__file__).parent.parent
AGENTS_DIR  = BASE_DIR / "agents"
ORCHESTRATOR_DIR = BASE_DIR / "hs-orchestrator"
WRITING_DIR = BASE_DIR / "writing_samples"
ARCHIVE_DIR = BASE_DIR / "archive"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── 상태 관리 ──────────────────────────────────────────────
pending_archive: dict[int, dict] = {}   # chat_id → {content, topic}
pending_linkedin: dict[int, str] = {}   # chat_id → content (날짜 대기 중)
current_agent:   dict[int, str]  = {}   # chat_id → agent_name

COMMAND_TO_AGENT = {
    "brain":   "brain",
    "venture": "venture",
    "atlas":   "atlas",
    "ai":      "ai-org",
}

# ── 프롬프트 로딩 ───────────────────────────────────────────
def load_writing_samples() -> str:
    samples = []
    for subdir in ["linkedin", "telegram"]:
        sample_dir = WRITING_DIR / subdir
        if not sample_dir.exists():
            continue
        files = sorted(sample_dir.glob("*.md"), reverse=True)[:3]
        for f in files:
            samples.append(f"### [{subdir.upper()}]\n{f.read_text()}")
    if not samples:
        return ""
    return "## 과거 글쓰기 샘플 (스타일 학습용)\n\n" + "\n\n---\n\n".join(samples)


def load_agent_system(agent_name: str) -> str:
    parts = []

    agent_file = AGENTS_DIR / f"{agent_name}.md"
    if agent_file.exists():
        parts.append(agent_file.read_text())

    # partner 메모리 컨텍스트
    for fname in ["SOUL.md", "MEMORY.md"]:
        fpath = ORCHESTRATOR_DIR / fname
        if fpath.exists():
            parts.append(fpath.read_text())

    # Brain Food: 과거 글 샘플 추가
    if agent_name == "brain":
        samples = load_writing_samples()
        if samples:
            parts.append(samples)

    # 오늘/어제 일기
    for delta in [0, 1]:
        day = date.today() - timedelta(days=delta)
        diary = ORCHESTRATOR_DIR / "memory" / f"{day}.md"
        if diary.exists():
            parts.append(diary.read_text())

    return "\n\n---\n\n".join(parts)


# ── 아카이브 유틸 ───────────────────────────────────────────
ARCHIVE_TAG_RE = re.compile(r"\[ARCHIVE\?\s*([^\]]+)\]", re.IGNORECASE)


def extract_archive_tag(text: str) -> tuple[str, str | None]:
    match = ARCHIVE_TAG_RE.search(text)
    if match:
        topic = match.group(1).strip()
        clean = ARCHIVE_TAG_RE.sub("", text).strip()
        return clean, topic
    return text, None


def save_to_archive(content: str, topic: str) -> Path:
    safe_topic = re.sub(r"[^\w가-힣\s-]", "", topic)[:50].strip().replace(" ", "-")
    filename = f"{date.today()}-{safe_topic}.md"
    ARCHIVE_DIR.mkdir(exist_ok=True)
    path = ARCHIVE_DIR / filename
    path.write_text(f"# {topic}\n\n날짜: {date.today()}\n\n---\n\n{content}")
    return path


def save_writing_sample(text: str, platform: str = "telegram", save_date: date | None = None) -> Path:
    if save_date is None:
        save_date = date.today()
    sample_dir = WRITING_DIR / platform
    sample_dir.mkdir(parents=True, exist_ok=True)
    idx = len(list(sample_dir.glob(f"{save_date}-*.md"))) + 1
    filename = f"{save_date}-{idx:03d}.md"
    path = sample_dir / filename
    path.write_text(f"날짜: {save_date}\n플랫폼: {platform}\n\n---\n\n{text}")
    return path


# ── 에이전트 실행 ───────────────────────────────────────────
AGENT_LABELS = {
    "brain":   "Brain Food ✍️",
    "venture": "Venture Strategy 📊",
    "atlas":   "Atlas 🗂️",
    "ai-org":  "AI Native Org 🤖",
}


async def run_agent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    agent_name: str,
    user_message: str,
):
    chat_id = update.effective_chat.id
    current_agent[chat_id] = agent_name

    label = AGENT_LABELS.get(agent_name, agent_name)
    await update.message.reply_text(f"⚙️ {label} 처리 중...")

    try:
        system = load_agent_system(agent_name)
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        reply = response.content[0].text
        clean_reply, archive_topic = extract_archive_tag(reply)

        if len(clean_reply) > 4000:
            clean_reply = clean_reply[:4000] + "\n\n…(생략)"

        await update.message.reply_text(clean_reply)

        if archive_topic:
            pending_archive[chat_id] = {"content": clean_reply, "topic": archive_topic}
            await update.message.reply_text(
                f"💾 이 내용을 아카이브할까요?\n"
                f"📌 제안 주제: *{archive_topic}*\n\n"
                f"'예' / '아니오' 또는 주제를 수정해서 답해주세요.",
                parse_mode="Markdown",
            )

    except Exception as e:
        await update.message.reply_text(f"오류: {str(e)[:300]}")


# ── 아카이브 응답 처리 ──────────────────────────────────────
async def handle_archive_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
):
    chat_id = update.effective_chat.id
    state = pending_archive.pop(chat_id)
    content = state["content"]
    suggested_topic = state["topic"]

    msg = message.strip().lower()
    if msg in ("아니오", "아니요", "no", "n", "노", "ㄴ"):
        await update.message.reply_text("아카이브 건너뜀.")
        return

    topic = suggested_topic if msg in ("예", "yes", "y", "네", "ㅇ") else message.strip()

    try:
        path = save_to_archive(content, topic)
        await update.message.reply_text(f"✅ 저장: `{path.name}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"저장 실패: {e}")


# ── 커맨드 핸들러 ───────────────────────────────────────────
def _make_cmd(agent_name: str, hint: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != HS_CHAT_ID:
            return
        msg = " ".join(context.args) if context.args else None
        if msg:
            await run_agent(update, context, agent_name, msg)
        else:
            current_agent[update.effective_chat.id] = agent_name
            await update.message.reply_text(hint)
    return handler


cmd_brain   = _make_cmd("brain",   "✍️ Brain Food 활성화. 어떤 글을 쓸까요?\n(포맷: LinkedIn / Telegram / 에세이)")
cmd_venture = _make_cmd("venture", "📊 Venture Strategy 활성화. 어떤 사업 기회를 분석할까요?")
cmd_atlas   = _make_cmd("atlas",   "🗂️ Atlas 활성화. 무엇을 도와드릴까요?")
cmd_ai      = _make_cmd("ai-org",  "🤖 AI Native Org 활성화. 어떤 워크플로우를 개선할까요?")


async def cmd_archive_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    files = sorted(ARCHIVE_DIR.glob("*.md"), reverse=True)[:10]
    if not files:
        await update.message.reply_text("아카이브가 비어있습니다.")
        return
    lines = [f"📚 최근 아카이브 ({len(files)}개)\n"]
    for f in files:
        lines.append(f"• `{f.stem}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_samples(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    platform = context.args[0].lower() if context.args else None
    platforms = [platform] if platform in ("telegram", "linkedin") else ["telegram", "linkedin"]

    lines = []
    for p in platforms:
        files = sorted((WRITING_DIR / p).glob("*.md"), reverse=True)[:10]
        if not files:
            continue
        lines.append(f"*{p.upper()}* ({len(files)}개)")
        for f in files:
            lines.append(f"• `{f.stem}`")
        lines.append("")

    if not lines:
        await update.message.reply_text("저장된 샘플이 없습니다.")
        return
    lines.append("삭제: `/delete [파일명]`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_delete_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    if not context.args:
        await update.message.reply_text("사용법: `/delete [파일명]`\n예: `/delete 2026-03-12-001`", parse_mode="Markdown")
        return

    stem = context.args[0].strip()
    deleted = []
    for p in ["telegram", "linkedin"]:
        path = WRITING_DIR / p / f"{stem}.md"
        if path.exists():
            path.unlink()
            deleted.append(f"{p}/{stem}.md")

    if deleted:
        await update.message.reply_text(f"🗑️ 삭제 완료: `{'`, `'.join(deleted)}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"`{stem}.md` 파일을 찾을 수 없습니다.", parse_mode="Markdown")


async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "사용법: /save [platform] [글 내용]\n\n"
            "예시:\n"
            "/save telegram 글 내용...\n"
            "/save linkedin 글 내용..."
        )
        return

    platform = context.args[0].lower()
    if platform not in ("telegram", "linkedin"):
        await update.message.reply_text("플랫폼은 telegram 또는 linkedin만 가능합니다.")
        return

    text = " ".join(context.args[1:]).strip()
    if not text:
        await update.message.reply_text("글 내용을 입력해주세요.")
        return

    if platform == "linkedin":
        pending_linkedin[update.effective_chat.id] = text
        await update.message.reply_text(
            "📅 날짜를 입력해주세요 (YYYY-MM-DD)\n오늘 날짜로 저장하려면 *오늘* 입력",
            parse_mode="Markdown",
        )
    else:
        try:
            path = save_writing_sample(text, platform=platform)
            await update.message.reply_text(f"✅ 저장: `{path.name}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"저장 실패: {e}")


async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.message.chat.id) != HS_CHAT_ID:
        return
    await query.answer()

    pending_file  = Path("/tmp/claude_pending_approval.json")
    response_file = Path("/tmp/claude_approval_response.txt")

    if not pending_file.exists():
        await query.edit_message_text("⏱️ 이미 처리됐거나 타임아웃된 요청입니다.")
        return

    info = json.loads(pending_file.read_text())

    if query.data == "approval_ok":
        response_file.write_text("ok")
        await query.edit_message_text(
            f"✅ *승인됨*\n툴: `{info['tool_name']}`\n`{info['detail'][:100]}`",
            parse_mode="Markdown"
        )
    else:
        response_file.write_text("no")
        await query.edit_message_text(
            f"❌ *거절됨*\n툴: `{info['tool_name']}`",
            parse_mode="Markdown"
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return
    await update.message.reply_text(
        "안녕하세요, HS. ARK Point 에이전트 시스템입니다.\n\n"
        "/brain   — Brain Food 글쓰기\n"
        "/venture — 사업 기회 분석\n"
        "/atlas   — Personal Ops\n"
        "/ai      — AI Native 조직\n"
        "/archive — 아카이브 조회\n"
        "/save    — 글 샘플 저장 (telegram/linkedin)"
    )


# ── LinkedIn 날짜 응답 처리 ─────────────────────────────────
async def handle_linkedin_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
):
    from datetime import datetime
    chat_id = update.effective_chat.id
    content = pending_linkedin.pop(chat_id)

    msg = message.strip()
    if msg in ("오늘", "today", ""):
        save_date = date.today()
    else:
        try:
            save_date = datetime.strptime(msg, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text(
                "날짜 형식이 올바르지 않습니다. YYYY-MM-DD 또는 *오늘* 입력해주세요.",
                parse_mode="Markdown",
            )
            pending_linkedin[chat_id] = content
            return

    try:
        path = save_writing_sample(content, platform="linkedin", save_date=save_date)
        await update.message.reply_text(f"✅ 저장: `{path.name}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"저장 실패: {e}")


# ── 메시지 핸들러 ───────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != HS_CHAT_ID:
        return

    msg = update.message
    chat_id = update.effective_chat.id
    message = msg.text or ""

    # 포워드된 메시지 → Brain Food 텔레그램 샘플로 저장
    if msg.forward_origin is not None:
        text = message.strip()
        if text:
            try:
                from telegram import MessageOriginChannel, MessageOriginUser
                origin = msg.forward_origin
                if hasattr(origin, "date") and origin.date:
                    save_date = origin.date.date()
                else:
                    save_date = date.today()
                path = save_writing_sample(text, platform="telegram", save_date=save_date)
                await msg.reply_text(f"✅ 포워드 저장: `{path.name}`", parse_mode="Markdown")
            except Exception as e:
                await msg.reply_text(f"저장 실패: {e}")
        return

    if chat_id in pending_archive:
        await handle_archive_response(update, context, message)
        return

    if chat_id in pending_linkedin:
        await handle_linkedin_date(update, context, message)
        return

    agent = current_agent.get(chat_id, "atlas")
    await run_agent(update, context, agent, message)


# ── Brain Food 채널 자동 저장 ───────────────────────────────
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BRAIN_FOOD_CHANNEL_ID:
        return
    post = update.channel_post
    if not post or str(post.chat.id) != BRAIN_FOOD_CHANNEL_ID:
        return
    text = post.text or post.caption or ""
    if not text.strip():
        return
    try:
        path = save_writing_sample(text, platform="telegram")
        print(f"[brain-food] 샘플 저장: {path.name}")
    except Exception as e:
        print(f"[brain-food] 저장 실패: {e}")


# ── 봇 실행 ────────────────────────────────────────────────
def main():
    app = Application.builder().token(HS_ORCHESTRATOR_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("brain",   cmd_brain))
    app.add_handler(CommandHandler("venture", cmd_venture))
    app.add_handler(CommandHandler("atlas",   cmd_atlas))
    app.add_handler(CommandHandler("ai",      cmd_ai))
    app.add_handler(CommandHandler("archive", cmd_archive_list))
    app.add_handler(CommandHandler("save",    cmd_save))
    app.add_handler(CommandHandler("samples", cmd_samples))
    app.add_handler(CommandHandler("delete",  cmd_delete_sample))
    app.add_handler(CallbackQueryHandler(handle_approval_callback, pattern="^approval_"))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(int(HS_CHAT_ID)),
        handle_message,
    ))

    if BRAIN_FOOD_CHANNEL_ID:
        app.add_handler(MessageHandler(
            filters.UpdateType.CHANNEL_POSTS,
            handle_channel_post,
        ))

    print("[bot] ARK Point 에이전트 시스템 시작...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
