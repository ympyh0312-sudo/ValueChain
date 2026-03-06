"""
tests/test_risk_engine.py
---------------------------------------------------------
Phase 3 리스크 엔진 단위 테스트.

테스트 범위:
- RiskPropagationEngine._compute_timeline() : 순수 함수, DB 불필요
- ShockSimulator.compute_sector_exposure()  : 순수 함수, DB 불필요
- ShockSimulator.get_top_vulnerable()       : 순수 함수, DB 불필요
- ShockSimulator.get_risk_timeline()        : 순수 함수, DB 불필요
- PropagationResult 프로퍼티                : 순수 로직

DB 연동이 필요한 통합 테스트(propagate, run_scenario)는
Phase 6 또는 별도 integration_tests/에서 실행한다.
"""

import math
import pytest

from app.engine.risk_propagator import RiskPropagationEngine, PropagationResult
from app.engine.shock_simulator import ShockSimulator, ScenarioConfig, SectorExposure
from app.models.graph_models import RiskNode, RiskEdge


# ─────────────────────────────────────────────────────
# 헬퍼 팩토리
# ─────────────────────────────────────────────────────

def make_node(
    ticker: str,
    risk_score: float,
    hop: int = 1,
    sector: str = "Technology",
    is_origin: bool = False,
) -> RiskNode:
    return RiskNode(
        ticker=ticker,
        name=f"Company_{ticker}",
        sector=sector,
        country="US",
        risk_score=risk_score,
        hop_distance=hop,
        risk_timeline={},
        is_origin=is_origin,
    )


def make_result(nodes: list[RiskNode], edges=None) -> PropagationResult:
    return PropagationResult(
        origin_ticker="ORIG",
        nodes=nodes,
        edges=edges or [],
        params={},
    )


# ─────────────────────────────────────────────────────
# RiskPropagationEngine._compute_timeline
# ─────────────────────────────────────────────────────

class TestComputeTimeline:
    """_compute_timeline 단위 테스트 (순수 함수)."""

    def setup_method(self) -> None:
        self.engine = RiskPropagationEngine()

    def test_origin_starts_at_t0(self) -> None:
        """hop=0 원점: t=0부터 즉시 리스크 발생."""
        tl = self.engine._compute_timeline(
            base_risk=1.0, hop=0, decay_lambda=0.1, time_horizon=5
        )
        assert abs(tl[0] - 1.0) < 1e-9
        assert abs(tl[1] - math.exp(-0.1)) < 1e-9
        assert abs(tl[5] - math.exp(-0.5)) < 1e-9

    def test_hop1_zero_before_arrival(self) -> None:
        """hop=1 노드: t=0은 0 (아직 도달 전), t=1부터 리스크."""
        tl = self.engine._compute_timeline(
            base_risk=0.5, hop=1, decay_lambda=0.1, time_horizon=5
        )
        assert tl[0] == 0.0
        # t=1: base_risk * e^(-lambda*(1-1)) = 0.5 * 1 = 0.5
        assert abs(tl[1] - 0.5) < 1e-9
        # t=3: base_risk * e^(-lambda*(3-1)) = 0.5 * e^(-0.2)
        assert abs(tl[3] - 0.5 * math.exp(-0.2)) < 1e-9

    def test_hop3_zeros_until_arrival(self) -> None:
        """hop=3: t=0,1,2는 0, t=3부터 리스크."""
        tl = self.engine._compute_timeline(
            base_risk=0.3, hop=3, decay_lambda=0.1, time_horizon=5
        )
        assert tl[0] == 0.0
        assert tl[1] == 0.0
        assert tl[2] == 0.0
        # t=3: peak
        assert abs(tl[3] - 0.3) < 1e-9
        # t=4: 0.3 * e^(-0.1)
        assert abs(tl[4] - 0.3 * math.exp(-0.1)) < 1e-9

    def test_zero_decay_lambda(self) -> None:
        """decay_lambda=0이면 리스크가 시간에 따라 감소하지 않음."""
        tl = self.engine._compute_timeline(
            base_risk=0.8, hop=0, decay_lambda=0.0, time_horizon=10
        )
        for t in range(11):
            assert abs(tl[t] - 0.8) < 1e-9

    def test_high_decay_lambda(self) -> None:
        """lambda=1.0이면 하루 만에 급격히 감소."""
        tl = self.engine._compute_timeline(
            base_risk=1.0, hop=0, decay_lambda=1.0, time_horizon=5
        )
        # t=1: e^(-1) ≈ 0.368
        assert abs(tl[1] - math.exp(-1.0)) < 1e-9
        # t=5: e^(-5) ≈ 0.0067 (거의 소멸)
        assert tl[5] < 0.01

    def test_timeline_keys_range(self) -> None:
        """타임라인 키는 0부터 time_horizon까지 포함."""
        tl = self.engine._compute_timeline(
            base_risk=1.0, hop=0, decay_lambda=0.1, time_horizon=7
        )
        assert set(tl.keys()) == set(range(8))   # 0~7

    def test_base_risk_scaling(self) -> None:
        """base_risk 크기에 비례한 타임라인 값."""
        tl_a = self.engine._compute_timeline(0.5, 0, 0.1, 5)
        tl_b = self.engine._compute_timeline(1.0, 0, 0.1, 5)
        for t in range(6):
            assert abs(tl_b[t] - 2 * tl_a[t]) < 1e-9


# ─────────────────────────────────────────────────────
# PropagationResult 프로퍼티
# ─────────────────────────────────────────────────────

class TestPropagationResult:
    """PropagationResult 계산 프로퍼티 테스트."""

    def test_affected_count_excludes_origin(self) -> None:
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.5, hop=1),
            make_node("B",    0.3, hop=2),
        ]
        result = make_result(nodes)
        assert result.affected_count == 2

    def test_affected_count_empty(self) -> None:
        result = make_result([make_node("ORIG", 1.0, hop=0, is_origin=True)])
        assert result.affected_count == 0

    def test_max_risk_node_finds_highest(self) -> None:
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("LOW",  0.1, hop=2),
            make_node("HIGH", 0.8, hop=1),
        ]
        result = make_result(nodes)
        assert result.max_risk_node.ticker == "HIGH"

    def test_max_risk_node_none_when_only_origin(self) -> None:
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)]
        result = make_result(nodes)
        assert result.max_risk_node is None

    def test_to_dict_structure(self) -> None:
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.4, hop=1),
        ]
        result = make_result(nodes)
        d = result.to_dict()

        assert d["origin_ticker"] == "ORIG"
        assert d["affected_count"] == 1
        assert d["max_risk_ticker"] == "A"
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)


# ─────────────────────────────────────────────────────
# ShockSimulator.compute_sector_exposure
# ─────────────────────────────────────────────────────

class TestComputeSectorExposure:
    """섹터별 리스크 노출 집계 테스트."""

    def setup_method(self) -> None:
        self.sim = ShockSimulator()

    def test_origin_excluded(self) -> None:
        """원점 노드는 섹터 집계에서 제외."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, sector="Technology", is_origin=True),
            make_node("B1",   0.3, hop=1, sector="Technology"),
        ]
        exposures = self.sim.compute_sector_exposure(make_result(nodes))
        assert len(exposures) == 1
        assert abs(exposures[0].total_risk - 0.3) < 1e-9
        assert exposures[0].company_count == 1

    def test_sector_risk_aggregation(self) -> None:
        """같은 섹터의 리스크는 합산."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("T1",   0.5, hop=1, sector="Technology"),
            make_node("T2",   0.3, hop=2, sector="Technology"),
            make_node("E1",   0.4, hop=1, sector="Energy"),
        ]
        exposures = self.sim.compute_sector_exposure(make_result(nodes))
        sector_map = {e.sector: e for e in exposures}

        assert "Technology" in sector_map
        assert abs(sector_map["Technology"].total_risk - 0.8) < 1e-9
        assert sector_map["Technology"].company_count == 2

        assert "Energy" in sector_map
        assert abs(sector_map["Energy"].total_risk - 0.4) < 1e-9

    def test_sorted_by_total_risk_desc(self) -> None:
        """결과는 total_risk 내림차순."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("E1",   0.1, hop=1, sector="Energy"),
            make_node("T1",   0.8, hop=1, sector="Technology"),
            make_node("T2",   0.5, hop=2, sector="Technology"),
        ]
        exposures = self.sim.compute_sector_exposure(make_result(nodes))
        # Technology(0.8+0.5=1.3) > Energy(0.1)
        assert exposures[0].sector == "Technology"
        assert exposures[1].sector == "Energy"

    def test_max_risk_ticker_correct(self) -> None:
        """섹터 내 최고 리스크 기업 식별."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("LOW",  0.2, hop=2, sector="Technology"),
            make_node("HIGH", 0.9, hop=1, sector="Technology"),
        ]
        exposures = self.sim.compute_sector_exposure(make_result(nodes))
        assert exposures[0].max_risk_ticker == "HIGH"

    def test_empty_result(self) -> None:
        """원점만 있으면 빈 리스트 반환."""
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)]
        exposures = self.sim.compute_sector_exposure(make_result(nodes))
        assert exposures == []


# ─────────────────────────────────────────────────────
# ShockSimulator.get_top_vulnerable
# ─────────────────────────────────────────────────────

class TestGetTopVulnerable:
    """취약 기업 상위 N개 추출 테스트."""

    def setup_method(self) -> None:
        self.sim = ShockSimulator()

    def test_sorted_by_risk_score_desc(self) -> None:
        """리스크 점수 내림차순 정렬 확인."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("LOW",  0.1, hop=2),
            make_node("HIGH", 0.8, hop=1),
            make_node("MID",  0.4, hop=2),
        ]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=10)
        assert top[0]["ticker"] == "HIGH"
        assert top[1]["ticker"] == "MID"
        assert top[2]["ticker"] == "LOW"

    def test_origin_excluded(self) -> None:
        """원점은 top 목록에서 제외."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.5, hop=1),
        ]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=5)
        tickers = [t["ticker"] for t in top]
        assert "ORIG" not in tickers

    def test_top_n_limit_respected(self) -> None:
        """top_n 개수 제한이 정확히 적용됨."""
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)] + [
            make_node(f"B{i}", 0.1 * i, hop=1)
            for i in range(1, 9)   # 8개 기업
        ]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=3)
        assert len(top) == 3

    def test_rank_starts_at_1(self) -> None:
        """rank 필드는 1부터 시작."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.5, hop=1),
            make_node("B",    0.3, hop=2),
        ]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=5)
        assert top[0]["rank"] == 1
        assert top[1]["rank"] == 2

    def test_result_fields_present(self) -> None:
        """반환 dict에 필수 필드가 포함됨."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.5, hop=1),
        ]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=5)
        assert len(top) == 1
        required_keys = {"rank", "ticker", "name", "sector", "country", "risk_score", "hop_distance"}
        assert required_keys.issubset(set(top[0].keys()))

    def test_empty_when_only_origin(self) -> None:
        """원점만 있을 때 빈 리스트 반환."""
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)]
        top = self.sim.get_top_vulnerable(make_result(nodes), top_n=5)
        assert top == []


# ─────────────────────────────────────────────────────
# ShockSimulator.get_risk_timeline
# ─────────────────────────────────────────────────────

class TestGetRiskTimeline:
    """특정 기업 리스크 타임라인 조회 테스트."""

    def setup_method(self) -> None:
        self.sim = ShockSimulator()

    def test_returns_timeline_for_existing_ticker(self) -> None:
        node = make_node("AAPL", 0.4, hop=1)
        node.risk_timeline = {0: 0.0, 1: 0.4, 2: 0.36}
        result = make_result([node])

        tl = self.sim.get_risk_timeline(result, "AAPL")
        assert tl is not None
        assert tl[1] == 0.4

    def test_case_insensitive_ticker(self) -> None:
        """티커는 대소문자 구분 없이 조회 가능."""
        node = make_node("AAPL", 0.4, hop=1)
        node.risk_timeline = {0: 0.0, 1: 0.4}
        result = make_result([node])

        assert self.sim.get_risk_timeline(result, "aapl") is not None

    def test_returns_none_for_missing_ticker(self) -> None:
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)]
        assert self.sim.get_risk_timeline(make_result(nodes), "NOTEXIST") is None


# ─────────────────────────────────────────────────────
# ScenarioConfig 초기화 테스트
# ─────────────────────────────────────────────────────

class TestScenarioConfig:
    def test_ticker_normalized_to_upper(self) -> None:
        config = ScenarioConfig(origin_ticker="tsmc", shock_intensity=0.8)
        assert config.origin_ticker == "TSMC"

    def test_default_label_generated(self) -> None:
        config = ScenarioConfig(origin_ticker="TSMC", shock_intensity=0.9)
        assert "TSMC" in config.label
        assert "0.9" in config.label

    def test_custom_label_preserved(self) -> None:
        config = ScenarioConfig(origin_ticker="TSMC", shock_intensity=1.0, label="my_scenario")
        assert config.label == "my_scenario"
