import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind 클래스 병합 유틸 (Shadcn 패턴) */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * risk_score (0~1) → 색상 반환
 * 토스 스타일 Light 테마 기준
 */
export function getRiskColor(score: number): string {
  if (score >= 0.6) return "#EF4444"; // 위험 (빨강)
  if (score >= 0.3) return "#F59E0B"; // 주의 (주황)
  return "#10B981";                   // 안전 (초록)
}

export function getRiskBgColor(score: number): string {
  if (score >= 0.6) return "#FEF2F2";
  if (score >= 0.3) return "#FFFBEB";
  return "#ECFDF5";
}

export function getRiskLabel(score: number): "high" | "mid" | "low" {
  if (score >= 0.6) return "high";
  if (score >= 0.3) return "mid";
  return "low";
}

export function getRiskLabelKr(score: number): string {
  if (score >= 0.6) return "위험";
  if (score >= 0.3) return "주의";
  return "안전";
}

/** 숫자를 퍼센트 문자열로 변환 */
export function toPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** 소수점 N자리 반올림 */
export function round(value: number, digits = 4): number {
  return Math.round(value * 10 ** digits) / 10 ** digits;
}
