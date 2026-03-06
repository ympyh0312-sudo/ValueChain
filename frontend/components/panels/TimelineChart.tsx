"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { getRiskColor } from "@/lib/utils";
import type { RiskNode } from "@/lib/types";

interface TimelineChartProps {
  nodes:          RiskNode[];
  selectedTicker: string | null;
  timeHorizon:    number;
  playbackDay?:   number;
}

/** 리스크 타임라인 라인차트. 선택된 노드 + 전체 평균을 표시. */
export default function TimelineChart({
  nodes,
  selectedTicker,
  timeHorizon,
  playbackDay = 0,
}: TimelineChartProps) {
  if (nodes.length === 0) return null;

  // 표시할 노드: 선택 노드 + 리스크 top 3 (중복 제거)
  const topNodes = [...nodes]
    .filter((n) => !n.is_origin)
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 3);

  const selectedNode = selectedTicker
    ? nodes.find((n) => n.ticker === selectedTicker)
    : null;

  const displayNodes: RiskNode[] = [];
  if (selectedNode && !topNodes.find((n) => n.ticker === selectedNode.ticker)) {
    displayNodes.push(selectedNode);
  }
  displayNodes.push(...topNodes);

  // 전체 평균 계산
  const days = Array.from({ length: Math.min(timeHorizon, 30) + 1 }, (_, i) => i);
  const chartData = days.map((day) => {
    const point: Record<string, number> = { day };
    displayNodes.forEach((n) => {
      point[n.ticker] = Math.round((n.risk_timeline[day] ?? 0) * 1000) / 1000;
    });
    // 전체 평균
    const vals = nodes.map((n) => n.risk_timeline[day] ?? 0);
    point["평균"] = Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 1000) / 1000;
    return point;
  });

  const colors = [
    "#3182F6", // 평균 (파랑)
    "#EF4444",
    "#F59E0B",
    "#10B981",
    "#8B5CF6",
  ];

  const lines = [
    { key: "평균", color: colors[0], dash: "4 2" },
    ...displayNodes.map((n, i) => ({
      key:   n.ticker,
      color: selectedTicker === n.ticker ? getRiskColor(n.risk_score) : colors[i + 1] ?? "#ADB5BD",
      dash:  undefined,
    })),
  ];

  return (
    <div>
      <p className="section-title">리스크 타임라인</p>
      <div className="card p-2">
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E8EB" />
            <XAxis
              dataKey="day"
              tick={{ fontSize: 9, fill: "#ADB5BD" }}
              tickLine={false}
              axisLine={{ stroke: "#E5E8EB" }}
              label={{ value: "일(day)", position: "insideBottomRight", offset: 0, fontSize: 9, fill: "#ADB5BD" }}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#ADB5BD" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
              domain={[0, 1]}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                border: "1px solid #E5E8EB",
                borderRadius: 8,
                boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
              }}
              formatter={(value: number, name: string) => [
                `${(value * 100).toFixed(1)}%`, name,
              ]}
              labelFormatter={(label: number) => `${label}일 후`}
            />
            <Legend
              wrapperStyle={{ fontSize: 10, paddingTop: 4 }}
              iconType="circle"
              iconSize={8}
            />
            {lines.map(({ key, color, dash }) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={color}
                strokeWidth={key === "평균" ? 1.5 : 2}
                strokeDasharray={dash}
                dot={false}
                activeDot={{ r: 4 }}
              />
            ))}
            {/* 플레이백 현재 위치 수직선 */}
            {playbackDay > 0 && (
              <ReferenceLine
                x={Math.min(playbackDay, Math.min(timeHorizon, 30))}
                stroke="#3182F6"
                strokeWidth={1.5}
                strokeDasharray="3 2"
                label={{ value: `${playbackDay}일`, position: "top", fontSize: 9, fill: "#3182F6" }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
        <p className="text-[10px] text-text-tertiary text-center mt-1">
          상위 3개 기업 + {selectedTicker ? `선택(${selectedTicker}) + ` : ""}전체 평균 (점선)
        </p>
      </div>
    </div>
  );
}
