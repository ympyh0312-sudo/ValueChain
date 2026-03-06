"""
app/db/simulation_repository.py
---------------------------------------------------------
시뮬레이션 결과 PostgreSQL CRUD.

PropagationResult를 simulation_runs 테이블에 영속화.

설계:
- save_simulation()   : 결과 저장, 부여된 ID 반환
- get_simulation()    : ID로 전체 결과(result_snapshot 포함) 조회
- list_simulations()  : 목록 조회 (result_snapshot 제외, 페이지네이션 지원)
- delete_simulation() : 단건 삭제

postgres_client.get_session() 은 성공 시 자동 commit,
예외 시 자동 rollback 하므로 명시적 commit 불필요.
"""

from typing import Optional

from sqlalchemy import select, desc

from app.db.postgres_client import postgres_client
from app.models.db_models import SimulationRun
from app.engine.risk_propagator import PropagationResult
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# 저장
# ─────────────────────────────────────────────────────

async def save_simulation(
    result: PropagationResult,
    label: str = "",
) -> int:
    """
    PropagationResult를 simulation_runs 테이블에 저장.

    Args:
        result: 전파 결과 객체
        label:  시나리오 식별 레이블 (예: "TSMC_fullshock_2024Q1")

    Returns:
        저장된 레코드 ID (int)
    """
    params    = result.params
    max_node  = result.max_risk_node

    async with postgres_client.get_session() as session:
        run = SimulationRun(
            origin_ticker    = result.origin_ticker,
            shock_intensity  = params.get("shock_intensity", 1.0),
            decay_lambda     = params.get("decay_lambda",    0.1),
            max_hop          = params.get("max_hop",         5),
            time_horizon     = params.get("time_horizon",    30),
            cutoff_threshold = params.get("cutoff",          0.01),
            scenario_label   = label or "",
            affected_count   = result.affected_count,
            total_nodes      = len(result.nodes),
            total_edges      = len(result.edges),
            max_risk_ticker  = max_node.ticker    if max_node else None,
            max_risk_score   = max_node.risk_score if max_node else None,
            result_snapshot  = result.to_dict(),
        )
        session.add(run)
        await session.flush()   # auto-increment ID 확보
        sim_id = run.id         # flush 후에는 ID 사용 가능
        # get_session() 컨텍스트 종료 시 자동 commit

    logger.info("simulation_saved", sim_id=sim_id, origin=result.origin_ticker, label=label)
    return sim_id


# ─────────────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────────────

async def get_simulation(sim_id: int) -> Optional[dict]:
    """
    ID로 시뮬레이션 전체 결과(result_snapshot 포함) 조회.

    Returns:
        dict 또는 None (존재하지 않을 경우)
    """
    async with postgres_client.get_session() as session:
        run = await session.get(SimulationRun, sim_id)
        if run is None:
            return None
        return _to_full_dict(run)


async def list_simulations(
    origin_ticker: Optional[str] = None,
    label:         Optional[str] = None,
    limit:         int = 20,
    offset:        int = 0,
) -> list[dict]:
    """
    시뮬레이션 목록 조회 (result_snapshot 제외, 최신순).

    Args:
        origin_ticker: 특정 기업만 필터 (None이면 전체)
        label:         특정 레이블만 필터
        limit:         최대 반환 건수 (기본 20)
        offset:        건너뛸 건수 (페이지네이션)

    Returns:
        요약 dict 리스트 (result_snapshot 없음)
    """
    async with postgres_client.get_session() as session:
        stmt = (
            select(SimulationRun)
            .order_by(desc(SimulationRun.created_at))
            .limit(limit)
            .offset(offset)
        )
        if origin_ticker:
            stmt = stmt.where(SimulationRun.origin_ticker == origin_ticker.upper())
        if label:
            stmt = stmt.where(SimulationRun.scenario_label == label)

        rows = (await session.execute(stmt)).scalars().all()
        return [_to_summary(r) for r in rows]


# ─────────────────────────────────────────────────────
# 삭제
# ─────────────────────────────────────────────────────

async def delete_simulation(sim_id: int) -> bool:
    """
    시뮬레이션 레코드 삭제.

    Returns:
        True: 삭제 성공 / False: 레코드 없음
    """
    async with postgres_client.get_session() as session:
        run = await session.get(SimulationRun, sim_id)
        if run is None:
            return False
        await session.delete(run)

    logger.info("simulation_deleted", sim_id=sim_id)
    return True


# ─────────────────────────────────────────────────────
# 내부 직렬화 헬퍼
# ─────────────────────────────────────────────────────

def _to_full_dict(run: SimulationRun) -> dict:
    """result_snapshot 포함 전체 dict."""
    return {
        "id":               run.id,
        "origin_ticker":    run.origin_ticker,
        "shock_intensity":  run.shock_intensity,
        "decay_lambda":     run.decay_lambda,
        "max_hop":          run.max_hop,
        "time_horizon":     run.time_horizon,
        "cutoff_threshold": run.cutoff_threshold,
        "scenario_label":   run.scenario_label,
        "affected_count":   run.affected_count,
        "total_nodes":      run.total_nodes,
        "total_edges":      run.total_edges,
        "max_risk_ticker":  run.max_risk_ticker,
        "max_risk_score":   run.max_risk_score,
        "result_snapshot":  run.result_snapshot,
        "created_at":       run.created_at.isoformat() if run.created_at else None,
        "updated_at":       run.updated_at.isoformat() if run.updated_at else None,
    }


def _to_summary(run: SimulationRun) -> dict:
    """목록용 요약 (result_snapshot 제외)."""
    d = _to_full_dict(run)
    d.pop("result_snapshot", None)
    return d
