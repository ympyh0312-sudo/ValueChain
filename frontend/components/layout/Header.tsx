"use client";

import { useState } from "react";
import { Activity, AlertTriangle, CheckCircle, Database } from "lucide-react";
import SeedDataModal from "@/components/ui/SeedDataModal";

interface HeaderProps {
  apiStatus: "healthy" | "degraded" | "loading";
}

export default function Header({ apiStatus }: HeaderProps) {
  const [seedOpen, setSeedOpen] = useState(false);

  const statusConfig = {
    healthy:  { icon: CheckCircle,   color: "text-risk-low",  bg: "bg-risk-low-bg",  label: "정상" },
    degraded: { icon: AlertTriangle, color: "text-risk-high", bg: "bg-risk-high-bg", label: "오류" },
    loading:  { icon: Activity,      color: "text-text-tertiary", bg: "bg-bg-subtle", label: "연결 중" },
  };
  const { icon: StatusIcon, color, bg, label } = statusConfig[apiStatus];

  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-50 h-[60px] bg-white border-b border-border
                   flex items-center justify-between px-5 shadow-card"
      >
        {/* 로고 + 타이틀 */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center shadow-sm">
            <Activity size={16} className="text-white" strokeWidth={2.5} />
          </div>
          <div>
            <span className="font-bold text-[15px] text-text-primary tracking-tight">
              Risk Engine
            </span>
            <span className="ml-1.5 text-[11px] font-medium text-text-tertiary">
              Supply Chain Analytics
            </span>
          </div>
        </div>

        {/* 우측: 샘플 데이터 버튼 + API 상태 */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setSeedOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                       text-xs font-medium text-text-secondary border border-border
                       hover:bg-bg-subtle hover:text-text-primary transition-colors"
          >
            <Database size={12} />
            샘플 데이터
          </button>

          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-pill text-xs font-medium ${bg} ${color}`}>
            <StatusIcon size={12} strokeWidth={2.5} />
            <span>API {label}</span>
          </div>
        </div>
      </header>

      {seedOpen && <SeedDataModal onClose={() => setSeedOpen(false)} />}
    </>
  );
}
