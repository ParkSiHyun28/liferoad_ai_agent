"""팀 공용 시스템 프롬프트. 모든 부문이 같은 프롬프트를 써서 LLM 출력 톤을 통일한다.

다국어 지원: 외국인 사용자가 모국어로 금융 상담을 받게 한다. 답변 언어를 인자로 받아
시스템 프롬프트에 그 언어로 답하라는 지시를 끼운다. tool 데이터(카드 등)는 한국어 원본을
유지하되 LLM이 사용자에게 전달하는 답변 문장만 선택 언어로 생성한다."""

from shared.personas import get_persona

# 지원 언어. 키는 코드 식별자, name은 사람이 읽을 라벨, instruct는 LLM에 주는 답변 언어 지시.
LANGUAGES = {
    "ko": {"name": "한국어", "instruct": "반드시 한국어로만 답합니다."},
    "vi": {"name": "Tiếng Việt (베트남어)", "instruct": "Trả lời hoàn toàn bằng tiếng Việt. (반드시 베트남어로만 답합니다.)"},
    "ne": {"name": "नेपाली (네팔어)", "instruct": "पूर्ण रूपमा नेपाली भाषामा जवाफ दिनुहोस्। (반드시 네팔어로만 답합니다.)"},
    "en": {"name": "English (영어)", "instruct": "Respond entirely in English. (반드시 영어로만 답합니다.)"},
}

# 국가명에서 모국어 코드를 유도한다. persona_id 하드코딩 없이 country로 언어를 정한다.
# LANGUAGES에 instruct가 있는 코드(vi ne)만 실제 효과가 있고 나머지는 ko로 폴백한다.
COUNTRY_LANG = {
    "베트남": "vi",
    "네팔": "ne",
    # 아래는 모국어 코드를 표기만 해 두되 LANGUAGES 미정의라 실제론 ko로 폴백된다.
    "태국": "th", "인도네시아": "id", "캄보디아": "km", "미얀마": "my",
    "필리핀": "en", "방글라데시": "bn", "인도": "en", "우즈베키스탄": "uz",
    "중국": "zh", "몽골": "mn",
}


def default_lang_for_persona(persona_id: str) -> str:
    """페르소나의 country에서 모국어 코드를 유도한다. persona_id 하드코딩 없음.
    country가 미지정이거나 LANGUAGES에 instruct가 없는 언어면 ko로 폴백한다.
    참고: 데모 기본값은 app.py가 'ko'로 고정한다. 이 함수는 모국어 유도가
    필요할 때 쓰는 보조 도구다."""
    try:
        p = get_persona(persona_id)
    except ValueError:
        return "ko"
    lang = COUNTRY_LANG.get(p.get("country", ""), "ko")
    return lang if lang in LANGUAGES else "ko"

_BASE = """당신은 My LifeRoad입니다. 외국인의 한국 금융 생활을 입국부터 귀국까지 동행하는 라이프케어 AI 에이전트입니다.

## 3원리
1. 능동성: 사용자가 묻기 전에 마감과 손실을 먼저 감지해 알립니다.
2. 개인화: 페르소나의 비자와 국적과 체류 상황을 기준으로 답합니다.
3. 대리처리: 정보 안내에 그치지 않고 서류 작성까지 대행합니다.

{persona_block}
## 답변 언어 (중요)
- {lang_instruct}
- 단 고유명사(비자 코드 E-9, 기관명, 상품명)와 금액 숫자는 원형을 유지해도 됩니다.
- tool 결과 카드의 내용은 한국어 원본입니다. 그 의미를 사용자 언어로 풀어 전달합니다.

## 답변 규칙
- 이모지(이모티콘)를 절대 쓰지 않습니다. 텍스트로만 답합니다.
- 핵심 결론을 먼저 말합니다.
- 수치는 반드시 근거와 함께 제시합니다.
- 외국인이 이해하기 쉬운 평이한 문장을 씁니다. 전문용어는 풀어 설명합니다.
- 마지막은 다음에 할 행동을 제안하며 마무리합니다.
- 불리한 사실(연금 수령 불가 등)도 숨기지 않고 정직하게 안내합니다.
- tool 결과의 card 정보가 있으면 그 내용을 사용자에게 명확히 전달합니다.

## 도구 사용
- 사용자 질문에 답하려면 적절한 tool을 호출합니다.
- 어느 페르소나에 대한 질문인지 persona_id로 구분합니다.
"""


def _persona_block(persona_id: str | None) -> str:
    """현재 상담 중인 페르소나 한 명만 설명 블록으로 만든다. 동적 페르소나 50~100명을
    전부 싣지 않고 지금 상담 대상 한 명만 넣어 프롬프트와 캐싱을 안정화한다.
    persona_id가 없거나 알 수 없으면 빈 문자열을 돌려줘 기존 톤을 유지한다."""
    if not persona_id:
        return ""
    try:
        p = get_persona(persona_id)
    except ValueError:
        return ""
    return (
        "## 현재 사용자(페르소나)\n"
        f"- id {p['id']} / {p['name']} ({p['name_en']})\n"
        f"- {p['country']} 국적. {p['visa']} {p['role']}.\n"
        f"- 입국 {p['entry_date']}, 출국 예정 {p['exit_plan']}.\n"
        f"- {p['summary']}\n"
    )


def build_system_prompt(lang: str = "ko", persona_id: str | None = None) -> str:
    """공용 시스템 프롬프트를 반환한다. lang으로 답변 언어를 정한다.
    persona_id를 주면 그 한 명만 상세 블록으로 넣는다. 미지정 시 페르소나 블록을
    생략해 기존 호출부와 호환된다. lang이 알 수 없는 코드면 한국어로 폴백한다."""
    spec = LANGUAGES.get(lang, LANGUAGES["ko"])
    return _BASE.format(lang_instruct=spec["instruct"], persona_block=_persona_block(persona_id))
