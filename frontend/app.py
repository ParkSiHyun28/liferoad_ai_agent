"""My LifeRoad 자산 부문 데모 Streamlit 앱.
대화 모드(LLM tool use)와 능동 모드(버튼 트리거) 둘 다 지원.
대화 모드의 LLM 공급자는 llm_provider.py가 LLM_PROVIDER 환경변수로 분기한다(ollama/claude).
대화 모드는 LLM이 어떤 tool을 어떤 순서로 호출하는지 '처리 과정' 패널로 단계별 시각화한다."""

import os
import sys

# repo 루트를 import 경로에 넣는다. `streamlit run frontend/app.py`만으로 동작하게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

# 키 로딩은 반드시 llm_provider import 전에 끝낸다.
# llm_provider는 import 시점에 모듈 수준 os.environ.get으로 PROVIDER와 키를 한 번 읽어 동결한다.
# 그 전에 (1) .env를 로컬에서 읽고 (2) Streamlit Cloud의 st.secrets를 os.environ으로 옮긴다.
load_dotenv()
from shared.secrets_bridge import bridge_secrets

bridge_secrets()

from shared.system_prompt import build_system_prompt
from shared.personas import PERSONAS
from shared.registry import TOOL_REGISTRY, ACTIVE_TOOLS
from frontend.llm_provider import run_chat, provider_label, PROVIDER

TODAY = "2026-10-03"  # 데모 기준일. 민 출국 D-90 무렵.

# tool 이름을 사람이 읽을 한글 단계명으로. 처리 과정 패널 라벨에 쓴다.
TOOL_LABELS = {
    "deadline_radar": "마감 D-Day 추적",
    "pension_estimator": "연금 반환일시금 산출",
    "collateral_calc": "예금담보대출 한도 계산",
    "remit_optimizer": "송금 경로 최적화",
    "credit_builder": "대안신용 축적도 추정",
    "perception_parse": "서류 OCR 파싱",
    "compliance_reason": "준법 가드레일 심사",
    "form_autofill": "신청서 자동작성",
}

st.set_page_config(page_title="My LifeRoad 자산", layout="wide")


def run_tool(name: str, args: dict) -> dict:
    """tool을 실제 실행한다. deadline_radar의 as_of는 항상 데모 기준일로 강제한다.
    LLM이 임의 날짜를 넣어도 덮어써서 데모 일관성을 지킨다.
    등록되지 않은 tool 이름이면 RuntimeError를 던진다."""
    if name not in TOOL_REGISTRY:
        raise RuntimeError(
            f"알 수 없는 tool: {name}. 사용 가능: {list(TOOL_REGISTRY.keys())}"
        )
    if name == "deadline_radar":
        args["as_of"] = TODAY
    return TOOL_REGISTRY[name](**args)


def render_card(card: dict):
    """결과 카드를 그린다. 이모지를 쓰지 않는다. 왼쪽 골드 막대로 구분한다."""
    if not card:
        return
    st.markdown(
        "<div style='border:1px solid #5A4D26;border-left:4px solid #E7B85C;"
        "border-radius:8px;padding:14px;background:#16223C;margin:6px 0'>"
        f"<div style='font-size:17px;color:#F2E9D8'><b>{card['head']}</b></div>"
        f"<div style='color:#93A0B8;margin-top:6px'>{card['body']}</div>"
        f"<div style='color:#E7B85C;font-family:monospace;margin-top:6px'>{card['metric']}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_step(idx: int, name: str, args: dict, output: dict):
    """처리 과정 한 단계를 그린다. 어떤 tool을 왜 호출해 무엇을 얻었는지 보여준다.
    output에 'error' 키가 있으면 오류 단계로 판단해 빨간 막대로 표시한다."""
    label = TOOL_LABELS.get(name, name)
    persona = args.get("persona_id", "")
    is_error = "error" in output
    if is_error:
        st.markdown(
            "<div style='border-left:3px solid #C0392B;padding:8px 12px;margin:4px 0;"
            "background:#1E0A0A;border-radius:6px'>"
            f"<span style='color:#E87070;font-family:monospace'>단계 {idx} [오류]</span> "
            f"<b style='color:#F2C0C0'>{label}</b> "
            f"<span style='color:#A06060;font-size:13px'>(tool: {name}, 대상: {persona})</span><br>"
            f"<span style='color:#E87070;font-size:13px'>오류: {output['error']}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='border-left:3px solid #4A6FA5;padding:8px 12px;margin:4px 0;"
            "background:#101A2E;border-radius:6px'>"
            f"<span style='color:#7FA8E0;font-family:monospace'>단계 {idx}</span> "
            f"<b style='color:#D7E2F2'>{label}</b> "
            f"<span style='color:#5E7BA6;font-size:13px'>(tool: {name}, 대상: {persona})</span><br>"
            f"<span style='color:#8FA3BE;font-size:13px'>→ {output['summary']}</span>"
            "</div>",
            unsafe_allow_html=True,
        )


# 사이드바
st.sidebar.title("My LifeRoad 자산")
persona_id = st.sidebar.radio(
    "페르소나",
    options=list(PERSONAS.keys()),
    format_func=lambda k: f"[{PERSONAS[k]['flag']}] {PERSONAS[k]['name']} ({PERSONAS[k]['visa']})",
)
st.sidebar.caption(f"모델: {provider_label()}")
if PROVIDER == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
    key_in = st.sidebar.text_input("ANTHROPIC_API_KEY", type="password")
    if key_in:
        os.environ["ANTHROPIC_API_KEY"] = key_in

st.sidebar.divider()
if st.sidebar.button("능동 점검 실행"):
    st.session_state["run_active"] = True

def active_plan(persona_id: str) -> list[tuple[str, dict]]:
    """페르소나별 능동 점검 계획을 반환한다. 각 항목은 (tool_name, args_dict) 튜플이다.
    minh: 보험/송금/서류 위주. suman: 담보대출/신용/비자/서류 위주."""
    if persona_id == "minh":
        return [
            ("deadline_radar", {"persona_id": persona_id}),
            ("remit_optimizer", {"persona_id": persona_id}),
            ("form_autofill", {"form_id": "departure_insurance_claim", "persona_id": persona_id}),
            ("perception_parse", {"persona_id": persona_id}),
        ]
    # suman(기본 및 기타 페르소나)
    return [
        ("collateral_calc", {"persona_id": persona_id}),
        ("credit_builder", {"months_accrued": 8, "persona_id": persona_id}),
        ("compliance_reason", {"check_type": "visa_work_eligibility", "persona_id": persona_id}),
        ("form_autofill", {"form_id": "alien_registration_renewal", "persona_id": persona_id}),
    ]


# 능동 모드
if st.session_state.get("run_active"):
    st.subheader("능동 점검 결과")
    st.caption(f"{PERSONAS[persona_id]['name']}님 기준일 {TODAY}")
    plan = active_plan(persona_id)
    # 한 tool이 실패해도 나머지는 계속 표시한다.
    for tname, targs in plan:
        try:
            out = run_tool(tname, targs)
            if out.get("card"):
                render_card(out["card"])
            else:
                st.info(out["summary"])
        except Exception as e:
            st.warning(f"{TOOL_LABELS.get(tname, tname)} 처리 중 오류: {e}")
    st.session_state["run_active"] = False
    st.divider()

# 대화 모드
st.subheader("대화")
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# 지난 대화 재생. assistant 메시지는 처리 과정과 답변을 함께 복원한다.
for m in st.session_state["messages"]:
    if m["role"] == "user_display":
        with st.chat_message("user"):
            st.write(m["text"])
    elif m["role"] == "assistant_display":
        with st.chat_message("assistant"):
            if m.get("steps"):
                with st.expander(f"처리 과정 {len(m['steps'])}단계", expanded=False):
                    for i, s in enumerate(m["steps"], 1):
                        render_step(i, s["name"], s["args"], s["output"])
            st.write(m["text"])

prompt = st.chat_input("질문을 입력하세요. 예: 민 씨 연금 얼마 받아요?")
if prompt:
    st.session_state["messages"].append({"role": "user_display", "text": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    user_text = f"[페르소나: {persona_id}] {prompt}"
    steps = []  # 처리 과정 수집용

    def on_step(kind, payload):
        if kind == "tool_call":
            steps.append(payload)
        elif kind == "tool_error":
            # 오류 단계도 수집해 처리 과정 패널에 빨간 막대로 표시한다.
            steps.append({
                "name": payload["name"],
                "args": payload.get("args", {}),
                "output": {"error": payload["error"], "summary": f"{payload['name']} 오류"},
            })

    with st.chat_message("assistant"):
        proc_box = st.container()  # 처리 과정을 답변 위에 둔다
        # 기본 공급자 gemini는 OpenAI 호환 엔드포인트가 토큰 스트리밍을 사실상 지원하지 않는다.
        # 실측상 스트리밍이 응답을 한꺼번에 보내 오히려 느렸다(6.9초 대 비스트리밍 3.6초).
        # 그래서 시연 경로는 빠른 비스트리밍 run_chat을 쓴다.
        # 토큰 스트리밍이 필요한 본선 Claude 전환 시엔 run_chat_stream을 쓰면 된다.
        with st.spinner("에이전트가 처리 중..."):
            try:
                text = run_chat(user_text, build_system_prompt(), run_tool, on_step=on_step)
            except Exception as e:
                text = f"오류: {e}"
        # 처리 과정 표시(실제 호출된 tool 단계). 답변 위에 둔다.
        with proc_box:
            if steps:
                st.markdown("**처리 과정**")
                for i, s in enumerate(steps, 1):
                    render_step(i, s["name"], s["args"], s["output"])
                st.markdown("**답변**")
        st.write(text)

    st.session_state["messages"].append(
        {"role": "assistant_display", "text": text, "steps": steps}
    )
