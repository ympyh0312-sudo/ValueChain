"""
app/engine
---------------------------------------------------------
리스크 전파 엔진 패키지.

Public API:
    RiskPropagationEngine  - BFS 기반 핵심 전파 엔진 (Phase 3)
    PropagationResult      - 전파 결과 컨테이너 (Phase 3)
    ShockSimulator         - 시나리오 시뮬레이터 (Phase 3)
    ScenarioConfig         - 시나리오 설정 (Phase 3)
    SectorExposure         - 섹터별 노출 집계 결과 (Phase 3)
    MultiShockAnalyzer     - 복수 충격원 동시 시뮬레이션 (Phase 4)
    MultiShockResult       - 복수 충격 결과 컨테이너 (Phase 4)
    SensitivityAnalyzer    - 파라미터 민감도 스윕 (Phase 4)
    SweepPoint             - 스윕 단일 데이터 포인트 (Phase 4)
    SystemicRiskScorer     - 시스템 리스크 중요도 계산 (Phase 4)
    SystemicRiskScore      - 기업별 시스템 리스크 점수 (Phase 4)
"""

from app.engine.risk_propagator import RiskPropagationEngine, PropagationResult
from app.engine.shock_simulator import ShockSimulator, ScenarioConfig, SectorExposure
from app.engine.scenario_analysis import (
    MultiShockAnalyzer,
    MultiShockResult,
    SensitivityAnalyzer,
    SweepPoint,
    SystemicRiskScorer,
    SystemicRiskScore,
)

__all__ = [
    # Phase 3
    "RiskPropagationEngine",
    "PropagationResult",
    "ShockSimulator",
    "ScenarioConfig",
    "SectorExposure",
    # Phase 4
    "MultiShockAnalyzer",
    "MultiShockResult",
    "SensitivityAnalyzer",
    "SweepPoint",
    "SystemicRiskScorer",
    "SystemicRiskScore",
]
