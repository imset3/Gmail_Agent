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
python3 start.py --dummy --llm ollama
python3 start.py --review-gmail --limit 20 --llm openai
python3 start.py --gmail --limit 20 --llm auto
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

Windows에서 실제 Gmail 메일 검토만 실행:

```text
REVIEW_GMAIL_WINDOWS.bat
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

실행할 때 LLM 방식을 선택할 수 있습니다.

```bash
python3 start.py --dummy --llm auto
python3 start.py --dummy --llm openai
python3 start.py --dummy --llm ollama
python3 start.py --dummy --llm rules
```

- `auto`: OpenAI 키가 있으면 OpenAI를 우선 사용하고, 없으면 로컬 Ollama를 감지합니다. 둘 다 실패하면 규칙 기반 fallback으로 실행됩니다.
- `openai`: 현재 환경에 연결된 OpenAI API를 우선 사용합니다.
- `ollama`: 로컬 Ollama 서버를 사용합니다.
- `rules`: 외부 LLM 없이 규칙 기반으로만 실행합니다.

메뉴 실행인 `python3 start.py`에서는 현재 OpenAI/Ollama 감지 상태를 보여준 뒤 선택할 수 있습니다.

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
ollama serve
ollama pull llama3.1
```

## Gmail API

Gmail API는 두 가지 방식으로 사용할 수 있습니다.

- 검토 전용 모드: 실제 Gmail 메일을 읽고 분류/리포트만 생성하며 Draft를 만들지 않습니다.
- Gmail 실행 모드: 실제 Gmail 메일을 읽고, 자동답장 가능한 메일은 Gmail Draft 초안까지 생성합니다.

1. Google Cloud Console에서 Gmail API를 활성화합니다.
2. OAuth Desktop App credentials를 내려받아 `config/credentials.json`에 둡니다.
3. 의존성을 설치합니다.

```bash
pip install -r requirements.txt
python main.py auth-gmail
python main.py review-gmail --limit 20 --llm auto --interactive --report
python main.py run --source gmail --limit 20 --llm openai --interactive --report
```

가장 안전한 실제 Gmail 시연은 아래 명령입니다.

```bash
python3 start.py --review-gmail --limit 20 --llm auto
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
