from __future__ import annotations

import argparse
import asyncio
import sys

from agent import main_async


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="간편 실행 메뉴")
    parser.add_argument("--dummy", action="store_true", help="더미 메일 모드로 바로 실행")
    parser.add_argument("--gmail", action="store_true", help="Gmail API 모드로 바로 실행")
    parser.add_argument("--auth", action="store_true", help="Gmail OAuth 인증 실행")
    parser.add_argument("--limit", type=int, default=20, help="Gmail에서 가져올 최대 메일 수")
    return parser


async def run_menu(limit: int) -> int:
    print("=" * 54)
    print("Gmail Multi-Agent Email Assistant")
    print("=" * 54)
    print("1. 더미 메일로 실행")
    print("2. 실제 Gmail로 실행")
    print("3. Gmail 인증하기")
    print("4. 종료")
    print()

    choice = input("선택 [1]: ").strip() or "1"
    if choice == "1":
        return await main_async(["run", "--source", "dummy", "--interactive", "--report"])
    if choice == "2":
        return await main_async(
            ["run", "--source", "gmail", "--limit", str(limit), "--interactive", "--report"]
        )
    if choice == "3":
        return await main_async(["auth-gmail"])
    if choice == "4":
        print("종료합니다.")
        return 0

    print("알 수 없는 선택입니다.")
    return 1


async def main() -> int:
    args = build_parser().parse_args()
    selected = sum([args.dummy, args.gmail, args.auth])
    if selected > 1:
        print("--dummy, --gmail, --auth 중 하나만 선택하세요.", file=sys.stderr)
        return 2
    if args.dummy:
        return await main_async(["run", "--source", "dummy", "--interactive", "--report"])
    if args.gmail:
        return await main_async(
            ["run", "--source", "gmail", "--limit", str(args.limit), "--interactive", "--report"]
        )
    if args.auth:
        return await main_async(["auth-gmail"])
    return await run_menu(args.limit)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
