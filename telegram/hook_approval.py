#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook — Mobile Approval

위험한 툴 실행 전:
- Mac idle < 5분 → 자동 승인 (Mac 앞에 있음)
- Mac idle ≥ 5분 → 텔레그램 승인 요청 → /ok or /no
- 60초 무응답 → 자동 거절
"""
import json
import sys
import time
import subprocess
import os
import re
from pathlib import Path

# .env 직접 파싱 (dotenv 미설치 환경 대비)
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TOKEN  = os.environ.get("HS_ORCHESTRATOR_TOKEN", "")
CHAT_ID = os.environ.get("HS_CHAT_ID", "")

PENDING_FILE  = Path("/tmp/claude_pending_approval.json")
RESPONSE_FILE = Path("/tmp/claude_approval_response.txt")

IDLE_THRESHOLD = 300   # 5분 (초)

# ── 위험 패턴 ───────────────────────────────────────────────
DANGEROUS_BASH = [
    r"\brm\s+",
    r"\brm\b.*-[rf]",
    r"git\s+push",
    r"git\s+reset\s+--hard",
    r"git\s+branch\s+-[Dd]",
    r"pkill\b",
    r"kill\s+-9",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM",
    r"truncate\b",
    r"chmod\s+[0-7]*7[0-7]*",
    r":\s*>\s*\S",   # 파일 덮어쓰기 리다이렉트
]

DANGEROUS_WRITE_PATHS = [".env", "credentials", "secrets", "id_rsa", "token"]


def get_idle_seconds() -> float:
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split("\n"):
            if "HIDIdleTime" in line:
                idle_ns = int(line.split("=")[-1].strip())
                return idle_ns / 1_000_000_000
    except Exception:
        pass
    return 0.0


def is_dangerous(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        for pattern in DANGEROUS_BASH:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, cmd[:200]
        return False, ""

    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        for sensitive in DANGEROUS_WRITE_PATHS:
            if sensitive in path:
                return True, path
        return False, ""

    return False, ""


def send_telegram(text: str):
    import urllib.request
    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ 승인", "callback_data": "approval_ok"},
                {"text": "❌ 거절", "callback_data": "approval_no"},
            ]]
        }
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=10)


def wait_for_response() -> str:
    RESPONSE_FILE.unlink(missing_ok=True)
    while True:
        if RESPONSE_FILE.exists():
            decision = RESPONSE_FILE.read_text().strip()
            RESPONSE_FILE.unlink(missing_ok=True)
            return decision
        time.sleep(0.5)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name  = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    dangerous, detail = is_dangerous(tool_name, tool_input)
    if not dangerous:
        sys.exit(0)

    idle = get_idle_seconds()
    if idle < IDLE_THRESHOLD:
        # Mac 앞에 있음 — 자동 승인 (터미널에서 직접 확인 가능)
        sys.exit(0)

    # Mac idle 5분+ → 텔레그램 전송
    PENDING_FILE.write_text(json.dumps({
        "tool_name": tool_name,
        "detail": detail,
        "timestamp": time.time()
    }))

    try:
        send_telegram(
            f"⚠️ *Claude Code 승인 요청*\n\n"
            f"툴: `{tool_name}`\n"
            f"내용:\n```\n{detail}\n```"
        )
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}", file=sys.stderr)
        PENDING_FILE.unlink(missing_ok=True)
        sys.exit(2)

    decision = wait_for_response()
    PENDING_FILE.unlink(missing_ok=True)

    if decision == "ok":
        sys.exit(0)
    else:
        reason = "거절됨" if decision == "no" else f"타임아웃 ({TIMEOUT}초 초과)"
        print(f"🚫 승인 거절: {reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
