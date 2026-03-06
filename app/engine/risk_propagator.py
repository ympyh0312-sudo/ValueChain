"""
app/engine/risk_propagator.py
---------------------------------------------------------
핵심 리스크 전파 엔진.

리스크 전파 공식:
    Risk_dest(t) = Risk_src(t-1) x Dependency x SectorSensitivity
                   x (1 - LiquidityBuffer) x e^(-lambda*t) x ShockIntensity

알고리즘:
    - 비동기 BFS: 충격 원점(origin)에서 공급망 하류(buyer 방향)로 전파
    - 사이클 방지: expanded set으로 이미 탐색한 노드 재탐색 차단
    - 다중 경로 누적: 같은 노드에 여러 경로로 도달하면 risk 합산
    - Threshold Cutoff: transmitted_risk < cutoff 이면 해당 경로 탐색 중단

BFS 방향:
    (supplier) -[:SUPPLY_TO]-> (buyer)
    즉, 공급망 충격은 supplier에서 buyer 방향으로 전파

시간 모델:
    - 원점(hop=0): risk_timeline[t] = ShockIntensity x e^(-lambda*t)
    - hop-h 노드:  risk_timeline[t] = peak_risk x e^(-lambda*(t-h))   for t >= h
                                    = 0                                for t < h
    - peak_risk = 누적 전파 계수 x ShockIntensity (BFS 경로 전체 곱)
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.graph_repository import get_company, get_direct_buyers
from app.models.graph_models import RiskNode, RiskEdge, get_sector_sensitivity

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# 전파 결과 컨테이너
# ─────────────────────────────────────────────────────

@dataclass
class PropagationResult:
    """
    리스크 전파 시뮬레이션 결과 컨테이너.

    nodes: 충격을 받은 모든 기업 (origin 포함)
    edges: 실제로 리스크가 흘러간 공급망 엣지
    params: 시뮬레이션에 사용된 파라미터 스냅샷
    """
    origin_ticker: str
    nodes: list[RiskNode]
    edges: list[RiskEdge]
    params: dict[str, Any]

    @property
    def affected_count(self) -> int:
        """원점 제외 리스크를 받은 기업 수."""
        return sum(1 for n in self.nodes if not n.is_origin)

    @property
    def max_risk_node(self) -> Optional[RiskNode]:
        """원점 제외 리스크 점수가 가장 높은 노드."""
        non_origin = [n for n in self.nodes if not n.is_origin]
        if not non_origin:
            return None
        return max(non_origin, key=lambda n: n.risk_score)

    def to_dict(self) -> dict:
        """API 응답 또는 직렬화용 dict 변환."""
        max_node = self.max_risk_node
        return {
            "origin_ticker":    self.origin_ticker,
            "params":           self.params,
            "affected_count":   self.affected_count,
            "max_risk_ticker":  max_node.ticker    if max_node else None,
            "max_risk_score":   max_node.risk_score if max_node else 0.0,
            "nodes":            [n.model_dump() for n in self.nodes],
            "edges":            [e.model_dump() for e in self.edges],
        }


# ─────────────────────────────────────────────────────
# 리스크 전파 엔진
# ─────────────────────────────────────────────────────

class RiskPropagationEngine:
    """
    공급망 리스크 전파 엔진.

    BFS 기반으로 그래프를 탐색하며 공식에 따라 리스크를 전파한다.
    각 기업의 risk_timeline[t]은 시간(일)별 리스크 추이를 나타낸다.

    Usage:
        engine = RiskPropagationEngine()
        result = await engine.propagate("TSMC", shock_intensity=0.9)
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ── 시간 감쇠 타임라인 계산 (순수 함수, 테스트 가능) ─────────────

    def _compute_timeline(
        self,
        base_risk: float,
        hop: int,
        decay_lambda: float,
        time_horizon: int,
    ) -> dict[int, float]:
        """
        노드의 시간별 리스크 타임라인 계산.

        risk_timeline[t] = base_risk x e^(-lambda*(t-hop))   for t >= hop
                         = 0                                   for t < hop

        Args:
            base_risk:     hop 도달 시점의 피크 리스크
            hop:           이 노드까지의 홉 거리 (리스크 도달 시각)
            decay_lambda:  시간 감쇠 계수 (클수록 빠르게 소멸)
            time_horizon:  계산할 최대 일수
        """
        timeline: dict[int, float] = {}
        for t in range(time_horizon + 1):
            if t < hop:
                timeline[t] = 0.0
            else:
                timeline[t] = base_risk * math.exp(-decay_lambda * (t - hop))
        return timeline

    # ── 메인 전파 함수 ────────────────────────────────────────────────

    async def propagate(
        self,
        origin_ticker: str,
        shock_intensity: Optional[float] = None,
        decay_lambda:    Optional[float] = None,
        max_hop:         Optional[int]   = None,
        time_horizon:    Optional[int]   = None,
        cutoff:          Optional[float] = None,
    ) -> PropagationResult:
        """
        BFS 기반 리스크 전파 시뮬레이션 실행.

        Args:
            origin_ticker:   충격 발생 기업 티커
            shock_intensity: 초기 충격 강도 (0~1)
            decay_lambda:    시간 감쇠 계수
            max_hop:         최대 전파 홉 수
            time_horizon:    분석 기간 (일)
            cutoff:          전파 중단 임계값 (이 값 미만 경로는 탐색 중단)

        Returns:
            PropagationResult: 전파된 모든 노드/엣지 및 시뮬레이션 파라미터
        """
        # 기본값: settings에서 로드
        s = self._settings
        si  = shock_intensity if shock_intensity is not None else s.default_shock_intensity
        lam = decay_lambda    if decay_lambda    is not None else s.default_decay_lambda
        mh  = max_hop         if max_hop         is not None else s.default_max_hop
        th  = time_horizon    if time_horizon     is not None else s.default_time_horizon
        cut = cutoff          if cutoff           is not None else s.risk_cutoff_threshold

        params: dict[str, Any] = {
            "origin_ticker":   origin_ticker.upper(),
            "shock_intensity": si,
            "decay_lambda":    lam,
            "max_hop":         mh,
            "time_horizon":    th,
            "cutoff":          cut,
        }

        logger.info("risk_propagation_started", **params)

        # ── 원점 기업 조회 ──────────────────────────────────────────
        origin_ticker_up = origin_ticker.upper()
        origin_company = await get_company(origin_ticker_up)
        if origin_company is None:
            logger.warning("origin_company_not_found", ticker=origin_ticker_up)
            return PropagationResult(
                origin_ticker=origin_ticker_up,
                nodes=[],
                edges=[],
                params=params,
            )

        # ── 누적 저장소 초기화 ─────────────────────────────────────
        # ticker → 누적 리스크 (여러 경로의 합)
        accumulated_risk: dict[str, float] = {}
        # ticker → 첫 도달 홉 거리
        hop_distance: dict[str, int] = {}
        # ticker → 기업 정보 캐시 (DB 중복 조회 방지)
        node_info_cache: dict[str, dict[str, Any]] = {}

        # 이미 BFS 확장(expand)을 완료한 노드 (사이클/재탐색 방지)
        expanded: set[str] = set()

        # 엣지 수집 (중복 방지)
        edge_records: list[RiskEdge] = []
        edge_seen: set[tuple[str, str]] = set()

        # 원점 정보 캐싱
        node_info_cache[origin_ticker_up] = {
            "ticker":          origin_company.ticker,
            "name":            origin_company.name,
            "sector":          origin_company.sector,
            "country":         origin_company.country,
            "liquidity_score": origin_company.liquidity_score,
        }

        # ── BFS 큐: (ticker, hop, incoming_risk) ──────────────────
        queue: deque[tuple[str, int, float]] = deque()
        queue.append((origin_ticker_up, 0, si))

        while queue:
            ticker, hop, incoming_risk = queue.popleft()

            # 리스크 누적 (다중 경로 합산)
            accumulated_risk[ticker] = accumulated_risk.get(ticker, 0.0) + incoming_risk
            if ticker not in hop_distance:
                hop_distance[ticker] = hop

            # Cutoff: 전파 강도가 너무 작으면 이 경로 더 탐색 안 함
            if incoming_risk < cut:
                continue

            # 최대 홉 초과 시 탐색 종료
            if hop >= mh:
                continue

            # 이미 확장한 노드 재탐색 방지 (사이클 차단)
            if ticker in expanded:
                continue
            expanded.add(ticker)

            # ── 하류(구매사) 목록 조회 ───────────────────────────
            try:
                buyers = await get_direct_buyers(ticker)
            except Exception as e:
                logger.warning("get_buyers_failed", ticker=ticker, error=str(e))
                continue

            for buyer in buyers:
                buyer_ticker: str  = buyer["buyer_ticker"]
                dep:  float        = float(buyer.get("dependency_score", 0.5) or 0.5)
                conf: float        = float(buyer.get("confidence_score",  1.0) or 1.0)
                # get_direct_buyers 결과에서 buyer 노드 정보 바로 사용
                b_sector: str      = buyer.get("sector") or "Unknown"
                b_liq:    float    = float(buyer.get("liquidity_score", 0.5) or 0.5)
                b_name:   str      = buyer.get("buyer_name") or buyer_ticker

                # 구매사 기본 정보 캐싱 (get_direct_buyers 결과에 country 포함)
                b_country = buyer.get("country") or ""
                if buyer_ticker not in node_info_cache:
                    node_info_cache[buyer_ticker] = {
                        "ticker":          buyer_ticker,
                        "name":            b_name,
                        "sector":          b_sector,
                        "country":         b_country,
                        "liquidity_score": b_liq,
                    }

                # ── 공식 적용 ──────────────────────────────────
                # Risk_dest = Risk_src x Dependency x SectorSensitivity
                #             x LiquidityFactor x conf
                # LiquidityFactor = max(0.30, 1 - LiquidityBuffer)
                #   유동성이 높아도 최소 30%는 전달 → 8홉 체인 유지
                # (e^(-lambda*t) 항은 timeline 계산 시 적용)
                sect_sens: float   = get_sector_sensitivity(b_sector)
                liq_factor: float  = max(0.30, 1.0 - b_liq)
                transmitted: float = incoming_risk * dep * sect_sens * liq_factor * conf

                if transmitted < cut:
                    continue

                # 엣지 기록 (source→target 중복 방지)
                edge_key = (ticker, buyer_ticker)
                if edge_key not in edge_seen:
                    edge_seen.add(edge_key)
                    edge_records.append(RiskEdge(
                        source_ticker=ticker,
                        target_ticker=buyer_ticker,
                        transmitted_risk=round(transmitted, 6),
                        dependency_score=dep,
                        sector_sensitivity=sect_sens,
                    ))

                # 다음 홉 큐에 추가
                queue.append((buyer_ticker, hop + 1, transmitted))

        # ── RiskNode 빌드 ──────────────────────────────────────────
        risk_nodes: list[RiskNode] = []

        for ticker, base_risk in accumulated_risk.items():
            info = node_info_cache.get(ticker)
            if not info:
                continue

            hop  = hop_distance.get(ticker, 0)
            timeline = self._compute_timeline(base_risk, hop, lam, th)

            risk_nodes.append(RiskNode(
                ticker=info["ticker"],
                name=info["name"],
                sector=info["sector"],
                country=info.get("country", ""),
                risk_score=round(min(base_risk, 1.0), 6),  # 다중 경로 누적 시 1.0 초과 방지
                hop_distance=hop,
                risk_timeline={k: round(v, 6) for k, v in timeline.items()},
                is_origin=(ticker == origin_ticker_up),
            ))

        # 리스크 점수 내림차순 정렬 (원점 항상 첫 번째)
        risk_nodes.sort(
            key=lambda n: (not n.is_origin, -n.risk_score)
        )

        logger.info(
            "risk_propagation_completed",
            origin=origin_ticker_up,
            total_nodes=len(risk_nodes),
            affected=len(risk_nodes) - 1,
            edges=len(edge_records),
        )

        return PropagationResult(
            origin_ticker=origin_ticker_up,
            nodes=risk_nodes,
            edges=edge_records,
            params=params,
        )
