"""
app/engine/shock_simulator.py
---------------------------------------------------------
시나리오 기반 리스크 시뮬레이션 인터페이스.

RiskPropagationEngine 위에서 동작하는 고수준 레이어.
- run_scenario():        단일 시나리오 실행
- compare_scenarios():   복수 시나리오 비교 요약
- compute_sector_exposure(): 섹터별 총 리스크 노출 집계
- get_top_vulnerable():  리스크 상위 N개 기업 추출

설계:
- ScenarioConfig: 시나리오 설정값을 하나의 객체로 캡슐화
- SectorExposure: 섹터별 집계 결과
- ShockSimulator: 상태를 갖지 않는 stateless 클래스 (engine은 내부 보유)
"""

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.engine.risk_propagator import RiskPropagationEngine, PropagationResult

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# 시나리오 설정 및 결과 컨테이너
# ─────────────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    """
    단일 시뮬레이션 시나리오 설정.

    label: 시나리오 이름 (예: "TSMC_full_shock", "TSMC_mild_shock")
    """
    origin_ticker:   str
    shock_intensity: float = 1.0
    decay_lambda:    float = 0.1
    max_hop:         int   = 5
    time_horizon:    int   = 30
    cutoff:          float = 0.01
    label:           str   = ""

    def __post_init__(self) -> None:
        self.origin_ticker = self.origin_ticker.upper()
        if not self.label:
            self.label = f"{self.origin_ticker}_shock{self.shock_intensity}"


@dataclass
class SectorExposure:
    """
    섹터별 리스크 노출 집계 결과.

    total_risk:        섹터 내 모든 기업의 risk_score 합
    company_count:     영향받은 기업 수
    avg_risk:          평균 리스크
    max_risk_ticker:   섹터 내 최고 리스크 기업
    """
    sector:           str
    total_risk:       float
    company_count:    int
    avg_risk:         float
    max_risk_ticker:  str


# ─────────────────────────────────────────────────────
# 시뮬레이터
# ─────────────────────────────────────────────────────

class ShockSimulator:
    """
    충격 시나리오 시뮬레이터.

    Usage:
        simulator = ShockSimulator()

        # 단일 시나리오
        result = await simulator.run_scenario(
            ScenarioConfig(origin_ticker="TSMC", shock_intensity=0.9)
        )

        # 섹터별 노출 집계
        exposures = simulator.compute_sector_exposure(result)

        # 취약 기업 상위 10개
        top10 = simulator.get_top_vulnerable(result, top_n=10)
    """

    def __init__(self) -> None:
        self._engine = RiskPropagationEngine()
        self._settings = get_settings()

    # ── 단일 시나리오 실행 ────────────────────────────────────────────

    async def run_scenario(self, config: ScenarioConfig) -> PropagationResult:
        """
        단일 시나리오 실행.

        Args:
            config: ScenarioConfig 객체 (origin, shock 파라미터 포함)

        Returns:
            PropagationResult: 전파 결과 (nodes, edges, params)
        """
        logger.info(
            "scenario_started",
            label=config.label,
            origin=config.origin_ticker,
            shock=config.shock_intensity,
            lambda_=config.decay_lambda,
            max_hop=config.max_hop,
        )

        result = await self._engine.propagate(
            origin_ticker=config.origin_ticker,
            shock_intensity=config.shock_intensity,
            decay_lambda=config.decay_lambda,
            max_hop=config.max_hop,
            time_horizon=config.time_horizon,
            cutoff=config.cutoff,
        )

        max_node = result.max_risk_node
        logger.info(
            "scenario_completed",
            label=config.label,
            affected=result.affected_count,
            max_risk_ticker=max_node.ticker if max_node else None,
            max_risk_score=max_node.risk_score if max_node else 0.0,
        )

        return result

    # ── 복수 시나리오 비교 ────────────────────────────────────────────

    async def compare_scenarios(
        self,
        configs: list[ScenarioConfig],
    ) -> list[dict]:
        """
        여러 시나리오를 순차적으로 실행하고 비교 요약 반환.

        반환값 구조:
            [
                {
                    "label":           "TSMC_full_shock",
                    "origin_ticker":   "TSMC",
                    "shock_intensity": 1.0,
                    "affected_count":  12,
                    "max_risk_ticker": "AAPL",
                    "max_risk_score":  0.35,
                },
                ...
            ]
        """
        summaries: list[dict] = []

        for config in configs:
            result = await self.run_scenario(config)
            max_node = result.max_risk_node

            summaries.append({
                "label":           config.label,
                "origin_ticker":   config.origin_ticker,
                "shock_intensity": config.shock_intensity,
                "decay_lambda":    config.decay_lambda,
                "max_hop":         config.max_hop,
                "affected_count":  result.affected_count,
                "max_risk_ticker": max_node.ticker    if max_node else None,
                "max_risk_score":  max_node.risk_score if max_node else 0.0,
            })

        # 영향받은 기업 수 내림차순 정렬
        summaries.sort(key=lambda s: s["affected_count"], reverse=True)
        return summaries

    # ── 섹터별 리스크 노출 집계 ────────────────────────────────────────

    def compute_sector_exposure(
        self,
        result: PropagationResult,
    ) -> list[SectorExposure]:
        """
        전파 결과에서 섹터별 리스크 노출을 집계한다.

        원점 기업은 제외하고 전파된 기업들만 집계.
        (원점 기업의 충격 자체는 별도 맥락이므로 노출 집계에서 분리)

        Returns:
            SectorExposure 리스트 (total_risk 내림차순 정렬)
        """
        # 섹터별 노드 그룹화
        sector_nodes: dict[str, list] = {}
        for node in result.nodes:
            if node.is_origin:
                continue
            sector = node.sector or "Unknown"
            if sector not in sector_nodes:
                sector_nodes[sector] = []
            sector_nodes[sector].append(node)

        exposures: list[SectorExposure] = []
        for sector, nodes in sector_nodes.items():
            total_risk = sum(n.risk_score for n in nodes)
            max_node = max(nodes, key=lambda n: n.risk_score)

            exposures.append(SectorExposure(
                sector=sector,
                total_risk=round(total_risk, 6),
                company_count=len(nodes),
                avg_risk=round(total_risk / len(nodes), 6),
                max_risk_ticker=max_node.ticker,
            ))

        return sorted(exposures, key=lambda e: e.total_risk, reverse=True)

    # ── 취약 기업 상위 N개 ────────────────────────────────────────────

    def get_top_vulnerable(
        self,
        result: PropagationResult,
        top_n: int = 10,
    ) -> list[dict]:
        """
        리스크 점수 기준 상위 N개 기업 반환 (원점 제외).

        Returns:
            [
                {
                    "rank":         1,
                    "ticker":       "AAPL",
                    "name":         "Apple Inc.",
                    "sector":       "Technology",
                    "country":      "US",
                    "risk_score":   0.432,
                    "hop_distance": 1,
                },
                ...
            ]
        """
        non_origin = [n for n in result.nodes if not n.is_origin]
        non_origin.sort(key=lambda n: n.risk_score, reverse=True)

        return [
            {
                "rank":         idx + 1,
                "ticker":       node.ticker,
                "name":         node.name,
                "sector":       node.sector,
                "country":      node.country,
                "risk_score":   node.risk_score,
                "hop_distance": node.hop_distance,
            }
            for idx, node in enumerate(non_origin[:top_n])
        ]

    # ── 리스크 타임라인 추출 ──────────────────────────────────────────

    def get_risk_timeline(
        self,
        result: PropagationResult,
        ticker: str,
    ) -> Optional[dict[int, float]]:
        """
        특정 기업의 시간별 리스크 타임라인 반환.

        Args:
            result: 전파 결과
            ticker: 조회할 기업 티커

        Returns:
            {0: 0.8, 1: 0.72, ..., 30: 0.03} 또는 None (기업이 없으면)
        """
        ticker = ticker.upper()
        for node in result.nodes:
            if node.ticker == ticker:
                return node.risk_timeline
        return None
