"""두 페르소나 공용 데이터. 모든 부문이 이 모듈을 import 한다."""

PERSONAS = {
    "minh": {
        "id": "minh",
        "name": "응웬 반 민",
        "name_en": "Nguyen Van Minh",
        "flag": "VN",
        "country": "베트남",
        "visa": "E-9",
        "role": "근로자",
        "entry_date": "2022-03",
        "exit_plan": "2027-01",
        "monthly_wage_krw": 2_700_000,
        "monthly_remit_krw": 1_000_000,
        "pension_months": 58,
        "social_security_treaty": False,  # 베트남 미체결 → 반환일시금 수령 가능
        "deposit_balance_krw": 0,
        "summary": "베트남 E-9 근로자. 출국 1년 전. 반환일시금과 출국만기보험 수령 대상.",
    },
    "suman": {
        "id": "suman",
        "name": "수만 라이",
        "name_en": "Suman Rai",
        "flag": "NP",
        "country": "네팔",
        "visa": "D-2",
        "role": "유학생",
        "entry_date": "2023-03",
        "exit_plan": "2027-02",
        "monthly_wage_krw": 0,
        "monthly_remit_krw": 0,
        "pension_months": 0,
        "social_security_treaty": False,  # 네팔 미체결 → 귀국 시 반환일시금 불가
        "deposit_balance_krw": 20_000_000,  # 잔고증명 요건
        "summary": "네팔 D-2 유학생. Thin Filer. 잔고증명 예치금 보유. 대안신용 축적 대상.",
    },
}


def get_persona(persona_id: str) -> dict:
    """페르소나 식별자로 데이터를 반환한다. 없으면 ValueError."""
    if persona_id not in PERSONAS:
        raise ValueError(f"unknown persona_id: {persona_id}")
    return PERSONAS[persona_id]
