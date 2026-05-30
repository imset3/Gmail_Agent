from __future__ import annotations

import argparse
import asyncio
import sys

from agent import llm_status_summary, main_async


LLM_CHOICES = {"1": "auto", "2": "openai", "3": "ollama", "4": "rules"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="간편 실행 메뉴")
    parser.add_argument("--dummy", action="store_true", help="더미 메일 모드로 바로 실행")
    parser.add_argument("--gmail", action="store_true", help="Gmail API 모드로 바로 실행")
    parser.add_argument("--review-gmail", action="store_true", help="실제 Gmail 메일을 읽어 검토 전용으로 실행")
    parser.add_argument("--auth", action="store_true", help="Gmail OAuth 인증 실행")
    parser.add_argument("--llm", choices=["auto", "openai", "ollama", "rules"], default="auto", help="LLM 실행 방식")
    parser.add_argument("--limit", type=int, default=20, help="Gmail에서 가져올 최대 메일 수")
    return parser


def ask_llm_choice() -> str:
    print()
    print("LLM 실행 방식")
    print(f"현재 상태: {llm_status_summary()}")
    print("1. 자동 선택(OpenAI 우선, 없으면 Ollama, 실패 시 규칙)")
    print("2. OpenAI 사용")
    print("3. Ollama 로컬 사용")
    print("4. 규칙 기반만 사용")
    choice = input("선택 [1]: ").strip() or "1"
    return LLM_CHOICES.get(choice, "auto")


async def run_menu(limit: int, llm: str) -> int:
    print("=" * 54)
    print("Gmail Multi-Agent Email Assistant")
    print("=" * 54)
    print("1. 더미 메일로 실행")
    print("2. 실제 Gmail 메일 검토하기")
    print("3. 실제 Gmail 실행하기(Draft 생성 가능)")
    print("4. Gmail 인증하기")
    print("5. 종료")
    print()

    choice = input("선택 [1]: ").strip() or "1"
    if choice == "1":
        selected_llm = ask_llm_choice()
        return await main_async(["run", "--source", "dummy", "--llm", selected_llm, "--interactive", "--report"])
    if choice == "2":
        selected_llm = ask_llm_choice()
        return await main_async(
            ["review-gmail", "--limit", str(limit), "--llm", selected_llm, "--interactive", "--report"]
        )
    if choice == "3":
        selected_llm = ask_llm_choice()
        return await main_async(
            ["run", "--source", "gmail", "--limit", str(limit), "--llm", selected_llm, "--interactive", "--report"]
        )
    if choice == "4":
        return await main_async(["auth-gmail"])
    if choice == "5":
        print("종료합니다.")
        return 0

    print("알 수 없는 선택입니다.")
    return 1


async def main() -> int:
    args = build_parser().parse_args()
    selected = sum([args.dummy, args.gmail, args.review_gmail, args.auth])
    if selected > 1:
        print("--dummy, --gmail, --review-gmail, --auth 중 하나만 선택하세요.", file=sys.stderr)
        return 2
    if args.dummy:
        return await main_async(["run", "--source", "dummy", "--llm", args.llm, "--interactive", "--report"])
    if args.gmail:
        return await main_async(
            ["run", "--source", "gmail", "--limit", str(args.limit), "--llm", args.llm, "--interactive", "--report"]
        )
    if args.review_gmail:
        return await main_async(["review-gmail", "--limit", str(args.limit), "--llm", args.llm, "--interactive", "--report"])
    if args.auth:
        return await main_async(["auth-gmail"])
    return await run_menu(args.limit, args.llm)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
