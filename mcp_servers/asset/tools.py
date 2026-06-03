"""자산 부문 tool 5개. 순수 함수다. MCP나 Claude를 모른다.
입력은 키워드 인자, 출력은 {summary, detail, numbers, card} dict."""

from datetime import date

from shared.personas import get_persona
from mcp_servers.asset import data


def _won(n: int) -> str:
    """원화 정수를 만 원 단위 한국어 문자열로."""
    return f"{n:,}원"


def collateral_calc(persona_id: str) -> dict:
    """잔고증명 예치금 기준 예금담보대출 한도(95%)를 산출한다.
    커버 자산종: 예금, 대출."""
    p = get_persona(persona_id)
    deposit = p["deposit_balance_krw"]
    limit = int(deposit * data.COLLATERAL_LOAN_RATIO)
    numbers = {
        "deposit_krw": deposit,
        "loan_ratio": data.COLLATERAL_LOAN_RATIO,
        "loan_limit_krw": limit,
    }
    if deposit == 0:
        return {
            "summary": f"{p['name']}님은 잔고증명 예치금이 없어 예금담보대출 대상이 아닙니다.",
            "detail": "예금담보대출은 잔고증명 예치금을 담보로 합니다. 현재 예치금이 없습니다.",
            "numbers": numbers,
            "card": None,
        }
    return {
        "summary": f"잔고 {_won(deposit)}을 유지하면서 예금담보대출로 {_won(limit)}까지 활용할 수 있습니다.",
        "detail": (
            f"D-2 비자는 잔고증명 예치금 {_won(deposit)} 유지가 요건입니다. "
            f"직접 인출하면 비자 요건을 위반합니다. 대신 예금담보대출(한도 {int(data.COLLATERAL_LOAN_RATIO*100)}%)로 "
            f"{_won(limit)}까지 생활비를 마련하면 잔고 요건 위반 없이 안전합니다."
        ),
        "numbers": numbers,
        "card": {
            "icon": "🔐",
            "head": f"잔고 {_won(deposit)} 유지하며 {_won(limit)} 활용 가능",
            "body": f"예금담보대출(한도 {int(data.COLLATERAL_LOAN_RATIO*100)}%)로 생활비 마련 가능. 잔고 요건 위반 없이 안전하게 쓸 수 있습니다.",
            "metric": f"담보대출 한도 {_won(limit)}",
        },
    }


def pension_estimator(persona_id: str) -> dict:
    """국민연금 반환일시금 예상액을 산출한다. 사회보장협정 체결 여부를 반영한다.
    커버 자산종: 연금."""
    p = get_persona(persona_id)
    months = p["pension_months"]
    treaty = p["social_security_treaty"]
    # 협정 미체결(treaty False)이면 반환일시금 수령 대상. 단 납부월수 0이면 받을 게 없다.
    can_receive = (not treaty) and months > 0
    refund = months * data.PENSION_MONTHLY_REFUND_KRW
    numbers = {
        "pension_months": months,
        "treaty": treaty,
        "can_receive": can_receive,
        "estimated_refund_krw": refund,
    }
    if can_receive:
        return {
            "summary": f"{p['name']}님은 귀국 시 국민연금 반환일시금 약 {_won(refund)}을 받을 수 있습니다.",
            "detail": (
                f"{p['country']}은 한국과 사회보장협정이 미체결이라 {p['visa']} 근로자는 귀국 시 반환일시금 수령 대상입니다. "
                f"납부 {months}개월 기준 예상 수령액은 약 {_won(refund)}입니다. "
                f"2023년 외국인 반환일시금 총 지급액은 3,294억 원 규모입니다."
            ),
            "numbers": numbers,
            "card": {
                "icon": "🏛️",
                "head": f"귀국 시 반환일시금 약 {_won(refund)} 수령 가능",
                "body": f"납부 {months}개월치. 출국 후 청구하면 받습니다. 신청서 작성을 도와드립니다.",
                "metric": f"예상 수령 {_won(refund)}",
            },
        }
    # 수령 불가 (협정 미체결이지만 유학생이라 납부 이력 없음, 또는 협정 체결국)
    return {
        "summary": f"{p['name']}님은 귀국 시 국민연금 반환일시금을 받기 어렵습니다.",
        "detail": (
            f"{p['country']}은 한국과 사회보장협정이 미체결입니다. "
            f"현재 납부 이력({months}개월)으로는 귀국 시 반환일시금 수령이 어렵습니다. "
            f"단 취업비자(E-7)로 전환해 한국에 남으면 납부 이력이 수령으로 이어질 수 있습니다. "
            f"유학생 취업전환율은 {int(data.STUDENT_VISA_CONVERT_RATE*100)}.4%입니다. 이 사실을 숨기지 않고 안내합니다."
        ),
        "numbers": numbers,
        "card": {
            "icon": "⚖️",
            "head": "귀국하면 연금 돌려받기 어렵습니다",
            "body": f"{p['country']}-한국 협정 미체결. 단 E-7 취업전환 시 납부 이력이 수령으로 이어집니다. 취업비자 전환 도움 필요하면 알려주세요.",
            "metric": f"취업전환 가능성 {int(data.STUDENT_VISA_CONVERT_RATE*100)}.4%",
        },
    }
