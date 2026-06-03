from mcp_servers.asset import tools
from mcp_servers.asset import data


def test_collateral_calc_suman_returns_95_percent_limit():
    result = tools.collateral_calc(persona_id="suman")
    # 수만 잔고 2,000만 원의 95% = 1,900만 원
    assert result["numbers"]["loan_limit_krw"] == 19_000_000
    assert result["numbers"]["deposit_krw"] == 20_000_000
    assert "summary" in result
    assert "detail" in result
    assert result["card"] is not None
    assert set(result["card"].keys()) == {"icon", "head", "body", "metric"}


def test_collateral_calc_minh_has_no_deposit():
    result = tools.collateral_calc(persona_id="minh")
    # 민은 잔고 0 → 한도 0, card는 None (담보 없음)
    assert result["numbers"]["loan_limit_krw"] == 0
    assert result["card"] is None
