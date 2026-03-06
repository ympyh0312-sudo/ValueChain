"use client";

import { ReactNode } from "react";

interface DashboardLayoutProps {
  sidebar: ReactNode;    // 왼쪽: 시뮬레이션 컨트롤
  canvas: ReactNode;     // 가운데: Force Graph
  analytics: ReactNode;  // 오른쪽: Analytics 패널
}

/**
 * 3패널 대시보드 레이아웃
 *
 *  ┌──────────┬──────────────────────────┬────────────────┐
 *  │ Sidebar  │        Canvas            │   Analytics    │
 *  │ 280px    │        flex-1            │    320px       │
 *  └──────────┴──────────────────────────┴────────────────┘
 *
 * Header 높이(60px)만큼 pt-[60px] 적용
 */
export default function DashboardLayout({
  sidebar,
  canvas,
  analytics,
}: DashboardLayoutProps) {
  return (
    <div className="flex h-screen pt-[60px] bg-bg-base overflow-hidden">
      {/* ── 왼쪽: Control Sidebar ───────────────────────────── */}
      <aside
        className="w-[280px] shrink-0 h-full bg-white border-r border-border
                   overflow-y-auto flex flex-col"
      >
        {sidebar}
      </aside>

      {/* ── 가운데: 메인 캔버스 ─────────────────────────────── */}
      <main className="flex-1 min-w-0 h-full overflow-hidden relative bg-bg-base">
        {canvas}
      </main>

      {/* ── 오른쪽: Analytics 패널 ──────────────────────────── */}
      <aside
        className="w-[320px] shrink-0 h-full bg-white border-l border-border
                   overflow-y-auto flex flex-col"
      >
        {analytics}
      </aside>
    </div>
  );
}
