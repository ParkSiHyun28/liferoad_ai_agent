"""LLM 공급자 스위치.
환경변수 LLM_PROVIDER로 ollama(무료 로컬)와 claude(API)를 분기한다.

- 시연: LLM_PROVIDER=ollama. Ollama 로컬 모델(qwen3.5:4b)로 무료 구동. API 키 불필요.
- 본선: LLM_PROVIDER=claude. 실제 ANTHROPIC_API_KEY로 고성능 모델 구동.

tool 정의(schemas.py)와 tool 실행(tools.py)과 시스템 프롬프트(system_prompt.py)는
공급자와 무관하게 그대로 재사용한다. 이 파일은 공급자별 호출 형식 차이만 흡수한다.
"""

import os
import re
import json

from shared.registry import TOOL_SCHEMAS

# 이모지 제거용 정규식. LLM이 시스템 프롬프트 지시를 흘려 이모지를 써도 코드로 강제 제거한다.
# 산출물에 이모지를 절대 노출하지 않는다는 규칙을 출력단에서 확정한다.
_EMOJI_RE = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF" "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F" "\U000020D0-\U000020FF" "\U00002190-\U000021FF" "]+",
    flags=re.UNICODE,
)
# 한자(CJK) 제거용. 로컬 모델이 가끔 중국어를 섞는다(벤치에서 qwen3.5:4b 한자 1회 누출 관측).
# 우리 도메인은 외국인 금융 상담이라 순한국어가 정상이고 한자는 누출이므로 제거한다.
_HANZI_RE = re.compile("[㐀-䶿一-鿿豈-﫿]+")


def strip_emoji(text: str) -> str:
    """텍스트에서 이모지와 한자(중국어 누출)를 제거하고 군더더기 공백을 정리한다."""
    if not text:
        return text
    out = _EMOJI_RE.sub("", text)
    out = _HANZI_RE.sub("", out)
    # 제거 자리에 남은 연속 공백과 줄머리 공백과 빈 괄호를 정리한다.
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"^[ \t]+", "", out, flags=re.MULTILINE)
    return out

# 공급자 설정. 기본은 무료 시연용 ollama.
PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()

# claude 경로 설정
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# ollama 경로 설정. Ollama는 OpenAI 호환 엔드포인트를 제공한다.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")

# gemini 경로 설정. 무료 티어. OpenAI 호환 엔드포인트를 제공한다.
GEMINI_BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# groq 경로 설정. 무료 티어. OpenAI 호환 엔드포인트를 제공한다. LPU 가속으로 매우 빠르다.
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# OpenAI 호환 공급자 표. base_url/모델/키 환경변수만 다르고 호출 로직은 같다.
# ollama는 키 검증이 없어 더미 키를 쓴다.
_OPENAI_COMPAT = {
    "ollama": {"base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL, "key_env": None, "no_think": True, "tool_retry": 0},
    "gemini": {"base_url": GEMINI_BASE_URL, "model": GEMINI_MODEL, "key_env": "GEMINI_API_KEY", "no_think": False, "tool_retry": 0},
    # groq의 Llama 3.3 70B는 긴 한국어 시스템 프롬프트에서 가끔 tool call을 <function=...> XML로
    # 잘못 뱉어 400(tool_use_failed)이 난다. 알려진 간헐 버그라 같은 입력도 재시도하면 대개 통과한다.
    "groq": {"base_url": GROQ_BASE_URL, "model": GROQ_MODEL, "key_env": "GROQ_API_KEY", "no_think": False, "tool_retry": 3},
}


def provider_label() -> str:
    """현재 공급자와 모델을 사람이 읽을 라벨로 반환한다. 사이드바 표시용."""
    if PROVIDER == "claude":
        return f"Claude API ({CLAUDE_MODEL})"
    if PROVIDER == "gemini":
        return f"Gemini 무료 ({GEMINI_MODEL})"
    if PROVIDER == "groq":
        return f"Groq 무료 ({GROQ_MODEL})"
    return f"Ollama 로컬 ({OLLAMA_MODEL})"


def _anthropic_tools() -> list[dict]:
    """schemas.py를 Anthropic tools 형식 그대로 반환한다."""
    return list(TOOL_SCHEMAS.values())


def _openai_tools() -> list[dict]:
    """schemas.py를 OpenAI function-calling 형식으로 변환한다.
    Anthropic {name, description, input_schema} → OpenAI {type, function:{name, description, parameters}}."""
    out = []
    for s in TOOL_SCHEMAS.values():
        out.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["input_schema"],
            },
        })
    return out


# --- Claude 경로 ---

def _run_claude(history: list[dict], system: str, run_tool) -> tuple[str, list[dict]]:
    """Anthropic tool use 루프. history는 Anthropic messages 형식을 받는다."""
    from anthropic import Anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("LLM_PROVIDER=claude인데 ANTHROPIC_API_KEY가 없습니다.")
    client = Anthropic(api_key=key)
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    tools = _anthropic_tools()

    while True:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=sys_blocks,
            tools=tools,
            messages=history,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            history.append({"role": "assistant", "content": resp.content})
            return text, history
        history.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = run_tool(block.name, dict(block.input))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })
        history.append({"role": "user", "content": results})


# --- OpenAI 호환 경로 (ollama / gemini / groq 공용) ---

def _run_openai_compat(cfg: dict, history: list[dict], system: str, run_tool) -> tuple[str, list[dict]]:
    """OpenAI 호환 tool calling 루프. ollama/gemini/groq가 같은 로직을 공유한다.
    cfg는 _OPENAI_COMPAT의 한 항목(base_url/model/key_env/no_think).
    history는 OpenAI messages 형식을 받는다(첫 호출 시 user 메시지 1개)."""
    from openai import OpenAI

    key_env = cfg["key_env"]
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise RuntimeError(f"LLM_PROVIDER={PROVIDER}인데 {key_env}가 없습니다.")
    else:
        key = "ollama"  # 로컬은 키 검증 없음
    client = OpenAI(base_url=cfg["base_url"], api_key=key)
    tools = _openai_tools()
    # qwen3 등 로컬 모델은 thinking 모드가 기본이라 추론 토큰으로 크게 느려진다.
    # /no_think로 추론을 꺼 속도를 확보한다. 클라우드 모델(gemini/groq)은 불필요.
    sys_text = system + ("\n\n/no_think" if cfg["no_think"] else "")
    # groq Llama는 tool call을 XML로 잘못 뱉는 버릇이 있어 표준 JSON 형식을 명시한다.
    if cfg.get("tool_retry"):
        sys_text += "\n\ntool을 호출할 때는 반드시 표준 JSON tool_call 형식만 쓴다. <function=...> 같은 텍스트 형식은 금지한다."
    messages = [{"role": "system", "content": sys_text}] + history

    def _create():
        """tool_use_failed(groq 간헐 400)면 재시도한다. 다른 오류는 그대로 올린다."""
        from openai import BadRequestError
        last = None
        for _ in range(cfg.get("tool_retry", 0) + 1):
            try:
                return client.chat.completions.create(
                    model=cfg["model"], messages=messages, tools=tools,
                    max_tokens=1500,  # 4b 폭주(4천 토큰 장황 생성) 방지. 요약 답변엔 충분.
                )
            except BadRequestError as e:
                if "tool_use_failed" not in str(e):
                    raise
                last = e  # 간헐 버그. 다시 시도.
        raise last

    while True:
        resp = _create()
        msg = resp.choices[0].message
        if not msg.tool_calls:
            text = msg.content or ""
            messages.append({"role": "assistant", "content": text})
            return text, messages
        # assistant turn에 tool_calls 보존
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            out = run_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(out, ensure_ascii=False),
            })


def run_chat(user_text: str, system: str, run_tool, on_step=None) -> str:
    """공급자 무관 진입점. 사용자 발화 1개를 받아 최종 텍스트를 반환한다.

    user_text: 페르소나 태그가 붙은 사용자 질문.
    system: build_system_prompt() 결과.
    run_tool: (name, args) -> dict. app.py가 넘기는 tool 실행 함수.
    on_step: 선택. 처리 단계를 보고받는 콜백. on_step(kind, payload) 형태로 호출된다.
             kind="tool_call"이면 payload={name, args, output}. 시각화 패널이 이걸 받는다.
    """
    # run_tool을 감싸 호출 단계를 on_step으로 흘린다. 실제 동작과 100% 일치한다.
    def traced_run_tool(name, args):
        out = run_tool(name, args)
        if on_step:
            on_step("tool_call", {"name": name, "args": dict(args), "output": out})
        return out

    if PROVIDER == "claude":
        history = [{"role": "user", "content": user_text}]
        text, _ = _run_claude(history, system, traced_run_tool)
        return strip_emoji(text)
    cfg = _OPENAI_COMPAT.get(PROVIDER)
    if cfg is None:
        raise RuntimeError(
            f"알 수 없는 LLM_PROVIDER={PROVIDER}. 가능: claude, ollama, gemini, groq."
        )
    history = [{"role": "user", "content": user_text}]
    text, _ = _run_openai_compat(cfg, history, system, traced_run_tool)
    return strip_emoji(text)
