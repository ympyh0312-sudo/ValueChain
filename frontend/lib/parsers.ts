// ─────────────────────────────────────────────────────────
// lib/parsers.ts  ─ 백엔드 응답 → 시각화 데이터 변환
//
// SimResult(백엔드) → GraphData(react-force-graph-2d)
// SubgraphResponse  → GraphData (네트워크 탐색용)
// ─────────────────────────────────────────────────────────

import { getRiskColor } from "@/lib/utils";
import type {
  SimResult,
  SubgraphResponse,
  GraphData,
  GraphNode,
  GraphLink,
} from "@/lib/types";

// ── 노드 크기 계산 ────────────────────────────────────
// 원점: 가장 크게, hop이 멀어질수록 작아짐

function calcNodeSize(isOrigin: boolean, hopDistance: number): number {
  if (isOrigin) return 14;
  const base = 10;
  return Math.max(base - hopDistance * 1.5, 5);
}

// ── 링크 굵기 계산 ────────────────────────────────────
// dependency_score (0~1) → 선 굵기 (1~6)

function calcLinkWidth(dependencyScore: number): number {
  return Math.max(1, Math.round(dependencyScore * 6));
}

// ── SimResult → GraphData ──────────────────────────────
/**
 * 리스크 시뮬레이션 결과를 Force Graph 입력 형태로 변환.
 *
 * nodes: risk_score에 따라 색상, hop에 따라 크기 결정
 * links: dependency_score에 따라 선 굵기 결정
 */
export function parseSimResultToGraph(result: SimResult): GraphData {
  const nodes: GraphNode[] = result.nodes.map((n) => ({
    id:          n.ticker,
    name:        n.name,
    sector:      n.sector,
    country:     n.country,
    riskScore:   n.risk_score,
    hopDistance: n.hop_distance,
    isOrigin:    n.is_origin,
    color:       n.is_origin ? "#3182F6" : getRiskColor(n.risk_score),
    nodeSize:    calcNodeSize(n.is_origin, n.hop_distance),
  }));

  const links: GraphLink[] = result.edges.map((e) => ({
    source:          e.source_ticker,
    target:          e.target_ticker,
    transmittedRisk: e.transmitted_risk,
    dependencyScore: e.dependency_score,
    revenueShare:    (e as any).revenue_share ?? e.dependency_score * 0.5,
    linkWidth:       calcLinkWidth(e.dependency_score),
  }));

  return { nodes, links };
}

// ── SubgraphResponse → GraphData ──────────────────────
/**
 * 특정 기업 서브그래프(공급망 구조)를 Force Graph 입력 형태로 변환.
 * 리스크 점수 없이 순수 네트워크 구조만 표현.
 * (시뮬레이션 실행 전 기업 네트워크 미리보기에 사용)
 */
export function parseSubgraphToGraph(
  data:         SubgraphResponse,
  centerTicker: string
): GraphData {
  const nodes: GraphNode[] = data.nodes.map((n) => ({
    id:          n.ticker,
    name:        n.name,
    sector:      n.sector,
    country:     n.country,
    riskScore:   0,
    hopDistance: n.ticker === centerTicker.toUpperCase() ? 0 : 1,
    isOrigin:    n.ticker === centerTicker.toUpperCase(),
    color:       n.ticker === centerTicker.toUpperCase() ? "#3182F6" : "#6B7684",
    nodeSize:    n.ticker === centerTicker.toUpperCase() ? 14 : 8,
  }));

  const links: GraphLink[] = data.edges.map((e) => ({
    source:          e.source,
    target:          e.target,
    transmittedRisk: 0,
    dependencyScore: e.dependency_score,
    revenueShare:    e.revenue_share,
    linkWidth:       calcLinkWidth(e.dependency_score),
  }));

  return { nodes, links };
}

// ── 섹터별 집계 ───────────────────────────────────────
/**
 * 리스크 노드를 섹터별로 그룹화하여 평균 리스크 계산.
 * AnalyticsPanel 바차트에서 사용.
 */
export function aggregateBySector(
  result: SimResult
): Array<{ sector: string; avgRisk: number; count: number }> {
  const map = new Map<string, { total: number; count: number }>();

  result.nodes.forEach((n) => {
    const sector = n.sector || "Unknown";
    const prev = map.get(sector) ?? { total: 0, count: 0 };
    map.set(sector, { total: prev.total + n.risk_score, count: prev.count + 1 });
  });

  return Array.from(map.entries())
    .map(([sector, { total, count }]) => ({
      sector,
      avgRisk: total / count,
      count,
    }))
    .sort((a, b) => b.avgRisk - a.avgRisk);
}

// ── 타임라인 집계 ─────────────────────────────────────
/**
 * 전체 노드의 날짜별 리스크 합계 타임라인 생성.
 * 리스크 추이 라인차트에서 사용.
 */
export function aggregateTimeline(
  result: SimResult
): Array<{ day: number; totalRisk: number; avgRisk: number }> {
  if (result.nodes.length === 0) return [];

  // 모든 타임라인 키 수집
  const allDays = new Set<number>();
  result.nodes.forEach((n) => {
    Object.keys(n.risk_timeline).forEach((k) => allDays.add(Number(k)));
  });

  return Array.from(allDays)
    .sort((a, b) => a - b)
    .map((day) => {
      const values = result.nodes
        .map((n) => n.risk_timeline[day] ?? 0)
        .filter((v) => v > 0);
      const total = values.reduce((s, v) => s + v, 0);
      return {
        day,
        totalRisk: Math.round(total * 10000) / 10000,
        avgRisk:   values.length > 0
          ? Math.round((total / values.length) * 10000) / 10000
          : 0,
      };
    });
}
