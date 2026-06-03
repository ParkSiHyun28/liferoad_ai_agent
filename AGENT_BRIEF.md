# AGENT_BRIEF — AI 에이전트용 작업 지시문

> 이 문서는 사람이 아니라 **AI(LLM)에게 주는 지시문**입니다. 팀원이 자기 LLM에게 "이 repo를 읽고 AGENT_BRIEF.md 지시를 따라줘"라고 시키면, LLM은 이 문서를 읽고 그 팀원이 맡은 부문 작업을 안내하고 코드를 작성합니다.

---

## 0. AI에게 — 먼저 이것부터

당신은 My LifeRoad 프로젝트에서 한 팀원의 작업을 돕는 AI 비서입니다. 이 프로젝트는 데이콘 JB금융그룹 Fin:AI Challenge 출전작입니다. 외국인 금융 라이프케어 AI 에이전트입니다.

작업을 시작하기 전에 반드시 아래 순서로 파일을 읽으세요.
1. `README.md` — 프로젝트 전체 구조.
2. `CONTRACT.md` — tool 인터페이스 규약. 이 규약을 어기면 통합이 깨집니다.
3. `mcp_servers/asset/` 폴더 전체 — **완성된 표준 예시**입니다. 자산 부문이 이미 구현돼 있습니다. 당신이 만들 부문은 이 폴더를 그대로 본떠 만듭니다.

그다음 이 팀원에게 물어보세요. **"어느 부문을 맡으셨나요? 사기탐지(fraud)인가요, 서류행정(docs)인가요?"** 답을 듣고 해당 부문 작업으로 넘어갑니다.

---

## 1. 이 프로젝트가 무엇인가

세 부문이 하나의 AI 에이전트로 합쳐집니다.
- **자산(asset)** — 이미 완성. 표준 예시. (담당자 따로 있음)
- **사기탐지(fraud)** — 팀원이 만들 부문.
- **서류행정(docs)** — 팀원이 만들 부문.

구조는 MCP 서버 부문별 분리입니다. 각 부문이 독립 폴더이고, 공용 Streamlit 프론트 하나가 Claude tool use로 세 부문 tool을 모두 호출합니다. 합칠 때 충돌이 없도록 모든 부문이 **똑같은 폴더 구조와 똑같은 tool 입출력 형식**을 씁니다. 이것이 CONTRACT.md입니다.

---

## 2. 부문 작업 절차 (사기 또는 서류 공통)

자산 부문(`mcp_servers/asset/`)을 그대로 복제해 만듭니다. 절차는 다음과 같습니다.

### 단계 1: 폴더 복제
`mcp_servers/asset/`를 `mcp_servers/<부문>/`로 복제합니다. 부문 이름은 `fraud` 또는 `docs`입니다. 파일 6개가 생깁니다.
```
mcp_servers/<부문>/
├─ __init__.py      (빈 파일)
├─ data.py          (mock 상수 — 부문 내용으로 교체)
├─ tools.py         (tool 함수 — 부문 tool로 교체)
├─ schemas.py       (JSON 스키마 — 부문 tool로 교체)
├─ server.py        (MCP 서버 — Server 이름만 부문명으로 바꿈)
└─ tests/
   └─ test_tools.py (테스트 — 부문 tool로 교체)
```

### 단계 2: tool 결정
부문에서 LLM이 호출할 **행동(동사) 단위** tool을 정합니다. 분야(명사)가 아니라 행동입니다. 노션 사례조사 페이지에 이미 tool 후보가 있습니다.
- **사기탐지(fraud)** tool 4개: `register_baseline`(국적별 정상거래 분포 학습), `score_transaction`(거래 위험 점수화), `detect_account_takeover`(계좌양도 탐지), `request_verification`(모국어 본인확인 발송).
- **서류행정(docs)** tool: `perception_parse`(OCR로 서류 파싱과 실명 불일치 검출), `compliance_reason`(준법 추론과 전세사기 비자 가드레일 심사), `form_autofill`(정부 PDF 원클릭 자동작성). 3엔진(Perception, Reasoning, Action) 기준.

위 tool 이름과 개수는 제안입니다. 부문 담당자가 노션 자료를 보고 조정해도 됩니다. 단 **tool 입출력 형식은 절대 바꾸지 않습니다**(단계 3).

### 단계 3: tool 함수 작성 (규약 엄수)
각 tool은 순수 함수입니다. MCP와 Claude를 import 하지 않습니다. CONTRACT.md의 규약을 그대로 지킵니다.
- 첫 인자는 항상 `persona_id`("minh" 또는 "suman").
- 출력은 dict. 필수 키 4개: `summary`(str), `detail`(str), `numbers`(dict), `card`(dict 또는 None).
- card 구조: `{"icon": str, "head": str, "body": str, "metric": str}`.
- 모든 수치는 data.py 상수에서 계산식으로 도출합니다. 결과 문자열 하드코딩 금지.

자산 부문 `mcp_servers/asset/tools.py`의 함수들이 정확한 예시입니다. 그 형태를 그대로 따르세요.

### 단계 4: TOOL_REGISTRY와 스키마
- `tools.py` 맨 끝에 `TOOL_REGISTRY = {"tool이름": 함수, ...}`와 `ACTIVE_TOOLS = [...]`를 둡니다.
- `schemas.py`에 각 tool의 `TOOL_SCHEMAS`를 둡니다. persona_id는 enum `["minh", "suman"]`로 고정합니다.

### 단계 5: 테스트
`tests/test_tools.py`에 각 tool 단위 테스트를 씁니다. mock 입력에 대해 출력 dict의 numbers 값과 card 유무를 검증합니다. 자산 부문 테스트가 예시입니다.
```bash
source .venv/bin/activate
python -m pytest mcp_servers/<부문>/tests/ -v
```
전부 통과해야 합니다.

### 단계 6: 통합 (자산 담당자가 함, 팀원은 안 해도 됨)
`frontend/app.py`에 부문 import를 한 줄 추가하면 Claude가 그 부문 tool도 호출합니다. 이 작업은 합칠 때 자산 담당자가 합니다. 팀원은 자기 폴더만 완성하면 됩니다.

---

## 3. 절대 건드리면 안 되는 것

- `shared/personas.py` — 두 페르소나 공용 데이터. 새 필드가 필요하면 자산 담당자와 협의 후 추가합니다. 임의 수정 금지.
- `shared/system_prompt.py` — 공용 시스템 프롬프트. 부문별로 바꾸지 않습니다.
- `mcp_servers/asset/` — 자산 부문. 참고만 하고 수정하지 않습니다.
- tool 출력 dict의 4개 키 형식. 이걸 바꾸면 통합이 깨집니다.

---

## 4. 작업 환경 준비

```bash
git clone https://github.com/ParkSiHyun28/liferoad_ai_agent
cd liferoad_ai_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v   # 자산 부문 11개 통과 확인 (작업 시작 전 정상 상태 확인)
```

작업이 끝나면 자기 부문 폴더를 커밋하고 push 하거나 PR을 올립니다.

---

## 5. AI에게 — 마지막 확인

부문 폴더를 다 만들었으면 팀원에게 다음을 보고하세요.
- 만든 tool 목록과 각 tool이 하는 일.
- pytest 통과 결과.
- 통합은 자산 담당자가 한다는 안내.

규약(CONTRACT.md)을 어긴 부분이 없는지 스스로 점검한 뒤 보고하세요. 특히 tool 출력 dict의 4개 키와 persona_id 규약을 확인하세요.
