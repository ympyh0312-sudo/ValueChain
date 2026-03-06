"""
app/api/v1/risk.py
---------------------------------------------------------
리스크 시뮬레이션 엔드포인트.

엔드포인트:
    POST /risk/analyze                    - 단일 기업 리스크 전파 시뮬레이션
    POST /risk/scenario/multi-shock       - 복수 충격원 시뮬레이션
    POST /risk/scenario/sensitivity       - 파라미터 민감도 스윕
    GET  /risk/simulations/{id}           - 저장된 시뮬레이션 결과 조회
    GET  /risk/simulations                - 시뮬레이션 목록
    DELETE /risk/simulations/{id}         - 시뮬레이션 삭제

설계:
- save_result=True이면 PostgreSQL simulation_runs에 결과 저장
- 전파 결과(nodes/edges)는 dict 직렬화하여 반환 (RiskNode 그대로 사용)
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.logging import get_logger
from app.core.config import get_settings
from app.db import simulation_repository
from app.engine.risk_propagator import RiskPropagationEngine
from app.engine.scenario_analysis import (
    MultiShockAnalyzer,
    SensitivityAnalyzer,
    SystemicRiskScorer,
)
from app.api.v1.schemas import (
    RiskAnalysisRequest,
    RiskAnalysisResponse,
    MultiShockRequest,
    SensitivitySweepRequest,
    SweepPointResponse,
)

logger   = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/risk", tags=["Risk"])


# ─────────────────────────────────────────────────────
# POST /risk/analyze
# ─────────────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=RiskAnalysisResponse,
    summary="리스크 전파 시뮬레이션",
    description=(
        "특정 기업에 충격을 가했을 때 공급망 전체로 리스크가 어떻게 전파되는지 BFS로 시뮬레이션합니다. "
        "`save_result=true`이면 결과를 PostgreSQL에 저장하고 `simulation_id`를 반환합니다."
    ),
)
async def analyze_risk(body: RiskAnalysisRequest) -> RiskAnalysisResponse:
    engine = RiskPropagationEngine()

    try:
        result = await engine.propagate(
            body.ticker,
            shock_intensity = body.shock_intensity,
            decay_lambda    = body.decay_lambda,
            max_hop         = body.max_hop,
            time_horizon    = body.time_horizon,
            cutoff          = body.cutoff,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("risk_analyze_failed", ticker=body.ticker, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"시뮬레이션 오류: {e}",
        )

    sim_id: Optional[int] = None
    if body.save_result:
        try:
            sim_id = await simulation_repository.save_simulation(result, label=body.label)
        except Exception as e:
            logger.error("risk_save_failed", error=str(e))
            # 저장 실패해도 결과 반환은 유지

    max_node = result.max_risk_node
    nodes_dicts = [n.model_dump() for n in result.nodes]
    edges_dicts = [e.model_dump() for e in result.edges]

    return RiskAnalysisResponse(
        origin_ticker   = result.origin_ticker,
        params          = result.params,
        affected_count  = result.affected_count,
        max_risk_ticker = max_node.ticker     if max_node else None,
        max_risk_score  = max_node.risk_score if max_node else 0.0,
        nodes           = nodes_dicts,
        edges           = edges_dicts,
        simulation_id   = sim_id,
    )


# ─────────────────────────────────────────────────────
# POST /risk/scenario/multi-shock
# ─────────────────────────────────────────────────────

@router.post(
    "/scenario/multi-shock",
    summary="복수 충격원 시뮬레이션",
    description=(
        "여러 기업에 동시에 충격을 가했을 때의 합산 리스크를 시뮬레이션합니다. "
        "각 충격원의 결과를 독립 실행 후 병합하며, 각 기업별 개별 결과도 반환합니다."
    ),
)
async def multi_shock(body: MultiShockRequest) -> dict:
    analyzer = MultiShockAnalyzer()
    origins = [(o.ticker, o.shock_intensity) for o in body.origins]

    try:
        result = await analyzer.run_combined(
            origins,
            decay_lambda = body.decay_lambda,
            max_hop      = body.max_hop,
            time_horizon = body.time_horizon,
        )
    except Exception as e:
        logger.error("multi_shock_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"다중 충격 시뮬레이션 오류: {e}",
        )

    return {
        "shock_origins":   [{"ticker": t, "shock_intensity": i} for t, i in result.shock_origins],
        "affected_count":  result.affected_count,
        "total_system_risk": result.total_system_risk,
        "combined_nodes":  [n.model_dump() for n in result.combined_nodes],
        "combined_edges":  [e.model_dump() for e in result.combined_edges],
        "per_origin": {
            ticker: {
                "affected_count":  r.affected_count,
                "max_risk_ticker": r.max_risk_node.ticker if r.max_risk_node else None,
                "max_risk_score":  r.max_risk_node.risk_score if r.max_risk_node else 0.0,
            }
            for ticker, r in result.per_origin.items()
        },
    }


# ─────────────────────────────────────────────────────
# POST /risk/scenario/sensitivity
# ─────────────────────────────────────────────────────

@router.post(
    "/scenario/sensitivity",
    response_model=list[SweepPointResponse],
    summary="파라미터 민감도 스윕",
    description=(
        "`sweep_type`으로 지정한 파라미터를 `values` 목록으로 순차 스윕하여 "
        "각 값에서의 전파 결과를 반환합니다. "
        "`sweep_type`: 'shock_intensity' 또는 'decay_lambda'"
    ),
)
async def sensitivity_sweep(body: SensitivitySweepRequest) -> list[SweepPointResponse]:
    analyzer = SensitivityAnalyzer()

    try:
        if body.sweep_type == "shock_intensity":
            sweep_results = await analyzer.sweep_shock_intensity(
                body.ticker,
                intensities  = body.values,
                decay_lambda = body.decay_lambda,
                max_hop      = body.max_hop,
                time_horizon = body.time_horizon,
            )
        elif body.sweep_type == "decay_lambda":
            sweep_results = await analyzer.sweep_decay_lambda(
                body.ticker,
                lambdas         = body.values,
                shock_intensity = body.shock_intensity,
                max_hop         = body.max_hop,
                time_horizon    = body.time_horizon,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="sweep_type은 'shock_intensity' 또는 'decay_lambda' 이어야 합니다.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("sensitivity_sweep_failed", ticker=body.ticker, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"민감도 스윕 오류: {e}",
        )

    return [
        SweepPointResponse(
            param_name     = r.param_name,
            param_value    = r.param_value,
            affected_count = r.affected_count,
            max_risk_score = r.max_risk_score,
            total_risk     = r.total_risk,
        )
        for r in sweep_results
    ]


# ─────────────────────────────────────────────────────
# GET /risk/simulations
# ─────────────────────────────────────────────────────

@router.get(
    "/simulations",
    summary="시뮬레이션 목록 조회",
    description="저장된 시뮬레이션 결과 목록을 반환합니다. 필터 및 페이지네이션 지원.",
)
async def list_simulations(
    origin_ticker: Optional[str] = Query(None, description="기업 티커로 필터"),
    label:         Optional[str] = Query(None, description="시나리오 레이블로 필터"),
    limit:         int           = Query(20, ge=1, le=100, description="최대 반환 건수"),
    offset:        int           = Query(0,  ge=0,         description="건너뛸 건수"),
) -> list[dict]:
    return await simulation_repository.list_simulations(
        origin_ticker=origin_ticker,
        label=label,
        limit=limit,
        offset=offset,
    )


# ─────────────────────────────────────────────────────
# GET /risk/simulations/{sim_id}
# ─────────────────────────────────────────────────────

@router.get(
    "/simulations/{sim_id}",
    summary="시뮬레이션 결과 단건 조회",
    description="저장된 시뮬레이션 전체 결과(result_snapshot 포함)를 반환합니다.",
)
async def get_simulation(sim_id: int) -> dict:
    result = await simulation_repository.get_simulation(sim_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"simulation_id={sim_id} 를 찾을 수 없습니다.",
        )
    return result


# ─────────────────────────────────────────────────────
# DELETE /risk/simulations/{sim_id}
# ─────────────────────────────────────────────────────

@router.delete(
    "/simulations/{sim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="시뮬레이션 삭제",
)
async def delete_simulation(sim_id: int) -> None:
    deleted = await simulation_repository.delete_simulation(sim_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"simulation_id={sim_id} 를 찾을 수 없습니다.",
        )
