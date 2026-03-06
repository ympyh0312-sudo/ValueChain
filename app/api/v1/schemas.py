"""
app/api/v1/schemas.py
---------------------------------------------------------
API 요청/응답 Pydantic 스키마.

graph_models.py (Neo4j 도메인 모델) 와 분리하여
API 경계에서만 사용하는 스키마를 정의한다.

분리 이유:
- API 버전 독립: v1 스키마가 바뀌어도 도메인 모델 불변
- 입력 검증 강화: min_length, ge/le 등 API 전용 제약
- Swagger 문서 최적화: description, examples 포함
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────
# Ingest 스키마
# ─────────────────────────────────────────────────────

class IngestArticleRequest(BaseModel):
    """뉴스 기사 수집 요청."""
    title:        str            = Field(..., min_length=1, max_length=1024, description="기사 제목")
    content:      str            = Field(..., min_length=10,                 description="기사 본문 전체")
    source_url:   Optional[str] = Field(None,                               description="원문 URL")
    source_name:  Optional[str] = Field(None, max_length=255,              description="출처 (Reuters, Bloomberg 등)")
    published_at: Optional[datetime] = Field(None,                         description="발행 시각 (없으면 현재 시각)")
    language:     str            = Field(default="en", max_length=10,       description="언어 코드")
    auto_process: bool           = Field(
        default=False,
        description="True이면 저장 즉시 LLM 추출 파이프라인 실행"
    )

    model_config = {"json_schema_extra": {"example": {
        "title": "TSMC reports record chip orders from Apple",
        "content": "Taiwan Semiconductor Manufacturing Company announced...",
        "source_name": "Reuters",
        "auto_process": True,
    }}}


class IngestArticleResponse(BaseModel):
    """뉴스 기사 수집 응답."""
    article_id: int
    status:     str
    message:    str = ""


class ProcessArticleResponse(BaseModel):
    """기사 LLM 처리 결과."""
    article_id:         int
    status:             str
    relations_found:    int
    relations_applied:  int
    relations_rejected: int
    details:            list[dict] = []
    error:              Optional[str] = None


# ─────────────────────────────────────────────────────
# Risk 스키마
# ─────────────────────────────────────────────────────

class RiskAnalysisRequest(BaseModel):
    """리스크 전파 시뮬레이션 요청."""
    ticker:          str   = Field(..., description="충격 발생 기업 티커 (예: TSMC)")
    shock_intensity: float = Field(default=1.0, ge=0.0, le=1.0,    description="초기 충격 강도 (0=없음, 1=최대)")
    decay_lambda:    float = Field(default=0.1, gt=0.0,            description="시간 감쇠 계수 (클수록 빨리 소멸)")
    max_hop:         int   = Field(default=5,   ge=1, le=10,       description="최대 전파 홉 수")
    time_horizon:    int   = Field(default=30,  ge=1, le=365,      description="리스크 타임라인 분석 기간 (일)")
    cutoff:          float = Field(default=0.01, gt=0.0, lt=1.0,  description="전파 중단 임계값")
    save_result:     bool  = Field(default=False,                  description="결과를 PostgreSQL에 저장")
    label:           str   = Field(default="",                     description="저장 시 사용할 시나리오 레이블")

    model_config = {"json_schema_extra": {"example": {
        "ticker": "TSMC",
        "shock_intensity": 1.0,
        "decay_lambda": 0.1,
        "max_hop": 5,
        "time_horizon": 30,
        "save_result": True,
        "label": "TSMC_full_shock_2024Q1",
    }}}


class RiskNodeResponse(BaseModel):
    """리스크 전파 결과 노드."""
    ticker:          str
    name:            str
    sector:          str
    country:         str
    risk_score:      float
    hop_distance:    int
    risk_timeline:   dict[int, float]
    is_origin:       bool


class RiskEdgeResponse(BaseModel):
    """리스크 전파 결과 엣지."""
    source_ticker:     str
    target_ticker:     str
    transmitted_risk:  float
    dependency_score:  float
    sector_sensitivity: float


class RiskAnalysisResponse(BaseModel):
    """리스크 전파 시뮬레이션 응답."""
    origin_ticker:    str
    params:           dict
    affected_count:   int
    max_risk_ticker:  Optional[str]
    max_risk_score:   float
    nodes:            list[dict]   # RiskNodeResponse 직렬화
    edges:            list[dict]   # RiskEdgeResponse 직렬화
    simulation_id:    Optional[int] = None


class ShockOrigin(BaseModel):
    """다중 충격 시나리오의 단일 충격원."""
    ticker:          str
    shock_intensity: float = Field(default=1.0, ge=0.0, le=1.0)


class MultiShockRequest(BaseModel):
    """다중 충격원 동시 시뮬레이션 요청."""
    origins:      list[ShockOrigin] = Field(..., min_length=1, description="충격 발생 기업 목록")
    decay_lambda: Optional[float]   = Field(None, gt=0.0)
    max_hop:      Optional[int]     = Field(None, ge=1, le=10)
    time_horizon: Optional[int]     = Field(None, ge=1, le=365)

    model_config = {"json_schema_extra": {"example": {
        "origins": [
            {"ticker": "TSMC", "shock_intensity": 1.0},
            {"ticker": "SAMSUNG", "shock_intensity": 0.7},
        ],
        "max_hop": 4,
    }}}


class SensitivitySweepRequest(BaseModel):
    """파라미터 민감도 스윕 요청."""
    ticker:          str        = Field(..., description="분석 대상 기업 티커")
    sweep_type:      str        = Field(
        ...,
        description="스윕 파라미터 종류: 'shock_intensity' 또는 'decay_lambda'"
    )
    values:          list[float] = Field(..., min_length=1, description="스윕 값 목록")
    decay_lambda:    Optional[float] = Field(None, gt=0.0)
    shock_intensity: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_hop:         Optional[int]   = Field(None, ge=1, le=10)
    time_horizon:    Optional[int]   = Field(None, ge=1, le=365)

    model_config = {"json_schema_extra": {"example": {
        "ticker": "TSMC",
        "sweep_type": "shock_intensity",
        "values": [0.2, 0.4, 0.6, 0.8, 1.0],
    }}}


class SweepPointResponse(BaseModel):
    """민감도 스윕 단일 데이터 포인트."""
    param_name:     str
    param_value:    float
    affected_count: int
    max_risk_score: float
    total_risk:     float


# ─────────────────────────────────────────────────────
# Network 스키마
# ─────────────────────────────────────────────────────

class SystemicRiskRequest(BaseModel):
    """시스템 리스크 중요도 계산 요청."""
    tickers:         list[str] = Field(..., min_length=1, description="평가할 기업 티커 목록")
    shock_intensity: float     = Field(default=1.0, ge=0.0, le=1.0)
    max_hop:         int       = Field(default=5,   ge=1, le=10)

    model_config = {"json_schema_extra": {"example": {
        "tickers": ["TSMC", "AAPL", "SAMSUNG", "ASML", "NVDA"],
        "shock_intensity": 1.0,
        "max_hop": 5,
    }}}
