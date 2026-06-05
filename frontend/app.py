"""My LifeRoad 자산 부문 데모 Streamlit 앱.
대화 모드(LLM tool use)와 능동 모드(버튼 트리거) 둘 다 지원.
대화 모드의 LLM 공급자는 llm_provider.py가 LLM_PROVIDER 환경변수로 분기한다(ollama/claude).
대화 모드는 LLM이 어떤 tool을 어떤 순서로 호출하는지 '처리 과정' 패널로 단계별 시각화한다."""

from __future__ import annotations  # 타입 힌트를 문자열로 지연 평가(낮은 파이썬 버전 안전)

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

import random

from shared.system_prompt import build_system_prompt, LANGUAGES, detect_lang
from shared.personas import (
    PERSONAS, get_persona, all_personas, make_random_personas, register_personas,
)
from shared.registry import TOOL_REGISTRY, ACTIVE_TOOLS
from frontend.llm_provider import run_chat, run_chat_stream, strip_emoji, provider_label, PROVIDER

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


def render_persona_card(p: dict):
    """첫 화면에서 지금 상담 중인 사람이 누구인지 한눈에 보여주는 요약 카드.
    비자와 체류 상황을 박아 '에이전트가 이 사람을 인식하고 있다'를 시각적으로 드러낸다."""
    st.markdown(
        "<div style='border:1px solid #5A4D26;border-left:4px solid #E7B85C;"
        "border-radius:8px;padding:14px;background:#16223C;margin:6px 0'>"
        f"<div style='font-size:17px;color:#F2E9D8'><b>[{p['flag']}] {p['name']}</b> "
        f"<span style='color:#93A0B8;font-size:14px'>({p['name_en']})</span></div>"
        f"<div style='color:#93A0B8;margin-top:6px'>{p['country']} / {p['visa']} {p['role']} / "
        f"입국 {p['entry_date']} / 출국 예정 {p['exit_plan']}</div>"
        f"<div style='color:#8FA3BE;margin-top:6px;font-size:14px'>{p['summary']}</div>"
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


# 부팅 시 한 번만 동적 페르소나를 만들어 등록한다. seed 고정이라 재실행해도 같은 50명.
# session_state 가드로 rerun마다 새로 만들지 않게 한다.
if "personas_loaded" not in st.session_state:
    register_personas(make_random_personas(60, seed=42))
    st.session_state["personas_loaded"] = True

# 고정 2명과 동적 페르소나를 합친 전체. 사이드바와 시연이 이 목록을 쓴다.
PERS = all_personas()

# 사이드바
st.sidebar.title("My LifeRoad 자산")
st.sidebar.caption("시연용 페르소나를 골라 그 사람 기준으로 에이전트가 어떻게 동작하는지 봅니다.")

# 비자 필터로 후보를 좁힌다. 50~100명이라 라디오 대신 드롭다운을 쓴다.
visa_opts = ["전체"] + sorted({p["visa"] for p in PERS.values()})
vf = st.sidebar.selectbox("비자 필터", visa_opts)
ids = sorted(k for k, p in PERS.items() if vf == "전체" or p["visa"] == vf)

# 랜덤 페르소나 버튼. 다양한 사람을 빠르게 시연하려고 후보 중 하나를 무작위 선택한다.
if st.sidebar.button("랜덤 페르소나"):
    st.session_state["_rand_pid"] = random.choice(ids)
    st.rerun()

# 랜덤으로 뽑힌 id가 현재 필터 후보에 있으면 기본 선택으로 쓴다.
rand_pid = st.session_state.get("_rand_pid")
default_idx = ids.index(rand_pid) if rand_pid in ids else 0
persona_id = st.sidebar.selectbox(
    "페르소나",
    options=ids,
    index=default_idx,
    format_func=lambda k: f"[{PERS[k]['flag']}] {PERS[k]['name']} ({PERS[k]['visa']} {PERS[k]['role']})",
)

# 페르소나가 바뀌면 대화 이력을 비운다. 다른 사람 상담이 시작되므로 선택지와 누적
# 사용 이력도 새 사람 기준으로 초기화돼야 한다(엉뚱한 사람의 선택지가 남는 것 방지).
if st.session_state.get("_active_persona") != persona_id:
    st.session_state["_active_persona"] = persona_id
    st.session_state["messages"] = []
    st.session_state.pop("pending_intent", None)

# 답변 언어. 기본은 '자동감지'다. 사용자가 입력한 질문의 언어를 감지해 같은 언어로 답한다.
# 외국인이 모국어로 물으면 모국어로, 심사위원이 한국어로 물으면 한국어로 자연히 분기된다.
# 특정 언어로 고정해 보고 싶으면 드롭다운에서 그 언어를 직접 골라 자동감지를 끈다(수동 오버라이드).
lang_codes = ["auto"] + list(LANGUAGES.keys())
LANG_LABELS = {"auto": "자동감지 (질문 언어 따라감)"}
LANG_LABELS.update({c: LANGUAGES[c]["name"] for c in LANGUAGES})
lang = st.sidebar.selectbox(
    "답변 언어",
    options=lang_codes,
    index=lang_codes.index(st.session_state.get("lang", "auto")),
    format_func=lambda c: LANG_LABELS[c],
)
st.session_state["lang"] = lang

st.sidebar.caption(f"모델: {provider_label()}")
if PROVIDER == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
    key_in = st.sidebar.text_input("ANTHROPIC_API_KEY", type="password")
    if key_in:
        os.environ["ANTHROPIC_API_KEY"] = key_in

st.sidebar.divider()
if st.sidebar.button("능동 점검 실행"):
    st.session_state["run_active"] = True

def active_plan(persona_id: str) -> list[tuple[str, dict]]:
    """페르소나 속성으로 능동 점검 계획을 만든다. persona_id 하드코딩 없이
    visa wage deposit pension 값으로 어떤 tool이 의미 있는지 판단한다.
    어떤 페르소나든 form_autofill과 perception_parse가 무조건 들어가 최소 2개를 보장한다.
    각 항목은 (tool_name, args_dict) 튜플이다."""
    p = get_persona(persona_id)
    plan: list[tuple[str, dict]] = []

    # E-9 근로자만 출국만기보험과 마감 추적 대상
    if p["visa"] == "E-9":
        plan.append(("deadline_radar", {"persona_id": persona_id}))
    # 정기 송금이 있으면 경로 최적화
    if p["monthly_remit_krw"] > 0:
        plan.append(("remit_optimizer", {"persona_id": persona_id}))
    # 협정 미체결이고 납부이력이 있으면 반환일시금 산출
    if (not p["social_security_treaty"]) and p["pension_months"] > 0:
        plan.append(("pension_estimator", {"persona_id": persona_id}))
    # 잔고증명 예치금이 있으면 예금담보대출 한도
    if p["deposit_balance_krw"] > 0:
        plan.append(("collateral_calc", {"persona_id": persona_id}))
    # 소득 없고 예치금만 있는 Thin Filer형이면 대안신용 축적
    if p["monthly_wage_krw"] == 0 and p["deposit_balance_krw"] > 0:
        plan.append(("credit_builder", {"months_accrued": 8, "persona_id": persona_id}))
    # E-9 D-2만 비자 취업 가드레일이 의미 있는 분기를 가짐
    if p["visa"] in ("E-9", "D-2"):
        plan.append(("compliance_reason", {"check_type": "visa_work_eligibility", "persona_id": persona_id}))
    # 신청서 자동작성. E-9는 출국만기보험 청구서, 그 외는 외국인등록증 갱신
    form_id = "departure_insurance_claim" if p["visa"] == "E-9" else "alien_registration_renewal"
    plan.append(("form_autofill", {"form_id": form_id, "persona_id": persona_id}))
    # 서류 파싱은 항상 최소 1개 점검 보장
    plan.append(("perception_parse", {"persona_id": persona_id}))
    return plan


# 다음 행동 선택지 버튼에 쓸 다국어 행동 문구.
# tool 이름 -> 언어별 "이 행동을 해줘" 형태의 짧은 제안 문구.
# 자동감지된 응답 언어(ko/vi/ne/en)에 맞춰 버튼 라벨을 그 언어로 보여준다.
ACTION_LABELS = {
    "deadline_radar": {
        "ko": "마감 기한 확인하기", "en": "Check upcoming deadlines",
        "vi": "Kiểm tra hạn chót sắp tới", "ne": "आउँदो म्याद जाँच गर्नुहोस्",
    },
    "pension_estimator": {
        "ko": "연금 반환일시금 계산하기", "en": "Estimate my pension refund",
        "vi": "Tính tiền hoàn bảo hiểm hưu trí", "ne": "पेन्सन फिर्ता रकम अनुमान गर्नुहोस्",
    },
    "collateral_calc": {
        "ko": "예금담보대출 한도 계산하기", "en": "Calculate my loan limit",
        "vi": "Tính hạn mức vay thế chấp", "ne": "ऋण सीमा गणना गर्नुहोस्",
    },
    "remit_optimizer": {
        "ko": "송금 비용 줄이기", "en": "Lower my remittance cost",
        "vi": "Giảm phí chuyển tiền", "ne": "रेमिट्यान्स लागत घटाउनुहोस्",
    },
    "credit_builder": {
        "ko": "신용 점수 쌓기 시작하기", "en": "Start building my credit",
        "vi": "Bắt đầu xây dựng tín dụng", "ne": "क्रेडिट निर्माण सुरु गर्नुहोस्",
    },
    "compliance_reason": {
        "ko": "비자 취업 가능 여부 확인하기", "en": "Check my visa work eligibility",
        "vi": "Kiểm tra điều kiện làm việc theo visa", "ne": "भिसा कामको योग्यता जाँच गर्नुहोस्",
    },
    "form_autofill": {
        "ko": "신청서 자동으로 작성하기", "en": "Auto-fill the application form",
        "vi": "Tự động điền đơn", "ne": "आवेदन फारम स्वतः भर्नुहोस्",
    },
    "perception_parse": {
        "ko": "내 서류 점검하기", "en": "Review my documents",
        "vi": "Kiểm tra giấy tờ của tôi", "ne": "मेरा कागजात जाँच गर्नुहोस्",
    },
}

# 선택지 블럭 안내 문구(헤더)도 응답 언어로.
NEXT_HEADER = {
    "ko": "다음으로 무엇을 도와드릴까요?",
    "en": "What would you like me to do next?",
    "vi": "Tiếp theo bạn muốn tôi làm gì?",
    "ne": "अब म तपाईंलाई के मद्दत गरूँ?",
}

# 첫 화면 선제 선택지 헤더. 대화 시작 전 페르소나 카드 아래에 띄운다.
START_HEADER = {
    "ko": "이런 것을 도와드릴 수 있습니다. 무엇부터 할까요?",
    "en": "Here is how I can help. Where shall we start?",
    "vi": "Tôi có thể giúp những việc sau. Bắt đầu từ đâu?",
    "ne": "म यी कुराहरूमा मद्दत गर्न सक्छु। कहाँबाट सुरु गरौं?",
}

# 버튼이 눌렸을 때 LLM에 보낼 '사용자 의도' 자연어 문장.
# 버튼을 그냥 tool 직접 실행으로 처리하지 않는다. 이 문장을 일반 질문과 똑같이 LLM에 보낸다.
# 그러면 에이전트가 상황을 보고 어떤 tool을 쓸지 스스로 판단한다(진짜 능동성).
# 답변 언어는 별도로 강제하므로 여기 문구의 언어는 LLM 판단용일 뿐 노출 언어와 무관하다.
ACTION_INTENT = {
    "deadline_radar": "다가오는 마감 기한이 있는지 확인하고 알려주세요.",
    "pension_estimator": "제가 받을 수 있는 연금 반환일시금이 얼마인지 계산해 주세요.",
    "collateral_calc": "제 예금으로 받을 수 있는 담보대출 한도를 계산해 주세요.",
    "remit_optimizer": "본국 송금 비용을 줄일 수 있는 더 싼 경로를 찾아 주세요.",
    "credit_builder": "한국에서 신용 점수를 쌓으려면 어떻게 해야 하는지 알려주세요.",
    "compliance_reason": "제 비자로 일을 할 수 있는지 자격을 확인해 주세요.",
    "form_autofill": "필요한 신청서를 제 정보로 자동 작성해 주세요.",
    "perception_parse": "제 서류에 문제가 없는지 점검해 주세요.",
}


# 작업 흐름 후속 관계 그래프. 방금 한 작업 -> 자연스러운 다음 작업 후보(우선순위 순).
# 단순히 '안 쓴 tool 아무거나'가 아니라 방금 한 일과 논리로 이어지는 다음 단계를 먼저 제안한다.
# 예: 연금 반환일시금을 계산했으면 다음은 청구서 자동작성, 그 다음은 받은 돈 송금 경로.
# 우리 서비스 3원리 중 '대리처리'를 살려 대부분 흐름이 form_autofill(서류 대행)로 수렴한다.
FOLLOWUP = {
    "pension_estimator": ["form_autofill", "deadline_radar", "remit_optimizer"],
    "deadline_radar": ["form_autofill", "perception_parse", "pension_estimator"],
    "collateral_calc": ["credit_builder", "form_autofill", "remit_optimizer"],
    "credit_builder": ["collateral_calc", "form_autofill", "deadline_radar"],
    "compliance_reason": ["form_autofill", "perception_parse", "deadline_radar"],
    "perception_parse": ["form_autofill", "deadline_radar", "compliance_reason"],
    "remit_optimizer": ["pension_estimator", "form_autofill", "deadline_radar"],
    "form_autofill": ["deadline_radar", "perception_parse", "remit_optimizer"],
}


def next_actions(persona_id: str, used_tools: set[str], limit: int = 3,
                 last_tool: str | None = None) -> list[tuple[str, dict]]:
    """이 페르소나에게 의미 있는 '다음 행동' 후보를 만든다(작업 흐름 기반).

    핵심은 방금 한 작업(last_tool)의 자연스러운 후속을 먼저 제안하는 것이다.
    FOLLOWUP 그래프로 방금 일과 논리로 이어지는 다음 단계를 우선 배치한 뒤,
    부족분을 페르소나 속성 계획(active_plan)으로 채운다.

    필터:
    - 이미 실행한 tool(used_tools)은 다시 제안하지 않는다(같은 보기 반복 방지).
    - 그 페르소나에게 의미 있는 tool만(active_plan에 든 것). 엉뚱한 후속을 막는다.
    - ACTION_LABELS에 문구가 있는 tool만 버튼으로 노출한다.
    last_tool이 없으면(첫 화면) 페르소나 계획 순서대로만 채운다."""
    plan = active_plan(persona_id)
    # 이 페르소나에게 의미 있는 tool 집합과 기본 args. FOLLOWUP 후보를 이 안으로만 좁힌다.
    plan_tools = {tname: targs for tname, targs in plan}

    def usable(tname: str) -> bool:
        return (tname not in used_tools
                and tname in ACTION_LABELS
                and tname in plan_tools)

    seen: set[str] = set()
    out: list[tuple[str, dict]] = []

    def push(tname: str):
        if tname in seen or not usable(tname):
            return
        seen.add(tname)
        out.append((tname, plan_tools[tname]))

    # 1순위: 방금 한 작업의 후속(FOLLOWUP). 다음 단계와 관련된 버튼을 먼저 보여준다.
    if last_tool:
        for nxt in FOLLOWUP.get(last_tool, []):
            push(nxt)
            if len(out) >= limit:
                return out
    # 2순위: 페르소나 일반 계획으로 부족분을 채운다.
    for tname, _ in plan:
        push(tname)
        if len(out) >= limit:
            break
    return out


def render_actions(actions: list, reply_lang: str, msg_key: str, header: bool = True):
    """답변 아래에 '다음 행동' 선택지 버튼을 그린다. 능동성을 눈에 보이게 만드는 핵심 UI.

    actions: next_actions가 만든 (tool_name, args) 리스트.
    reply_lang: 버튼 라벨을 보여줄 언어(자동감지된 응답 언어).
    msg_key: 버튼 위젯 key 충돌을 막는 접두어(메시지 식별자). 과거 메시지의 버튼과 안 겹치게 한다.
    header: NEXT_HEADER caption을 직접 그릴지. 첫 화면은 호출부가 START_HEADER를 따로 그리므로 False.

    버튼이 눌리면 session_state['pending_intent']에 의도 문장을 담고 rerun한다.
    실제 처리는 스크립트 상단의 pending_intent 처리 블록(run_agent_turn)이 맡는다."""
    if not actions:
        return
    if header:
        st.caption(NEXT_HEADER.get(reply_lang, NEXT_HEADER["ko"]))
    cols = st.columns(len(actions))
    for col, (tname, targs) in zip(cols, actions):
        label = ACTION_LABELS.get(tname, {}).get(reply_lang) \
            or ACTION_LABELS.get(tname, {}).get("ko") or tname
        if col.button(label, key=f"act_{msg_key}_{tname}", use_container_width=True):
            # 버튼은 tool을 직접 실행하지 않는다. 그 의도를 자연어 질문으로 바꿔
            # 일반 질문과 똑같이 LLM에 보낸다. 에이전트가 상황을 보고 tool을 스스로 고른다.
            st.session_state["pending_intent"] = {
                "intent": ACTION_INTENT.get(tname, label),
                "label": label,  # 대화에 남길 '사용자가 고른 행동' 표시용
                "lang": reply_lang,
            }
            st.rerun()


def used_tools_so_far() -> set[str]:
    """이번 대화에서 지금까지 실제로 실행된 모든 tool 이름의 합집합.
    마지막 메시지 한 개가 아니라 전체 이력을 본다. 같은 선택지가 계속 뜨던 버그의 핵심 수정.
    페르소나가 바뀌면 history_reset이 messages를 비우므로 자연히 새 사람 기준으로 초기화된다."""
    used: set[str] = set()
    for m in st.session_state.get("messages", []):
        if m.get("role") == "assistant_display":
            used.update(m.get("used_tools", []))
    return used


def last_used_tool() -> str | None:
    """가장 최근 assistant 답변에서 마지막으로 실행한 tool 이름.
    다음 행동 선택지에서 '방금 한 작업의 후속'을 우선 배치하는 기준으로 쓴다.
    LLM이 한 답변에서 여러 tool을 쓰면 마지막 것을 핵심 작업으로 본다."""
    for m in reversed(st.session_state.get("messages", [])):
        if m.get("role") == "assistant_display":
            ut = m.get("used_tools", [])
            return ut[-1] if ut else None
    return None


def run_agent_turn(user_intent: str, reply_lang: str, display_user: str, is_action: bool):
    """사용자 발화 1건을 에이전트에 보내고 답변과 처리 과정을 messages에 남긴다.
    일반 질문과 선택지 버튼이 같은 경로를 쓰게 하는 공통 함수.

    user_intent: LLM에 보낼 실제 의도 문장(버튼이면 ACTION_INTENT, 질문이면 입력 원문).
    reply_lang: 답변 언어 코드.
    display_user: 대화에 남길 사용자 측 표시 텍스트(버튼이면 버튼 라벨, 질문이면 입력 원문).
    is_action: 버튼에서 왔으면 True. 대화에 '[선택]' 칩으로 구분 표시한다.

    LLM이 상황을 보고 tool을 스스로 골라 실행한다(진짜 능동성). 실제 실행된 tool을
    used_tools로 정확히 기록해 다음 선택지에서 중복 제거가 올바르게 된다."""
    role = "user_action" if is_action else "user_display"
    st.session_state["messages"].append({"role": role, "text": display_user})

    # 답변 언어를 user 메시지에 직접 박는다(시스템 프롬프트만으론 입력 언어에 끌려가므로).
    lang_directive = LANGUAGES[reply_lang]["instruct"]
    user_text = f"[페르소나: {persona_id}] [답변 언어 강제: {lang_directive}] {user_intent}"
    steps: list = []

    def on_step(kind, payload):
        if kind == "tool_call":
            steps.append(payload)
        elif kind == "tool_error":
            steps.append({
                "name": payload["name"],
                "args": payload.get("args", {}),
                "output": {"error": payload["error"], "summary": f"{payload['name']} 오류"},
            })

    system = build_system_prompt(reply_lang, persona_id)
    if PROVIDER == "claude":
        text = ""
        try:
            for chunk in run_chat_stream(user_text, system, run_tool, on_step=on_step):
                if chunk:
                    text += chunk
            text = strip_emoji(text)
        except Exception as e:
            text = f"오류: {e}"
    else:
        try:
            text = run_chat(user_text, system, run_tool, on_step=on_step)
        except Exception as e:
            text = f"오류: {e}"

    used = [s["name"] for s in steps if "name" in s]
    st.session_state["messages"].append({
        "role": "assistant_display", "text": text, "steps": steps,
        "lang": reply_lang, "used_tools": used, "persona_id": persona_id,
    })


# 능동 모드
if st.session_state.get("run_active"):
    st.subheader("능동 점검 결과")
    st.caption(f"{PERS[persona_id]['name']}님 기준일 {TODAY}")
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

# 선택지 버튼이 눌린 경우를 먼저 처리한다(메시지 재생보다 앞).
# 버튼을 tool 직접 실행으로 처리하지 않는다. 그 의도를 자연어 문장으로 바꿔 LLM에 보낸다.
# 에이전트가 상황을 보고 어떤 tool을 어떤 순서로 쓸지 스스로 판단한다(진짜 능동성).
# 일반 질문 입력과 완전히 같은 경로(run_agent_turn)를 타므로 처리 과정 패널도 동일하게 뜬다.
pending = st.session_state.pop("pending_intent", None)
if pending:
    with st.spinner("에이전트가 처리 중..."):
        run_agent_turn(
            user_intent=pending["intent"],
            reply_lang=pending["lang"],
            display_user=pending["label"],
            is_action=True,
        )

# 지난 대화 재생. assistant 메시지는 처리 과정과 답변을 함께 복원한다.
# 마지막 assistant 메시지에는 '다음 행동' 선택지 버튼을 함께 그린다.
last_assistant_idx = max(
    (i for i, m in enumerate(st.session_state["messages"]) if m["role"] == "assistant_display"),
    default=-1,
)
for idx, m in enumerate(st.session_state["messages"]):
    if m["role"] == "user_display":
        with st.chat_message("user"):
            st.write(m["text"])
    elif m["role"] == "user_action":
        # 사용자가 선택지 버튼으로 고른 행동. 일반 질문과 구분되게 표시한다.
        with st.chat_message("user"):
            st.markdown(f"<span style='color:#E7B85C'>[선택]</span> {m['text']}", unsafe_allow_html=True)
    elif m["role"] == "assistant_display":
        with st.chat_message("assistant"):
            if m.get("steps"):
                with st.expander(f"처리 과정 {len(m['steps'])}단계", expanded=False):
                    for i, s in enumerate(m["steps"], 1):
                        render_step(i, s["name"], s["args"], s["output"])
            st.write(m["text"])
            # 선택지로 처리된 결과 메시지면 카드도 복원한다.
            if m.get("card"):
                render_card(m["card"])
            # 마지막 assistant 메시지에만 '다음 행동' 선택지 버튼을 붙인다.
            # used는 이번 대화 전체에서 쓴 tool의 합집합이다(마지막 한 개가 아니라).
            # 같은 보기가 계속 뜨던 버그를 여기서 막는다.
            if idx == last_assistant_idx:
                used = used_tools_so_far()
                pid = m.get("persona_id", persona_id)
                mlang = m.get("lang", "ko")
                # last_tool로 방금 한 작업의 후속을 우선 제안한다(작업 흐름 연결).
                acts = next_actions(pid, used, last_tool=last_used_tool())
                render_actions(acts, mlang, msg_key=str(idx))

# 첫 화면 선제 선택지. 대화가 아직 비어 있을 때만 띄운다.
# 페르소나를 인식한 요약 카드와 그 사람 상황에 맞는 행동 버튼을 먼저 보여준다.
# 버튼을 누르면 일반 질문과 같은 경로(run_agent_turn)로 LLM이 상황을 판단해 처리한다.
if not st.session_state["messages"]:
    # 첫 화면 선제 선택지 언어. 기본은 한국어로 고정한다(심사 기본 언어).
    # 페르소나 모국어를 따라가면 영어/네팔어 버튼이 섞여 첫 화면이 들쭉날쭉했다.
    # 외국인 모국어 분기는 사용자가 질문을 입력하면 그때 자동감지로 자연히 일어난다.
    # 단 사이드바에서 특정 언어를 명시적으로 고른 경우는 그 언어를 존중한다.
    start_lang = "ko" if lang == "auto" else lang
    render_persona_card(PERS[persona_id])
    st.caption(START_HEADER.get(start_lang, START_HEADER["ko"]))
    acts = next_actions(persona_id, set())  # 아직 쓴 tool 없음
    render_actions(acts, start_lang, msg_key="start", header=False)

prompt = st.chat_input("질문을 입력하세요")
if prompt:
    st.session_state["messages"].append({"role": "user_display", "text": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # 응답 언어 확정. 사이드바가 '자동감지(auto)'면 질문 텍스트의 언어를 감지해 그 언어로 답한다.
    # 사용자가 특정 언어를 골랐으면 그 언어로 강제한다(수동 오버라이드).
    reply_lang = detect_lang(prompt) if lang == "auto" else lang

    # 답변 언어를 user 메시지에 직접 박는다. 시스템 프롬프트의 언어 지시만으로는
    # 사용자 입력 언어(예: 한국어 질문)가 모델을 더 강하게 끌어 무시되기 때문이다.
    lang_directive = LANGUAGES[reply_lang]["instruct"]
    user_text = f"[페르소나: {persona_id}] [답변 언어 강제: {lang_directive}] {prompt}"
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

        def render_steps_panel():
            """tool 단계가 끝난 뒤 처리 과정을 답변 위에 그린다."""
            with proc_box:
                if steps:
                    st.markdown("**처리 과정**")
                    for i, s in enumerate(steps, 1):
                        render_step(i, s["name"], s["args"], s["output"])
                    st.markdown("**답변**")

        # Claude는 진짜 토큰 스트리밍을 지원해 글자가 흐른다(체감 속도 개선).
        # gemini의 OpenAI 호환 엔드포인트는 토큰 스트리밍을 사실상 안 해(응답을 한꺼번에 보냄)
        # 오히려 느리다. 그래서 Claude만 스트리밍, 나머지는 빠른 비스트리밍으로 분기한다.
        if PROVIDER == "claude":
            answer_box = st.empty()
            text = ""
            steps_shown = False
            try:
                with st.spinner("에이전트가 처리 중..."):
                    for chunk in run_chat_stream(
                        user_text, build_system_prompt(reply_lang, persona_id), run_tool, on_step=on_step
                    ):
                        if not chunk:
                            continue
                        if not steps_shown:
                            render_steps_panel()  # 첫 토큰 시점엔 tool 단계가 끝나 있다.
                            steps_shown = True
                        text += chunk
                        answer_box.markdown(strip_emoji(text))
                if not steps_shown:
                    render_steps_panel()
                text = strip_emoji(text)
                answer_box.markdown(text)
            except Exception as e:
                text = f"오류: {e}"
                answer_box.markdown(text)
        else:
            with st.spinner("에이전트가 처리 중..."):
                try:
                    text = run_chat(user_text, build_system_prompt(reply_lang, persona_id), run_tool, on_step=on_step)
                except Exception as e:
                    text = f"오류: {e}"
            render_steps_panel()
            st.write(text)

    # 이번 답변에서 실제로 실행된 tool 이름을 모은다. 다음 행동 선택지에서 이미 한 것을 빼는 데 쓴다.
    used_tools = [s["name"] for s in steps if "name" in s]
    st.session_state["messages"].append(
        {
            "role": "assistant_display", "text": text, "steps": steps,
            "lang": reply_lang, "used_tools": used_tools, "persona_id": persona_id,
        }
    )
    # 답변을 메시지로 확정한 뒤 한 번 더 그린다. 그래야 답변 바로 아래에
    # '다음 행동' 선택지 버튼이 정상 위젯으로 렌더된다(스트리밍 중 인라인 버튼은 key 흐름이 꼬인다).
    st.rerun()
