"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Header from "@/components/layout/Header";
import DashboardLayout from "@/components/layout/DashboardLayout";
import ControlSidebar from "@/components/panels/ControlSidebar";
import RiskGraph from "@/components/panels/RiskGraph";
import AnalyticsPanel from "@/components/panels/AnalyticsPanel";
import { ToastContainer } from "@/components/ui/Toast";
import { useToastStore } from "@/stores/useToastStore";
import { toast } from "@/stores/useToastStore";
import {
  useSimulationStore,
  selectParams,
  selectResult,
  selectGraphData,
  selectSectorData,
  selectIsLoading,
  selectError,
  selectApiStatus,
  selectSelectedTicker,
} from "@/stores/useSimulationStore";

export default function HomePage() {
  // ── 스토어 구독 ──────────────────────────────────────
  const params         = useSimulationStore(selectParams);
  const result         = useSimulationStore(selectResult);
  const graphData      = useSimulationStore(selectGraphData);
  const sectorData     = useSimulationStore(selectSectorData);
  const isLoading      = useSimulationStore(selectIsLoading);
  const error          = useSimulationStore(selectError);
  const apiStatus      = useSimulationStore(selectApiStatus);
  const selectedTicker = useSimulationStore(selectSelectedTicker);

  // ── 스토어 액션 ──────────────────────────────────────
  const setParams         = useSimulationStore((s) => s.setParams);
  const setSelectedTicker = useSimulationStore((s) => s.setSelectedTicker);
  const runSimulation     = useSimulationStore((s) => s.runSimulation);
  const checkApiHealth    = useSimulationStore((s) => s.checkApiHealth);

  // Toast 스토어
  const toasts      = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.remove);

  // ── 플레이백 상태 ─────────────────────────────────────
  const [playbackDay, setPlaybackDay] = useState(0);
  const [isPlaying, setIsPlaying]     = useState(false);
  const playIntervalRef               = useRef<ReturnType<typeof setInterval> | null>(null);

  // 시뮬레이션 결과 변경 시 플레이백 리셋
  useEffect(() => {
    setPlaybackDay(0);
    setIsPlaying(false);
  }, [result]);

  // 플레이백 인터벌 관리
  useEffect(() => {
    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current);
      playIntervalRef.current = null;
    }
    if (!isPlaying || !result) return;

    playIntervalRef.current = setInterval(() => {
      setPlaybackDay((d) => {
        const next = d + 1;
        if (next >= params.timeHorizon) {
          setIsPlaying(false);
          return params.timeHorizon;
        }
        return next;
      });
    }, 80); // 80ms per day → 30일 = ~2.4초

    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
        playIntervalRef.current = null;
      }
    };
  }, [isPlaying, result, params.timeHorizon]);

  const handlePlayToggle = useCallback(() => {
    if (!result) return;
    setIsPlaying((prev) => {
      if (!prev && playbackDay >= params.timeHorizon) {
        // 끝에서 재생 누르면 처음부터
        setPlaybackDay(0);
      }
      return !prev;
    });
  }, [result, playbackDay, params.timeHorizon]);

  const handlePlaybackReset = useCallback(() => {
    setIsPlaying(false);
    setPlaybackDay(0);
  }, []);

  // ── API 헬스체크 ─────────────────────────────────────
  useEffect(() => {
    checkApiHealth();
    const id = setInterval(checkApiHealth, 30_000);
    return () => clearInterval(id);
  }, [checkApiHealth]);

  // ── API 상태 변화 시 Toast ────────────────────────────
  useEffect(() => {
    if (apiStatus === "degraded") {
      toast.warning("백엔드 연결 오류", "uvicorn 서버가 실행 중인지 확인하세요");
    }
  }, [apiStatus]);

  // ── 에러 → Toast ─────────────────────────────────────
  useEffect(() => {
    if (error) {
      toast.error("시뮬레이션 오류", error);
    }
  }, [error]);

  // ── 시뮬레이션 성공 시 Toast ─────────────────────────
  useEffect(() => {
    if (result) {
      toast.success(
        `${result.origin_ticker} 시뮬레이션 완료`,
        `${result.affected_count}개 기업에 리스크 전파됨`
      );
    }
  }, [result]);

  return (
    <>
      <Header apiStatus={apiStatus} />

      <DashboardLayout
        sidebar={
          <ControlSidebar
            params={params}
            isLoading={isLoading}
            onParamsChange={setParams}
            onRunSimulation={runSimulation}
            playbackDay={playbackDay}
            isPlaying={isPlaying}
            hasSimResult={result !== null}
            onPlayToggle={handlePlayToggle}
            onPlaybackReset={handlePlaybackReset}
          />
        }
        canvas={
          <RiskGraph
            graphData={graphData}
            hasData={result !== null}
            isLoading={isLoading}
            ticker={params.ticker}
            selectedTicker={selectedTicker}
            onNodeClick={setSelectedTicker}
            playbackDay={playbackDay}
            isPlaying={isPlaying}
            simParams={params}
          />
        }
        analytics={
          <AnalyticsPanel
            nodes={result?.nodes ?? []}
            edges={result?.edges ?? []}
            sectorData={sectorData}
            originTicker={result?.origin_ticker ?? ""}
            isLoading={isLoading}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            timeHorizon={params.timeHorizon}
            simParams={result ? params : null}
            playbackDay={playbackDay}
          />
        }
      />

      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </>
  );
}
