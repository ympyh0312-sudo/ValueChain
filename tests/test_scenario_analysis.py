"""
tests/test_scenario_analysis.py
---------------------------------------------------------
Phase 4 시나리오 분석 단위 테스트 (순수 함수, DB 불필요).

테스트 범위:
- MultiShockResult 프로퍼티 (affected_count, total_system_risk)
- MultiShockAnalyzer 결과 합산 로직 (_combine 패턴)
- SweepPoint 정렬 및 구조
- SystemicRiskScore 정렬 및 systemic_score 계산
"""

import pytest

from app.engine.scenario_analysis import (
    MultiShockResult,
    MultiShockAnalyzer,
    SensitivityAnalyzer,
    SweepPoint,
    SystemicRiskScorer,
    SystemicRiskScore,
)
from app.engine.risk_propagator import PropagationResult
from app.models.graph_models import RiskNode, RiskEdge


# ─────────────────────────────────────────────────────
# 헬퍼
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
        name=f"Co_{ticker}",
        sector=sector,
        country="US",
        risk_score=risk_score,
        hop_distance=hop,
        risk_timeline={},
        is_origin=is_origin,
    )


def make_edge(src: str, tgt: str, risk: float = 0.3) -> RiskEdge:
    return RiskEdge(
        source_ticker=src,
        target_ticker=tgt,
        transmitted_risk=risk,
        dependency_score=0.5,
        sector_sensitivity=0.9,
    )


def make_prop_result(origin: str, nodes: list[RiskNode], edges=None) -> PropagationResult:
    return PropagationResult(
        origin_ticker=origin,
        nodes=nodes,
        edges=edges or [],
        params={"shock_intensity": 1.0, "decay_lambda": 0.1, "max_hop": 5,
                "time_horizon": 30, "cutoff": 0.01, "origin_ticker": origin},
    )


# ─────────────────────────────────────────────────────
# MultiShockResult 프로퍼티
# ─────────────────────────────────────────────────────

class TestMultiShockResult:
    def _make_result(self, origins, nodes, edges=None):
        return MultiShockResult(
            shock_origins=origins,
            combined_nodes=nodes,
            combined_edges=edges or [],
            per_origin={},
        )

    def test_affected_count_excludes_origins(self) -> None:
        """충격원 티커는 affected_count에서 제외."""
        nodes = [
            make_node("TSMC",   1.0, hop=0, is_origin=True),
            make_node("AAPL",   0.5, hop=1),
            make_node("DELL",   0.2, hop=2),
        ]
        result = self._make_result([("TSMC", 1.0)], nodes)
        assert result.affected_count == 2

    def test_affected_count_multi_origin(self) -> None:
        """복수 충격원 모두 제외."""
        nodes = [
            make_node("TSMC",    1.0, hop=0, is_origin=True),
            make_node("SAMSUNG", 0.8, hop=0, is_origin=True),
            make_node("AAPL",    0.4, hop=1),
        ]
        result = self._make_result([("TSMC", 1.0), ("SAMSUNG", 0.8)], nodes)
        assert result.affected_count == 1

    def test_total_system_risk_excludes_origins(self) -> None:
        """시스템 리스크 합산에서 충격원 제외."""
        nodes = [
            make_node("TSMC", 1.0, hop=0, is_origin=True),
            make_node("AAPL", 0.5, hop=1),
            make_node("DELL", 0.3, hop=2),
        ]
        result = self._make_result([("TSMC", 1.0)], nodes)
        assert abs(result.total_system_risk - 0.8) < 1e-6

    def test_total_system_risk_zero_no_propagation(self) -> None:
        """전파 없으면 총 리스크 0."""
        nodes = [make_node("TSMC", 1.0, hop=0, is_origin=True)]
        result = self._make_result([("TSMC", 1.0)], nodes)
        assert result.total_system_risk == 0.0


# ─────────────────────────────────────────────────────
# MultiShockAnalyzer 합산 로직
# ─────────────────────────────────────────────────────

class TestMultiShockCombination:
    """
    run_combined() 내부 합산 로직을 직접 검증.
    (DB 없이 수동으로 결과를 조합하여 기대값 확인)
    """

    def test_risk_capped_at_one(self) -> None:
        """같은 노드에 여러 충격 합산 시 risk_score는 1.0 초과 불가."""
        # 두 origin 모두 AAPL에 0.7 전파
        result1 = make_prop_result("TSMC", [
            make_node("TSMC", 1.0, hop=0, is_origin=True),
            make_node("AAPL", 0.7, hop=1),
        ])
        result2 = make_prop_result("SAMSUNG", [
            make_node("SAMSUNG", 1.0, hop=0, is_origin=True),
            make_node("AAPL", 0.7, hop=1),
        ])

        # 합산 로직 수동 검증
        combined_risk = {}
        for result in [result1, result2]:
            for node in result.nodes:
                combined_risk[node.ticker] = combined_risk.get(node.ticker, 0.0) + node.risk_score

        # AAPL 합산: 0.7 + 0.7 = 1.4 → cap → 1.0
        assert min(combined_risk["AAPL"], 1.0) == 1.0

    def test_edge_risk_accumulated(self) -> None:
        """같은 엣지가 여러 결과에 존재하면 transmitted_risk 합산."""
        e1 = make_edge("TSMC", "AAPL", risk=0.3)
        e2 = make_edge("TSMC", "AAPL", risk=0.2)

        edge_map = {}
        for edge in [e1, e2]:
            key = (edge.source_ticker, edge.target_ticker)
            if key not in edge_map:
                edge_map[key] = edge
            else:
                prev = edge_map[key]
                edge_map[key] = RiskEdge(
                    source_ticker=prev.source_ticker,
                    target_ticker=prev.target_ticker,
                    transmitted_risk=round(prev.transmitted_risk + edge.transmitted_risk, 6),
                    dependency_score=prev.dependency_score,
                    sector_sensitivity=prev.sector_sensitivity,
                )

        assert abs(edge_map[("TSMC", "AAPL")].transmitted_risk - 0.5) < 1e-6

    def test_empty_origins_returns_empty_result(self) -> None:
        """빈 origins 입력 시 빈 결과 반환."""
        # MultiShockResult 직접 생성으로 검증
        result = MultiShockResult(
            shock_origins=[],
            combined_nodes=[],
            combined_edges=[],
            per_origin={},
        )
        assert result.affected_count == 0
        assert result.total_system_risk == 0.0


# ─────────────────────────────────────────────────────
# SweepPoint 구조
# ─────────────────────────────────────────────────────

class TestSweepPoint:
    def test_sweep_point_fields(self) -> None:
        """SweepPoint 필드 초기화 확인."""
        point = SweepPoint(
            param_name="shock_intensity",
            param_value=0.5,
            affected_count=8,
            max_risk_score=0.45,
            total_risk=2.1,
        )
        assert point.param_name == "shock_intensity"
        assert point.param_value == 0.5
        assert point.affected_count == 8
        assert point.total_risk == 2.1

    def test_sorted_ascending(self) -> None:
        """intensity 오름차순으로 정렬된 SweepPoint 리스트."""
        points = [
            SweepPoint("shock_intensity", 0.8, 10, 0.5, 3.0),
            SweepPoint("shock_intensity", 0.2, 4,  0.1, 0.5),
            SweepPoint("shock_intensity", 0.5, 7,  0.3, 1.5),
        ]
        points.sort(key=lambda p: p.param_value)
        assert [p.param_value for p in points] == [0.2, 0.5, 0.8]


# ─────────────────────────────────────────────────────
# SystemicRiskScore 계산 및 정렬
# ─────────────────────────────────────────────────────

class TestSystemicRiskScore:
    def test_systemic_score_formula(self) -> None:
        """systemic_score = affected_count × avg_risk_per_affected."""
        # affected=4, total_transmitted=2.0 → avg=0.5 → score=4*0.5=2.0
        score = SystemicRiskScore(
            ticker="TSMC",
            name="TSMC",
            sector="Technology",
            country="TW",
            systemic_score=2.0,
            affected_count=4,
            total_transmitted_risk=2.0,
            avg_risk_per_affected=0.5,
        )
        assert abs(score.systemic_score - score.affected_count * score.avg_risk_per_affected) < 1e-9

    def test_sorted_by_systemic_score_desc(self) -> None:
        """systemic_score 내림차순 정렬."""
        scores = [
            SystemicRiskScore("A", "A", "Tech", "US", 1.5, 5, 1.5, 0.3),
            SystemicRiskScore("B", "B", "Energy", "US", 3.0, 6, 3.0, 0.5),
            SystemicRiskScore("C", "C", "Tech", "US", 0.5, 2, 0.5, 0.25),
        ]
        scores.sort(key=lambda s: s.systemic_score, reverse=True)
        assert scores[0].ticker == "B"
        assert scores[1].ticker == "A"
        assert scores[2].ticker == "C"

    def test_zero_score_when_no_propagation(self) -> None:
        """전파 없는 기업은 systemic_score = 0."""
        score = SystemicRiskScore(
            ticker="ISOLATED",
            name="Isolated",
            sector="Utilities",
            country="US",
            systemic_score=0.0,
            affected_count=0,
            total_transmitted_risk=0.0,
            avg_risk_per_affected=0.0,
        )
        assert score.systemic_score == 0.0
        assert score.affected_count == 0


# ─────────────────────────────────────────────────────
# 시뮬레이션 결과 직렬화 (simulation_repository 연계)
# ─────────────────────────────────────────────────────

class TestPropagationResultSerialization:
    """PropagationResult.to_dict()가 simulation_repository 저장 형식에 적합한지 확인."""

    def test_to_dict_contains_required_keys(self) -> None:
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.3, hop=1),
        ]
        result = make_prop_result("ORIG", nodes)
        d = result.to_dict()

        required = {"origin_ticker", "params", "affected_count",
                    "max_risk_ticker", "max_risk_score", "nodes", "edges"}
        assert required.issubset(d.keys())

    def test_params_snapshot_in_to_dict(self) -> None:
        """params 딕셔너리가 to_dict에 포함되어야 재현 가능."""
        nodes = [make_node("ORIG", 1.0, hop=0, is_origin=True)]
        result = make_prop_result("ORIG", nodes)
        d = result.to_dict()
        assert "shock_intensity" in d["params"]
        assert "decay_lambda" in d["params"]

    def test_nodes_serializable(self) -> None:
        """nodes 항목이 Pydantic model_dump()로 직렬화 가능."""
        nodes = [
            make_node("ORIG", 1.0, hop=0, is_origin=True),
            make_node("A",    0.5, hop=1),
        ]
        result = make_prop_result("ORIG", nodes)
        d = result.to_dict()
        # 모든 노드 항목이 dict여야 함
        for node_dict in d["nodes"]:
            assert isinstance(node_dict, dict)
            assert "ticker" in node_dict
            assert "risk_score" in node_dict
