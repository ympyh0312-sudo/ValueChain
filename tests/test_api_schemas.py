"""
tests/test_api_schemas.py
---------------------------------------------------------
Phase 6 API 스키마 단위 테스트 (DB/LLM 불필요).

테스트 범위:
- IngestArticleRequest  : 필수 필드, 기본값, 경계값 검증
- RiskAnalysisRequest   : 파라미터 범위, 기본값
- MultiShockRequest     : origins min_length, ShockOrigin 검증
- SensitivitySweepRequest: sweep_type, values
- SystemicRiskRequest   : tickers min_length
- 라우터 임포트 가능 여부 (순환 임포트 / 문법 오류 검사)
- FastAPI 앱 생성 + 라우터 prefix 등록 검증
"""

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    IngestArticleRequest,
    IngestArticleResponse,
    ProcessArticleResponse,
    RiskAnalysisRequest,
    RiskNodeResponse,
    RiskEdgeResponse,
    RiskAnalysisResponse,
    ShockOrigin,
    MultiShockRequest,
    SensitivitySweepRequest,
    SweepPointResponse,
    SystemicRiskRequest,
)


# ─────────────────────────────────────────────────────
# IngestArticleRequest
# ─────────────────────────────────────────────────────

class TestIngestArticleRequest:
    def test_minimal_valid(self) -> None:
        """title + content 만으로 생성 가능."""
        req = IngestArticleRequest(
            title="Test headline",
            content="A" * 10,
        )
        assert req.auto_process is False
        assert req.language == "en"

    def test_title_min_length(self) -> None:
        """title은 최소 1자 이상."""
        with pytest.raises(ValidationError):
            IngestArticleRequest(title="", content="A" * 10)

    def test_content_min_length(self) -> None:
        """content는 최소 10자 이상."""
        with pytest.raises(ValidationError):
            IngestArticleRequest(title="T", content="short")

    def test_source_fields_optional(self) -> None:
        """source_url, source_name, published_at 모두 선택."""
        req = IngestArticleRequest(title="T", content="A" * 10)
        assert req.source_url is None
        assert req.source_name is None
        assert req.published_at is None

    def test_auto_process_flag(self) -> None:
        """auto_process=True 설정."""
        req = IngestArticleRequest(
            title="T", content="A" * 10, auto_process=True
        )
        assert req.auto_process is True

    def test_title_max_length(self) -> None:
        """title 최대 1024자 초과 시 오류."""
        with pytest.raises(ValidationError):
            IngestArticleRequest(title="x" * 1025, content="A" * 10)


# ─────────────────────────────────────────────────────
# IngestArticleResponse / ProcessArticleResponse
# ─────────────────────────────────────────────────────

class TestIngestResponses:
    def test_ingest_response(self) -> None:
        resp = IngestArticleResponse(
            article_id=42,
            status="ingested",
            message="저장 완료",
        )
        assert resp.article_id == 42
        assert resp.status == "ingested"

    def test_process_response_defaults(self) -> None:
        resp = ProcessArticleResponse(
            article_id=1,
            status="completed",
            relations_found=3,
            relations_applied=2,
            relations_rejected=1,
        )
        assert resp.details == []
        assert resp.error is None


# ─────────────────────────────────────────────────────
# RiskAnalysisRequest
# ─────────────────────────────────────────────────────

class TestRiskAnalysisRequest:
    def test_defaults(self) -> None:
        """기본값 확인."""
        req = RiskAnalysisRequest(ticker="TSMC")
        assert req.shock_intensity == 1.0
        assert req.decay_lambda == 0.1
        assert req.max_hop == 5
        assert req.time_horizon == 30
        assert req.cutoff == 0.01
        assert req.save_result is False

    def test_shock_intensity_bounds(self) -> None:
        """shock_intensity: 0~1 범위만 허용."""
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", shock_intensity=1.5)
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", shock_intensity=-0.1)

    def test_max_hop_bounds(self) -> None:
        """max_hop: 1~10 범위."""
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", max_hop=0)
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", max_hop=11)

    def test_time_horizon_bounds(self) -> None:
        """time_horizon: 1~365 범위."""
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", time_horizon=0)
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", time_horizon=366)

    def test_cutoff_bounds(self) -> None:
        """cutoff: 0 초과 ~ 1 미만."""
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", cutoff=0.0)
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", cutoff=1.0)

    def test_decay_lambda_gt_zero(self) -> None:
        """decay_lambda: 0 초과."""
        with pytest.raises(ValidationError):
            RiskAnalysisRequest(ticker="T", decay_lambda=0.0)

    def test_save_result_with_label(self) -> None:
        req = RiskAnalysisRequest(
            ticker="TSMC",
            save_result=True,
            label="Q1_test",
        )
        assert req.save_result is True
        assert req.label == "Q1_test"


# ─────────────────────────────────────────────────────
# RiskAnalysisResponse
# ─────────────────────────────────────────────────────

class TestRiskAnalysisResponse:
    def test_full_response(self) -> None:
        resp = RiskAnalysisResponse(
            origin_ticker   = "TSMC",
            params          = {"shock_intensity": 1.0},
            affected_count  = 5,
            max_risk_ticker = "AAPL",
            max_risk_score  = 0.72,
            nodes           = [],
            edges           = [],
        )
        assert resp.simulation_id is None
        assert resp.origin_ticker == "TSMC"

    def test_with_simulation_id(self) -> None:
        resp = RiskAnalysisResponse(
            origin_ticker   = "T",
            params          = {},
            affected_count  = 0,
            max_risk_ticker = None,
            max_risk_score  = 0.0,
            nodes           = [],
            edges           = [],
            simulation_id   = 42,
        )
        assert resp.simulation_id == 42


# ─────────────────────────────────────────────────────
# ShockOrigin / MultiShockRequest
# ─────────────────────────────────────────────────────

class TestMultiShockRequest:
    def test_valid(self) -> None:
        req = MultiShockRequest(
            origins=[
                ShockOrigin(ticker="TSMC", shock_intensity=1.0),
                ShockOrigin(ticker="AAPL", shock_intensity=0.5),
            ]
        )
        assert len(req.origins) == 2

    def test_origins_min_length(self) -> None:
        """origins는 최소 1개."""
        with pytest.raises(ValidationError):
            MultiShockRequest(origins=[])

    def test_shock_origin_defaults(self) -> None:
        """ShockOrigin shock_intensity 기본값 1.0."""
        o = ShockOrigin(ticker="TSMC")
        assert o.shock_intensity == 1.0

    def test_shock_origin_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ShockOrigin(ticker="T", shock_intensity=1.1)
        with pytest.raises(ValidationError):
            ShockOrigin(ticker="T", shock_intensity=-0.1)

    def test_optional_params_default_none(self) -> None:
        req = MultiShockRequest(origins=[ShockOrigin(ticker="T")])
        assert req.decay_lambda is None
        assert req.max_hop is None
        assert req.time_horizon is None


# ─────────────────────────────────────────────────────
# SensitivitySweepRequest
# ─────────────────────────────────────────────────────

class TestSensitivitySweepRequest:
    def test_valid_shock_intensity(self) -> None:
        req = SensitivitySweepRequest(
            ticker="TSMC",
            sweep_type="shock_intensity",
            values=[0.2, 0.4, 0.6, 0.8, 1.0],
        )
        assert req.sweep_type == "shock_intensity"
        assert len(req.values) == 5

    def test_valid_decay_lambda(self) -> None:
        req = SensitivitySweepRequest(
            ticker="TSMC",
            sweep_type="decay_lambda",
            values=[0.05, 0.1, 0.2],
        )
        assert req.sweep_type == "decay_lambda"

    def test_values_min_length(self) -> None:
        """values는 최소 1개."""
        with pytest.raises(ValidationError):
            SensitivitySweepRequest(
                ticker="T",
                sweep_type="shock_intensity",
                values=[],
            )

    def test_optional_overrides(self) -> None:
        req = SensitivitySweepRequest(
            ticker="T",
            sweep_type="shock_intensity",
            values=[1.0],
            decay_lambda=0.2,
            max_hop=3,
        )
        assert req.decay_lambda == 0.2
        assert req.max_hop == 3


# ─────────────────────────────────────────────────────
# SweepPointResponse
# ─────────────────────────────────────────────────────

class TestSweepPointResponse:
    def test_fields(self) -> None:
        pt = SweepPointResponse(
            param_name     = "shock_intensity",
            param_value    = 0.6,
            affected_count = 8,
            max_risk_score = 0.54,
            total_risk     = 3.2,
        )
        assert pt.param_name == "shock_intensity"
        assert pt.param_value == 0.6


# ─────────────────────────────────────────────────────
# SystemicRiskRequest
# ─────────────────────────────────────────────────────

class TestSystemicRiskRequest:
    def test_valid(self) -> None:
        req = SystemicRiskRequest(tickers=["TSMC", "AAPL", "NVDA"])
        assert len(req.tickers) == 3
        assert req.shock_intensity == 1.0
        assert req.max_hop == 5

    def test_tickers_min_length(self) -> None:
        """tickers 최소 1개."""
        with pytest.raises(ValidationError):
            SystemicRiskRequest(tickers=[])

    def test_shock_intensity_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SystemicRiskRequest(tickers=["T"], shock_intensity=1.5)

    def test_max_hop_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SystemicRiskRequest(tickers=["T"], max_hop=11)


# ─────────────────────────────────────────────────────
# 라우터 임포트 / 등록 검증
# ─────────────────────────────────────────────────────

class TestRouterImports:
    def test_ingest_router_importable(self) -> None:
        """ingest 라우터 임포트 오류 없음."""
        from app.api.v1.ingest import router
        assert router.prefix == "/ingest"

    def test_risk_router_importable(self) -> None:
        """risk 라우터 임포트 오류 없음."""
        from app.api.v1.risk import router
        assert router.prefix == "/risk"

    def test_network_router_importable(self) -> None:
        """network 라우터 임포트 오류 없음."""
        from app.api.v1.network import router
        assert router.prefix == "/network"

    def test_route_paths_registered(self) -> None:
        """각 라우터의 경로가 올바르게 등록됐는지 확인.
        APIRouter에 prefix가 있으면 r.path에 prefix가 포함됨."""
        from app.api.v1.ingest import router as ir
        from app.api.v1.risk   import router as rr
        from app.api.v1.network import router as nr

        ingest_paths  = {r.path for r in ir.routes}
        risk_paths    = {r.path for r in rr.routes}
        network_paths = {r.path for r in nr.routes}

        # ingest 엔드포인트 (prefix /ingest 포함)
        assert "/ingest/articles" in ingest_paths
        assert "/ingest/articles/{article_id}/process" in ingest_paths

        # risk 엔드포인트 (prefix /risk 포함)
        assert "/risk/analyze" in risk_paths
        assert "/risk/scenario/multi-shock" in risk_paths
        assert "/risk/scenario/sensitivity" in risk_paths
        assert "/risk/simulations" in risk_paths
        assert "/risk/simulations/{sim_id}" in risk_paths

        # network 엔드포인트 (prefix /network 포함)
        assert "/network/companies" in network_paths
        assert "/network/companies/{ticker}" in network_paths
        assert "/network/companies/{ticker}/suppliers" in network_paths
        assert "/network/companies/{ticker}/buyers" in network_paths
        assert "/network/companies/{ticker}/subgraph" in network_paths
        assert "/network/relations" in network_paths
        assert "/network/systemic-risk" in network_paths

    def test_fastapi_app_includes_routers(self) -> None:
        """FastAPI app에 라우터가 등록됐는지 확인 (DB 연결 없이)."""
        from app.main import app

        all_paths = {r.path for r in app.routes}

        # 주요 엔드포인트 포함 여부
        assert "/api/v1/ingest/articles" in all_paths
        assert "/api/v1/risk/analyze" in all_paths
        assert "/api/v1/network/companies" in all_paths
        assert "/health" in all_paths
        assert "/" in all_paths
