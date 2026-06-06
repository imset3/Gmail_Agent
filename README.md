# Gmail Multi-Agent Email Assistant

Gmail 또는 샘플 메일 데이터를 읽어 메일을 분류하고, 스팸 목록, 일정 검토, 답장 초안, 사용자 판단 필요 항목을 리포트하는 Python CLI 도구입니다.

기본 실행은 샘플 데이터로 동작합니다. Gmail API를 연결하면 실제 받은편지함을 읽어 같은 파이프라인으로 검토할 수 있고, 자동 답장 후보는 Gmail Draft 초안으로만 저장합니다.

## 빠른 실행

```bash
python3 start.py
```

메뉴 없이 바로 실행하려면 아래 명령을 사용합니다.

```bash
python3 start.py --dummy
python3 start.py --dummy --llm rules
python3 start.py --dummy --llm ollama
python3 start.py --review-gmail --limit 20 --llm auto
python3 start.py --auth
```

상세 CLI를 직접 호출할 수도 있습니다.

```bash
python3 main.py run --source dummy --interactive --report
python3 main.py review-gmail --limit 20 --llm rules --interactive --report
```

Windows에서는 포함된 실행 파일을 사용할 수 있습니다.

```text
RUN_WINDOWS.bat
RUN_DUMMY_WINDOWS.bat
AUTH_GMAIL_WINDOWS.bat
REVIEW_GMAIL_WINDOWS.bat
```

## 출력 파일

실행 중 생성되는 파일은 Git에서 제외됩니다.

- `dummy_mails/sent_mails.json`: 샘플 모드에서 저장한 답장 기록
- `output/results.json`: 전체 처리 결과
- `output/reply_drafts.json`: 답장 초안 결과
- `report/email_report.md`: Markdown 리포트
- `data/spam_db.json`: 신규 스팸 발신자 목록

## LLM 설정

실행할 때 판단 방식을 선택할 수 있습니다.

```bash
python3 start.py --dummy --llm auto
python3 start.py --dummy --llm openai
python3 start.py --dummy --llm ollama
python3 start.py --dummy --llm rules
```

- `auto`: OpenAI 키가 있으면 OpenAI를 먼저 사용하고, 없으면 로컬 Ollama를 감지합니다. 둘 다 실패하면 규칙 기반으로 실행합니다.
- `openai`: OpenAI API를 사용합니다.
- `ollama`: 로컬 Ollama 서버를 사용합니다.
- `rules`: 외부 LLM 없이 규칙 기반으로만 실행합니다.

OpenAI:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_api_key
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

## Gmail API 연결

Gmail API는 두 가지 모드로 사용할 수 있습니다.

- 검토 전용 모드: 실제 Gmail 메일을 읽고 분류/리포트만 생성합니다. Draft와 스팸 DB는 변경하지 않습니다.
- Gmail 실행 모드: 실제 Gmail 메일을 읽고, 자동 답장 가능한 메일은 Gmail Draft 초안으로 저장합니다.

설정 순서:

1. Google Cloud Console에서 Gmail API를 활성화합니다.
2. OAuth Desktop App credentials를 내려받아 `config/credentials.json`에 둡니다.
3. 의존성을 설치합니다.

```bash
pip install -r requirements.txt
python3 main.py auth-gmail
python3 main.py review-gmail --limit 20 --llm auto --interactive --report
python3 main.py run --source gmail --limit 20 --llm openai --interactive --report
```

실제 계정에서는 먼저 검토 전용 모드로 확인하는 편이 좋습니다.

```bash
python3 start.py --review-gmail --limit 20 --llm auto
```

## 문서

브라우저에서 아래 파일을 열면 구조, 실행 방법, Gmail API 연결 흐름을 더 자세히 볼 수 있습니다.

```text
docs/submission_guide.html
```

## 프로젝트 구조

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
start.py
requirements.txt
README.md
```
