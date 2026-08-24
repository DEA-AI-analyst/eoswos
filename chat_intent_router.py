"""Deterministic scope and intent routing for the EOSWOS AI panel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ChatRoute(str, Enum):
    TYPE_A_GENERAL = "TYPE_A_GENERAL"
    TYPE_B_EVALUATION = "TYPE_B_EVALUATION"
    TYPE_C_EVALUATION_EXPLANATION = "TYPE_C_EVALUATION_EXPLANATION"
    TYPE_D_BLOCKED = "TYPE_D_BLOCKED"


@dataclass(frozen=True)
class RouteDecision:
    route: ChatRoute

    @property
    def opens_evaluation_form(self) -> bool:
        return self.route is ChatRoute.TYPE_B_EVALUATION

    @property
    def calls_chatbase(self) -> bool:
        return self.route in {
            ChatRoute.TYPE_A_GENERAL,
            ChatRoute.TYPE_C_EVALUATION_EXPLANATION,
        }


BLOCKED_SCOPE_RESPONSE = (
    "본 AI는 메자닌 평가, 평가결과 설명 및 모델 사용법 지원 범위에서만 답변합니다."
)

EVALUATION_FORM_RESPONSE = (
    "메자닌 평가는 정형 입력창에서 진행합니다. 아래 입력창에 평가조건을 직접 입력해 주세요."
)

_BLOCKED_TERMS = (
    "api key",
    "api키",
    "api 키",
    "credential",
    "credentials",
    "secret",
    "비밀키",
    "인증정보",
    "시스템 프롬프트",
    "system prompt",
    "소스코드",
    "source code",
    "학습데이터",
    "학습 데이터",
    "모델 파라미터",
    "operating_reference",
    "운영 레퍼런스",
    "모델 우회",
    "모델 취약점",
)

_EVALUATION_ACTION_PATTERNS = (
    r"(?:메자닌|cb|bw|eb|m\s*grade|m등급|등급|회사|종목).{0,30}(?:평가|조회|산출|계산)\s*(?:해|해줘|해주세요|하자|시작|실행|진행|보고\s*싶)",
    r"(?:평가|조회|산출|계산)\s*(?:해|해줘|해주세요|하자|시작|실행|진행)",
    r"(?:신규\s*)?메자닌\s*평가",
    r"(?:m\s*grade|m등급)\s*(?:보고\s*싶|조회|평가|산출)",
    r"(?:전환사채|신주인수권부사채|교환사채|cb|bw|eb).{0,30}(?:평가|조회|산출)\s*(?:요청)?\s*$",
)

_RESULT_EXPLANATION_TERMS = (
    "왜",
    "이 결과",
    "평가 결과",
    "해석",
    "설명",
    "원인",
    "이유",
    "우선순위",
    "e_m",
    "p_m",
    "s_m",
    "final score",
    "m grade",
    "\ud3c9\uac00\ubcf4\uace0\uc11c",
    "\ud3c9\uac00 \ubcf4\uace0\uc11c",
    "\ubcf4\uace0\uc11c",
    "\uc9c4\ub2e8",
    "\ubd84\uc11d",
    "\uc694\uc57d",
    "\uac80\ud1a0 \ud3ec\uc778\ud2b8",
    "\uccb4\ud06c\ud3ec\uc778\ud2b8",
    "\uac80\ud1a0\uc758\uacac",
    "\uac80\ud1a0\ubcf4\uace0\uc11c",
    "\ud3c9\uac00\uc758\uacac",
    "\ud3c9\uac00\ubcf4\uace0\uc11c",
    "\uc2ec\uc0ac\uc758\uacac",
    "\uc2ec\uc0ac\ubcf4\uace0\uc11c",
    "\uac80\ud1a0 \uc758\uacac",
    "\uac80\ud1a0 \ubcf4\uace0\uc11c",
    "\ud3c9\uac00 \uc758\uacac",
    "\ud3c9\uac00 \ubcf4\uace0\uc11c",
    "\uc2ec\uc0ac \uc758\uacac",
    "\uc2ec\uc0ac \ubcf4\uace0\uc11c",
)


def route_chat_message(
    text: str,
    *,
    has_current_evaluation: bool = False,
) -> RouteDecision:
    """Classify intent only; never extract or infer evaluation field values."""

    normalized = " ".join(str(text or "").strip().split())
    lowered = normalized.lower()

    if any(term in lowered for term in _BLOCKED_TERMS):
        return RouteDecision(ChatRoute.TYPE_D_BLOCKED)

    if has_current_evaluation and any(
        term in lowered for term in _RESULT_EXPLANATION_TERMS
    ):
        return RouteDecision(ChatRoute.TYPE_C_EVALUATION_EXPLANATION)

    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _EVALUATION_ACTION_PATTERNS):
        return RouteDecision(ChatRoute.TYPE_B_EVALUATION)

    return RouteDecision(ChatRoute.TYPE_A_GENERAL)
