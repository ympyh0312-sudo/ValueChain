"use client";

import { useRef, useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  Network, AlertCircle,
  ZoomIn, ZoomOut, Maximize2, LayoutGrid, Share2,
  Download, Expand, Shrink,
} from "lucide-react";
import type { GraphData, SimParams } from "@/lib/types";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center">
      <div className="w-10 h-10 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
    </div>
  ),
});

interface RiskGraphProps {
  graphData:      GraphData | null;
  hasData:        boolean;
  isLoading:      boolean;
  ticker:         string;
  selectedTicker: string | null;
  onNodeClick:    (ticker: string | null) => void;
  // ── 플레이백 ───────────────────────────────────────────
  playbackDay?:   number;   // 0 = 현재, > 0 = 경과일
  isPlaying?:     boolean;
  simParams?:     SimParams | null;
}

// ── 색상 유틸 ─────────────────────────────────────────────

function getRiskColorFromScore(score: number): string {
  if (score >= 0.3) return "#EF4444";
  if (score >= 0.1) return "#F59E0B";
  return "#10B981";
}

function getLinkRiskColor(transmittedRisk: number): string {
  if (transmittedRisk >= 0.3)  return "#EF4444";
  if (transmittedRisk >= 0.1)  return "#F59E0B";
  if (transmittedRisk >= 0.03) return "#3B82F6";
  return "#CBD5E1";
}

// ── 방사형 배치 ───────────────────────────────────────────

function placeNodesOnRings(nodes: any[], hopRadius: number) {
  const byHop: Record<number, any[]> = {};
  nodes.forEach((n) => {
    const h = (n.hopDistance as number) ?? 0;
    (byHop[h] = byHop[h] || []).push(n);
  });
  Object.entries(byHop).forEach(([hopStr, group]) => {
    const hop = Number(hopStr);
    if (hop === 0) {
      group.forEach((n) => { n.x = 0; n.y = 0; n.fx = 0; n.fy = 0; });
    } else {
      const r = hop * hopRadius;
      const angleOffset = hop * 0.6;
      group.forEach((n, i) => {
        const angle = (i / group.length) * 2 * Math.PI + angleOffset;
        n.x = r * Math.cos(angle);
        n.y = r * Math.sin(angle);
        n.fx = n.x;
        n.fy = n.y;
      });
    }
  });
}

// ── 컴포넌트 ─────────────────────────────────────────────

export default function RiskGraph({
  graphData,
  hasData,
  isLoading,
  ticker,
  selectedTicker,
  onNodeClick,
  playbackDay = 0,
  isPlaying   = false,
  simParams,
}: RiskGraphProps) {
  const containerRef     = useRef<HTMLDivElement>(null);
  const graphRef         = useRef<any>(null);
  const [size, setSize]                 = useState({ w: 800, h: 600 });
  const [useHierarchy, setUseHierarchy] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Edge hover
  const [hoverLink, setHoverLink]   = useState<any>(null);
  const [mousePos, setMousePos]     = useState({ x: 0, y: 0 });

  const positionsApplied = useRef(false);
  useEffect(() => { positionsApplied.current = false; }, [graphData, useHierarchy]);

  // ── 컨테이너 크기 감지 ────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // ── 전체화면 변경 감지 ────────────────────────────────
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  // ── 첫 프레임 배치 ────────────────────────────────────
  const handleRenderFramePre = useCallback(
    (_ctx: CanvasRenderingContext2D) => {
      if (positionsApplied.current) return;
      if (!graphData?.nodes?.length)  return;
      positionsApplied.current = true;

      if (useHierarchy) {
        placeNodesOnRings(graphData.nodes as any[], 120);
        if (graphRef.current) {
          graphRef.current.d3Force("center", null);
          graphRef.current.d3Force("charge")?.strength(-60);
          graphRef.current.d3Force("link")?.distance(50).strength(0.03);
        }
      } else {
        (graphData.nodes as any[]).forEach((n) => {
          if (!n.isOrigin) { delete n.fx; delete n.fy; }
        });
        if (graphRef.current) {
          graphRef.current.d3Force("charge")?.strength(-280);
          graphRef.current.d3Force("link")?.distance(110).strength(0.35);
          graphRef.current.d3ReheatSimulation();
        }
      }
      // 500ms 딜레이: 엔진 정착 후 + 레이블 폭까지 감안한 넉넉한 패딩
      setTimeout(() => graphRef.current?.zoomToFit(400, 200), 500);
    },
    [graphData, useHierarchy],
  );

  // ── 노드 커스텀 렌더 ─────────────────────────────────
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const r          = node.nodeSize ?? 8;
      const x          = node.x ?? 0;
      const y          = node.y ?? 0;
      const isSelected = node.id === selectedTicker;

      // 플레이백 시 리스크 감쇠 계산
      const baseRisk    = node.riskScore ?? 0;
      const lambda      = simParams?.decayLambda ?? 0.1;
      const animRisk    = (playbackDay > 0 && !node.isOrigin)
        ? baseRisk * Math.exp(-lambda * playbackDay)
        : baseRisk;
      const nodeColor   = node.isOrigin ? "#3182F6" : getRiskColorFromScore(animRisk);

      // ── Glow 효과 (고위험 노드) ──────────────────────
      if (animRisk >= 0.1 && !node.isOrigin) {
        const intensity  = Math.min(animRisk / 0.35, 1.0);
        const glowR      = r + 10 * intensity;
        const gradient   = ctx.createRadialGradient(x, y, r * 0.6, x, y, glowR);
        gradient.addColorStop(0, `rgba(239,68,68,${0.45 * intensity})`);
        gradient.addColorStop(1, "rgba(239,68,68,0)");
        ctx.beginPath();
        ctx.arc(x, y, glowR, 0, 2 * Math.PI);
        ctx.fillStyle = gradient;
        ctx.fill();
      }

      // ── 선택 링 ─────────────────────────────────────
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(x, y, r + 7, 0, 2 * Math.PI);
        ctx.fillStyle = nodeColor + "38";
        ctx.fill();
      }

      // ── 원점 링 ─────────────────────────────────────
      if (node.isOrigin) {
        ctx.beginPath();
        ctx.arc(x, y, r + 4, 0, 2 * Math.PI);
        ctx.strokeStyle = "#3182F6";
        ctx.lineWidth   = 2.5 / globalScale;
        ctx.stroke();
      }

      // ── 노드 원 ─────────────────────────────────────
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle   = nodeColor;
      ctx.fill();
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth   = (isSelected ? 2.5 : 1.5) / globalScale;
      ctx.stroke();

      // ── 기업 심볼 슬롯 (작은 이니셜) ────────────────
      if (r >= 8) {
        const initial = String(node.id ?? "").charAt(0);
        const symSize = Math.max(5, r * 0.7);
        ctx.font      = `bold ${symSize}px sans-serif`;
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.textAlign    = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(initial, x, y);
      }

      // ── 레이블 ──────────────────────────────────────
      const hopDist   = node.hopDistance ?? 999;
      const showLabel = useHierarchy
        ? true
        : (hopDist <= 1 || node.isOrigin || isSelected || globalScale > 1.1);

      if (showLabel) {
        const fontSize = Math.max(8, 11 / globalScale);
        const isBold   = node.isOrigin || isSelected;
        ctx.textAlign    = "center";
        ctx.textBaseline = "top";

        const tickerId = String(node.id);
        const pad      = 2 / globalScale;
        const labelY   = y + r + 3 / globalScale;

        const showName = useHierarchy || node.isOrigin || isSelected;
        const rawName  = node.name ? String(node.name) : "";
        const nameStr  = showName && rawName
          ? (rawName.length > 14 ? rawName.slice(0, 13) + "…" : rawName)
          : null;

        ctx.font = `${isBold ? "bold " : ""}${fontSize}px sans-serif`;
        const tickerW  = ctx.measureText(tickerId).width;
        const nameSize = Math.max(6.5, 8.5 / globalScale);
        ctx.font = `${nameSize}px sans-serif`;
        const nameW = nameStr ? ctx.measureText(nameStr).width : 0;
        const boxW  = Math.max(tickerW, nameW);
        const boxH  = fontSize + (nameStr ? nameSize + 1 / globalScale : 0) + pad * 2;

        ctx.fillStyle = "rgba(255,255,255,0.93)";
        ctx.fillRect(x - boxW / 2 - pad, labelY - pad, boxW + pad * 2, boxH);

        ctx.font      = `${isBold ? "bold " : ""}${fontSize}px sans-serif`;
        ctx.fillStyle = node.isOrigin ? "#3182F6" : "#1B1B1B";
        ctx.fillText(tickerId, x, labelY);

        if (nameStr) {
          ctx.font      = `${nameSize}px sans-serif`;
          ctx.fillStyle = "#6B7684";
          ctx.fillText(nameStr, x, labelY + fontSize + 1 / globalScale);
        }
      }
    },
    [selectedTicker, useHierarchy, playbackDay, simParams],
  );

  // ── 링크 색상·굵기 ────────────────────────────────────
  const getLinkColor = useCallback(
    (link: any) => getLinkRiskColor(link.transmittedRisk ?? 0),
    [],
  );
  const getLinkWidth = useCallback(
    (link: any) => {
      // revenue_share 우선 → 없으면 dependencyScore fallback
      const rs = link.revenueShare ?? link.revenue_share ?? 0;
      if (rs > 0) return Math.max(1, Math.min(7, rs * 22 + 1));
      return Math.max(1, link.linkWidth ?? 1);
    },
    [],
  );

  // ── 이벤트 핸들러 ─────────────────────────────────────
  const handleNodeClick = useCallback(
    (node: any) => onNodeClick(selectedTicker === node.id ? null : String(node.id)),
    [onNodeClick, selectedTicker],
  );
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }, []);

  const handleZoomIn  = () => graphRef.current?.zoom(graphRef.current.zoom() * 1.4, 200);
  const handleZoomOut = () => graphRef.current?.zoom(graphRef.current.zoom() / 1.4, 200);
  const handleZoomFit = () => graphRef.current?.zoomToFit(400, 200);

  const handleFullscreen = () => {
    if (!containerRef.current) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      containerRef.current.requestFullscreen();
    }
  };

  const handleDownloadPNG = () => {
    const canvas = containerRef.current?.querySelector("canvas") as HTMLCanvasElement | null;
    if (!canvas) return;
    const link   = document.createElement("a");
    link.href    = canvas.toDataURL("image/png");
    link.download = `risk-graph-${ticker || "export"}.png`;
    link.click();
  };

  // ── 로딩 상태 ─────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-4">
        {/* 스켈레톤 노드 */}
        <div className="relative w-48 h-48 flex items-center justify-center">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="absolute w-10 h-10 rounded-full bg-bg-subtle animate-pulse"
              style={{
                transform: `rotate(${i * 60}deg) translateY(-64px)`,
                animationDelay: `${i * 0.1}s`,
              }}
            />
          ))}
          <div className="w-14 h-14 rounded-full bg-primary/20 animate-pulse" />
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold text-text-primary">{ticker} 리스크 계산 중</p>
          <p className="text-xs text-text-secondary mt-1">공급망 그래프를 분석하고 있습니다...</p>
        </div>
      </div>
    );
  }

  // ── 빈 상태 ───────────────────────────────────────────

  if (!hasData || !graphData) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center relative">
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage: "radial-gradient(circle, #CDD1D5 1px, transparent 1px)",
            backgroundSize:  "28px 28px",
          }}
        />
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
        <div className="absolute bottom-4 right-4 flex items-center gap-1 text-[11px] text-text-tertiary">
          <AlertCircle size={11} />
          <span>백엔드(uvicorn)와 DB가 실행 중이어야 합니다</span>
        </div>
      </div>
    );
  }

  // ── 그래프 렌더 ───────────────────────────────────────

  return (
    <div
      ref={containerRef}
      className="w-full h-full relative overflow-hidden bg-bg-base"
      onMouseMove={handleMouseMove}
    >
      <ForceGraph2D
        ref={graphRef}
        width={size.w}
        height={size.h}
        graphData={graphData}

        // ── 노드 ──────────────────────────────────────
        nodeId="id"
        nodeVal={(n: any) => n.nodeSize ?? 8}
        nodeLabel={(n: any) =>
          `${n.id} — ${n.name}\n` +
          `리스크: ${((n.riskScore ?? 0) * 100).toFixed(1)}%\n` +
          `섹터: ${n.sector} | 국가: ${n.country}\n` +
          `공급망 거리: ${n.hopDistance}홉`
        }
        nodeCanvasObject={drawNode}
        nodeCanvasObjectMode={() => "replace"}

        // ── 링크 ──────────────────────────────────────
        linkColor={getLinkColor}
        linkWidth={getLinkWidth}
        linkDirectionalArrowLength={7}
        linkDirectionalArrowRelPos={0.88}
        linkDirectionalArrowColor={getLinkColor}

        // ── 파티클 (흐름 가시화) ──────────────────────
        linkDirectionalParticles={(l: any) => {
          const r = l.transmittedRisk ?? 0;
          if (r >= 0.2) return 8;   // 고위험: 빽빽한 흐름
          if (r >= 0.05) return 5;  // 중위험
          return 3;                  // 저위험도 최소 3개
        }}
        linkDirectionalParticleWidth={(l: any) => {
          const r = l.transmittedRisk ?? 0;
          if (r >= 0.2) return 6;   // 크고 눈에 띄게
          if (r >= 0.05) return 5;
          return 4;
        }}
        linkDirectionalParticleSpeed={(l: any) => {
          const r = l.transmittedRisk ?? 0;
          if (r >= 0.2) return 0.010;
          if (r >= 0.05) return 0.007;
          return 0.005;
        }}
        linkDirectionalParticleColor={(l: any) => {
          // 엣지 색과 대비되는 밝은 계열로 구분
          const r = l.transmittedRisk ?? 0;
          if (r >= 0.2) return "#FFE4E4"; // 밝은 연핑크 (위험 엣지 위)
          if (r >= 0.05) return "#FFF3CD"; // 밝은 연노랑 (주의 엣지 위)
          return "#DBEAFE";               // 밝은 연파랑 (안전 엣지 위)
        }}

        // ── 인터랙션 ───────────────────────────────────
        onNodeClick={handleNodeClick}
        onBackgroundClick={() => onNodeClick(null)}
        onLinkHover={(link) => setHoverLink(link)}

        // ── 스타일 ────────────────────────────────────
        backgroundColor="#F5F7FA"

        // ── 물리 엔진 ─────────────────────────────────
        d3AlphaDecay={useHierarchy ? 0.1 : 0.04}
        d3VelocityDecay={useHierarchy ? 0.8 : 0.4}
        cooldownTicks={useHierarchy ? 60 : 300}

        onRenderFramePre={handleRenderFramePre}
        onEngineStop={() => {
          if (!useHierarchy) {
            graphData?.nodes.forEach((n: any) => {
              if (n.x !== undefined) n.fx = n.x;
              if (n.y !== undefined) n.fy = n.y;
            });
            // 자유형 모드: 엔진 정지 후 fit
            setTimeout(() => graphRef.current?.zoomToFit(500, 200), 200);
          }
          // 방사형은 handleRenderFramePre의 zoomToFit이 담당
        }}
      />

      {/* ── 엣지 호버 툴팁 ──────────────────────────── */}
      {hoverLink && (
        <div
          className="absolute pointer-events-none z-50
                     bg-gray-900/92 text-white rounded-xl px-3 py-2.5
                     shadow-xl backdrop-blur-sm border border-white/10"
          style={{
            left: Math.min(mousePos.x + 14, size.w - 200),
            top:  Math.max(mousePos.y - 70, 4),
          }}
        >
          <p className="text-[11px] font-bold text-white/95 mb-1">
            공급 관계:{" "}
            <span className="text-blue-300">
              {typeof hoverLink.source === "object" ? hoverLink.source.id : hoverLink.source}
            </span>
            {" → "}
            <span className="text-amber-300">
              {typeof hoverLink.target === "object" ? hoverLink.target.id : hoverLink.target}
            </span>
          </p>
          <div className="space-y-0.5 text-[10px] text-white/70">
            <div className="flex justify-between gap-4">
              <span>매출 비중</span>
              <span className="font-semibold text-white/90">
                {((hoverLink.revenueShare ?? hoverLink.revenue_share ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span>공급 의존도</span>
              <span className="font-semibold text-white/90">
                {((hoverLink.dependencyScore ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span>전달 리스크</span>
              <span className="font-semibold" style={{ color: getLinkRiskColor(hoverLink.transmittedRisk ?? 0) }}>
                {((hoverLink.transmittedRisk ?? 0) * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── 플레이백 인디케이터 ────────────────────────── */}
      {isPlaying && simParams && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2
                        bg-gray-900/90 text-white text-[11px] font-semibold
                        rounded-full px-4 py-1.5 flex items-center gap-2
                        shadow-lg border border-white/10">
          <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
          <span>시뮬레이션 {playbackDay}일</span>
          <span className="text-white/50">/ {simParams.timeHorizon}일</span>
        </div>
      )}
      {/* 정지 상태에서도 현재 날짜 표시 */}
      {!isPlaying && playbackDay > 0 && simParams && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2
                        bg-white/90 text-text-primary text-[11px] font-medium
                        rounded-full px-4 py-1.5 shadow-card border border-border">
          {playbackDay}일 후 상태 미리보기
        </div>
      )}

      {/* ── 레이아웃 토글 ─────────────────────────────── */}
      <div className="absolute top-4 left-4">
        <button
          onClick={() => setUseHierarchy(!useHierarchy)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white rounded-lg
                     shadow-card border border-border text-xs font-medium
                     text-text-secondary hover:text-primary hover:border-primary/40 transition-colors"
        >
          {useHierarchy ? (
            <><Share2 size={12} className="text-primary" /><span className="text-primary font-semibold">방사형</span></>
          ) : (
            <><LayoutGrid size={12} /><span>자유형</span></>
          )}
        </button>
      </div>

      {/* ── 우측 하단 컨트롤 ──────────────────────────── */}
      <div className="absolute bottom-5 right-5 flex flex-col gap-1.5">
        {[
          { Icon: ZoomIn,    action: handleZoomIn,     label: "확대" },
          { Icon: ZoomOut,   action: handleZoomOut,    label: "축소" },
          { Icon: Maximize2, action: handleZoomFit,    label: "전체 맞춤" },
        ].map(({ Icon, action, label }) => (
          <button
            key={label}
            onClick={action}
            title={label}
            className="w-8 h-8 bg-white rounded-lg shadow-card border border-border
                       flex items-center justify-center hover:bg-bg-hover transition-colors"
          >
            <Icon size={14} className="text-text-secondary" />
          </button>
        ))}

        {/* 구분선 */}
        <div className="h-px bg-border mx-1" />

        {/* 전체화면 */}
        <button
          onClick={handleFullscreen}
          title={isFullscreen ? "전체화면 종료" : "전체화면 보기"}
          className="w-8 h-8 bg-white rounded-lg shadow-card border border-border
                     flex items-center justify-center hover:bg-primary-light
                     hover:border-primary/40 hover:text-primary transition-colors"
        >
          {isFullscreen
            ? <Shrink size={14} className="text-primary" />
            : <Expand  size={14} className="text-text-secondary" />
          }
        </button>

        {/* PNG 저장 */}
        <button
          onClick={handleDownloadPNG}
          title="이미지 저장 (PNG)"
          className="w-8 h-8 bg-white rounded-lg shadow-card border border-border
                     flex items-center justify-center hover:bg-primary-light
                     hover:border-primary/40 hover:text-primary transition-colors"
        >
          <Download size={14} className="text-text-secondary" />
        </button>
      </div>

      {/* ── 범례 ──────────────────────────────────────── */}
      <div className="absolute bottom-5 left-5 bg-white/92 backdrop-blur-sm rounded-lg
                      shadow-card border border-border px-3 py-2.5 min-w-[148px]">
        <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider mb-2">
          리스크 수준 (노드 색상)
        </p>
        {[
          { color: "#EF4444", label: "위험  ≥ 30%" },
          { color: "#F59E0B", label: "주의  10~30%" },
          { color: "#10B981", label: "안전   < 10%" },
          { color: "#3182F6", label: "충격 원점" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full border border-white shadow-sm shrink-0"
                 style={{ backgroundColor: color }} />
            <span className="text-[11px] text-text-secondary">{label}</span>
          </div>
        ))}
        <div className="pt-1.5 mt-1 border-t border-border space-y-0.5">
          <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider mb-1">엣지 굵기</p>
          <p className="text-[9px] text-text-tertiary leading-relaxed">
            매출 비중(revenue_share)에 비례
          </p>
          {[
            { color: "#EF4444", label: "고위험 ≥30%" },
            { color: "#F59E0B", label: "중위험 10~30%" },
            { color: "#3B82F6", label: "저위험 3~10%" },
            { color: "#CBD5E1", label: "미미 <3%" },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2">
              <div className="w-6 h-0.5 rounded shrink-0" style={{ backgroundColor: color }} />
              <span className="text-[10px] text-text-tertiary">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── 공급망 부족 안내 ──────────────────────────── */}
      {graphData.nodes.length <= 4 && (
        <div className="absolute bottom-24 left-1/2 -translate-x-1/2 w-72
                        bg-amber-50 border border-amber-300 rounded-xl px-4 py-3 shadow-panel text-center">
          <p className="text-xs font-bold text-amber-700">📊 공급망 데이터가 부족합니다</p>
          <p className="text-[10px] text-amber-600 mt-1 leading-relaxed">
            현재 {graphData.nodes.length}개 기업만 표시됩니다.<br />
            왼쪽 <strong>"AI 공급망 자동 발견"</strong> 버튼으로<br />
            LLM이 공급사·구매사를 분석하여 그래프를 확장합니다.
          </p>
        </div>
      )}

      {/* ── 노드/엣지 수 ──────────────────────────────── */}
      <div className="absolute top-4 right-4 flex gap-2">
        <span className="bg-white/90 text-[11px] font-medium text-text-secondary px-2.5 py-1 rounded-pill shadow-card border border-border">
          노드 {graphData.nodes.length}개
        </span>
        <span className="bg-white/90 text-[11px] font-medium text-text-secondary px-2.5 py-1 rounded-pill shadow-card border border-border">
          엣지 {graphData.links.length}개
        </span>
      </div>

      {/* ── 방사 거리 안내 ────────────────────────────── */}
      {useHierarchy && (
        <div className="absolute top-14 left-4 bg-white/88 backdrop-blur-sm rounded-lg
                        shadow-card border border-border px-2.5 py-2 space-y-0.5">
          <p className="text-[9px] font-bold text-text-tertiary uppercase tracking-wide mb-1.5">방사 거리 (홉)</p>
          {[
            { hop: "0", label: "충격 원점 (중심)" },
            { hop: "1", label: "직접 공급·구매사" },
            { hop: "2", label: "2차 관계사" },
            { hop: "3+", label: "간접 영향기업" },
          ].map(({ hop, label }) => (
            <div key={hop} className="flex items-center gap-2">
              <span className="text-[9px] font-mono font-bold text-primary w-4">{hop}</span>
              <span className="text-[9px] text-text-secondary">{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
