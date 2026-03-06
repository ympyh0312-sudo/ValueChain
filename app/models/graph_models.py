"""
app/models/graph_models.py
---------------------------------------------------------
Neo4j 그래프 노드/관계에 대응하는 Pydantic 모델.

구조:
- Company: 기업 노드 (Create / Response 분리)
- SupplyRelation: SUPPLY_TO 관계 (Create / Response 분리)
- SectorSensitivity: 섹터별 리스크 민감도 매핑 테이블
- RiskNode / RiskEdge: 리스크 계산 결과 표현용

분리 원칙:
- XxxCreate  → API 입력 (검증 엄격, 기본값 없음)
- XxxResponse → API 출력 (계산 필드 포함, 직렬화 최적화)
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────
# 섹터별 리스크 민감도 (SectorSensitivity)
# 리스크 공식: Risk_dest = Risk_src × Dependency × SectorSensitivity × ...
#
# 값이 높을수록 같은 충격에 더 큰 리스크를 받음
# 예: Tech(0.9) 기업은 Materials(0.75) 기업보다 공급망 충격에 더 민감
# ─────────────────────────────────────────────────────
SECTOR_SENSITIVITY: dict[str, float] = {
    # ── 기술·반도체 ────────────────────────────────────────
    "Technology":                  0.90,  # 복잡한 글로벌 공급망, 단일 공급자 의존도 높음
    "Semiconductors":              0.90,  # 팹리스/파운드리 고의존 공급망
    "Semiconductor Equipment":     0.88,  # 장비 독점 리스크 (ASML 등)
    "Semiconductor Materials":     0.82,  # 소재 지리적 집중 리스크
    "Electronic Components":       0.80,  # 수동부품·디스플레이 공급망
    "Electronic Manufacturing":    0.78,  # EMS 조립 공급망
    "Enterprise Software":         0.88,  # 클라우드 의존·SaaS 잠금 효과
    "Networking":                  0.85,  # 네트워크 인프라 의존도
    # ── 에너지·전력 ────────────────────────────────────────
    "Energy":                      0.85,  # 지정학적 리스크, 원자재 가격 변동성
    "Oil & Gas":                   0.82,  # 원유·가스 공급망 집중
    "Oil & Gas Services":          0.78,  # 오일필드 서비스 사이클
    "Power Generation":            0.80,  # 전력 생산 인프라
    "Renewable Energy":            0.75,  # 재생에너지 설비 공급망
    "Electrical Equipment":        0.82,  # 전력설비·변압기 납기 리스크
    "Utilities":                   0.45,  # 지역 독점, 공급망 단순
    # ── 헬스케어 ───────────────────────────────────────────
    "Pharmaceuticals":             0.72,  # 규제·원료의약품(API) 의존
    "Biotechnology":               0.75,  # 바이오 공정 복잡성
    "Medical Devices":             0.72,  # 부품 조달·인허가 리스크
    "Health Services":             0.65,  # 의료서비스 운영 안정성
    "Healthcare":                  0.68,  # 규제 복잡성, 공급 다변화 어려움
    # ── 금융 ───────────────────────────────────────────────
    "Banking":                     0.55,  # 신용·유동성 채널
    "Financial Services":          0.55,  # 공급망보다 금융 채널 전파
    "Insurance":                   0.58,  # 재보험·리스크 이전
    "Financials":                  0.50,  # 공급망보다 신용/유동성 채널로 리스크 전파
    # ── 소비·산업 ──────────────────────────────────────────
    "Retail":                      0.65,  # 재고·물류 공급망
    "Consumer Goods":              0.62,  # 소비재 공급망
    "Chemicals":                   0.75,  # 화학 원료 공급 집중
    "Automotive":                  0.78,  # 자동차 부품 복잡 공급망
    "Automotive Components":       0.80,  # 배터리·전장부품 의존
    "Aerospace & Defense":         0.78,  # 장기 납기·규제 공급망
    "Industrial":                  0.75,  # 자본재 사이클, 납기 지연 민감
    "Industrials":                 0.75,
    "Materials":                   0.80,  # 원자재 직접 의존, 대체재 부족
    "Consumer Discretionary":      0.70,
    "Consumer Staples":            0.60,  # 필수재, 대체 공급망 확보 용이
    "Communication Services":      0.55,  # 인프라 기반, 물리적 공급망 의존도 낮음
    "Real Estate":                 0.40,  # 공급망 리스크 최소
    "Unknown":                     0.65,  # 섹터 미분류 기업 기본값
}


def get_sector_sensitivity(sector: str) -> float:
    """
    섹터명으로 민감도 반환.
    알 수 없는 섹터는 0.65(Unknown) 반환.
    대소문자 구분 없이 매칭 시도.
    """
    # 정확 매칭
    if sector in SECTOR_SENSITIVITY:
        return SECTOR_SENSITIVITY[sector]
    # 대소문자 무시 매칭
    sector_lower = sector.lower()
    for key, val in SECTOR_SENSITIVITY.items():
        if key.lower() == sector_lower:
            return val
    return SECTOR_SENSITIVITY["Unknown"]


# ─────────────────────────────────────────────────────
# Company Node
# ─────────────────────────────────────────────────────
class CompanyCreate(BaseModel):
    """기업 노드 생성 요청 스키마."""

    ticker: str = Field(
        ...,
        description="주식 티커 (전 세계 고유 식별자)",
        examples=["AAPL", "TSMC", "005930"]  # 005930 = 삼성전자
    )
    name: str = Field(..., description="기업 공식명")
    sector: str = Field(..., description="GICS 섹터 분류")
    country: str = Field(..., description="본사 소재 국가 코드 (ISO 3166-1 alpha-2)")

    # liquidity_score: 유동성 완충 능력
    # 공식에서 (1 - LiquidityBuffer)로 사용됨
    # 1.0이면 충격을 전혀 전파하지 않음 (이론적 최대)
    liquidity_score: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="유동성 완충 능력 (0=없음 ~ 1=완전 흡수)"
    )
    # supplier_concentration: 공급자 집중도
    # 1개 공급자에 100% 의존하면 1.0, 분산될수록 낮음
    supplier_concentration: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="공급자 집중도 (0=완전분산 ~ 1=단일공급자)"
    )

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """티커는 항상 대문자로 정규화."""
        return v.upper().strip()

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        """국가 코드는 항상 대문자."""
        return v.upper().strip()


class CompanyResponse(BaseModel):
    """기업 노드 조회 응답 스키마."""

    ticker: str
    name: str
    sector: str
    country: str
    liquidity_score: float
    supplier_concentration: float
    sector_sensitivity: float   # SECTOR_SENSITIVITY 테이블에서 자동 계산
    last_updated: Optional[datetime] = None


# ─────────────────────────────────────────────────────
# SUPPLY_TO Relationship
# ─────────────────────────────────────────────────────
class SupplyRelationCreate(BaseModel):
    """
    공급 관계(SUPPLY_TO) 생성 요청 스키마.
    방향: supplier_ticker → buyer_ticker
    (supplier가 buyer에게 부품/원자재를 공급)
    """

    supplier_ticker: str = Field(..., description="공급사 티커")
    buyer_ticker: str = Field(..., description="구매사 티커")

    # revenue_share: 공급사 매출 중 이 관계가 차지하는 비중
    # 0.3 = 공급사 매출의 30%가 이 구매사에 의존
    revenue_share: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="공급사 매출 내 이 관계 비중 (0~1)"
    )
    # dependency_score: 구매사 입장에서 이 공급사 의존도
    # 리스크 공식의 핵심 변수: Risk × dependency_score
    dependency_score: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="구매사의 해당 공급사 의존도 (0~1)"
    )
    # geographic_exposure: 지리적 집중 리스크
    # 같은 국가/지역에 공급망이 몰려 있으면 높음
    geographic_exposure: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="지리적 집중 리스크 (0=분산 ~ 1=단일지역)"
    )
    # alternative_supplier_score: 대체 공급자 확보 용이성
    # 1.0이면 즉시 대체 가능 → 실질 리스크 낮음
    alternative_supplier_score: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="대체 공급자 확보 용이성 (0=불가 ~ 1=즉시가능)"
    )
    # confidence_score: LLM 추출 결과의 신뢰도
    # 낮으면 데이터 품질 경고
    confidence_score: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="데이터 신뢰도 (LLM 추출 품질)"
    )

    @field_validator("supplier_ticker", "buyer_ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.upper().strip()


class SupplyRelationResponse(BaseModel):
    """공급 관계 조회 응답 스키마."""

    supplier_ticker: str
    buyer_ticker: str
    revenue_share: float
    dependency_score: float
    geographic_exposure: float
    alternative_supplier_score: float
    confidence_score: float
    last_verified_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────
# Risk 계산 결과 표현용
# Phase 3 (Risk Engine) 에서 사용
# ─────────────────────────────────────────────────────
class RiskNode(BaseModel):
    """
    리스크 전파 계산 후 각 노드의 리스크 상태.
    시간축(t)별 리스크 값을 포함.
    """

    ticker: str
    name: str
    sector: str
    country: str

    # risk_score: 현재 시점(t)의 리스크 값 (0~1)
    risk_score: float = Field(ge=0.0, le=1.0)

    # hop_distance: 충격 원점으로부터 몇 홉 떨어져 있는지
    hop_distance: int = Field(ge=0)

    # risk_timeline: 시간(일)별 리스크 추이
    # {0: 0.8, 1: 0.72, ..., 30: 0.03} 형태
    risk_timeline: dict[int, float] = Field(default_factory=dict)

    # is_origin: 충격 발생 기업 여부
    is_origin: bool = Field(default=False)


class RiskEdge(BaseModel):
    """리스크 전파 경로 표현 (엣지)."""

    source_ticker: str
    target_ticker: str
    transmitted_risk: float   # 이 경로로 전달된 리스크 양
    dependency_score: float
    sector_sensitivity: float
