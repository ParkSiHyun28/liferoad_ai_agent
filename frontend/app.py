"""My LifeRoad 자산 부문 데모 Streamlit 앱.
대화 모드(LLM tool use)와 능동 모드(버튼 트리거) 둘 다 지원.
대화 모드의 LLM 공급자는 llm_provider.py가 LLM_PROVIDER 환경변수로 분기한다(ollama/claude).
대화 모드는 LLM이 어떤 tool을 어떤 순서로 호출하는지 '처리 과정' 패널로 단계별 시각화한다."""

from __future__ import annotations  # 타입 힌트를 문자열로 지연 평가(낮은 파이썬 버전 안전)

import os
import re
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


# LLM이 답변 끝에 붙이는 후속 선택지 마커. 이 줄 이후를 버튼 라벨로 파싱한다.
_NEXT_MARKER = "<<NEXT>>"


def split_answer_and_actions(text: str) -> tuple[str, list[str]]:
    """LLM 답변에서 본문과 후속 선택지 라벨을 분리한다.

    LLM은 답변 끝에 `<<NEXT>>` 한 줄을 두고 그 아래 후속 행동을 한 줄씩 적도록 지시받는다.
    이 함수는 마커 앞은 화면에 보일 본문으로, 마커 뒤 각 줄은 버튼 라벨로 가른다.
    마커가 없으면(모델이 형식을 안 지킴) 본문 전체를 그대로 두고 빈 라벨 리스트를 돌려준다.
    번호나 기호로 시작하는 줄은 기호를 떼어 정리한다. 너무 길거나 빈 줄은 버린다.
    스트리밍 중 꼬리가 마커 접두사(<<NEXT 또는 <)로 끝나면 그 앞까지만 본문으로 쓴다."""
    if not text:
        return text, []
    # 스트리밍 중 마커가 부분적으로 들어온 경우: 꼬리가 마커 접두사로 끝나면 숨긴다.
    # <<NEXT>> 가 완전히 없으면 partial_marker도 없다 → 일반 경로로 처리.
    partial_marker_prefixes = ("<<NEXT>>", "<<NEXT>", "<<NEXT", "<<NEX", "<<NE", "<<N", "<<")
    if _NEXT_MARKER not in text:
        # 꼬리가 마커 접두사로 끝나면 그 앞까지만 반환(깜빡임 방지)
        for prefix in partial_marker_prefixes[1:]:  # <<NEXT>> 제외(완전한 마커)
            if text.endswith(prefix):
                return text[: -len(prefix)].rstrip(), []
        return text, []
    # 마지막 마커 기준으로 분리(본문 중간에 우발적으로 마커가 끼면 마지막을 기준으로 함).
    idx = text.rfind(_NEXT_MARKER)
    body = text[:idx]
    tail = text[idx + len(_NEXT_MARKER):]
    # 본문이 공백뿐이면 마커 분리를 취소하고 원문을 본문으로 씀(빈 답변 말풍선 방지).
    if not body.strip():
        return text, []
    labels: list[str] = []
    for raw in tail.splitlines():
        line = raw.strip()
        if not line:
            continue
        # "- ", "* ", "1. ", "1) " 같은 머리 기호를 떼어낸다.
        line = re.sub(r"^[\-\*•]\s*", "", line)
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = line.strip().strip('"').strip("'").strip()
        if not line or len(line) > 40:
            continue  # 빈 줄과 비정상적으로 긴 줄(문장 누출)은 버튼으로 안 만든다.
        if line.endswith((".", "다", "요")) and len(line) > 28:
            continue  # 명령형 짧은 문구가 아니라 서술 문장이 새면 버튼으로 안 만든다.
        labels.append(line)
        if len(labels) >= 4:
            break
    return body.rstrip(), labels


_DONE_MARKER = "<<DONE>>"


def parse_done_marker(text: str) -> tuple[str, bool]:
    """LLM 답변에서 <<DONE>> 마커를 찾아 제거하고 is_done 불리언을 함께 반환한다.

    <<DONE>> 마커는 화면에 노출하지 않는다. 본문에서 제거한 뒤 is_done=True로 알린다.
    마커가 없으면 원본 텍스트와 is_done=False를 그대로 돌려준다.
    split_answer_and_actions 호출 전에 먼저 적용하면 기존 파싱 흐름을 그대로 유지한다."""
    if _DONE_MARKER not in text:
        return text, False
    cleaned = text.replace(_DONE_MARKER, "").strip()
    # 마커 제거 뒤 연속 빈 줄이 생기면 하나로 줄인다.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, True


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
# _rand_pid를 사용한 뒤 즉시 제거해 비자 필터 변경 시 기본값이 튀지 않게 한다.
st.session_state.pop("_rand_pid", None)
persona_id = st.sidebar.selectbox(
    "페르소나",
    options=ids,
    index=default_idx,
    key="persona_selectbox",
    format_func=lambda k: f"[{PERS[k]['flag']}] {PERS[k]['name']} ({PERS[k]['visa']} {PERS[k]['role']})",
)

# 페르소나가 바뀌면 대화 이력을 비운다. 다른 사람 상담이 시작되므로 선택지와 누적
# 사용 이력도 새 사람 기준으로 초기화돼야 한다(엉뚱한 사람의 선택지가 남는 것 방지).
if st.session_state.get("_active_persona") != persona_id:
    st.session_state["_active_persona"] = persona_id
    st.session_state["messages"] = []
    st.session_state.pop("pending_intent", None)
    # 페르소나가 바뀌면 AI 추천 캐시와 완료 작업 기록을 초기화한다.
    st.session_state.pop("ai_intro", None)
    st.session_state["completed_tools"] = set()

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

def start_action_labels(
    persona_id: str,
    reply_lang: str,
    limit: int = 3,
    exclude_tools: set | None = None,
) -> list[str]:
    """첫 화면 선제 선택지 라벨을 만든다(정적, 페르소나 기반).

    첫 화면에는 아직 LLM 답변이 없어 LLM이 후속을 만들 수 없다. 그래서 여기서만
    페르소나 속성(active_plan)으로 의미 있는 행동을 골라 정적 라벨로 보여준다.
    버튼을 누르면 그 라벨 문구가 LLM에 전달되고, 이후 모든 후속 선택지는
    LLM이 답변과 함께 직접 생성한다(split_answer_and_actions로 파싱).
    exclude_tools: 이미 완료한 tool 이름. 해당 tool의 행동은 추천에서 뺀다."""
    plan = active_plan(persona_id)
    excluded = exclude_tools or set()
    out: list[str] = []
    seen: set[str] = set()
    for tname, _ in plan:
        if tname in seen or tname not in ACTION_LABELS:
            continue
        if tname in excluded:
            continue
        seen.add(tname)
        label = ACTION_LABELS.get(tname, {}).get(reply_lang) \
            or ACTION_LABELS.get(tname, {}).get("ko") or tname
        out.append(label)
        if len(out) >= limit:
            break
    return out


# 종결 안내 문구. 대화가 자연스럽게 끝났을 때 떠야 할 안내.
_DONE_CAPTION = {
    "ko": "필요한 점검을 모두 마쳤습니다. 다른 궁금한 점이 있으면 말씀해 주세요.",
    "en": "All checks are complete. Let me know if you have other questions.",
    "vi": "Đã hoàn tất mọi kiểm tra. Nếu bạn còn câu hỏi, hãy cho tôi biết.",
    "ne": "सबै जाँच सकियो। अरू प्रश्न भए सोध्नुहोस्।",
}


def ai_recommend_actions(
    persona_id: str,
    reply_lang: str,
    exclude_tools: set | None = None,
) -> tuple[str, list[str]]:
    """LLM이 페르소나 상황을 읽고 첫 화면 추천 행동을 동적으로 생성한다.

    반환: (인사+상황요약 본문, 추천 라벨 리스트).
    LLM 호출 실패 또는 라벨이 비면 정적 폴백(start_action_labels)을 쓴다.
    결과는 st.session_state["ai_intro"]에 캐싱한다. 같은 페르소나+언어로 rerun해도
    LLM을 다시 부르지 않는다."""
    cache_key = f"{persona_id}__{reply_lang}"
    cached = st.session_state.get("ai_intro", {})
    if cache_key in cached:
        return cached[cache_key]

    p = get_persona(persona_id)
    lang_directive = LANGUAGES[reply_lang]["instruct"]

    excluded = exclude_tools or set()
    exclude_note = ""
    if excluded:
        done_labels = [
            ACTION_LABELS.get(t, {}).get("ko") or t
            for t in excluded
            if t in ACTION_LABELS
        ]
        if done_labels:
            exclude_note = f" 이미 처리한 작업은 제외해 줘: {', '.join(done_labels)}."

    user_text = (
        f"[페르소나: {persona_id}] [답변 언어 강제: {lang_directive}] "
        f"오늘은 {TODAY}입니다. "
        f"지금 이 사용자의 비자와 입국일과 출국 예정일과 오늘 날짜와 자산과 연금 납부 상황을 종합해 "
        f"지금 가장 먼저 챙겨야 할 금융 행동을 우선순위로 3개 추천해 줘. "
        f"짧은 인사와 핵심 상황 한 줄 요약 뒤에 <<NEXT>>로 추천 행동 3개를 적어 줘."
        f"{exclude_note}"
    )

    fallback_body = f"{p['name']}님 상황을 살펴봤습니다."
    fallback_labels = start_action_labels(persona_id, reply_lang, exclude_tools=excluded)

    system = build_system_prompt(reply_lang, persona_id)
    try:
        raw = run_chat(user_text, system, run_tool)
        raw = strip_emoji(raw)
        # <<DONE>> 마커가 오면 제거(첫 화면에선 의미 없음)
        raw, _ = parse_done_marker(raw)
        body, labels = split_answer_and_actions(raw)
        if not labels:
            labels = fallback_labels
        if not body.strip():
            body = fallback_body
    except Exception:
        body = fallback_body
        labels = fallback_labels

    result = (body, labels)
    if "ai_intro" not in st.session_state:
        st.session_state["ai_intro"] = {}
    st.session_state["ai_intro"][cache_key] = result
    return result


def render_actions(
    labels: list[str],
    reply_lang: str,
    msg_key: str,
    header: bool = True,
    is_start: bool = False,
    body_text: str = "",
    show_end_button: bool = False,
):
    """답변 아래에 '다음 행동' 선택지 버튼을 그린다. 능동성을 눈에 보이게 만드는 핵심 UI.

    labels: 버튼에 그대로 들어갈 문구 리스트.
            대화 진행 중에는 LLM이 답변과 함께 생성한 후속 행동이다(답변과 일치 보장).
            첫 화면에서는 페르소나 기반 정적 문구다(아직 LLM 답변이 없으므로).
    reply_lang: 헤더 caption 언어.
    msg_key: 버튼 위젯 key 충돌 방지용 접두어.
    header: NEXT_HEADER caption을 직접 그릴지. 첫 화면은 호출부가 START_HEADER를 따로 그리므로 False.
    is_start: True면 첫 화면(대화 시작 전). 종결 안내를 띄우지 않는다.
    body_text: 본문 텍스트. 종결 의도 판별에 쓴다.
    show_end_button: 작업 매듭(is_done)일 때만 True. "대화 종료하기" 버튼을 추가로 그린다.

    버튼이 눌리면 그 문구 자체를 사용자 의도로 session_state['pending_intent']에 담고 rerun한다.
    문구를 그대로 LLM에 보내므로 에이전트가 그 요청을 보고 tool을 스스로 골라 처리한다."""
    if not labels and not show_end_button:
        # 첫 화면이 아니고 라벨도 종료 버튼도 없으면 종결 안내 caption을 띄운다.
        if not is_start:
            st.caption(_DONE_CAPTION.get(reply_lang, _DONE_CAPTION["ko"]))
        return
    if header and labels:
        st.caption(NEXT_HEADER.get(reply_lang, NEXT_HEADER["ko"]))
    if labels:
        cols = st.columns(len(labels))
        for i, (col, label) in enumerate(zip(cols, labels)):
            if col.button(label, key=f"act_{msg_key}_{i}", use_container_width=True):
                # 버튼 문구를 그대로 LLM에 보낸다. 에이전트가 상황을 보고 tool을 스스로 고른다.
                st.session_state["pending_intent"] = {
                    "intent": label,
                    "label": label,  # 대화에 남길 '사용자가 고른 행동' 표시
                    "lang": reply_lang,
                }
                st.rerun()
    if show_end_button:
        if st.button("대화 종료하기", key=f"end_{msg_key}", use_container_width=False):
            # 대화를 초기화하고 AI 추천 캐시를 무효화한다. completed_tools는 유지한다.
            st.session_state["messages"] = []
            st.session_state.pop("ai_intro", None)
            st.rerun()


def _build_history(max_turns: int = 3) -> list[dict]:
    """session_state["messages"]에서 직전 최대 max_turns 턴을 [{role, content}] 형태로 변환한다.

    LLM 멀티턴 메모리용. user_display/user_action은 role="user"로, assistant_display의 text는
    role="assistant"로 매핑한다. tool_result 블록은 토큰 비용 때문에 제외한다.
    현재 발화는 호출부에서 user_text로 별도 전달하므로 여기에 포함하지 않는다."""
    messages = st.session_state.get("messages", [])
    # assistant_display 기준으로 완성된 턴을 뒤에서 max_turns개 자른다.
    # 하나의 "턴" = 직전 user 메시지 1개 + assistant 메시지 1개 쌍.
    pairs: list[tuple[str, str]] = []
    i = len(messages) - 1
    while i >= 0 and len(pairs) < max_turns:
        m = messages[i]
        if m["role"] == "assistant_display":
            # assistant 메시지를 찾았으면 직전 user 메시지를 탐색한다.
            asst_text = m.get("text", "")
            j = i - 1
            while j >= 0 and messages[j]["role"] not in ("user_display", "user_action"):
                j -= 1
            if j >= 0:
                user_text = messages[j].get("text", "")
                pairs.append((user_text, asst_text))
                i = j - 1
            else:
                break
        else:
            i -= 1
    # 오래된 것이 앞에 오게 역전한다.
    pairs.reverse()
    history: list[dict] = []
    for u, a in pairs:
        history.append({"role": "user", "content": u})
        history.append({"role": "assistant", "content": a})
    return history


def _korean_error_msg(e: Exception) -> str:
    """예외를 종류별 한국어 안내 문구로 변환한다."""
    try:
        import anthropic as _ant
        if isinstance(e, _ant.RateLimitError):
            return "지금 요청이 몰려 잠시 후 다시 시도해 주세요."
        if isinstance(e, (_ant.APITimeoutError, _ant.APIConnectionError)):
            return "응답이 지연됩니다. 잠시 후 다시 시도해 주세요."
    except ImportError:
        pass
    msg = str(e)
    if "API 키" in msg or "ANTHROPIC_API_KEY" in msg or "GEMINI_API_KEY" in msg or "key" in msg.lower():
        return "API 키 설정이 필요합니다. 사이드바에서 키를 입력해 주세요."
    if "RuntimeError" in type(e).__name__ and "키" in msg:
        return "API 키 설정이 필요합니다. 사이드바에서 키를 입력해 주세요."
    return "일시적인 오류가 발생했습니다. 다시 시도해 주세요."


def run_agent_turn(user_intent: str, reply_lang: str, display_user: str, is_action: bool):
    """사용자 발화 1건을 에이전트에 보내고 답변과 처리 과정을 messages에 남긴다.
    일반 질문과 선택지 버튼이 같은 경로를 쓰게 하는 공통 함수.

    user_intent: LLM에 보낼 실제 의도 문장(버튼이면 버튼 라벨 문구, 질문이면 입력 원문).
    reply_lang: 답변 언어 코드.
    display_user: 대화에 남길 사용자 측 표시 텍스트(버튼이면 버튼 라벨, 질문이면 입력 원문).
    is_action: 버튼에서 왔으면 True. 대화에 '[선택]' 칩으로 구분 표시한다.

    LLM이 상황을 보고 tool을 스스로 골라 실행하고, 답변 끝에 다음 행동 선택지까지 직접 만든다.
    그래서 답변에서 던진 제안과 화면 버튼이 항상 일치한다."""
    role = "user_action" if is_action else "user_display"
    st.session_state["messages"].append({"role": role, "text": display_user})

    # 멀티턴 메모리: 직전 최대 3턴을 히스토리로 넘겨 LLM이 문맥을 기억하게 한다.
    prior_history = _build_history(max_turns=3)

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
    error_occurred = False
    if PROVIDER == "claude":
        text = ""
        try:
            for chunk in run_chat_stream(
                user_text, system, run_tool, on_step=on_step, history=prior_history
            ):
                if chunk:
                    text += chunk
            text = strip_emoji(text)
        except Exception as e:
            print(repr(e), file=sys.stderr)
            error_occurred = True
            text = _korean_error_msg(e)
    else:
        try:
            text = run_chat(
                user_text, system, run_tool, on_step=on_step, history=prior_history
            )
        except Exception as e:
            print(repr(e), file=sys.stderr)
            error_occurred = True
            text = _korean_error_msg(e)

    # 오류로 끝난 turn은 messages에 저장하지 않는다(영문 예외가 영구 박제되지 않게).
    if error_occurred:
        st.error(text)
        # 직전에 push했던 user 메시지도 제거해 대화 흐름을 정갈하게 유지한다.
        if st.session_state["messages"] and st.session_state["messages"][-1]["role"] == role:
            st.session_state["messages"].pop()
        return

    used = [s["name"] for s in steps if "name" in s]
    # <<DONE>> 마커를 먼저 제거하고 is_done 여부를 확인한다.
    text_no_done, is_done = parse_done_marker(text)
    # LLM이 답변 끝에 붙인 후속 선택지(<<NEXT>>)를 본문과 분리한다.
    # 본문만 화면에 보이고, 라벨은 다음 행동 버튼이 된다(답변과 일치 보장).
    body, next_labels = split_answer_and_actions(text_no_done)

    # 완료된 작업을 누적한다. 이번 턴 used_tools를 completed_tools에 쌓는다.
    if used:
        st.session_state["completed_tools"] = (
            st.session_state.get("completed_tools", set()) | set(used)
        )

    # 작업이 끝나지 않았는데 next_labels가 비면 start_action_labels에서 폴백 1~2개를 채운다.
    # 작업 종결(is_done) 시에는 폴백을 넣지 않아 종료 흐름을 막지 않는다.
    if not next_labels and not is_done:
        _completed = st.session_state.get("completed_tools", set())
        fallback = start_action_labels(persona_id, reply_lang, exclude_tools=_completed)
        next_labels = fallback[:2]

    st.session_state["messages"].append({
        "role": "assistant_display", "text": body, "steps": steps,
        "lang": reply_lang, "used_tools": used, "persona_id": persona_id,
        "next_labels": next_labels, "is_done": is_done,
    })


# 능동 모드 — 실행 후 결과를 session_state에 저장해 rerun 후에도 재렌더된다(P2-2).
if st.session_state.get("run_active"):
    st.session_state["run_active"] = False
    p_name = PERS[persona_id]["name"]
    plan = active_plan(persona_id)
    collected: list[dict] = []  # {tname, card, summary, error}
    for tname, targs in plan:
        try:
            out = run_tool(tname, targs)
            collected.append({"tname": tname, "card": out.get("card"), "summary": out.get("summary", "")})
        except Exception as e:
            collected.append({"tname": tname, "card": None, "summary": "", "error": str(e)})
    # 결과를 assistant_display 메시지로 대화 흐름에 흡수한다. rerun 후에도 재생 루프가 표시한다.
    summary_lines = []
    for item in collected:
        label = TOOL_LABELS.get(item["tname"], item["tname"])
        if item.get("error"):
            summary_lines.append(f"{label}: 오류 — {item['error']}")
        elif item["card"]:
            summary_lines.append(f"{label}: {item['card'].get('head', '')} — {item['card'].get('metric', '')}")
        else:
            summary_lines.append(f"{label}: {item['summary']}")
    summary_text = f"{p_name}님 능동 점검 결과 (기준일 {TODAY})\n\n" + "\n".join(summary_lines)
    st.session_state["messages"].append({
        "role": "assistant_display",
        "text": summary_text,
        "steps": [],
        "lang": "ko",
        "used_tools": [c["tname"] for c in collected],
        "persona_id": persona_id,
        "next_labels": [],
        "active_cards": collected,  # 카드 재렌더용 리스트
    })
    st.divider()

# 대화 모드
st.subheader("대화")
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "completed_tools" not in st.session_state:
    st.session_state["completed_tools"] = set()

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
            # 능동 점검 결과 카드들을 순회 렌더한다(rerun 후에도 재생 루프가 재현).
            for item in m.get("active_cards", []):
                if item.get("card"):
                    render_card(item["card"])
                elif item.get("error"):
                    st.warning(f"{TOOL_LABELS.get(item['tname'], item['tname'])} 처리 중 오류: {item['error']}")
                else:
                    st.info(item.get("summary", ""))
            # 개별 카드 복원(단일 card 키 하위 호환).
            if m.get("card"):
                render_card(m["card"])
            # 마지막 assistant 메시지에만 '다음 행동' 선택지 버튼을 붙인다.
            # 선택지는 LLM이 답변과 함께 생성한 것이다(답변에서 던진 제안과 버튼이 일치).
            if idx == last_assistant_idx:
                mlang = m.get("lang", "ko")
                _is_done = m.get("is_done", False)
                _has_completed = bool(st.session_state.get("completed_tools"))
                render_actions(
                    m.get("next_labels", []),
                    mlang,
                    msg_key=str(idx),
                    show_end_button=(_is_done and _has_completed),
                )

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
    # AI 추천 캐시 여부 확인. 캐시가 없으면 LLM을 1회 호출해 동적 추천을 생성한다.
    _cache_key = f"{persona_id}__{start_lang}"
    _has_cache = _cache_key in st.session_state.get("ai_intro", {})
    _completed = st.session_state.get("completed_tools", set())

    # 모든 active_plan tool을 완료했으면 별도 안내를 보여준다.
    _plan_tools = {t for t, _ in active_plan(persona_id)}
    _all_done = bool(_plan_tools) and _plan_tools.issubset(_completed)

    if _all_done:
        st.info("현재 챙겨야 할 주요 작업을 모두 마쳤습니다. 다른 궁금한 점이 있으면 입력해 주세요.")
    else:
        if not _has_cache:
            with st.spinner("상황을 분석하고 있습니다..."):
                intro_body, intro_labels = ai_recommend_actions(
                    persona_id, start_lang, exclude_tools=_completed
                )
        else:
            intro_body, intro_labels = ai_recommend_actions(
                persona_id, start_lang, exclude_tools=_completed
            )

        if intro_body:
            st.markdown(intro_body)
        st.caption(START_HEADER.get(start_lang, START_HEADER["ko"]))
        render_actions(intro_labels, start_lang, msg_key="start", header=False, is_start=True)

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

    # 멀티턴 메모리: 직전 최대 3턴을 히스토리로 넘겨 LLM이 문맥을 기억하게 한다.
    # user_display 메시지를 방금 push했으므로 _build_history는 그 직전까지를 반환한다.
    # (현재 user 메시지는 user_text로 별도 전달해 중복을 막는다)
    prior_history = _build_history(max_turns=3)
    # 방금 push한 user_display가 아직 assistant 짝이 없으므로 히스토리에서 빠진다(정상).

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

    error_occurred_chat = False
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
                        user_text,
                        build_system_prompt(reply_lang, persona_id),
                        run_tool,
                        on_step=on_step,
                        history=prior_history,
                    ):
                        if not chunk:
                            continue
                        if not steps_shown:
                            render_steps_panel()  # 첫 토큰 시점엔 tool 단계가 끝나 있다.
                            steps_shown = True
                        text += chunk
                        # 스트리밍 중에는 <<NEXT>> 마커와 <<DONE>> 마커 이후를 숨기고 본문만 흘린다.
                        _preview = split_answer_and_actions(parse_done_marker(strip_emoji(text))[0])[0]
                        answer_box.markdown(_preview)
                if not steps_shown:
                    render_steps_panel()
                text = strip_emoji(text)
                answer_box.markdown(split_answer_and_actions(parse_done_marker(text)[0])[0])
            except Exception as e:
                print(repr(e), file=sys.stderr)
                error_occurred_chat = True
                err_msg = _korean_error_msg(e)
                # 누적 텍스트가 있으면 부분 답변을 살리고 중단 안내를 붙인다.
                if text.strip():
                    text = strip_emoji(text) + "\n\n(응답이 일시 중단되었습니다)"
                else:
                    text = err_msg
                answer_box.markdown(split_answer_and_actions(text)[0])
        else:
            with st.spinner("에이전트가 처리 중..."):
                try:
                    text = run_chat(
                        user_text,
                        build_system_prompt(reply_lang, persona_id),
                        run_tool,
                        on_step=on_step,
                        history=prior_history,
                    )
                except Exception as e:
                    print(repr(e), file=sys.stderr)
                    error_occurred_chat = True
                    text = _korean_error_msg(e)
            render_steps_panel()
            st.write(split_answer_and_actions(text)[0])

    # 오류로 끝난 turn은 messages에 저장하지 않는다(영문 예외가 영구 박제되지 않게).
    if error_occurred_chat:
        # 방금 push한 user_display를 제거해 대화 흐름을 정갈하게 유지한다.
        if st.session_state["messages"] and st.session_state["messages"][-1]["role"] == "user_display":
            st.session_state["messages"].pop()
        st.rerun()

    # 이번 답변에서 실제로 실행된 tool 이름을 모은다.
    used_tools = [s["name"] for s in steps if "name" in s]
    # <<DONE>> 마커를 먼저 제거하고 is_done 여부를 확인한다.
    text_no_done, is_done = parse_done_marker(text)
    # LLM이 답변 끝에 붙인 후속 선택지(<<NEXT>>)를 본문과 분리해 저장한다.
    body, next_labels = split_answer_and_actions(text_no_done)

    # 완료된 작업을 누적한다. 이번 턴 used_tools를 completed_tools에 쌓는다.
    if used_tools:
        st.session_state["completed_tools"] = (
            st.session_state.get("completed_tools", set()) | set(used_tools)
        )

    # 작업이 끝나지 않았는데 next_labels가 비면 start_action_labels에서 폴백 1~2개를 채운다.
    # 작업 종결(is_done) 시에는 폴백을 넣지 않아 종료 흐름을 막지 않는다.
    if not next_labels and not is_done:
        _completed = st.session_state.get("completed_tools", set())
        fallback_chat = start_action_labels(persona_id, reply_lang, exclude_tools=_completed)
        next_labels = fallback_chat[:2]

    st.session_state["messages"].append(
        {
            "role": "assistant_display", "text": body, "steps": steps,
            "lang": reply_lang, "used_tools": used_tools, "persona_id": persona_id,
            "next_labels": next_labels, "is_done": is_done,
        }
    )
    # 답변을 메시지로 확정한 뒤 한 번 더 그린다. 그래야 답변 바로 아래에
    # '다음 행동' 선택지 버튼이 정상 위젯으로 렌더된다(스트리밍 중 인라인 버튼은 key 흐름이 꼬인다).
    st.rerun()
