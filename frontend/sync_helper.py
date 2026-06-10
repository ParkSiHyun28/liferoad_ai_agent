"""앱(Streamlit) → 데모 셸(바깥 페르소나 카드) 실시간 동기화 헬퍼.

폰 안 iframe(streamlit.app)은 바깥 페이지와 다른 도메인이라 바깥에서 앱 내부를
읽을 수 없다(브라우저 보안). 그래서 앱이 현재 페르소나를 바깥으로 쏴주는 방식으로
동기화한다. 페르소나가 바뀔 때마다 sync_persona를 호출하면 된다.
"""

from __future__ import annotations

import json
import streamlit as st
import streamlit.components.v1 as components

from shared.personas import visa_expiry_info


def is_embedded() -> bool:
    """데모 셸의 폰 안에서 열렸는지 여부 (?embed=true 쿼리파라미터 확인)."""
    return st.query_params.get("embed") == "true"


def sync_persona(p: dict) -> None:
    """현재 페르소나 정보를 데모 셸(최상위 창)로 postMessage 전송.

    페르소나 dict(shared.personas의 형식)를 받아 셸이 기대하는 키로 변환한 뒤
    비자 만료/갱신 정보까지 함께 보낸다.

    셸의 postMessage 수신 핸들러가 기대하는 키:
      code, name, en, nationality, visa, entry, exit, exitNote, note
      visaExpiry, visaRenewal (추가 필드)
    """
    # personas.py 키 → 셸 카드 키 매핑
    payload: dict = {
        "code": p.get("flag", ""),
        "name": p.get("name", ""),
        "en": p.get("name_en", ""),
        "nationality": p.get("country", ""),
        "visa": p.get("visa", ""),
        "entry": p.get("entry_date", ""),
        "exit": p.get("exit_plan", ""),
        "exitNote": "",
        "note": p.get("summary", ""),
    }

    # 비자 만료/갱신 정보를 추가한다.
    try:
        vinfo = visa_expiry_info(p)
        payload["visaExpiry"] = vinfo.get("expiry", "")
        payload["visaRenewal"] = vinfo.get("renewal_start", "")
        payload["visaMonthsLeft"] = vinfo.get("months_left", 0)
        payload["visaStatus"] = vinfo.get("status", "")
    except Exception:
        payload["visaExpiry"] = ""
        payload["visaRenewal"] = ""
        payload["visaMonthsLeft"] = 0
        payload["visaStatus"] = ""

    serialized = json.dumps(payload, ensure_ascii=False)
    components.html(
        f"""
        <script>
          const persona = {serialized};
          const msg = {{ type: "liferoad:persona", persona: persona }};
          // 컴포넌트 iframe → 앱 iframe → 데모 셸(top) 모두 시도
          try {{ window.top.postMessage(msg, "*"); }} catch (e) {{}}
          try {{ window.parent.postMessage(msg, "*"); }} catch (e) {{}}
        </script>
        """,
        height=0,
    )
