"""
app/engine/scenario_analysis.py
---------------------------------------------------------
고급 시나리오 분석 모듈.

RiskPropagationEngine 위에서 동작하는 분석 레이어:

1. MultiShockAnalyzer
   - 복수 기업 동시 충격 (예: TSMC + Samsung 동시 파산)
   - 각 origin 독립 실행 후 결과 합산 (asyncio.gather로 병렬 실행)
   - 중복 경로 도달 시 risk 누적, 1.0 캡

2. SensitivityAnalyzer
   - shock_intensity 스윕: 충격 강도에 따른 전파 범위 변화
   - decay_lambda 스윕: 감쇠 계수에 따른 리스크 지속 기간 변화

3. SystemicRiskScorer
   - 각 기업을 origin으로 설정 → 시뮬레이션 실행
   - '제거했을 때 가장 피해가 큰' 핵심 기업 순위화 (systemic importance)
   - 공급망 내 TBTF(Too-Big-To-Fail) 기업 식별
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.engine.risk_propagator import RiskPropagationEngine, PropagationResult
from app.models.graph_models import RiskNode, RiskEdge

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# 1. MultiShockAnalyzer
# ─────────────────────────────────────────────────────

@dataclass
class MultiShockResult:
    """
    복수 충격원 시뮬레이션 결과.

    combined_nodes: 모든 충격원의 전파를 합산한 노드 목록
    per_origin:     충격원별 독립 결과 (개별 영향 비교 가능)
    """
    shock_origins:      list[tuple[str, float]]         # [(ticker, intensity), ...]
    combined_nodes:     list[RiskNode]
    combined_edges:     list[RiskEdge]
    per_origin:         dict[str, PropagationResult]    # ticker → result

    @property
    def affected_count(self) -> int:
        """충격원이 아닌 기업 중 risk를 받은 기업 수."""
        origin_tickers = {t.upper() for t, _ in self.shock_origins}
        return sum(1 for n in self.combined_nodes if n.ticker not in origin_tickers)

    @property
    def total_system_risk(self) -> float:
        """시스템 전체 누적 리스크 (충격원 제외)."""
        origin_tickers = {t.upper() for t, _ in self.shock_origins}
        return round(sum(
            n.risk_score for n in self.combined_nodes
            if n.ticker not in origin_tickers
        ), 6)


class MultiShockAnalyzer:
    """
    복수 기업 동시 충격 시뮬레이션.

    각 origin에서 독립적으로 전파를 실행한 뒤,
    같은 노드에 도달한 리스크를 합산한다.
    합산 후 risk_score는 1.0을 초과할 수 없음 (cap).

    Usage:
        analyzer = MultiShockAnalyzer()
        result = await analyzer.run_combined(
            shock_origins=[("TSMC", 1.0), ("Samsung", 0.7)],
            max_hop=4,
        )
    """

    def __init__(self) -> None:
        self._engine = RiskPropagationEngine()

    async def run_combined(
        self,
        shock_origins:  list[tuple[str, float]],
        decay_lambda:   Optional[float] = None,
        max_hop:        Optional[int]   = None,
        time_horizon:   Optional[int]   = None,
        cutoff:         Optional[float] = None,
    ) -> MultiShockResult:
        """
        복수 origin에서 동시 충격 → 결과 합산.

        asyncio.gather()로 모든 origin을 병렬 실행하여 전체 소요 시간 최소화.

        Args:
            shock_origins: [(ticker, shock_intensity), ...] 리스트

        Returns:
            MultiShockResult: 합산된 노드/엣지 + origin별 독립 결과
        """
        if not shock_origins:
            return MultiShockResult(
                shock_origins=[],
                combined_nodes=[],
                combined_edges=[],
                per_origin={},
            )

        logger.info("multi_shock_started", origins=len(shock_origins))

        # 모든 origin 병렬 실행
        tasks = [
            self._engine.propagate(
                origin_ticker=ticker,
                shock_intensity=intensity,
                decay_lambda=decay_lambda,
                max_hop=max_hop,
                time_horizon=time_horizon,
                cutoff=cutoff,
            )
            for ticker, intensity in shock_origins
        ]
        results: list[PropagationResult] = await asyncio.gather(*tasks)

        # origin별 결과 매핑
        per_origin: dict[str, PropagationResult] = {
            shock_origins[i][0].upper(): results[i]
            for i in range(len(results))
        }

        # ── 결과 합산 ──────────────────────────────────────────────
        # ticker → 누적 risk_score
        combined_risk: dict[str, float] = {}
        # ticker → 노드 메타 (첫 발견 기준)
        node_meta:     dict[str, RiskNode] = {}
        # (source, target) → 엣지 (transmitted_risk 합산)
        edge_map:      dict[tuple[str, str], RiskEdge] = {}

        origin_tickers = {t.upper() for t, _ in shock_origins}

        for result in results:
            for node in result.nodes:
                t = node.ticker
                combined_risk[t] = combined_risk.get(t, 0.0) + node.risk_score
                if t not in node_meta:
                    node_meta[t] = node

            for edge in result.edges:
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

        # 합산 RiskNode 재빌드 (risk_score cap 1.0)
        combined_nodes: list[RiskNode] = []
        for ticker, total_risk in combined_risk.items():
            meta = node_meta[ticker]
            combined_nodes.append(RiskNode(
                ticker=meta.ticker,
                name=meta.name,
                sector=meta.sector,
                country=meta.country,
                risk_score=round(min(total_risk, 1.0), 6),
                hop_distance=meta.hop_distance,
                risk_timeline=meta.risk_timeline,
                is_origin=(ticker in origin_tickers),
            ))

        combined_nodes.sort(key=lambda n: (n.is_origin, -n.risk_score))

        logger.info(
            "multi_shock_completed",
            origins=len(shock_origins),
            total_nodes=len(combined_nodes),
        )

        return MultiShockResult(
            shock_origins=shock_origins,
            combined_nodes=combined_nodes,
            combined_edges=list(edge_map.values()),
            per_origin=per_origin,
        )


# ─────────────────────────────────────────────────────
# 2. SensitivityAnalyzer
# ─────────────────────────────────────────────────────

@dataclass
class SweepPoint:
    """
    파라미터 스윕의 단일 데이터 포인트.

    total_risk: 모든 affected 노드의 risk_score 합
                (전체 시스템 리스크 노출 지표)
    """
    param_name:     str
    param_value:    float
    affected_count: int
    max_risk_score: float
    total_risk:     float


class SensitivityAnalyzer:
    """
    파라미터 민감도 분석.

    shock_intensity 또는 decay_lambda를 범위로 스윕하여
    리스크 전파 결과가 어떻게 변화하는지 분석한다.

    활용 예:
    - "충격 강도를 0.2씩 높이면 영향받는 기업이 어떻게 늘어나나?"
    - "감쇠 계수를 높이면 리스크가 얼마나 빨리 소멸하나?"

    Usage:
        analyzer = SensitivityAnalyzer()
        points = await analyzer.sweep_shock_intensity(
            "TSMC",
            intensities=[0.2, 0.4, 0.6, 0.8, 1.0],
        )
    """

    def __init__(self) -> None:
        self._engine = RiskPropagationEngine()

    async def sweep_shock_intensity(
        self,
        origin_ticker: str,
        intensities:   list[float],
        decay_lambda:  Optional[float] = None,
        max_hop:       Optional[int]   = None,
        time_horizon:  Optional[int]   = None,
    ) -> list[SweepPoint]:
        """
        다양한 shock_intensity 값으로 시뮬레이션 반복.

        Args:
            intensities: 테스트할 충격 강도 목록 (예: [0.2, 0.4, 0.6, 0.8, 1.0])

        Returns:
            SweepPoint 리스트 (intensity 오름차순)
        """
        logger.info(
            "sweep_shock_intensity",
            ticker=origin_ticker,
            steps=len(intensities),
        )
        points: list[SweepPoint] = []

        for intensity in sorted(intensities):
            result = await self._engine.propagate(
                origin_ticker=origin_ticker,
                shock_intensity=intensity,
                decay_lambda=decay_lambda,
                max_hop=max_hop,
                time_horizon=time_horizon,
            )
            non_origin = [n for n in result.nodes if not n.is_origin]
            total_risk = sum(n.risk_score for n in non_origin)
            max_risk   = max((n.risk_score for n in non_origin), default=0.0)

            points.append(SweepPoint(
                param_name="shock_intensity",
                param_value=round(intensity, 4),
                affected_count=result.affected_count,
                max_risk_score=round(max_risk, 6),
                total_risk=round(total_risk, 6),
            ))

        return points

    async def sweep_decay_lambda(
        self,
        origin_ticker:   str,
        lambdas:         list[float],
        shock_intensity: Optional[float] = None,
        max_hop:         Optional[int]   = None,
        time_horizon:    Optional[int]   = None,
    ) -> list[SweepPoint]:
        """
        다양한 decay_lambda 값으로 시뮬레이션 반복.

        lambda가 클수록 리스크가 빨리 소멸 → 먼 노드의 누적 리스크 감소.
        (BFS 자체 전파에는 영향 없음 — timeline 계산에만 적용)

        Args:
            lambdas: 테스트할 감쇠 계수 목록 (예: [0.05, 0.1, 0.2, 0.5])

        Returns:
            SweepPoint 리스트 (lambda 오름차순)
        """
        logger.info(
            "sweep_decay_lambda",
            ticker=origin_ticker,
            steps=len(lambdas),
        )
        points: list[SweepPoint] = []

        for lam in sorted(lambdas):
            result = await self._engine.propagate(
                origin_ticker=origin_ticker,
                decay_lambda=lam,
                shock_intensity=shock_intensity,
                max_hop=max_hop,
                time_horizon=time_horizon,
            )
            non_origin = [n for n in result.nodes if not n.is_origin]
            total_risk = sum(n.risk_score for n in non_origin)
            max_risk   = max((n.risk_score for n in non_origin), default=0.0)

            points.append(SweepPoint(
                param_name="decay_lambda",
                param_value=round(lam, 4),
                affected_count=result.affected_count,
                max_risk_score=round(max_risk, 6),
                total_risk=round(total_risk, 6),
            ))

        return points


# ─────────────────────────────────────────────────────
# 3. SystemicRiskScorer
# ─────────────────────────────────────────────────────

@dataclass
class SystemicRiskScore:
    """
    단일 기업의 시스템 리스크 중요도 점수.

    systemic_score = affected_count × avg_transmitted_risk
                   → 영향 범위(수)와 강도(크기) 동시 반영

    활용:
    - 공급망 내 TBTF(Too-Big-To-Fail) 기업 식별
    - 리스크 모니터링 우선순위 결정
    - 대안 공급자 전략 수립 기준
    """
    ticker:                 str
    name:                   str
    sector:                 str
    country:                str
    systemic_score:         float   # 핵심 지표: 높을수록 시스템 영향력 큼
    affected_count:         int     # 전파된 기업 수
    total_transmitted_risk: float   # 전파된 리스크 총합
    avg_risk_per_affected:  float   # 영향받은 기업당 평균 리스크


class SystemicRiskScorer:
    """
    전체 공급망 시스템 리스크 중요도 계산.

    주어진 ticker 목록을 각각 origin으로 시뮬레이션 실행 후,
    systemic_score(영향 범위 × 평균 강도)를 기준으로 순위를 매긴다.

    Usage:
        scorer = SystemicRiskScorer()
        scores = await scorer.compute_all(
            tickers=["TSMC", "AAPL", "SAMSUNG", "ASML"],
            shock_intensity=1.0,
        )
        # scores[0] = 공급망 붕괴 시 가장 큰 피해를 주는 기업
    """

    def __init__(self) -> None:
        self._engine = RiskPropagationEngine()
        self._settings = get_settings()

    async def compute_all(
        self,
        tickers:         list[str],
        shock_intensity: float         = 1.0,
        decay_lambda:    Optional[float] = None,
        max_hop:         Optional[int]   = None,
        cutoff:          Optional[float] = None,
    ) -> list[SystemicRiskScore]:
        """
        모든 기업을 origin으로 시뮬레이션 → 시스템 리스크 영향력 순위.

        time_horizon=1로 고정: t=0 스냅샷만으로 순위 계산 (효율화).
        (timeline 상세 분석이 필요한 경우 별도 propagate() 호출)

        Args:
            tickers: 평가할 기업 티커 목록

        Returns:
            SystemicRiskScore 리스트 (systemic_score 내림차순)
        """
        logger.info("systemic_risk_scoring_started", ticker_count=len(tickers))

        scores: list[SystemicRiskScore] = []

        for ticker in tickers:
            result = await self._engine.propagate(
                origin_ticker=ticker,
                shock_intensity=shock_intensity,
                decay_lambda=decay_lambda,
                max_hop=max_hop,
                cutoff=cutoff,
                time_horizon=1,   # 스냅샷만 필요 → time_horizon 최소화
            )

            origin_node = next(
                (n for n in result.nodes if n.is_origin), None
            )
            if origin_node is None:
                continue  # 그래프에 없는 ticker 건너뜀

            non_origin = [n for n in result.nodes if not n.is_origin]
            affected_count   = len(non_origin)
            total_transmitted = sum(n.risk_score for n in non_origin)

            if affected_count > 0:
                avg_risk = total_transmitted / affected_count
                # systemic_score: 영향 범위 × 평균 강도
                systemic_score = affected_count * avg_risk
            else:
                avg_risk       = 0.0
                systemic_score = 0.0

            scores.append(SystemicRiskScore(
                ticker=origin_node.ticker,
                name=origin_node.name,
                sector=origin_node.sector,
                country=origin_node.country,
                systemic_score=round(systemic_score, 6),
                affected_count=affected_count,
                total_transmitted_risk=round(total_transmitted, 6),
                avg_risk_per_affected=round(avg_risk, 6),
            ))

        scores.sort(key=lambda s: s.systemic_score, reverse=True)

        logger.info(
            "systemic_risk_scoring_completed",
            scored=len(scores),
            top_ticker=scores[0].ticker if scores else None,
        )

        return scores
