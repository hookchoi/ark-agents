"""
야간 증류 스크립트 — 매일 23:00
1. 오늘 일기 작성 (없으면 생성)
2. M30 → M90 승급 판단 후 MEMORY.md 업데이트
3. git commit
"""
import os
import subprocess
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).parent / ".env")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

WORKSPACES = {
    "hs-partner": Path.home() / "workspace/ai/hs-partner",
    "hs-intelli": Path.home() / "workspace/ai/hs-intelli",
}


def distill(agent_name: str, workspace: Path):
    today = date.today()
    diary_path = workspace / "memory" / f"{today}.md"
    memory_path = workspace / "MEMORY.md"

    memory_content = memory_path.read_text() if memory_path.exists() else ""
    diary_content = diary_path.read_text() if diary_path.exists() else ""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=f"당신은 {agent_name}입니다. 오늘 하루를 정리하는 야간 증류 작업을 수행합니다. 한국어로 답변하세요.",
        messages=[{
            "role": "user",
            "content": f"""현재 MEMORY.md:
{memory_content}

오늘 일기 ({today}):
{diary_content if diary_content else "(없음)"}

작업:
1. 오늘 일기가 없으면 MEMORY.md 맥락 기반으로 간단한 일기를 작성해줘 (2-3줄)
2. M30 항목 중 90일 이상 기억할 가치가 있는 것은 M90으로 이동
3. 만료된 M30 항목 제거 (expires 날짜 지난 것)
4. 업데이트된 MEMORY.md 전체를 출력

반드시 아래 형식으로 출력:
DIARY:
(일기 내용, 이미 있으면 "SKIP")

MEMORY:
(업데이트된 MEMORY.md 전체 내용)"""
        }]
    )

    result = response.content[0].text

    if "DIARY:" not in result or "MEMORY:" not in result:
        print(f"[{agent_name}] 파싱 실패 — 스킵")
        return

    diary_part = result.split("DIARY:")[1].split("MEMORY:")[0].strip()
    memory_part = result.split("MEMORY:")[1].strip()

    diary_path.parent.mkdir(exist_ok=True)
    if not diary_path.exists() and diary_part != "SKIP":
        diary_path.write_text(diary_part)
        print(f"[{agent_name}] 일기 작성: {diary_path.name}")

    memory_path.write_text(memory_part)
    print(f"[{agent_name}] MEMORY.md 업데이트 완료")


def git_commit(workspace: Path, agent_name: str):
    today = date.today()
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace, capture_output=True, text=True
        )
        if not result.stdout.strip():
            print(f"[{agent_name}] 변경사항 없음 — 커밋 스킵")
            return
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"nightly: {today} 야간 증류"],
            cwd=workspace, check=True
        )
        print(f"[{agent_name}] git commit 완료")
    except subprocess.CalledProcessError as e:
        print(f"[{agent_name}] git 오류: {e}")


if __name__ == "__main__":
    for name, workspace in WORKSPACES.items():
        print(f"\n[{name}] 야간 증류 시작...")
        distill(name, workspace)
        git_commit(workspace, name)
    print("\n야간 증류 완료")
