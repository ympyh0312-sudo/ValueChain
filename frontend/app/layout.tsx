import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Risk Engine Dashboard",
  description: "공급망 시스템 리스크 분석 대시보드",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
