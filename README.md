# My LifeRoad — 외국인 금융 라이프케어 AI 에이전트

데이콘 JB금융그룹 Fin:AI Challenge 출전작. 외국인의 한국 금융 생활을 입국부터 귀국까지 동행하는 능동형 AI 에이전트다.

> **처음 들어온 팀원은 이 README만 끝까지 읽으면 된다.** 무엇을 만드는지, 어떻게 실행하는지, 내 부문을 어떻게 붙이는지가 다 있다.

---

## 1. 이게 뭐야 (한 장 그림)

외국인 페르소나(베트남 E-9 근로자 / 네팔 D-2 유학생)에게 **묻기 전에 먼저** 금융 손실과 마감을 잡아주는 에이전트다. 챗봇이 아니라 "능동 점검 + 비자별 정밀 자문 + 서류 대리작성"을 한다.

세 부문이 각각 독립 모듈이고, 공용 Streamlit 프론트 하나가 LLM을 통해 부문 tool을 호출한다.

```
frontend/        공용 Streamlit 챗 UI + LLM 공급자 스위치
shared/
  personas.py    페르소나 2명 (전 부문 공용, 동결)
  system_prompt.py  공용 시스템 프롬프트
  registry.py    부문 자동 발견 + 병합 (★ 손댈 일 거의 없음)
mcp_servers/
  asset/         자산 부문 (구현 완료, 팀 표준 예시)
  docs/          서류행정 부문 (구현 완료)
  <내 부문>/      여기에 폴더만 넣으면 자동 연결된다
CONTRACT.md      tool 인터페이스 규약 (부문 만들 때 필독)
AGENT_BRIEF.md   AI에게 부문 작업을 맡길 때 주는 지시문
```

---

## 2. 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # 키 입력 (아래 3번 참고)
streamlit run frontend/app.py
```

브라우저가 열리면 사이드바에서 페르소나를 고르고 "능동 점검 실행"을 누르거나 대화창에 질문한다.

### 테스트
```bash
source .venv/bin/activate
python -m pytest -v
```

---

## 3. LLM 공급자 (무료/유료 스위치)

`.env`의 `LLM_PROVIDER` 한 줄로 바꾼다. 코드는 그대로다.

| 공급자 | 설정값 | 키 | 비용 | 특징 |
|---|---|---|---|---|
| **Gemini** | `gemini` | `GEMINI_API_KEY` (AIza…) | 무료 1,500회/일 | 한국어 안정 + tool 정확. **현재 기본 권장** |
| Groq | `groq` | `GROQ_API_KEY` (gsk_…) | 무료 14,400회/일 | 초고속(0.7초). tool 호출 보정 작업 중 |
| Ollama | `ollama` | 불필요 | 무료 로컬 | 인터넷 없이 구동. 느리고 한국어 가끔 깨짐 |
| Claude | `claude` | `ANTHROPIC_API_KEY` | 유료 | 본선용. 최고 품질 |

- 무료 키 발급: Gemini는 https://aistudio.google.com/apikey , Groq는 https://console.groq.com (둘 다 카드 불필요).
- `.env`는 깃에 안 올라간다(`.gitignore`). 각자 자기 키를 `.env`에 넣는다. 견본은 `.env.example`.

---

## 4. 내 부문을 붙이는 법 (★ 자동 연결)

**핵심: `mcp_servers/` 아래에 규약대로 만든 폴더를 넣기만 하면 앱 재시작 시 자동으로 연결된다.** `registry.py`나 `app.py`를 손댈 필요 없다.

### 절차
1. 이 repo를 clone 한다. (GitHub: `ParkSiHyun28/liferoad_ai_agent`)
2. **CONTRACT.md를 읽는다.** (입출력 규약. 이걸 어기면 통합이 깨진다)
3. `mcp_servers/asset` 폴더를 자기 부문 영문명으로 복제한다. (예: `mcp_servers/fraud/`)
   - 폴더명은 **반드시 영문**. 한글이면 import가 깨진다.
4. `tools.py`의 함수를 자기 부문 tool로 바꾼다. 입출력 4키 규약(`summary/detail/numbers/card`)은 그대로 지킨다.
5. `schemas.py`의 `TOOL_SCHEMAS`도 자기 tool에 맞게 바꾼다.
6. `python -m pytest`로 검증한다. **가드레일(tests/test_contract.py)이 새 부문도 자동 검사**한다. 통과하면 규약 OK.
7. push 하거나, 폴더를 압축해 보내면 받는 쪽이 `mcp_servers/`에 풀어 넣는다. 끝.

### 폴더만 넣으면 왜 자동으로 붙나
`shared/registry.py`가 앱 시작 때 `mcp_servers/` 아래를 스캔해서 `TOOL_REGISTRY`가 있는 폴더를 전부 찾아 병합한다. tool 실행, LLM 스키마, 능동 모드 트리거가 한꺼번에 합쳐진다. tool 이름이 다른 부문과 겹치면 즉시 에러로 알려준다.

### AI(LLM)에게 부문 작업을 맡길 경우
자기 LLM에게 이렇게 시키면 된다:
> **"이 repo를 읽고 AGENT_BRIEF.md 지시를 따라줘: https://github.com/ParkSiHyun28/liferoad_ai_agent"**

`AGENT_BRIEF.md`가 AI에게 주는 작업 지시문이다.

---

## 5. 현재 부문 상태

- **asset (자산)** — 구현 완료. 팀 표준 예시. tool 5개: deadline_radar, pension_estimator, collateral_calc, remit_optimizer, credit_builder.
- **docs (서류행정)** — 구현 완료. tool 3개: perception_parse(OCR 파싱), compliance_reason(전세사기/비자 가드레일), form_autofill(신청서 자동작성).
- **fraud (사기탐지)** — 미합류. 폴더 오면 `mcp_servers/fraud/`에 넣으면 자동 연결된다.

페르소나 2명(동결): `minh` 응웬 반 민(베트남 E-9 근로자), `suman` 수만 라이(네팔 D-2 유학생).
