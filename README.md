# Gmail Multi-Agent Email Assistant

캡쳐 예시처럼 메일을 분류하고, 스팸 DB/일정/답장/사용자 판단 필요 항목을 리포트하는 Python CLI 과제 프로젝트입니다.

## 빠른 실행

가장 쉬운 실행:

```bash
python3 start.py
```

메뉴 없이 바로 실행:

```bash
python3 start.py --dummy
python3 start.py --gmail --limit 20
python3 start.py --auth
```

Windows에서 ZIP으로 받은 경우:

```text
RUN_WINDOWS.bat
```

Windows에서 바로 더미 모드만 실행:

```text
RUN_DUMMY_WINDOWS.bat
```

Windows에서 Gmail 인증:

```text
AUTH_GMAIL_WINDOWS.bat
```

기존 상세 명령:

```bash
python main.py run --source dummy --interactive --report
```

또는 기본값으로 실행할 수 있습니다.

```bash
python main.py
```

## 출력 파일

- `dummy_mails/sent_mails.json`: 더미 모드에서 자동답장한 발신 메일
- `output/results.json`: 전체 Agent 처리 결과
- `output/reply_drafts.json`: 생성된 답장 초안
- `report/email_report.md`: 제출용 Markdown 리포트
- `data/spam_db.json`: 신규 스팸 발신자 목록

## LLM 설정

설정이 없으면 규칙 기반 fallback으로 실행됩니다.

OpenAI:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4o-mini
```

Ollama:

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.1
```

## Gmail API

Gmail 모드는 실제 발송하지 않고 Draft 초안만 생성합니다.

1. Google Cloud Console에서 Gmail API를 활성화합니다.
2. OAuth Desktop App credentials를 내려받아 `config/credentials.json`에 둡니다.
3. 의존성을 설치합니다.

```bash
pip install -r requirements.txt
python main.py auth-gmail
python main.py run --source gmail --limit 20 --interactive --report
```

## 제출 문서

브라우저로 아래 파일을 열면 전체 개념, 진행 내역, 실행 방법, 오류 해결 방법을 보기 좋게 확인할 수 있습니다.

```text
docs/submission_guide.html
```

## 구조

```text
config/
data/
dummy_mails/
output/
prompts/
report/
tools/
agent.py
main.py
requirements.txt
README.md
```
