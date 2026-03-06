// ─────────────────────────────────────────────────────────
// stores/useSimulationStore.ts  ─ Zustand 전역 상태 관리
//
// 이 스토어 하나에서 대시보드 전체 상태를 관리.
//
// 상태 흐름:
//   사용자 입력 → params 업데이트
//   Run 버튼 클릭 → runSimulation() 호출
//   API 응답 → result, graphData 저장
//   컴포넌트들 → 스토어 구독하여 자동 업데이트
// ─────────────────────────────────────────────────────────

import { create } from "zustand";
import { analyzeRisk, checkHealth, ApiError } from "@/lib/api";
import { parseSimResultToGraph, aggregateBySector, aggregateTimeline } from "@/lib/parsers";
import { DEFAULT_PARAMS as DEFAULTS } from "@/lib/types";
import type { SimParams, SimResult, GraphData, ApiStatus } from "@/lib/types";

// ── 스토어 타입 ─────────────────────────────────────────

interface SimulationState {
  // ── 상태 ───────────────────────────────────────────
  params:          SimParams;
  result:          SimResult | null;
  graphData:       GraphData | null;
  sectorData:      Array<{ sector: string; avgRisk: number; count: number }>;
  timelineData:    Array<{ day: number; totalRisk: number; avgRisk: number }>;
  selectedTicker:  string | null;   // 그래프 노드 클릭 시
  isLoading:       boolean;
  error:           string | null;
  apiStatus:       ApiStatus;

  // ── 파라미터 액션 ──────────────────────────────────
  setParams:          (params: Partial<SimParams>) => void;
  setSelectedTicker:  (ticker: string | null) => void;
  resetResult:        () => void;

  // ── 비동기 액션 ────────────────────────────────────
  runSimulation:      () => Promise<void>;
  checkApiHealth:     () => Promise<void>;
}

// ── 스토어 생성 ─────────────────────────────────────────

export const useSimulationStore = create<SimulationState>((set, get) => ({
  // ── 초기값 ─────────────────────────────────────────
  params:         DEFAULTS,
  result:         null,
  graphData:      null,
  sectorData:     [],
  timelineData:   [],
  selectedTicker: null,
  isLoading:      false,
  error:          null,
  apiStatus:      "loading",

  // ── 파라미터 액션 ──────────────────────────────────

  /** 파라미터 부분 업데이트 (Partial 허용) */
  setParams: (partial) =>
    set((state) => ({ params: { ...state.params, ...partial } })),

  /** 그래프 노드 선택/해제 */
  setSelectedTicker: (ticker) => set({ selectedTicker: ticker }),

  /** 시뮬레이션 결과 초기화 */
  resetResult: () =>
    set({
      result:         null,
      graphData:      null,
      sectorData:     [],
      timelineData:   [],
      selectedTicker: null,
      error:          null,
    }),

  // ── 시뮬레이션 실행 ────────────────────────────────

  runSimulation: async () => {
    const { params } = get();
    if (!params.ticker.trim()) return;

    set({ isLoading: true, error: null });

    try {
      const result = await analyzeRisk(params);

      // 파싱: 그래프 / 섹터 집계 / 타임라인
      const graphData    = parseSimResultToGraph(result);
      const sectorData   = aggregateBySector(result);
      const timelineData = aggregateTimeline(result);

      set({
        result,
        graphData,
        sectorData,
        timelineData,
        isLoading:      false,
        selectedTicker: null,
      });
    } catch (e) {
      const message =
        e instanceof ApiError
          ? e.message
          : "서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.";

      set({ isLoading: false, error: message });
    }
  },

  // ── API 헬스체크 ───────────────────────────────────

  checkApiHealth: async () => {
    try {
      const health = await checkHealth();
      set({ apiStatus: health.status === "healthy" ? "healthy" : "degraded" });
    } catch {
      set({ apiStatus: "degraded" });
    }
  },
}));

// ── 셀렉터 (성능 최적화용) ──────────────────────────────
// 컴포넌트에서 필요한 상태만 구독하면 불필요한 리렌더 방지

export const selectParams         = (s: SimulationState) => s.params;
export const selectResult         = (s: SimulationState) => s.result;
export const selectGraphData      = (s: SimulationState) => s.graphData;
export const selectSectorData     = (s: SimulationState) => s.sectorData;
export const selectTimelineData   = (s: SimulationState) => s.timelineData;
export const selectSelectedTicker = (s: SimulationState) => s.selectedTicker;
export const selectIsLoading      = (s: SimulationState) => s.isLoading;
export const selectError          = (s: SimulationState) => s.error;
export const selectApiStatus      = (s: SimulationState) => s.apiStatus;
