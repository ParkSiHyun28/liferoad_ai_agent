"""서류행정 tool의 Claude tool use용 JSON 스키마. server.py와 app.py가 공유한다.
Anthropic SDK tool 형식(name, description, input_schema)을 따른다."""

_PERSONA_PROP = {
    "persona_id": {
        "type": "string",
        "enum": ["minh", "suman"],
        "description": "페르소나 식별자. minh=응웬 반 민(베트남 E-9), suman=수만 라이(네팔 D-2).",
    }
}

TOOL_SCHEMAS = {
    "perception_parse": {
        "name": "perception_parse",
        "description": "OCR로 서류를 파싱하고 실명 불일치를 검출한다. 외국인등록증, 여권, 임대차계약서, 통장사본을 지원한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_PERSONA_PROP,
                "doc_type": {
                    "type": "string",
                    "enum": ["alien_registration", "lease_contract", "passport", "bank_statement"],
                    "description": "파싱할 서류 유형. 기본값 alien_registration(외국인등록증).",
                },
            },
            "required": ["persona_id"],
        },
    },
    "compliance_reason": {
        "name": "compliance_reason",
        "description": "준법 추론과 전세사기와 비자 가드레일 심사를 한다. 전세사기 위험 지표와 비자별 취업 허용 시간을 검토한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_PERSONA_PROP,
                "check_type": {
                    "type": "string",
                    "enum": ["jeonse_fraud", "visa_work_eligibility"],
                    "description": "심사 유형. jeonse_fraud=전세사기 위험 지표, visa_work_eligibility=비자별 취업 허용.",
                },
            },
            "required": ["persona_id"],
        },
    },
    "form_autofill": {
        "name": "form_autofill",
        "description": "정부 PDF 신청서를 원클릭 자동작성한다. 국민연금 반환일시금, 출국만기보험, 외국인등록증 갱신, 세금 정산 신청서를 지원한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                **_PERSONA_PROP,
                "form_id": {
                    "type": "string",
                    "enum": [
                        "pension_return_claim",
                        "departure_insurance_claim",
                        "alien_registration_renewal",
                        "foreign_worker_tax",
                    ],
                    "description": "자동작성할 신청서 양식 ID. 기본값 alien_registration_renewal.",
                },
            },
            "required": ["persona_id"],
        },
    },
}
