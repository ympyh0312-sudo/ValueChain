"use client";

import { Network, AlertCircle } from "lucide-react";
import type { GraphData } from "@/lib/types";

interface GraphCanvasProps {
  graphData:      GraphData | null;
  hasData:        boolean;
  isLoading:      boolean;
  ticker:         string;
  selectedTicker: string | null;
  onNodeClick:    (ticker: string | null) => void;
}

/**
 * Phase 2~3: 플레이스홀더 캔버스.
 * Phase 4에서 react-force-graph-2d로 교체 예정.
 * graphData, selectedTicker, onNodeClick props는 Phase 4에서 사용.
 */
export default function GraphCanvas({
  graphData,
  hasData,
  isLoading,
  ticker,
}: GraphCanvasProps) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center relative">
      {/* 배경 격자 */}
      <div
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage: "radial-gradient(circle, #CDD1D5 1px, transparent 1px)",
          backgroundSize:  "28px 28px",
        }}
      />

      {isLoading ? (
        <div className="relative flex flex-col items-center gap-4">
          <div className="w-16 h-16 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
          <div className="text-center">
            <p className="text-sm font-semibold text-text-primary">{ticker} 리스크 계산 중</p>
            <p className="text-xs text-text-secondary mt-1">공급망 그래프를 분석하고 있습니다...</p>
          </div>
        </div>
      ) : hasData && graphData ? (
        /* 데이터 있음: 노드/엣지 수 미리보기 */
        <div className="relative flex flex-col items-center gap-3">
          <div className="w-16 h-16 bg-primary-light rounded-full flex items-center justify-center">
            <Network size={28} className="text-primary" />
          </div>
          <p className="text-sm font-semibold text-text-primary">그래프 데이터 로드됨</p>
          <div className="flex gap-4 text-xs text-text-secondary">
            <span>노드 <strong className="text-text-primary">{graphData.nodes.length}개</strong></span>
            <span>엣지 <strong className="text-text-primary">{graphData.links.length}개</strong></span>
          </div>
          <p className="text-xs text-text-tertiary mt-1">Phase 4에서 인터랙티브 그래프로 교체됩니다</p>
        </div>
      ) : (
        /* 초기 상태 */
        <div className="relative flex flex-col items-center gap-4 max-w-xs text-center">
          <div className="w-20 h-20 bg-white rounded-2xl shadow-card flex items-center justify-center">
            <Network size={36} className="text-text-tertiary" />
          </div>
          <div>
            <p className="text-base font-bold text-text-primary">공급망 리스크 시뮬레이터</p>
            <p className="text-sm text-text-secondary mt-2 leading-relaxed">
              왼쪽에서 기업 티커와 파라미터를 설정한 후<br />
              <strong className="text-primary">시뮬레이션 실행</strong> 버튼을 누르세요
            </p>
          </div>
          <div className="w-full grid grid-cols-3 gap-2 mt-2">
            {[
              { step: "1", label: "기업 선택" },
              { step: "2", label: "파라미터 조정" },
              { step: "3", label: "결과 확인" },
            ].map(({ step, label }) => (
              <div key={step} className="bg-white rounded-lg shadow-card p-2.5 text-center">
                <div className="w-6 h-6 bg-primary-light rounded-full flex items-center justify-center mx-auto mb-1">
                  <span className="text-[11px] font-bold text-primary">{step}</span>
                </div>
                <p className="text-[11px] text-text-secondary">{label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="absolute bottom-4 right-4 flex items-center gap-1 text-[11px] text-text-tertiary">
        <AlertCircle size={11} />
        <span>Force-Directed Graph (Phase 4 구현 예정)</span>
      </div>
    </div>
  );
}
