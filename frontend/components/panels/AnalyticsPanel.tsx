"use client";

import { useState } from "react";
import { AlertTriangle, BarChart2, Info, ChevronDown, ChevronUp, HelpCircle } from "lucide-react";
import { getRiskColor, getRiskBgColor, getRiskLabelKr, toPercent } from "@/lib/utils";
import type { RiskNode, RiskEdge, SimParams } from "@/lib/types";
import TimelineChart from "@/components/panels/TimelineChart";

interface AnalyticsPanelProps {
  nodes:           RiskNode[];
  edges:           RiskEdge[];
  sectorData:      Array<{ sector: string; avgRisk: number; count: number }>;
  originTicker:    string;
  isLoading:       boolean;
  selectedTicker:  string | null;
  onSelectTicker:  (ticker: string | null) => void;
  timeHorizon:     number;
  simParams:       SimParams | null;
  playbackDay?:    number;
}

// 노드 속성으로 주요 리스크 요인 한 줄 추출
function getRiskFactor(node: RiskNode, edges: RiskEdge[]): string {
  const edge = edges.find((e) => e.target_ticker === node.ticker);
  if (edge?.dependency_score >= 0.8) return "단일 공급처 의존도 극도로 높음";
  if (edge?.dependency_score >= 0.6) return "핵심 공급사 대체 어려움";
  if (node.hop_distance === 1 && node.risk_score >= 0.5) return "직접 공급망 충격 전파";
  if (node.sector === "Semiconductors" || node.sector === "Technology")
    return "반도체·테크 공급망 병목 노출";
  if (node.sector === "Energy" || node.sector === "Oil & Gas")
    return "에너지 원자재 가격 연동 리스크";
  if (node.country && !["USA","South Korea","Japan","Germany","Netherlands"].includes(node.country))
    return "지정학적 불안정 국가 노출";
  if (edge?.sector_sensitivity >= 1.2) return `고민감 섹터 (${edge.sector_sensitivity.toFixed(2)}× 증폭)`;
  return `${node.hop_distance}단계 간접 전파 경로`;
}

// 섹터별 민감도 계수 (백엔드 risk_propagator.py 와 동일)
const SECTOR_SENSITIVITY: Record<string, number> = {
  "Semiconductors":    1.30,
  "Technology":        1.20,
  "Automotive":        1.15,
  "Energy":            1.10,
  "Pharmaceuticals":   1.05,
  "Financial":         1.00,
  "Consumer":          0.95,
  "Industrial":        1.05,
  "Unknown":           1.00,
};

export default function AnalyticsPanel({
  nodes,
  edges,
  sectorData,
  originTicker,
  isLoading,
  selectedTicker,
  onSelectTicker,
  timeHorizon,
  simParams,
  playbackDay = 0,
}: AnalyticsPanelProps) {
  const [formulaOpen, setFormulaOpen]   = useState(false);
  const [gaugeHover, setGaugeHover]     = useState(false);

  const topNodes = [...nodes]
    .filter((n) => !n.is_origin)
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 5);

  const systemRisk =
    nodes.length > 0
      ? nodes.reduce((s, n) => s + n.risk_score, 0) / nodes.length
      : 0;

  const isEmpty = nodes.length === 0;
  const selectedNode = selectedTicker
    ? nodes.find((n) => n.ticker === selectedTicker)
    : null;

  // 선택된 노드로 들어오는 엣지 (직접 공급사 관계)
  const incomingEdge = selectedNode
    ? edges.find((e) => e.target_ticker === selectedNode.ticker)
    : null;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-4 border-b border-border">
        <p className="text-sm font-bold text-text-primary">Risk Intelligence</p>
        <p className="text-xs text-text-secondary mt-0.5">
          {originTicker ? `${originTicker} 충격 분석 결과` : "시뮬레이션 결과가 여기 표시됩니다"}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">

        {/* ── 선택된 노드 상세 ── */}
        {selectedNode && (
          <div>
            <p className="section-title">선택된 기업 상세</p>
            <div className="card border-l-4" style={{ borderLeftColor: getRiskColor(selectedNode.risk_score) }}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-bold text-text-primary">{selectedNode.ticker}</p>
                  <p className="text-xs text-text-secondary">{selectedNode.sector}</p>
                  <p className="text-xs text-text-tertiary mt-0.5">{selectedNode.country}</p>
                </div>
                <div
                  className="text-right px-2 py-1 rounded-badge"
                  style={{ backgroundColor: getRiskBgColor(selectedNode.risk_score), color: getRiskColor(selectedNode.risk_score) }}
                >
                  <p className="text-sm font-bold">{toPercent(selectedNode.risk_score)}</p>
                  <p className="text-[10px]">{getRiskLabelKr(selectedNode.risk_score)}</p>
                </div>
              </div>

              {/* 전파 경로 설명 */}
              <div className="mt-2 pt-2 border-t border-border space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-text-tertiary">공급망 거리</span>
                  <span className="font-semibold text-text-primary">
                    {selectedNode.hop_distance}홉 —{" "}
                    {selectedNode.hop_distance === 1
                      ? "직접 공급사·구매사"
                      : selectedNode.hop_distance === 2
                      ? "2차 간접 관계사"
                      : `${selectedNode.hop_distance}단계 간접 영향`}
                  </span>
                </div>
                {incomingEdge && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">공급 의존도</span>
                      <span className="font-semibold text-primary">
                        {toPercent(incomingEdge.dependency_score)}
                        <span className="text-text-tertiary font-normal"> (교체 난이도)</span>
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">전달된 리스크</span>
                      <span className="font-semibold" style={{ color: getRiskColor(incomingEdge.transmitted_risk) }}>
                        {toPercent(incomingEdge.transmitted_risk)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">섹터 민감도</span>
                      <span className="font-semibold text-text-primary">
                        {incomingEdge.sector_sensitivity.toFixed(2)}×
                      </span>
                    </div>
                  </>
                )}
                {/* 홉 거리 의미 설명 */}
                <p className="text-[10px] text-text-tertiary bg-bg-subtle rounded px-2 py-1.5 leading-relaxed mt-1">
                  {selectedNode.hop_distance === 1
                    ? "원점 기업과 직접 SUPPLY_TO 관계. 충격이 거의 감쇠 없이 전달됩니다."
                    : selectedNode.hop_distance === 2
                    ? "공급사의 공급사. 1차 전파 이후 한 번 더 의존도·유동성으로 감쇠된 리스크를 받습니다."
                    : `${selectedNode.hop_distance}단계를 거쳐 전달되어 매 단계마다 리스크가 감쇠됩니다.`}
                </p>
              </div>
              <button onClick={() => onSelectTicker(null)} className="mt-2 text-[11px] text-text-tertiary hover:text-text-secondary">
                선택 해제 ×
              </button>
            </div>
          </div>
        )}

        {/* ── 시스템 리스크 게이지 ── */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <p className="section-title mb-0">시스템 리스크 지수</p>
            <span className="text-[9px] text-text-tertiary">(영향받은 전체 기업 평균)</span>
          </div>
          <div
            className="card relative"
            onMouseEnter={() => setGaugeHover(true)}
            onMouseLeave={() => setGaugeHover(false)}
          >
            {isEmpty || isLoading ? (
              <div className="h-24 flex items-center justify-center">
                <span className="text-xs text-text-tertiary">{isLoading ? "계산 중..." : "데이터 없음"}</span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-2">
                <div className="relative">
                  <GaugeChart value={systemRisk} />
                  {/* 공식 힌트 아이콘 */}
                  <div className="absolute -top-1 -right-1">
                    <HelpCircle size={12} className="text-text-tertiary" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold" style={{ color: getRiskColor(systemRisk) }}>
                    {toPercent(systemRisk)}
                  </p>
                  <p className="text-xs text-text-secondary mt-0.5">
                    {getRiskLabelKr(systemRisk)} 수준 · <span className="font-medium">{nodes.length}개 기업 영향</span>
                  </p>
                </div>
              </div>
            )}
            {/* 공식 호버 팝업 */}
            {gaugeHover && !isEmpty && !isLoading && (
              <div className="absolute inset-x-0 top-full mt-1 z-50
                              bg-gray-900/95 text-white rounded-xl px-3 py-3 shadow-xl
                              border border-white/10 backdrop-blur-sm">
                <p className="text-[10px] font-bold text-blue-300 mb-1.5">계산 공식</p>
                <div className="bg-white/10 rounded-lg px-2 py-2 font-mono text-[9px] text-green-300 leading-relaxed mb-2">
                  R_dest = shock × dep × σ × (1-liq) × e^(-λt)
                </div>
                <div className="space-y-1 text-[9px] text-white/70">
                  {[
                    ["shock",    "충격 강도 (0~1)"],
                    ["dep",      "공급 의존도 (교체 불가능성)"],
                    ["σ",        "섹터 민감도 계수 (반도체 1.3×)"],
                    ["(1-liq)",  "충격 흡수력 역수 (유동성 낮을수록↑)"],
                    ["e^(-λt)",  `시간 감쇠 (λ=${simParams?.decayLambda?.toFixed(2) ?? "0.10"})`],
                  ].map(([term, desc]) => (
                    <div key={term} className="flex gap-1.5">
                      <span className="font-mono font-bold text-green-300 w-12 shrink-0">{term}</span>
                      <span>{desc}</span>
                    </div>
                  ))}
                </div>
                {simParams && (
                  <p className="text-[9px] text-white/50 mt-2 border-t border-white/10 pt-1.5">
                    현재: shock={simParams.shockIntensity.toFixed(2)} · λ={simParams.decayLambda.toFixed(2)} · 최대 {simParams.maxHop}홉
                  </p>
                )}
              </div>
            )}
          </div>

          {/* 리스크 수준 해석 가이드 */}
          {!isEmpty && !isLoading && (
            <div className="mt-2 grid grid-cols-3 gap-1 text-center">
              {[
                { color: "#EF4444", range: "≥30%", label: "즉각 대응" },
                { color: "#F59E0B", range: "10~30%", label: "모니터링" },
                { color: "#10B981", range: "<10%", label: "안전" },
              ].map(({ color, range, label }) => (
                <div key={range} className="bg-white border border-border rounded px-1.5 py-1">
                  <div className="w-2 h-2 rounded-full mx-auto mb-0.5" style={{ backgroundColor: color }} />
                  <p className="text-[9px] font-bold text-text-primary">{range}</p>
                  <p className="text-[9px] text-text-tertiary">{label}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 리스크 계산 원리 (접기/펼치기) ── */}
        {!isEmpty && !isLoading && (
          <div>
            <button
              type="button"
              onClick={() => setFormulaOpen(!formulaOpen)}
              className="w-full flex items-center justify-between px-3 py-2 bg-blue-50
                         border border-blue-200 rounded-lg text-[11px] text-blue-700 font-semibold"
            >
              <span className="flex items-center gap-1.5">
                <Info size={11} />
                리스크는 어떻게 계산되나요?
              </span>
              {formulaOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
            {formulaOpen && (
              <div className="mt-1 bg-blue-50 border border-blue-200 rounded-lg px-3 py-3 space-y-2.5">
                {/* 전파 공식 */}
                <div>
                  <p className="text-[10px] font-bold text-blue-800 mb-1">전파 공식</p>
                  <div className="bg-white/80 rounded px-2 py-1.5 font-mono text-[9px] text-blue-700 leading-relaxed">
                    R(홉n) = 충격강도 × 의존도 × 섹터민감도<br />
                    {"          "}× (1 - 유동성) × e^(-λ × t)
                  </div>
                  {simParams && (
                    <p className="text-[9px] text-blue-600 mt-1">
                      현재: 충격강도 <strong>{simParams.shockIntensity.toFixed(2)}</strong>,
                      λ = <strong>{simParams.decayLambda.toFixed(2)}</strong>,
                      최대 <strong>{simParams.maxHop}</strong>홉
                    </p>
                  )}
                </div>
                {/* 각 변수 설명 */}
                <div className="space-y-1">
                  {[
                    { term: "의존도", desc: "공급사 교체 불가능성. 1.0=대체 불가, 0.3=쉽게 교체" },
                    { term: "섹터민감도", desc: "반도체 1.3× · 테크 1.2× · 자동차 1.15× · 에너지 1.1×" },
                    { term: "유동성", desc: "기업의 충격 흡수력. 높을수록 최종 리스크가 감소" },
                    { term: "e^(-λt)", desc: `시간 감쇠. λ=${simParams?.decayLambda.toFixed(2) ?? "0.10"}이면 ${Math.round(Math.log(2) / (simParams?.decayLambda ?? 0.1))}일 후 리스크가 절반으로 감소` },
                  ].map(({ term, desc }) => (
                    <div key={term} className="flex gap-1.5">
                      <span className="text-[9px] font-bold text-blue-700 shrink-0 w-14">{term}</span>
                      <span className="text-[9px] text-blue-600 leading-relaxed">{desc}</span>
                    </div>
                  ))}
                </div>
                {/* 홉별 감쇠 예시 */}
                <div>
                  <p className="text-[10px] font-bold text-blue-800 mb-1">홉별 감쇠 예시 (의존도 0.7, 유동성 0.6 가정)</p>
                  <div className="space-y-0.5">
                    {[1, 2, 3, 4].map((hop) => {
                      const factor = Math.pow(0.7 * (1 - 0.6), hop);
                      const shock = simParams?.shockIntensity ?? 1.0;
                      return (
                        <div key={hop} className="flex items-center gap-1.5">
                          <span className="text-[9px] font-mono font-bold text-blue-700 w-8">{hop}홉</span>
                          <div className="flex-1 h-1.5 bg-blue-100 rounded-pill overflow-hidden">
                            <div
                              className="h-full rounded-pill bg-blue-400"
                              style={{ width: `${Math.min(factor * shock * 100, 100)}%` }}
                            />
                          </div>
                          <span className="text-[9px] text-blue-600 w-10 text-right">
                            ≈{(factor * shock * 100).toFixed(0)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Top 5 취약 기업 ── */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle size={13} className="text-risk-high" />
            <p className="section-title mb-0">가장 위험한 기업 Top 5</p>
          </div>
          <p className="text-[10px] text-text-tertiary mb-2 leading-relaxed">
            공급망을 통해 전달받은 최종 리스크 점수(risk_score) 기준.
            홉 거리가 가깝고 의존도가 높을수록 상위권에 올라갑니다.
          </p>
          {isEmpty || isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="card animate-pulse h-14 bg-bg-subtle" />)}
            </div>
          ) : topNodes.length === 0 ? (
            <div className="card text-center py-6">
              <p className="text-xs text-text-tertiary">전파된 기업 없음</p>
            </div>
          ) : (
            <div className="space-y-2">
              {topNodes.map((node, idx) => {
                // 이 노드로 들어오는 엣지 찾기
                const edge = edges.find((e) => e.target_ticker === node.ticker);
                return (
                  <button
                    key={node.ticker}
                    onClick={() => onSelectTicker(selectedTicker === node.ticker ? null : node.ticker)}
                    className={`card w-full flex items-center gap-3 py-2.5 text-left transition-all cursor-pointer hover:shadow-panel ${selectedTicker === node.ticker ? "ring-2 ring-primary/30" : ""}`}
                  >
                    <div
                      className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0"
                      style={{ backgroundColor: getRiskColor(node.risk_score) }}
                    >
                      {idx + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-bold text-text-primary">{node.ticker}</span>
                        <span className="text-[10px] text-text-tertiary bg-bg-subtle px-1.5 py-0.5 rounded">
                          {node.hop_distance}홉
                        </span>
                      </div>
                      <p className="text-[10px] text-text-secondary truncate">{node.sector}</p>
                      {/* 주요 리스크 요인 한 줄 요약 */}
                      <p className="text-[9px] font-medium mt-0.5 truncate"
                         style={{ color: getRiskColor(node.risk_score) }}>
                        ⚠ {getRiskFactor(node, edges)}
                      </p>
                      {edge && (
                        <p className="text-[9px] text-text-tertiary">
                          의존도 {toPercent(edge.dependency_score)} · 섹터 {edge.sector_sensitivity.toFixed(2)}×
                        </p>
                      )}
                    </div>
                    <div
                      className="text-right shrink-0 px-2 py-1 rounded-badge"
                      style={{ backgroundColor: getRiskBgColor(node.risk_score), color: getRiskColor(node.risk_score) }}
                    >
                      <p className="text-sm font-bold">{toPercent(node.risk_score)}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* ── 섹터별 Bar Chart ── */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <BarChart2 size={13} className="text-primary" />
            <p className="section-title mb-0">섹터별 평균 리스크</p>
          </div>
          <p className="text-[10px] text-text-tertiary mb-2 leading-relaxed">
            해당 섹터에 속한 기업들의 리스크 평균.
            반도체·테크 섹터는 민감도 계수(1.3×)가 높아 더 빠르게 상승합니다.
          </p>
          {isEmpty || isLoading ? (
            <div className="card space-y-3 py-3">
              {[80, 60, 45, 30].map((w) => (
                <div key={w} className="animate-pulse">
                  <div className="h-3 bg-bg-subtle rounded mb-1" style={{ width: `${w * 0.4}%` }} />
                  <div className="h-2 bg-bg-subtle rounded" style={{ width: `${w}%` }} />
                </div>
              ))}
            </div>
          ) : sectorData.length === 0 ? (
            <div className="card text-center py-6">
              <p className="text-xs text-text-tertiary">섹터 데이터 없음</p>
            </div>
          ) : (
            <div className="card space-y-3">
              {sectorData.map(({ sector, avgRisk, count }) => {
                const sensitivity = SECTOR_SENSITIVITY[sector] ?? 1.0;
                return (
                  <div key={sector}>
                    <div className="flex justify-between items-center mb-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] text-text-secondary truncate max-w-[120px]">
                          {sector}
                        </span>
                        <span className="text-[9px] text-text-tertiary bg-bg-subtle px-1 rounded">
                          {count}개 · σ{sensitivity.toFixed(2)}
                        </span>
                      </div>
                      <span className="text-[11px] font-bold" style={{ color: getRiskColor(avgRisk) }}>
                        {toPercent(avgRisk)}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-bg-subtle rounded-pill overflow-hidden">
                      <div
                        className="h-full rounded-pill transition-all duration-700"
                        style={{ width: toPercent(avgRisk), backgroundColor: getRiskColor(avgRisk) }}
                      />
                    </div>
                  </div>
                );
              })}
              <p className="text-[9px] text-text-tertiary border-t border-border pt-2">
                σ = 섹터 민감도 계수. 리스크 전파 시 이 배수로 증폭됩니다.
              </p>
            </div>
          )}
        </div>

        {/* ── 리스크 타임라인 차트 ── */}
        {!isEmpty && !isLoading && (
          <div>
            <TimelineChart
              nodes={nodes}
              selectedTicker={selectedTicker}
              timeHorizon={timeHorizon}
              playbackDay={playbackDay}
            />
            {playbackDay > 0 && (
              <p className="text-[10px] text-primary font-medium text-center mt-1">
                현재 미리보기: {playbackDay}일 후 (▶ 재생 중)
              </p>
            )}
          </div>
        )}

        {/* ── 요약 통계 ── */}
        {!isEmpty && !isLoading && (
          <div>
            <p className="section-title">요약 통계</p>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "영향받은 기업",  value: `${nodes.filter((n) => !n.is_origin).length}개` },
                { label: "최대 홉 거리",   value: `${Math.max(...nodes.map((n) => n.hop_distance))} hop` },
                { label: "최고 리스크",    value: toPercent(Math.max(...nodes.map((n) => n.risk_score))) },
                { label: "시스템 평균",    value: toPercent(systemRisk) },
              ].map(({ label, value }) => (
                <div key={label} className="card text-center py-3">
                  <p className="text-lg font-bold text-text-primary">{value}</p>
                  <p className="text-[10px] text-text-tertiary mt-0.5">{label}</p>
                </div>
              ))}
            </div>
            {/* 그래프 읽는 법 */}
            <div className="mt-2 bg-bg-subtle rounded-lg px-3 py-2.5 space-y-1">
              <p className="text-[10px] font-bold text-text-secondary">그래프 읽는 법</p>
              <div className="space-y-0.5">
                {[
                  { icon: "●", color: "#3182F6", text: "파란 원 = 충격 원점 (100% 리스크 시작점)" },
                  { icon: "●", color: "#EF4444", text: "빨간 원 = ≥30% 고위험 기업" },
                  { icon: "●", color: "#F59E0B", text: "주황 원 = 10~30% 주의 기업" },
                  { icon: "→", color: "#EF4444", text: "굵은 선 = 의존도가 높은 공급 관계" },
                  { icon: "·", color: "#6B7684", text: "파티클 = 리스크 전파 방향과 강도" },
                ].map(({ icon, color, text }) => (
                  <div key={text} className="flex items-start gap-1.5">
                    <span className="text-[10px] font-bold shrink-0 w-3" style={{ color }}>{icon}</span>
                    <span className="text-[10px] text-text-tertiary leading-relaxed">{text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function GaugeChart({ value }: { value: number }) {
  const r = 46, cx = 60, cy = 60;
  const circumference = Math.PI * r;
  const color = getRiskColor(value);

  return (
    <svg width="120" height="70" viewBox="0 0 120 70">
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#E5E8EB" strokeWidth="10" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${circumference}`}
        strokeDashoffset={`${circumference * (1 - value)}`}
        style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.4s ease" }}
      />
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="13" fontWeight="bold" fill={color}>
        {(value * 100).toFixed(0)}
      </text>
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize="8" fill="#ADB5BD">RISK INDEX</text>
    </svg>
  );
}
