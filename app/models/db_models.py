"""
app/models/db_models.py
---------------------------------------------------------
PostgreSQL SQLAlchemy ORM 모델.

테이블 구조:
- news_articles    : 뉴스 원문 저장 (LLM 입력 소스)
- extraction_results: LLM 추출 결과 + confidence (버전 관리)
- relationship_versions: SUPPLY_TO 관계 변경 이력

설계 포인트:
- TimestampMixin: 모든 테이블에 created_at / updated_at 자동 관리
- JSON 컬럼: 추출 결과는 구조가 유동적이므로 JSON으로 저장
- status Enum: 처리 상태를 명확하게 추적
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum,
    Float, ForeignKey, Index, Integer, String, Text, JSON
)
from sqlalchemy.sql import func

from app.db.postgres_client import Base


# ─────────────────────────────────────────────────────
# 공통 Timestamp Mixin
# 모든 테이블이 생성/수정 시각을 자동으로 기록
# ─────────────────────────────────────────────────────
class TimestampMixin:
    """
    created_at: 레코드 최초 삽입 시각 (변경 불가)
    updated_at: 마지막 수정 시각 (UPDATE 시 자동 갱신)
    """
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ─────────────────────────────────────────────────────
# Enum 정의
# ─────────────────────────────────────────────────────
class ArticleStatus(str, enum.Enum):
    """뉴스 처리 상태."""
    PENDING    = "pending"      # 수집됨, 아직 LLM 처리 안 됨
    PROCESSING = "processing"   # LLM 처리 중
    COMPLETED  = "completed"    # 추출 완료
    FAILED     = "failed"       # 추출 실패
    REJECTED   = "rejected"     # 신뢰도 기준 미달로 거부


class RelationEventType(str, enum.Enum):
    """관계 변경 이벤트 유형."""
    CREATED  = "created"    # 신규 관계 생성
    UPDATED  = "updated"    # 관계 속성 업데이트
    DELETED  = "deleted"    # 관계 삭제 (공급 중단 등)
    VERIFIED = "verified"   # 기존 관계 재확인


# ─────────────────────────────────────────────────────
# news_articles 테이블
# ─────────────────────────────────────────────────────
class NewsArticle(TimestampMixin, Base):
    """
    뉴스 원문 저장 테이블.
    LLM 추출 파이프라인의 입력 소스.
    """
    __tablename__ = "news_articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 뉴스 출처 정보
    source_url  = Column(String(2048), nullable=True)
    source_name = Column(String(255),  nullable=True)    # 예: "Reuters", "Bloomberg"

    # 뉴스 본문
    title   = Column(String(1024), nullable=False)
    content = Column(Text,         nullable=False)       # 원문 전체

    # 발행 정보
    published_at = Column(DateTime(timezone=True), nullable=True)
    language     = Column(String(10), default="en")

    # 처리 상태
    status = Column(
        Enum(ArticleStatus, name="article_status_enum"),
        default=ArticleStatus.PENDING,
        nullable=False,
    )

    # 관련 티커 (LLM 처리 전 간단 필터링용, 선택적)
    mentioned_tickers = Column(JSON, default=list)  # ["AAPL", "TSMC"]

    __table_args__ = (
        Index("ix_news_status",       "status"),
        Index("ix_news_published_at", "published_at"),
        Index("ix_news_source_name",  "source_name"),
    )

    def __repr__(self) -> str:
        return f"<NewsArticle id={self.id} title={self.title[:40]!r}>"


# ─────────────────────────────────────────────────────
# extraction_results 테이블
# ─────────────────────────────────────────────────────
class ExtractionResult(TimestampMixin, Base):
    """
    LLM이 뉴스에서 추출한 공급망 관계 데이터.
    같은 뉴스에서 여러 관계가 추출될 수 있음 (1:N).

    extracted_data JSON 구조:
    {
        "supplier": "TSMC",
        "buyer": "AAPL",
        "relation_type": "SUPPLY_TO",
        "revenue_share_estimate": 0.25,
        "event_type": "supply_disruption",
        "event_severity": 0.8
    }
    """
    __tablename__ = "extraction_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 원본 뉴스 참조 (FK 제약으로 참조 무결성 보장)
    article_id = Column(BigInteger, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)

    # LLM 추출 원시 결과 (JSON)
    extracted_data  = Column(JSON, nullable=False)
    raw_llm_output  = Column(Text, nullable=True)    # 디버깅용 LLM 원본 응답

    # 신뢰도 및 검증
    # confidence_score < LLM_CONFIDENCE_THRESHOLD → 그래프 반영 거부
    confidence_score = Column(Float, nullable=False)
    is_applied       = Column(Boolean, default=False)  # 그래프에 반영됐는지 여부

    # 정규화된 티커 (fuzzy matching 후)
    supplier_ticker = Column(String(50), nullable=True)
    buyer_ticker    = Column(String(50), nullable=True)

    # LLM 모델 정보 (재현성 추적)
    llm_model   = Column(String(100), nullable=True)   # 예: "gpt-4o-mini"
    llm_version = Column(String(50),  nullable=True)

    # 거부 사유 (confidence 미달 등)
    rejection_reason = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_extraction_article",    "article_id"),
        Index("ix_extraction_confidence", "confidence_score"),
        Index("ix_extraction_applied",    "is_applied"),
        Index("ix_extraction_supplier",   "supplier_ticker"),
        Index("ix_extraction_buyer",      "buyer_ticker"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExtractionResult id={self.id} "
            f"{self.supplier_ticker}->{self.buyer_ticker} "
            f"conf={self.confidence_score:.2f}>"
        )


# ─────────────────────────────────────────────────────
# relationship_versions 테이블
# ─────────────────────────────────────────────────────
class RelationshipVersion(TimestampMixin, Base):
    """
    SUPPLY_TO 관계의 변경 이력 테이블.

    Neo4j 그래프에는 항상 '최신 상태'만 유지.
    이 테이블은 시간에 따른 관계 변화를 추적함.

    활용 예:
    - "AAPL-TSMC 의존도가 6개월 전 0.8 → 현재 0.6으로 감소"
    - "AAPL이 새로운 공급사를 추가한 시점 파악"
    """
    __tablename__ = "relationship_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 관계 식별
    supplier_ticker = Column(String(50), nullable=False)
    buyer_ticker    = Column(String(50), nullable=False)

    # 변경 이벤트
    event_type = Column(
        Enum(RelationEventType, name="relation_event_type_enum"),
        nullable=False,
    )

    # 변경 전/후 스냅샷 (JSON)
    previous_state = Column(JSON, nullable=True)   # 변경 전 속성
    new_state      = Column(JSON, nullable=False)  # 변경 후 속성

    # 변경 근거
    source_article_id = Column(BigInteger, nullable=True)  # FK → news_articles.id
    confidence_score  = Column(Float, nullable=False)

    # 변경 시각 (created_at과 별도 관리 — 뉴스 발행 시각 기준)
    event_occurred_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_relver_supplier", "supplier_ticker"),
        Index("ix_relver_buyer",    "buyer_ticker"),
        Index("ix_relver_event",    "event_type"),
        Index("ix_relver_occurred", "event_occurred_at"),
        # 복합 인덱스: 특정 관계의 전체 이력 조회용
        Index("ix_relver_pair", "supplier_ticker", "buyer_ticker"),
    )

    def __repr__(self) -> str:
        return (
            f"<RelationshipVersion "
            f"{self.supplier_ticker}->{self.buyer_ticker} "
            f"event={self.event_type}>"
        )


# ─────────────────────────────────────────────────────
# simulation_runs 테이블   (Phase 4 추가)
# ─────────────────────────────────────────────────────
class SimulationRun(TimestampMixin, Base):
    """
    리스크 전파 시뮬레이션 실행 이력.

    PropagationResult를 PostgreSQL에 영속화하여:
    - 동일 시나리오 재실행 없이 결과 재사용
    - 파라미터별 결과 비교 분석
    - API 응답 캐싱 (DB 조회로 대체)

    result_snapshot: PropagationResult.to_dict() 전체를 JSON으로 저장
    """
    __tablename__ = "simulation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 시나리오 파라미터 (쿼리 필터링 및 재현성 추적용)
    origin_ticker    = Column(String(50),  nullable=False)
    shock_intensity  = Column(Float,       nullable=False)
    decay_lambda     = Column(Float,       nullable=False)
    max_hop          = Column(Integer,     nullable=False)
    time_horizon     = Column(Integer,     nullable=False)
    cutoff_threshold = Column(Float,       nullable=False)
    scenario_label   = Column(String(200), nullable=True)

    # 결과 요약 (목록 조회 시 result_snapshot 없이 빠르게 조회 가능)
    affected_count  = Column(Integer,     nullable=False, default=0)
    total_nodes     = Column(Integer,     nullable=False, default=0)
    total_edges     = Column(Integer,     nullable=False, default=0)
    max_risk_ticker = Column(String(50),  nullable=True)
    max_risk_score  = Column(Float,       nullable=True)

    # 전체 결과 스냅샷 (JSON) — API 재사용, 재계산 없이 즉시 반환 가능
    result_snapshot = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_simrun_origin",  "origin_ticker"),
        Index("ix_simrun_created", "created_at"),
        Index("ix_simrun_label",   "scenario_label"),
        # 같은 파라미터 조합 빠른 탐색
        Index("ix_simrun_params", "origin_ticker", "shock_intensity", "decay_lambda"),
    )

    def __repr__(self) -> str:
        return (
            f"<SimulationRun id={self.id} "
            f"origin={self.origin_ticker} "
            f"shock={self.shock_intensity} "
            f"affected={self.affected_count}>"
        )
