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


def remit_optimizer(persona_id: str) -> dict:
    """송금 수수료와 경로를 비교해 최저비용 경로를 안내한다.
    커버 자산종: 송금."""
    p = get_persona(persona_id)
    monthly = p["monthly_remit_krw"]
    routes = sorted(data.REMIT_ROUTES, key=lambda r: r["fee_rate"])
    best = routes[0]
    default = next(r for r in data.REMIT_ROUTES if r["name"] == "은행 한도제한계좌")
    saving = int((default["fee_rate"] - best["fee_rate"]) * monthly)
    numbers = {
        "monthly_remit_krw": monthly,
        "default_fee_rate": default["fee_rate"],
        "best_route": "WireBarley" if best["name"] == "WireBarley" else best["name"],
        "best_fee_rate": best["fee_rate"],
        "monthly_saving_krw": saving,
        "annual_saving_krw": saving * 12,
    }
    if monthly == 0:
        return {
            "summary": f"{p['name']}님은 정기 송금 내역이 없어 경로 비교가 필요하지 않습니다.",
            "detail": "송금 발생 시 최저비용 경로를 다시 안내합니다.",
            "numbers": numbers,
            "card": None,
        }
    return {
        "summary": f"송금 경로를 {best['name']}로 바꾸면 매달 {_won(saving)}을 아낍니다.",
        "detail": (
            f"현재 은행 한도제한계좌 경로는 수수료율 {default['fee_rate']*100:.2f}%입니다. "
            f"{best['name']} 경로는 {best['fee_rate']*100:.1f}%입니다. "
            f"월 송금 {_won(monthly)} 기준 매달 {_won(saving)}, 연간 약 {_won(saving*12)}을 절감합니다."
        ),
        "numbers": numbers,
        "card": {
            "icon": "💸",
            "head": "송금 비용 절반으로 줄일 수 있습니다",
            "body": f"현재 경로({default['fee_rate']*100:.2f}%) 대신 {best['name']}({best['fee_rate']*100:.1f}%)를 쓰면 매달 {_won(saving)} 아낍니다. 연간 약 {_won(saving*12)} 절감.",
            "metric": f"경로 {len(data.REMIT_ROUTES)}개 비교 완료",
        },
    }


def credit_builder(persona_id: str, months_accrued: int = 0) -> dict:
    """월세와 통신비와 공과금을 대안신용 데이터로 축적한다. 축적 개월 기준 프로필 형성도를 추정한다.
    커버 자산종: 신용."""
    p = get_persona(persona_id)
    started = months_accrued >= data.CREDIT_PROFILE_MIN_MONTHS
    complete = months_accrued >= data.CREDIT_PROFILE_FULL_MONTHS
    numbers = {
        "months_accrued": months_accrued,
        "min_months": data.CREDIT_PROFILE_MIN_MONTHS,
        "full_months": data.CREDIT_PROFILE_FULL_MONTHS,
        "profile_started": started,
        "profile_complete": complete,
    }
    if complete:
        head = f"{months_accrued}개월 납부 이력으로 신용 프로필 완성"
        body = "JB 외국인 전용 대출과 카드 심사에 바로 활용 가능합니다. 취업 후 신용대출도 준비됩니다."
        metric = f"대안신용 데이터 {months_accrued}개월치"
    elif started:
        head = "대안신용 등급 형성 시작"
        body = f"{months_accrued}개월 납부 이력 축적. {data.CREDIT_PROFILE_FULL_MONTHS}개월 도달 시 프로필 완성됩니다."
        metric = f"신용데이터 {months_accrued}개월치"
    else:
        head = "오늘부터 신용 쌓기 시작"
        body = f"월세와 통신비 납부 이력을 신용데이터로 연동했습니다. {data.CREDIT_PROFILE_MIN_MONTHS}개월 후 JB 대출 심사에서 활용됩니다."
        metric = "신용데이터 연동 완료"
    return {
        "summary": f"{p['name']}님의 월세와 통신비 납부 이력을 대안신용으로 축적합니다.",
        "detail": (
            f"{p['name']}님은 소득이 적어 신용이력이 거의 없는 Thin Filer입니다. "
            f"월세와 통신비와 공과금을 KCB 마이데이터로 연동해 대안신용 데이터로 축적합니다. "
            f"현재 {months_accrued}개월 축적. {data.CREDIT_PROFILE_MIN_MONTHS}개월 이상이면 JB 외국인 전용 신용평가에 활용할 수 있습니다."
        ),
        "numbers": numbers,
        "card": {"icon": "📈", "head": head, "body": body, "metric": metric},
    }
