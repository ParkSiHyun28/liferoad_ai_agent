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
