# My LifeRoad — 외국인 금융 라이프케어 AI 에이전트

데이콘 JB금융그룹 Fin:AI Challenge 출전작. 외국인의 한국 금융 생활을 입국부터 귀국까지 동행하는 능동형 AI 에이전트다.

## 구조
세 부문(자산, 사기탐지, 서류행정)이 각각 MCP 서버다. 공용 Streamlit 프론트 하나가 Claude(tool use)를 통해 부문 tool을 호출한다.

```
frontend/        공용 Streamlit 챗 UI
shared/          페르소나, 시스템 프롬프트 (전 부문 공용)
mcp_servers/
  asset/         자산 부문 (구현 완료, 팀 표준 예시)
  fraud/         사기탐지 부문 (팀원 작업)
  docs/          서류행정 부문 (팀원 작업)
CONTRACT.md      tool 인터페이스 규약 (팀 통일 핵심)
```

## 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 입력 (또는 앱 사이드바에서 입력)
streamlit run frontend/app.py
```

## 테스트
```bash
source .venv/bin/activate
python -m pytest -v
```

## 팀원 작업 안내
1. 이 repo를 clone 한다.
2. CONTRACT.md를 읽는다.
3. mcp_servers/asset 폴더를 자기 부문명으로 복제한다.
4. tools.py의 함수를 자기 부문 tool로 바꾼다. 입출력 규약은 그대로 지킨다.
5. test_tools.py로 검증한 뒤 PR을 올린다.

### AI(LLM)에게 작업을 맡길 경우
자기 LLM에게 이렇게 시키면 된다: **"이 repo를 읽고 AGENT_BRIEF.md 지시를 따라줘: https://github.com/ParkSiHyun28/liferoad_ai_agent"**
`AGENT_BRIEF.md`는 AI에게 주는 작업 지시문이다. AI가 그 문서를 읽고 부문 작업을 안내하고 코드를 작성한다.

## 자산 부문 tool
- deadline_radar: 반환일시금과 출국만기보험 마감 D-Day 추적 (능동)
- pension_estimator: 국민연금 반환일시금 산출 (협정 체결 여부 반영)
- collateral_calc: 예금담보대출 한도(95%) 산출
- remit_optimizer: 송금 최저비용 경로 비교
- credit_builder: 월세와 통신비 대안신용 축적
