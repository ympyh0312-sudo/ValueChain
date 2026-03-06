"""
app/core/logging.py
─────────────────────────────────────────────────────────
structlog 기반 구조화 로깅 설정.

설계 원칙:
- 개발 환경: 컬러 + 사람이 읽기 좋은 포맷
- 프로덕션 환경: JSON 포맷 (ELK / Datadog 등 수집 도구 연동용)
- 표준 logging 모듈과 브릿지 연결 → 서드파티 라이브러리 로그도 통합
"""

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings


def setup_logging() -> None:
    """
    앱 시작 시 1회 호출.
    structlog 프로세서 체인을 구성하고 표준 logging과 연결한다.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.app_log_level.upper(), logging.INFO)

    # 공통 프로세서 (개발/프로덕션 공통 적용)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,       # request-scoped context 자동 병합
        structlog.stdlib.add_log_level,                # level 필드 추가
        structlog.stdlib.add_logger_name,              # logger 이름 추가
        structlog.processors.TimeStamper(fmt="iso"),   # ISO 8601 타임스탬프
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,          # 예외 스택 트레이스 포함
    ]

    if settings.is_production:
        # 프로덕션: JSON 포맷 (로그 수집 도구 친화적)
        renderer = structlog.processors.JSONRenderer()
    else:
        # 개발: 컬러 + 들여쓰기 (터미널 가독성)
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 표준 logging 포맷터 설정 (서드파티 라이브러리 로그 통합)
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    모듈별 로거 획득.

    Usage:
        logger = get_logger(__name__)
        logger.info("risk_propagation_started", ticker="AAPL", hop=1)
    """
    return structlog.get_logger(name)
