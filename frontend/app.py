"""My LifeRoad 자산 부문 데모 Streamlit 앱.
대화 모드(Claude tool use)와 능동 모드(버튼 트리거) 둘 다 지원."""

import os
import sys
import json
from datetime import date

# repo 루트를 import 경로에 넣는다. `streamlit run frontend/app.py`만으로 동작하게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv
from anthropic import Anthropic

from shared.system_prompt import build_system_prompt
from shared.personas import PERSONAS
from mcp_servers.asset.tools import TOOL_REGISTRY, ACTIVE_TOOLS
from mcp_servers.asset.schemas import TOOL_SCHEMAS

load_dotenv()

MODEL = "claude-opus-4-8"
TODAY = "2026-10-03"  # 데모 기준일. 민 출국 D-90 무렵.

st.set_page_config(page_title="My LifeRoad 자산", page_icon="💰", layout="wide")


def get_client() -> Anthropic | None:
    key = os.environ.get("ANTHROPIC_API_KEY") or st.session_state.get("api_key")
    if not key:
        return None
    return Anthropic(api_key=key)


def run_tool(name: str, args: dict) -> dict:
    """tool을 실제 실행한다. as_of 누락 시 데모 기준일을 채운다."""
    if name == "deadline_radar" and "as_of" not in args:
        args["as_of"] = TODAY
    return TOOL_REGISTRY[name](**args)


def claude_tools_param() -> list[dict]:
    return list(TOOL_SCHEMAS.values())


def chat_turn(client: Anthropic, history: list[dict]) -> tuple[str, list[dict]]:
    """tool use 루프. history를 받아 최종 텍스트와 갱신된 history를 반환한다."""
    system = [{"type": "text", "text": build_system_prompt(), "cache_control": {"type": "ephemeral"}}]
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=system,
            tools=claude_tools_param(),
            messages=history,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            history.append({"role": "assistant", "content": resp.content})
            return text, history
        history.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = run_tool(block.name, dict(block.input))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })
        history.append({"role": "user", "content": tool_results})


def render_card(card: dict):
    if not card:
        return
    st.markdown(
        f"<div style='border:1px solid #5A4D26;border-radius:10px;padding:14px;background:#16223C;margin:6px 0'>"
        f"<div style='font-size:20px'>{card['icon']} <b>{card['head']}</b></div>"
        f"<div style='color:#93A0B8;margin-top:6px'>{card['body']}</div>"
        f"<div style='color:#E7B85C;font-family:monospace;margin-top:6px'>{card['metric']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# 사이드바
st.sidebar.title("💰 My LifeRoad 자산")
persona_id = st.sidebar.radio(
    "페르소나",
    options=list(PERSONAS.keys()),
    format_func=lambda k: f"{PERSONAS[k]['flag']} {PERSONAS[k]['name']} ({PERSONAS[k]['visa']})",
)
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.session_state["api_key"] = st.sidebar.text_input("ANTHROPIC_API_KEY", type="password")

st.sidebar.divider()
if st.sidebar.button("🔔 능동 점검 실행"):
    st.session_state["run_active"] = True

# 능동 모드
if st.session_state.get("run_active"):
    st.subheader("🔔 능동 점검 결과")
    st.caption(f"{PERSONAS[persona_id]['name']}님 기준일 {TODAY}")
    for tname in ACTIVE_TOOLS:
        out = run_tool(tname, {"persona_id": persona_id})
        if out["card"]:
            render_card(out["card"])
        else:
            st.info(out["summary"])
    st.session_state["run_active"] = False
    st.divider()

# 대화 모드
st.subheader("💬 대화")
if "messages" not in st.session_state:
    st.session_state["messages"] = []

for m in st.session_state["messages"]:
    if m["role"] in ("user_display", "assistant_display"):
        with st.chat_message("user" if m["role"] == "user_display" else "assistant"):
            st.write(m["text"])

prompt = st.chat_input("질문을 입력하세요. 예: 민 씨 연금 얼마 받아요?")
if prompt:
    client = get_client()
    if client is None:
        st.error("ANTHROPIC_API_KEY가 필요합니다. 사이드바에 입력하세요.")
    else:
        st.session_state["messages"].append({"role": "user_display", "text": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        api_history = [{"role": "user", "content": f"[페르소나: {persona_id}] {prompt}"}]
        with st.chat_message("assistant"):
            with st.spinner("생각 중..."):
                text, _ = chat_turn(client, api_history)
            st.write(text)
        st.session_state["messages"].append({"role": "assistant_display", "text": text})
