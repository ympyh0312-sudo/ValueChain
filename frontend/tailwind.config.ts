import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // ── 토스/핀다 스타일 Light 팔레트 ──────────────────────────
      colors: {
        // 배경
        bg: {
          base:    "#F5F7FA",   // 전체 페이지 배경 (연회색)
          card:    "#FFFFFF",   // 카드 배경
          subtle:  "#F0F2F5",   // 보조 배경 (입력창, 뱃지)
          hover:   "#EBF0FB",   // 호버 상태
        },
        // 텍스트
        text: {
          primary:   "#1B1B1B",
          secondary: "#6B7684",
          tertiary:  "#ADB5BD",
          inverse:   "#FFFFFF",
        },
        // 테두리
        border: {
          DEFAULT: "#E5E8EB",
          strong:  "#CDD1D5",
        },
        // Primary (토스 블루)
        primary: {
          DEFAULT: "#3182F6",
          light:   "#EBF2FE",
          dark:    "#1B64DA",
          "50":    "#F0F6FF",
          "100":   "#DBEAFE",
          "500":   "#3182F6",
          "600":   "#1B64DA",
          "700":   "#1550B2",
        },
        // 리스크 레벨
        risk: {
          high:   "#EF4444",  // 위험 (빨강)
          "high-bg":   "#FEF2F2",
          mid:    "#F59E0B",  // 주의 (주황)
          "mid-bg":    "#FFFBEB",
          low:    "#10B981",  // 안전 (초록)
          "low-bg":    "#ECFDF5",
          none:   "#6B7684",  // 데이터 없음
        },
      },
      // ── 폰트 ──────────────────────────────────────────────────
      fontFamily: {
        sans: [
          "Pretendard",      // 한국어 최적화
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      // ── 그림자 (카드 elevation) ────────────────────────────────
      boxShadow: {
        card:  "0 1px 3px 0 rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.04)",
        panel: "0 4px 16px 0 rgba(0,0,0,0.08)",
        focus: "0 0 0 3px rgba(49,130,246,0.20)",
      },
      // ── 반경 ──────────────────────────────────────────────────
      borderRadius: {
        card:  "12px",
        badge: "6px",
        pill:  "999px",
      },
      // ── 애니메이션 ────────────────────────────────────────────
      keyframes: {
        "slide-in-right": {
          from: { transform: "translateX(100%)", opacity: "0" },
          to:   { transform: "translateX(0)",    opacity: "1" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%":       { opacity: "0.4" },
        },
      },
      animation: {
        "slide-in-right": "slide-in-right 0.25s ease-out",
        "fade-in":        "fade-in 0.2s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
