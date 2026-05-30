from __future__ import annotations

import argparse
import asyncio
import base64
import email.message
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.header import Header
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DUMMY_DIR = ROOT / "dummy_mails"
OUTPUT_DIR = ROOT / "output"
REPORT_DIR = ROOT / "report"


CATEGORY_LABELS = {
    "spam": "스팸",
    "no_response": "무응답",
    "decision_required": "결정필요",
    "auto_reply": "답장완료",
    "schedule_update": "일정추가",
}

CATEGORY_ICONS = {
    "spam": "🚨",
    "no_response": "📋",
    "decision_required": "🚨",
    "auto_reply": "✅",
    "schedule_update": "📅",
}


def now_kst_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean_subject_for_reply(subject: str) -> str:
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def first_recipient(email: dict[str, Any]) -> str:
    recipients = email.get("to") or ["me@gmail.com"]
    if isinstance(recipients, list) and recipients:
        return recipients[0]
    return str(recipients)


@dataclass
class AgentResult:
    category: str
    confidence: float
    reason: str
    requires_user_decision: bool = False
    proposed_reply: str | None = None
    schedule_action: str = "none"
    schedule_conflict: dict[str, Any] | None = None
    gmail_action: str = "none"
    user_decision: str | None = None
    user_note: str | None = None
    email: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)

    @property
    def icon(self) -> str:
        return CATEGORY_ICONS.get(self.category, "•")


class LLMProvider:
    name = "base"

    def is_available(self) -> bool:
        return False

    async def analyze(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, force: bool = False) -> None:
        self.force = force
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def is_available(self) -> bool:
        return self.force or bool(self.api_key)

    async def analyze(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._analyze_sync, email_item, rule_hint)

    def _analyze_sync(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        prompt = make_llm_prompt(email_item, rule_hint)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You classify Korean emails for an email agent. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, force: bool = False) -> None:
        self.force = force
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1")

    def is_available(self) -> bool:
        return self.force or os.getenv("LLM_PROVIDER", "").lower() == "ollama" or self.server_is_running()

    def server_is_running(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url.rstrip('/')}/api/tags", timeout=0.5):
                return True
        except OSError:
            return False

    async def analyze(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._analyze_sync, email_item, rule_hint)

    def _analyze_sync(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": make_llm_prompt(email_item, rule_hint),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return json.loads(data.get("response", "{}"))


class LLMRouter:
    def __init__(self, provider_name: str | None = None) -> None:
        provider_name = (provider_name or os.getenv("LLM_PROVIDER", "auto")).lower()
        ordered: list[LLMProvider]
        if provider_name == "rules":
            ordered = []
        elif provider_name == "ollama":
            ordered = [OllamaProvider(force=True)]
        elif provider_name == "openai":
            ordered = [OpenAIProvider(force=True)]
        else:
            ordered = [OpenAIProvider(), OllamaProvider()]
        self.providers = ordered
        self.requested_provider = provider_name
        self.last_provider = "rules"

    async def analyze(self, email_item: dict[str, Any], rule_hint: dict[str, Any]) -> dict[str, Any]:
        for provider in self.providers:
            if not provider.is_available():
                continue
            try:
                result = await provider.analyze(email_item, rule_hint)
                self.last_provider = provider.name
                return normalize_llm_result(result, rule_hint)
            except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, KeyError):
                continue
        self.last_provider = "rules"
        return rule_hint


def llm_status_summary() -> str:
    openai_status = "사용 가능" if os.getenv("OPENAI_API_KEY") else "키 없음"
    ollama = OllamaProvider()
    ollama_status = f"감지됨 ({ollama.model})" if ollama.server_is_running() else "미감지"
    return f"OpenAI: {openai_status} | Ollama: {ollama_status}"


def make_llm_prompt(email_item: dict[str, Any], rule_hint: dict[str, Any]) -> str:
    schema = {
        "category": "spam | no_response | decision_required | auto_reply | schedule_update",
        "confidence": "0.0-1.0",
        "reason": "Korean short reason",
        "requires_user_decision": "boolean",
        "proposed_reply": "Korean reply body or null",
        "schedule_action": "none | add | conflict | review",
    }
    return textwrap.dedent(
        f"""
        다음 이메일을 분류하세요. 규칙 기반 힌트는 참고하되, 최종 판단은 메일 의미를 보고 하세요.

        JSON 스키마:
        {json.dumps(schema, ensure_ascii=False)}

        규칙 힌트:
        {json.dumps(rule_hint, ensure_ascii=False)}

        이메일:
        {json.dumps(email_item, ensure_ascii=False)}
        """
    ).strip()


def normalize_llm_result(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    category = result.get("category")
    if category not in CATEGORY_LABELS:
        category = fallback["category"]
    confidence = result.get("confidence", fallback.get("confidence", 0.7))
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = fallback.get("confidence", 0.7)
    return {
        "category": category,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(result.get("reason") or fallback.get("reason") or ""),
        "requires_user_decision": bool(
            result.get("requires_user_decision", fallback.get("requires_user_decision", False))
        ),
        "proposed_reply": result.get("proposed_reply", fallback.get("proposed_reply")),
        "schedule_action": result.get("schedule_action", fallback.get("schedule_action", "none")),
    }


class RuleEngine:
    spam_terms = [
        "당첨",
        "무료배송",
        "특가",
        "클릭",
        "쿠폰",
        "100만원",
        "기회를 놓치지",
        "수신거부",
    ]
    decision_terms = ["결정", "검토", "승인", "의견", "선택", "회의 안건", "예산안"]
    no_response_terms = ["merged", "점검 안내", "공지", "안내", "완료되었습니다", "추가 조치는 필요"]
    auto_reply_terms = ["오랜만", "밥 먹자", "시간 괜찮", "언제가 좋을지", "친한 동료"]

    def classify_hint(self, email_item: dict[str, Any]) -> dict[str, Any]:
        subject = email_item.get("subject", "")
        body = email_item.get("body", "")
        sender = email_item.get("sender_email", "")
        text = f"{subject}\n{body}".lower()

        if any(term.lower() in text for term in self.spam_terms) or "spam" in sender:
            return {
                "category": "spam",
                "confidence": 0.95,
                "reason": "광고/이벤트성 문구와 의심 발신자 패턴이 감지됨",
                "requires_user_decision": False,
                "proposed_reply": None,
                "schedule_action": "none",
            }

        if any(term.lower() in text for term in self.decision_terms):
            schedule_action = "conflict" if contains_date_time(text) else "review"
            return {
                "category": "decision_required",
                "confidence": 0.86,
                "reason": "사용자의 선택 또는 검토가 필요한 요청",
                "requires_user_decision": True,
                "proposed_reply": None,
                "schedule_action": schedule_action,
            }

        if any(term.lower() in text for term in self.auto_reply_terms):
            return {
                "category": "auto_reply",
                "confidence": 0.82,
                "reason": "친근한 개인 메일이며 간단한 회신 가능",
                "requires_user_decision": False,
                "proposed_reply": make_friendly_reply(email_item),
                "schedule_action": "none",
            }

        if any(term.lower() in text for term in self.no_response_terms):
            return {
                "category": "no_response",
                "confidence": 0.9,
                "reason": "공지 또는 시스템 알림으로 답장 불필요",
                "requires_user_decision": False,
                "proposed_reply": None,
                "schedule_action": "none",
            }

        return {
            "category": "no_response",
            "confidence": 0.55,
            "reason": "명확한 회신 요청이 없어 보류 없이 무응답 처리",
            "requires_user_decision": False,
            "proposed_reply": None,
            "schedule_action": "none",
        }


def contains_date_time(text: str) -> bool:
    return bool(re.search(r"20\d{2}-\d{2}-\d{2}|\d{1,2}:\d{2}|오전|오후|회의", text))


def make_friendly_reply(email_item: dict[str, Any]) -> str:
    name = email_item.get("sender_name", "친구")
    if name.endswith("희"):
        return f"안녕 {name}야! 나도 잘 지내고 있어. 서울 올라오는구나! 시간 괜찮으면 꼭 밥 먹자. 언제가 좋을지 이야기해줘 😄"
    return f"안녕하세요, {name}님. 연락 감사합니다. 가능한 시간 확인해서 다시 말씀드리겠습니다."


class MailFetchAgent:
    def __init__(self, source: str, limit: int) -> None:
        self.source = source
        self.limit = limit

    async def fetch(self) -> list[dict[str, Any]]:
        if self.source == "gmail":
            return await GmailClient().fetch_messages(self.limit)
        data = read_json(DUMMY_DIR / "emails.json", {"emails": []})
        return list(data.get("emails", []))[: self.limit]


class ClassificationAgent:
    def __init__(self, llm: LLMRouter) -> None:
        self.rules = RuleEngine()
        self.llm = llm

    async def classify(self, email_item: dict[str, Any]) -> AgentResult:
        rule_hint = self.rules.classify_hint(email_item)
        llm_result = await self.llm.analyze(email_item, rule_hint)
        if llm_result["category"] == "auto_reply" and not llm_result.get("proposed_reply"):
            llm_result["proposed_reply"] = make_friendly_reply(email_item)
        return AgentResult(email=email_item, **llm_result)


class SpamAgent:
    def __init__(self) -> None:
        self.path = DATA_DIR / "spam_db.json"

    def register(self, result: AgentResult) -> bool:
        data = read_json(self.path, {"spam_senders": []})
        senders = data.setdefault("spam_senders", [])
        sender = result.email.get("sender_email")
        if sender and sender not in senders:
            senders.append(sender)
            write_json(self.path, data)
            return True
        return False


class ScheduleAgent:
    def __init__(self) -> None:
        self.path = DATA_DIR / "schedule.json"
        self.events = read_json(self.path, {"events": []}).get("events", [])

    def enrich(self, result: AgentResult) -> AgentResult:
        if result.category != "decision_required":
            return result
        proposed = extract_schedule_window(result.email)
        if not proposed:
            return result
        conflict = self.find_conflict(proposed["from"], proposed["to"])
        if conflict:
            result.schedule_conflict = {
                "requested": proposed,
                "conflict": conflict,
                "alternative": suggest_alternative(result.email),
            }
            result.schedule_action = "conflict"
        else:
            result.schedule_conflict = {"requested": proposed, "conflict": None}
            result.schedule_action = "review"
        return result

    def find_conflict(self, start: str, end: str) -> dict[str, Any] | None:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
        except ValueError:
            return None
        for event in self.events:
            try:
                event_start = datetime.strptime(event["from"], "%Y-%m-%d %H:%M")
                event_end = datetime.strptime(event["to"], "%Y-%m-%d %H:%M")
            except (KeyError, ValueError):
                continue
            if start_dt < event_end and end_dt > event_start:
                return event
        return None


def extract_schedule_window(email_item: dict[str, Any]) -> dict[str, str] | None:
    text = f"{email_item.get('subject', '')}\n{email_item.get('body', '')}"
    match = re.search(
        r"(20\d{2}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*[~\-]\s*(20\d{2}-\d{2}-\d{2})?\s*(\d{1,2}:\d{2})",
        text,
    )
    if not match:
        return None
    start_date, start_time, end_date, end_time = match.groups()
    end_date = end_date or start_date
    return {"from": f"{start_date} {start_time}", "to": f"{end_date} {end_time}"}


def suggest_alternative(email_item: dict[str, Any]) -> str:
    body = email_item.get("body", "")
    match = re.search(r"대안:\s*(20\d{2}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*[~\-]\s*20\d{2}-\d{2}-\d{2}\s+\d{1,2}:\d{2})", body)
    if match:
        return match.group(1)
    return "대안 일정 확인 필요"


class ReplyAgent:
    def __init__(self, source: str) -> None:
        self.source = source

    async def handle(self, result: AgentResult) -> None:
        if result.category != "auto_reply" or not result.proposed_reply:
            return
        if self.source == "gmail":
            draft_id = await GmailClient().create_draft(result.email, result.proposed_reply)
            result.gmail_action = f"draft_created:{draft_id}"
            return
        self.save_dummy_sent_mail(result)
        result.gmail_action = "sent_dummy"

    def save_dummy_sent_mail(self, result: AgentResult) -> None:
        path = DUMMY_DIR / "sent_mails.json"
        data = read_json(path, {"sent_mails": []})
        sent = {
            "to": [result.email.get("sender_email", "")],
            "from": first_recipient(result.email),
            "subject": clean_subject_for_reply(result.email.get("subject", "")),
            "body": result.proposed_reply,
            "in_reply_to_msg_id": result.email.get("msg_id"),
            "thread_id": result.email.get("thread_id"),
            "date": now_kst_text(),
            "status": "sent_dummy",
        }
        sent_mails = data.setdefault("sent_mails", [])
        already_saved = any(
            item.get("in_reply_to_msg_id") == sent["in_reply_to_msg_id"] and item.get("status") == "sent_dummy"
            for item in sent_mails
        )
        if not already_saved:
            sent_mails.append(sent)
            write_json(path, data)


class GmailClient:
    def __init__(self) -> None:
        self.credentials_path = CONFIG_DIR / "credentials.json"
        self.token_path = CONFIG_DIR / "token.json"
        self.scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ]

    def _service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Gmail 연동 패키지가 설치되어 있지 않습니다. requirements.txt를 설치하세요.") from exc

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise RuntimeError("config/credentials.json 파일이 필요합니다.")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
                creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=creds)

    async def fetch_messages(self, limit: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_messages_sync, limit)

    def _fetch_messages_sync(self, limit: int) -> list[dict[str, Any]]:
        service = self._service()
        response = service.users().messages().list(userId="me", maxResults=limit, q="in:inbox").execute()
        messages = response.get("messages", [])
        results = []
        for message in messages:
            raw = service.users().messages().get(userId="me", id=message["id"], format="full").execute()
            results.append(convert_gmail_message(raw))
        return results

    async def create_draft(self, email_item: dict[str, Any], reply_body: str) -> str:
        return await asyncio.to_thread(self._create_draft_sync, email_item, reply_body)

    def _create_draft_sync(self, email_item: dict[str, Any], reply_body: str) -> str:
        service = self._service()
        msg = email.message.EmailMessage()
        msg["To"] = email_item.get("sender_email", "")
        msg["From"] = first_recipient(email_item)
        msg["Subject"] = str(Header(clean_subject_for_reply(email_item.get("subject", "")), "utf-8"))
        msg.set_content(reply_body)
        encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft = {"message": {"raw": encoded, "threadId": email_item.get("thread_id")}}
        created = service.users().drafts().create(userId="me", body=draft).execute()
        return created.get("id", "unknown")


def convert_gmail_message(raw: dict[str, Any]) -> dict[str, Any]:
    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    sender_name, sender_email = parse_sender(headers.get("from", ""))
    return {
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": headers.get("subject", "(제목 없음)"),
        "body": extract_gmail_body(raw.get("payload", {})),
        "to": [headers.get("to", "me@gmail.com")],
        "cc": [headers["cc"]] if headers.get("cc") else [],
        "date": headers.get("date", ""),
        "is_read": "UNREAD" not in raw.get("labelIds", []),
        "thread_id": raw.get("threadId"),
        "msg_id": raw.get("id"),
    }


def parse_sender(value: str) -> tuple[str, str]:
    match = re.match(r"(.+?)\s*<(.+?)>", value)
    if match:
        return match.group(1).strip('" '), match.group(2)
    return value, value


def extract_gmail_body(payload: dict[str, Any]) -> str:
    if payload.get("body", {}).get("data"):
        return decode_gmail_data(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return decode_gmail_data(part["body"]["data"])
    return ""


def decode_gmail_data(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


class ReportAgent:
    def __init__(self) -> None:
        self.results_path = OUTPUT_DIR / "results.json"
        self.reply_path = OUTPUT_DIR / "reply_drafts.json"
        self.report_path = REPORT_DIR / "email_report.md"

    def save(self, results: list[AgentResult]) -> None:
        write_json(self.results_path, {"generated_at": now_kst_text(), "results": [asdict(r) for r in results]})
        replies = [
            {
                "to": [r.email.get("sender_email", "")],
                "subject": clean_subject_for_reply(r.email.get("subject", "")),
                "body": r.proposed_reply,
                "status": r.gmail_action,
                "thread_id": r.email.get("thread_id"),
                "in_reply_to_msg_id": r.email.get("msg_id"),
            }
            for r in results
            if r.category == "auto_reply"
        ]
        write_json(self.reply_path, {"generated_at": now_kst_text(), "reply_drafts": replies})
        self.write_markdown(results)

    def write_markdown(self, results: list[AgentResult]) -> None:
        counts = count_results(results)
        lines = [
            "# 이메일 에이전트 처리 리포트",
            "",
            f"- 생성 시각: {now_kst_text()}",
            f"- 총 처리: {len(results)}개",
            f"- 의사결정: {counts['decision_required']}",
            f"- 일정추가: {counts['schedule_update']}",
            f"- 답장: {counts['auto_reply']}",
            f"- 무응답: {counts['no_response']}",
            f"- 스팸: {counts['spam']}",
            "",
            "## 처리 결과",
        ]
        for result in results:
            email_item = result.email
            lines.extend(
                [
                    "",
                    f"### {result.icon} {result.label} - {email_item.get('subject', '')}",
                    f"- 발신자: {email_item.get('sender_name')} <{email_item.get('sender_email')}>",
                    f"- 이유: {result.reason}",
                    f"- 신뢰도: {result.confidence:.2f}",
                ]
            )
            if result.proposed_reply:
                lines.append(f"- 답장: {result.proposed_reply}")
            if result.schedule_conflict:
                lines.append(f"- 일정 판단: `{json.dumps(result.schedule_conflict, ensure_ascii=False)}`")
            if result.user_decision:
                lines.append(f"- 사용자 판단: {result.user_decision}")
            if result.user_note:
                lines.append(f"- 사용자 메모: {result.user_note}")
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_results(results: list[AgentResult]) -> dict[str, int]:
    counts = {key: 0 for key in CATEGORY_LABELS}
    for result in results:
        counts[result.category] = counts.get(result.category, 0) + 1
    return counts


def print_progress(index: int, total: int, result: AgentResult, spam_new: bool = False) -> None:
    email_item = result.email
    suffix = "(신규)" if result.category == "spam" and spam_new else ""
    print(f"[{index}/{total}] {result.icon} {result.label}{suffix} | {email_item.get('subject', '')}")


def print_console_report(results: list[AgentResult], llm_provider: str) -> None:
    counts = count_results(results)
    print()
    print("=" * 68)
    print("📋 이메일 에이전트 처리 리포트")
    print(f"생성 시각: {now_kst_text()}")
    print(
        f"총 처리: {len(results)}개  |  의사결정 {counts['decision_required']}  |  "
        f"일정추가 {counts['schedule_update']}  |  답장 {counts['auto_reply']}  |  "
        f"무응답 {counts['no_response']}  |  스팸 {counts['spam']}"
    )
    print(f"판단 엔진: {llm_provider}")
    print("=" * 68)

    section("🚨 의사결정 필요", [r for r in results if r.category == "decision_required"], print_decision)
    section("📅 일정 추가됨", [r for r in results if r.category == "schedule_update"], print_basic_or_empty)
    section("✅ 답장 완료", [r for r in results if r.category == "auto_reply"], print_reply)
    section("📋 응답 불필요", [r for r in results if r.category == "no_response"], print_basic_or_empty)
    section("🚨 스팸 처리", [r for r in results if r.category == "spam"], print_spam)


def section(title: str, items: list[AgentResult], printer: Any) -> None:
    print()
    print(f"{title} ({len(items)}개)")
    print("-" * 52)
    if not items:
        print("(없음)")
        return
    for item in items:
        printer(item)


def print_basic_or_empty(result: AgentResult) -> None:
    email_item = result.email
    print(f"📌 발신자 : {email_item.get('sender_name')} <{email_item.get('sender_email')}>")
    print(f"   제목   : {email_item.get('subject')}")
    print(f"   이유   : {result.reason}")
    print()


def print_decision(result: AgentResult) -> None:
    email_item = result.email
    print(f"📌 발신자 : {email_item.get('sender_name')} <{email_item.get('sender_email')}>")
    print(f"   제목   : {email_item.get('subject')}")
    if result.schedule_conflict:
        requested = result.schedule_conflict.get("requested", {})
        conflict = result.schedule_conflict.get("conflict")
        alternative = result.schedule_conflict.get("alternative")
        if conflict:
            print(
                f"   일정 충돌: {requested.get('from')} ~ {requested.get('to')} "
                f"({conflict.get('event_name')}) -> 대안: {alternative}"
            )
    print(f"   {summarize_body(email_item.get('body', ''))}")
    if result.user_decision:
        print(f"   사용자 판단: {result.user_decision} ({result.user_note})")
    print()


def print_reply(result: AgentResult) -> None:
    email_item = result.email
    print(f"🗓 발신자 : {email_item.get('sender_name')} <{email_item.get('sender_email')}>")
    print(f"   제목   : {email_item.get('subject')}")
    print(f"   관계   : 친한 동료  |  톤 : 친근한 어조")
    print(f"   답장   : {result.proposed_reply}")
    print(f"   저장   : {result.gmail_action}")
    print()


def print_spam(result: AgentResult) -> None:
    email_item = result.email
    print(f"🚫 발신자 : {email_item.get('sender_name')} <{email_item.get('sender_email')}>")
    print(f"   제목   : {email_item.get('subject')}")
    if result.gmail_action == "review_only_no_spam_db":
        print("   처리   : 검토만 수행 (스팸 DB 미등록)")
    else:
        print("   처리   : 스팸 DB 등록")
    print()


def summarize_body(body: str) -> str:
    text = " ".join(body.split())
    return text[:120] + ("..." if len(text) > 120 else "")


async def run_pipeline(args: argparse.Namespace) -> list[AgentResult]:
    ensure_runtime_files()
    fetcher = MailFetchAgent(args.source, args.limit)
    llm_choice = getattr(args, "llm", "auto")
    classifier = ClassificationAgent(LLMRouter(llm_choice))
    spam_agent = SpamAgent()
    schedule_agent = ScheduleAgent()
    reply_agent = ReplyAgent(args.source)
    review_only = bool(getattr(args, "review_only", False))

    if review_only:
        print("🔎 검토 전용 모드: 메일을 읽고 분류하지만 Draft/스팸 DB 변경은 하지 않습니다.")
        print()
    print(f"🧠 LLM 선택: {llm_choice} ({llm_status_summary()})")
    print()

    emails = await fetcher.fetch()
    tasks = [classifier.classify(email_item) for email_item in emails]
    classified = await asyncio.gather(*tasks)
    results: list[AgentResult] = []

    for index, result in enumerate(classified, start=1):
        result = schedule_agent.enrich(result)
        spam_new = False
        if result.category == "spam":
            if review_only:
                result.gmail_action = "review_only_no_spam_db"
            else:
                spam_new = spam_agent.register(result)
        if review_only and result.category == "auto_reply":
            result.gmail_action = "review_only_no_draft"
        elif not review_only:
            await reply_agent.handle(result)
        print_progress(index, len(classified), result, spam_new)
        results.append(result)

    handle_interactive_decisions(results, args.interactive)
    ReportAgent().save(results)
    print_console_report(results, classifier.llm.last_provider)
    return results


def handle_interactive_decisions(results: list[AgentResult], interactive: bool) -> None:
    decision_items = [r for r in results if r.requires_user_decision]
    if not decision_items:
        return
    if not interactive or not sys.stdin.isatty():
        for result in decision_items:
            result.user_decision = "pending"
            result.user_note = "사용자 판단 대기"
        return

    print()
    print("=" * 68)
    print("🧑 사용자 판단 입력")
    print("각 항목에 대해 선택을 남깁니다. Enter만 누르면 보류 처리됩니다.")
    print("=" * 68)
    for index, result in enumerate(decision_items, start=1):
        email_item = result.email
        print()
        print(f"[{index}/{len(decision_items)}] {email_item.get('subject')}")
        print(f"발신자: {email_item.get('sender_name')} <{email_item.get('sender_email')}>")
        print(summarize_body(email_item.get("body", "")))
        if result.schedule_conflict:
            print(f"일정 판단: {json.dumps(result.schedule_conflict, ensure_ascii=False)}")
        print("선택: 1) 보류  2) 승인  3) 거절  4) 추가 검토")
        choice = input("판단 번호 [1]: ").strip() or "1"
        mapping = {"1": "pending", "2": "approved", "3": "rejected", "4": "needs_more_review"}
        result.user_decision = mapping.get(choice, "pending")
        note = input("메모(선택): ").strip()
        result.user_note = note or "사용자 판단 기록됨"


def ensure_runtime_files() -> None:
    for path in (OUTPUT_DIR, REPORT_DIR, DATA_DIR, DUMMY_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not (DUMMY_DIR / "sent_mails.json").exists():
        write_json(DUMMY_DIR / "sent_mails.json", {"sent_mails": []})
    if not (DATA_DIR / "spam_db.json").exists():
        write_json(DATA_DIR / "spam_db.json", {"spam_senders": []})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gmail/dummy multi-agent email assistant")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="메일 에이전트를 실행합니다.")
    run.add_argument("--source", choices=["dummy", "gmail"], default="dummy")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--llm", choices=["auto", "openai", "ollama", "rules"], default="auto")
    run.add_argument("--interactive", action="store_true", help="시연용 플래그입니다. 현재 자동 승인 정책으로 동작합니다.")
    run.add_argument("--report", action="store_true", help="시연용 플래그입니다. 리포트는 항상 생성됩니다.")
    run.add_argument("--review-only", action="store_true", help="메일 검토만 수행하고 Draft/스팸 DB 변경을 건너뜁니다.")

    review = subparsers.add_parser("review-gmail", help="실제 Gmail 메일을 읽어 검토 전용 리포트를 생성합니다.")
    review.add_argument("--limit", type=int, default=20)
    review.add_argument("--llm", choices=["auto", "openai", "ollama", "rules"], default="auto")
    review.add_argument("--interactive", action="store_true")
    review.add_argument("--report", action="store_true")

    subparsers.add_parser("auth-gmail", help="Gmail OAuth 토큰을 생성합니다.")
    return parser


async def main_async(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "auth-gmail":
        GmailClient()._service()
        print("Gmail OAuth 인증이 완료되었습니다.")
        return 0
    if args.command == "review-gmail":
        args.source = "gmail"
        args.review_only = True
        await run_pipeline(args)
        return 0
    if args.command in (None, "run"):
        if args.command is None:
            args = parser.parse_args(["run"])
        await run_pipeline(args)
        return 0
    parser.print_help()
    return 1


def main() -> None:
    try:
        raise SystemExit(asyncio.run(main_async()))
    except KeyboardInterrupt:
        print("\n사용자가 실행을 중단했습니다.")
        raise SystemExit(130)
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
