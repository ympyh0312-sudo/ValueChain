"use client";

import { useEffect, useState } from "react";
import { CheckCircle, AlertTriangle, XCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "warning" | "error";

export interface ToastData {
  id:      string;
  type:    ToastType;
  title:   string;
  message?: string;
}

const ICONS = {
  success: CheckCircle,
  warning: AlertTriangle,
  error:   XCircle,
};

const STYLES = {
  success: "border-risk-low  bg-risk-low-bg  text-risk-low",
  warning: "border-risk-mid  bg-risk-mid-bg  text-risk-mid",
  error:   "border-risk-high bg-risk-high-bg text-risk-high",
};

interface ToastItemProps {
  toast:    ToastData;
  onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const [visible, setVisible] = useState(false);
  const Icon = ICONS[toast.type];

  useEffect(() => {
    // 마운트 후 fade-in
    requestAnimationFrame(() => setVisible(true));
    // 4초 후 자동 제거
    const t = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onRemove(toast.id), 300);
    }, 4000);
    return () => clearTimeout(t);
  }, [toast.id, onRemove]);

  return (
    <div
      className={cn(
        "flex items-start gap-3 w-80 bg-white rounded-xl shadow-panel border-l-4 px-4 py-3",
        "transition-all duration-300",
        STYLES[toast.type],
        visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
      )}
    >
      <Icon size={16} className="shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary">{toast.title}</p>
        {toast.message && (
          <p className="text-xs text-text-secondary mt-0.5 break-words">{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => { setVisible(false); setTimeout(() => onRemove(toast.id), 300); }}
        className="shrink-0 text-text-tertiary hover:text-text-secondary"
      >
        <X size={14} />
      </button>
    </div>
  );
}

interface ToastContainerProps {
  toasts:   ToastData[];
  onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 items-end">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={onRemove} />
      ))}
    </div>
  );
}
