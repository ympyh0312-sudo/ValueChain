"use client";

import { useState } from "react";
import { Play, Pause, RefreshCw, ChevronDown, ChevronUp, Search, Info, Sparkles, Newspaper, CheckCircle2, AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { discoverSupplyChain, analyzeNewsShock, ApiError } from "@/lib/api";
import type { SimParams, DiscoverResult, NewsShockResult } from "@/lib/types";

interface ControlSidebarProps {
  params:           SimParams;
  isLoading:        boolean;
  onParamsChange:   (partial: Partial<SimParams>) => void;
  onRunSimulation:  () => void;
  // 플레이백
  playbackDay:      number;
  isPlaying:        boolean;
  hasSimResult:     boolean;
  onPlayToggle:     () => void;
  onPlaybackReset:  () => void;
}

// ─────────────────────────────────────────────────────
// 국가 → 섹터 → 기업 계층 구조
// ─────────────────────────────────────────────────────
interface CompanyEntry { ticker: string; name: string }
interface SectorEntry  { label: string; companies: CompanyEntry[] }
interface CountryGroup { label: string; flag: string; sectors: SectorEntry[] }

const COUNTRY_GROUPS: CountryGroup[] = [
  {
    label: "미국",
    flag: "🇺🇸",
    sectors: [
      {
        label: "반도체·테크",
        companies: [
          { ticker: "APD",   name: "Air Products" },
          { ticker: "LIN",   name: "Linde" },
          { ticker: "EMN",   name: "Eastman Chemical" },
          { ticker: "AMAT",  name: "Applied Materials" },
          { ticker: "LRCX",  name: "Lam Research" },
          { ticker: "KLAC",  name: "KLA Corporation" },
          { ticker: "INTC",  name: "Intel" },
          { ticker: "MU",    name: "Micron Technology" },
          { ticker: "NVDA",  name: "NVIDIA" },
          { ticker: "AMD",   name: "AMD" },
          { ticker: "QCOM",  name: "Qualcomm" },
          { ticker: "AVGO",  name: "Broadcom" },
          { ticker: "MRVL",  name: "Marvell" },
          { ticker: "ADI",   name: "Analog Devices" },
          { ticker: "TXN",   name: "Texas Instruments" },
          { ticker: "SWKS",  name: "Skyworks" },
          { ticker: "ON",    name: "ON Semiconductor" },
          { ticker: "GLW",   name: "Corning" },
          { ticker: "APH",   name: "Amphenol" },
          { ticker: "JBL",   name: "Jabil" },
          { ticker: "AAPL",  name: "Apple" },
          { ticker: "DELL",  name: "Dell" },
          { ticker: "HPQ",   name: "HP Inc." },
          { ticker: "CSCO",  name: "Cisco" },
          { ticker: "JNPR",  name: "Juniper Networks" },
          { ticker: "MSFT",  name: "Microsoft" },
          { ticker: "AMZN",  name: "Amazon" },
          { ticker: "GOOGL", name: "Alphabet" },
          { ticker: "META",  name: "Meta" },
          { ticker: "ORCL",  name: "Oracle" },
          { ticker: "CRM",   name: "Salesforce" },
          { ticker: "NOW",   name: "ServiceNow" },
          { ticker: "WDAY",  name: "Workday" },
          { ticker: "ADBE",  name: "Adobe" },
        ],
      },
      {
        label: "에너지·전력",
        companies: [
          { ticker: "XOM",  name: "ExxonMobil" },
          { ticker: "CVX",  name: "Chevron" },
          { ticker: "COP",  name: "ConocoPhillips" },
          { ticker: "SLB",  name: "SLB (Schlumberger)" },
          { ticker: "ENPH", name: "Enphase Energy" },
          { ticker: "FSLR", name: "First Solar" },
          { ticker: "ETN",  name: "Eaton" },
          { ticker: "GEV",  name: "GE Vernova" },
          { ticker: "VRT",  name: "Vertiv" },
          { ticker: "NEE",  name: "NextEra Energy" },
          { ticker: "DUK",  name: "Duke Energy" },
          { ticker: "SO",   name: "Southern Company" },
          { ticker: "EXC",  name: "Exelon" },
          { ticker: "AES",  name: "AES Corporation" },
          { ticker: "VST",  name: "Vistra Energy" },
        ],
      },
      {
        label: "헬스케어",
        companies: [
          { ticker: "AMGN",  name: "Amgen" },
          { ticker: "REGN",  name: "Regeneron" },
          { ticker: "VRTX",  name: "Vertex Pharma" },
          { ticker: "LLY",   name: "Eli Lilly" },
          { ticker: "ABBV",  name: "AbbVie" },
          { ticker: "PFE",   name: "Pfizer" },
          { ticker: "JNJ",   name: "Johnson & Johnson" },
          { ticker: "MRK",   name: "Merck & Co." },
          { ticker: "MDT",   name: "Medtronic" },
          { ticker: "ABT",   name: "Abbott" },
          { ticker: "SYK",   name: "Stryker" },
          { ticker: "ISRG",  name: "Intuitive Surgical" },
          { ticker: "UNH",   name: "UnitedHealth Group" },
          { ticker: "HCA",   name: "HCA Healthcare" },
          { ticker: "CVS",   name: "CVS Health" },
          { ticker: "IQVIA", name: "IQVIA" },
        ],
      },
      {
        label: "금융",
        companies: [
          { ticker: "JPM",  name: "JPMorgan Chase" },
          { ticker: "BAC",  name: "Bank of America" },
          { ticker: "GS",   name: "Goldman Sachs" },
          { ticker: "MS",   name: "Morgan Stanley" },
          { ticker: "V",    name: "Visa" },
          { ticker: "MA",   name: "Mastercard" },
          { ticker: "PYPL", name: "PayPal" },
          { ticker: "AXP",  name: "American Express" },
          { ticker: "BLK",  name: "BlackRock" },
          { ticker: "MMC",  name: "Marsh McLennan" },
        ],
      },
      {
        label: "소비·유통",
        companies: [
          { ticker: "WMT",  name: "Walmart" },
          { ticker: "COST", name: "Costco" },
          { ticker: "TGT",  name: "Target" },
          { ticker: "HD",   name: "Home Depot" },
          { ticker: "KO",   name: "Coca-Cola" },
          { ticker: "PEP",  name: "PepsiCo" },
          { ticker: "PG",   name: "Procter & Gamble" },
          { ticker: "NKE",  name: "Nike" },
        ],
      },
      {
        label: "산업·방산·자동차",
        companies: [
          { ticker: "BA",   name: "Boeing" },
          { ticker: "RTX",  name: "RTX" },
          { ticker: "LMT",  name: "Lockheed Martin" },
          { ticker: "GE",   name: "GE Aerospace" },
          { ticker: "HON",  name: "Honeywell" },
          { ticker: "CAT",  name: "Caterpillar" },
          { ticker: "MMM",  name: "3M" },
          { ticker: "TSLA", name: "Tesla" },
          { ticker: "F",    name: "Ford" },
          { ticker: "RIVN", name: "Rivian" },
        ],
      },
    ],
  },
  {
    label: "한국",
    flag: "🇰🇷",
    sectors: [
      {
        label: "반도체·메모리",
        companies: [
          { ticker: "005930", name: "Samsung Electronics" },
          { ticker: "000660", name: "SK Hynix" },
          { ticker: "009150", name: "Samsung Electro-Mech" },
        ],
      },
      {
        label: "디스플레이·부품",
        companies: [
          { ticker: "034220", name: "LG Display" },
          { ticker: "066570", name: "LG Electronics" },
        ],
      },
      {
        label: "배터리·화학",
        companies: [
          { ticker: "051910", name: "LG Chem" },
          { ticker: "373220", name: "LG Energy Solution" },
          { ticker: "006400", name: "Samsung SDI" },
          { ticker: "096770", name: "SK Innovation" },
          { ticker: "005490", name: "POSCO Holdings" },
        ],
      },
      {
        label: "자동차·부품",
        companies: [
          { ticker: "005380", name: "Hyundai Motor" },
          { ticker: "000270", name: "Kia Motors" },
          { ticker: "012330", name: "Hyundai Mobis" },
        ],
      },
      {
        label: "헬스케어·방산",
        companies: [
          { ticker: "068270", name: "Celltrion" },
          { ticker: "012450", name: "Hanwha Aerospace" },
          { ticker: "034020", name: "Doosan Enerbility" },
        ],
      },
      {
        label: "IT·금융",
        companies: [
          { ticker: "035420", name: "NAVER" },
          { ticker: "086790", name: "Hana Financial Group" },
          { ticker: "105560", name: "KB Financial Group" },
        ],
      },
    ],
  },
  {
    label: "글로벌",
    flag: "🌏",
    sectors: [
      {
        label: "일본 (Japan)",
        companies: [
          { ticker: "SHNEY",  name: "Shin-Etsu Chemical" },
          { ticker: "SUOPY",  name: "SUMCO" },
          { ticker: "TOELY",  name: "Tokyo Electron" },
          { ticker: "MRAAY",  name: "Murata" },
          { ticker: "TTDKY",  name: "TDK" },
        ],
      },
      {
        label: "유럽 (Europe)",
        companies: [
          { ticker: "ASML",  name: "ASML (Netherlands)" },
          { ticker: "WFRD",  name: "Merck KGaA (Germany)" },
          { ticker: "NXPI",  name: "NXP Semiconductors (NL)" },
          { ticker: "STM",   name: "STMicroelectronics (CH)" },
          { ticker: "IFNNY", name: "Infineon (Germany)" },
          { ticker: "SAP",   name: "SAP (Germany)" },
          { ticker: "ABB",   name: "ABB (Switzerland)" },
          { ticker: "LIN",   name: "Linde (UK/IE)" },
        ],
      },
      {
        label: "아시아·기타",
        companies: [
          { ticker: "TSMC",  name: "TSMC (Taiwan)" },
          { ticker: "UMC",   name: "UMC (Taiwan)" },
          { ticker: "HNHPF", name: "Hon Hai/Foxconn (Taiwan)" },
          { ticker: "FLEX",  name: "Flex Ltd. (Singapore)" },
          { ticker: "BEPC",  name: "Brookfield Renewable (Canada)" },
        ],
      },
    ],
  },
];

// 모든 기업 flat list (검색용)
const ALL_COMPANIES: (CompanyEntry & { country: string; sector: string })[] =
  COUNTRY_GROUPS.flatMap((cg) =>
    cg.sectors.flatMap((sec) =>
      sec.companies.map((c) => ({
        ...c,
        country: cg.label,
        sector:  sec.label,
      }))
    )
  );

// 파라미터 설명 텍스트
const PARAM_DESCRIPTIONS: Record<string, string> = {
  shockIntensity:
    "이 기업에 얼마나 큰 위기가 터졌나요?\n1.0 = 공장 전면 중단·파산 같은 최악의 상황\n0.5 = 생산 일부 차질, 원자재 수급 불안\n0.1 = 가벼운 납기 지연 수준",
  decayLambda:
    "위기가 시간이 지나면서 얼마나 빠르게 회복되나요?\n값이 작을수록(0.01) → 한 달이 지나도 충격이 남아있음 (장기 위기)\n값이 클수록(0.5) → 3~4일 만에 사실상 정상화 (단기 충격)",
  timeHorizon:
    "앞으로 며칠치 리스크 변화를 예측할까요?\n30일이면 한 달간, 90일이면 3개월간 공급망 영향을 분석합니다.",
  maxHop:
    "위기가 공급망을 타고 몇 단계까지 퍼지는지 추적합니다.\n1단계 = 직접 거래 기업만\n3단계 = 협력사의 협력사까지\n8단계 = 원자재 → 부품 → 조립 → 완성품 전체 체인",
};

export default function ControlSidebar({
  params,
  isLoading,
  onParamsChange,
  onRunSimulation,
  playbackDay,
  isPlaying,
  hasSimResult,
  onPlayToggle,
  onPlaybackReset,
}: ControlSidebarProps) {
  const [companyOpen,      setCompanyOpen]      = useState(false);
  const [selectedCountry,  setSelectedCountry]  = useState<string | null>(null);
  const [selectedSector,   setSelectedSector]   = useState<string | null>(null);
  const [searchQuery,      setSearchQuery]       = useState("");
  const [infoOpen,         setInfoOpen]          = useState<string | null>(null);

  // AI 공급망 발견
  const [isDiscovering,   setIsDiscovering]   = useState(false);
  const [discoverResult,  setDiscoverResult]  = useState<DiscoverResult | null>(null);
  const [discoverError,   setDiscoverError]   = useState<string | null>(null);

  // 뉴스 충격 분석
  const [newsOpen,         setNewsOpen]         = useState(false);
  const [newsText,         setNewsText]         = useState("");
  const [isAnalyzingNews,  setIsAnalyzingNews]  = useState(false);
  const [newsResult,       setNewsResult]       = useState<NewsShockResult | null>(null);
  const [newsError,        setNewsError]        = useState<string | null>(null);

  const isSearchMode = searchQuery.trim().length > 0;
  const searchResults = isSearchMode
    ? ALL_COMPANIES.filter(
        (c) =>
          c.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
          c.name.toLowerCase().includes(searchQuery.toLowerCase())
      ).slice(0, 30)
    : [];

  // 선택된 국가 그룹
  const activeCountry = COUNTRY_GROUPS.find((cg) => cg.label === selectedCountry) ?? null;
  // 선택된 섹터
  const activeSector = activeCountry?.sectors.find((s) => s.label === selectedSector) ?? null;

  const handleSelectTicker = (ticker: string) => {
    onParamsChange({ ticker });
    setCompanyOpen(false);
    setSearchQuery("");
    setSelectedCountry(null);
    setSelectedSector(null);
  };

  const handleCountryClick = (country: string) => {
    setSelectedCountry(country === selectedCountry ? null : country);
    setSelectedSector(null);
  };

  // AI 공급망 발견 핸들러
  const handleDiscover = async () => {
    if (!params.ticker.trim()) return;
    setIsDiscovering(true);
    setDiscoverResult(null);
    setDiscoverError(null);
    try {
      const result = await discoverSupplyChain(params.ticker);
      setDiscoverResult(result);
    } catch (e) {
      setDiscoverError(
        e instanceof ApiError ? e.message : "LLM 분석 중 오류가 발생했습니다.",
      );
    } finally {
      setIsDiscovering(false);
    }
  };

  // 뉴스 충격 분석 핸들러
  const handleNewsAnalyze = async () => {
    if (!newsText.trim()) return;
    setIsAnalyzingNews(true);
    setNewsResult(null);
    setNewsError(null);
    try {
      const result = await analyzeNewsShock(newsText);
      setNewsResult(result);
    } catch (e) {
      setNewsError(
        e instanceof ApiError ? e.message : "뉴스 분석 중 오류가 발생했습니다.",
      );
    } finally {
      setIsAnalyzingNews(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="px-4 py-4 border-b border-border">
        <p className="text-sm font-bold text-text-primary">리스크 시뮬레이션</p>
        <p className="text-xs text-text-secondary mt-0.5">기업을 선택하고 위기 상황을 설정하세요</p>
      </div>

      <div className="flex-1 px-4 py-4 space-y-5 overflow-y-auto">

        {/* ── 기업 선택 (국가 → 섹터 → 기업) ── */}
        <div>
          <label className="section-title">위기 발생 기업 선택</label>

          {/* 드롭다운 토글 버튼 */}
          <button
            type="button"
            onClick={() => { setCompanyOpen(!companyOpen); setSearchQuery(""); }}
            className="w-full flex items-center justify-between px-3 py-2.5
                       bg-bg-subtle border border-border rounded-lg text-sm
                       font-medium text-text-primary hover:bg-bg-hover transition-colors"
          >
            <span className={params.ticker ? "text-text-primary" : "text-text-tertiary"}>
              {params.ticker || "국가 → 섹터 → 기업 선택"}
            </span>
            {companyOpen
              ? <ChevronUp size={14} className="text-text-tertiary" />
              : <ChevronDown size={14} className="text-text-tertiary" />}
          </button>

          {/* 드롭다운 패널 */}
          {companyOpen && (
            <div className="mt-1 border border-border rounded-lg bg-white shadow-panel overflow-hidden">

              {/* 검색 */}
              <div className="relative px-2 pt-2 pb-1 border-b border-border bg-bg-subtle">
                <Search size={11} className="absolute left-4 top-[18px] text-text-tertiary" />
                <input
                  type="text"
                  placeholder="티커 또는 기업명 검색..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-7 pr-2 py-1.5 text-xs bg-white border border-border
                             rounded focus:outline-none focus:border-primary"
                  autoFocus
                />
              </div>

              {isSearchMode ? (
                /* 검색 결과 */
                <div className="max-h-60 overflow-y-auto">
                  {searchResults.length === 0 ? (
                    <p className="text-center text-xs text-text-tertiary py-4">결과 없음</p>
                  ) : (
                    searchResults.map((c) => (
                      <button
                        key={`${c.ticker}-${c.country}`}
                        type="button"
                        onClick={() => handleSelectTicker(c.ticker)}
                        className={cn(
                          "w-full flex items-center justify-between px-3 py-1.5 text-xs hover:bg-bg-hover transition-colors border-b border-border/30 last:border-0",
                          params.ticker === c.ticker && "bg-primary-light text-primary font-semibold"
                        )}
                      >
                        <span className="font-mono font-bold w-14 shrink-0">{c.ticker}</span>
                        <span className="text-text-secondary truncate flex-1 mx-1">{c.name}</span>
                        <span className="text-[9px] text-text-tertiary shrink-0">{c.country}</span>
                      </button>
                    ))
                  )}
                </div>
              ) : (
                /* 3단계: 국가 → 섹터 → 기업 */
                <div style={{ maxHeight: "320px" }} className="flex flex-col">

                  {/* 1단계: 국가 선택 */}
                  <div className="flex border-b border-border">
                    {COUNTRY_GROUPS.map((cg) => (
                      <button
                        key={cg.label}
                        type="button"
                        onClick={() => handleCountryClick(cg.label)}
                        className={cn(
                          "flex-1 flex flex-col items-center py-2 px-1 text-center text-[10px] font-medium transition-colors border-r border-border last:border-r-0",
                          selectedCountry === cg.label
                            ? "bg-primary-light text-primary border-b-2 border-b-primary"
                            : "text-text-secondary hover:bg-bg-hover"
                        )}
                      >
                        <span className="text-base">{cg.flag}</span>
                        <span className="mt-0.5">{cg.label}</span>
                      </button>
                    ))}
                  </div>

                  {!selectedCountry ? (
                    <div className="flex items-center justify-center py-6">
                      <p className="text-xs text-text-tertiary">국가를 선택하세요</p>
                    </div>
                  ) : (
                    <div className="flex flex-1 overflow-hidden">

                      {/* 2단계: 섹터 선택 */}
                      <div className="w-24 shrink-0 border-r border-border overflow-y-auto bg-bg-subtle">
                        {activeCountry?.sectors.map((sec) => (
                          <button
                            key={sec.label}
                            type="button"
                            onClick={() => setSelectedSector(sec.label)}
                            className={cn(
                              "w-full text-left px-2 py-2 text-[10px] leading-tight border-b border-border/50 last:border-0 transition-colors",
                              selectedSector === sec.label
                                ? "bg-primary-light text-primary font-semibold"
                                : "text-text-secondary hover:bg-bg-hover"
                            )}
                          >
                            {sec.label}
                          </button>
                        ))}
                      </div>

                      {/* 3단계: 기업 목록 */}
                      <div className="flex-1 overflow-y-auto">
                        {!selectedSector ? (
                          <div className="flex items-center justify-center h-full">
                            <p className="text-[10px] text-text-tertiary text-center px-2">
                              섹터를<br/>선택하세요
                            </p>
                          </div>
                        ) : (
                          activeSector?.companies.map((c) => (
                            <button
                              key={c.ticker}
                              type="button"
                              onClick={() => handleSelectTicker(c.ticker)}
                              className={cn(
                                "w-full flex items-center gap-1.5 px-2 py-1.5 text-xs hover:bg-bg-hover transition-colors border-b border-border/30 last:border-0",
                                params.ticker === c.ticker && "bg-primary-light text-primary font-semibold"
                              )}
                            >
                              <span className="font-mono font-bold text-[11px] w-14 shrink-0">{c.ticker}</span>
                              <span className="text-text-secondary text-[10px] truncate">{c.name}</span>
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 직접 입력 */}
          <input
            type="text"
            placeholder="또는 직접 입력 (예: MSFT)"
            value={params.ticker}
            onChange={(e) => onParamsChange({ ticker: e.target.value.toUpperCase() })}
            className="mt-2 w-full px-3 py-2 text-sm bg-bg-subtle border border-border
                       rounded-lg placeholder:text-text-tertiary focus:outline-none
                       focus:border-primary focus:ring-1 focus:ring-primary/20"
          />
        </div>

        {/* ── Shock Intensity ── */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1">
              <label className="section-title mb-0">위기 심각도</label>
              <button
                type="button"
                onClick={() => setInfoOpen(infoOpen === "shockIntensity" ? null : "shockIntensity")}
                className="text-text-tertiary hover:text-primary transition-colors"
              >
                <Info size={11} />
              </button>
            </div>
            <span className="text-xs font-bold text-primary bg-primary-light px-2 py-0.5 rounded-pill">
              {params.shockIntensity.toFixed(2)}
            </span>
          </div>
          <p className="text-[10px] text-text-tertiary mb-1.5">이 기업에 얼마나 큰 충격이 발생했나요?</p>
          {infoOpen === "shockIntensity" && (
            <p className="text-[10px] text-text-secondary bg-bg-subtle rounded p-2 mb-1.5 leading-relaxed whitespace-pre-line">
              {PARAM_DESCRIPTIONS.shockIntensity}
            </p>
          )}
          <input
            type="range" min={0} max={1} step={0.05}
            value={params.shockIntensity}
            onChange={(e) => onParamsChange({ shockIntensity: parseFloat(e.target.value) })}
          />
          <div className="flex justify-between text-[10px] text-text-tertiary mt-0.5">
            <span>가벼운 지연</span><span>부분 차질</span><span>최악 상황</span>
          </div>
        </div>

        {/* ── Decay Lambda ── */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1">
              <label className="section-title mb-0">충격 회복 속도</label>
              <button
                type="button"
                onClick={() => setInfoOpen(infoOpen === "decayLambda" ? null : "decayLambda")}
                className="text-text-tertiary hover:text-primary transition-colors"
              >
                <Info size={11} />
              </button>
            </div>
            <span className="text-xs font-bold text-primary bg-primary-light px-2 py-0.5 rounded-pill">
              {params.decayLambda.toFixed(2)}
            </span>
          </div>
          <p className="text-[10px] text-text-tertiary mb-1.5">위기가 시간이 지나면서 얼마나 빨리 회복되나요?</p>
          {infoOpen === "decayLambda" && (
            <p className="text-[10px] text-text-secondary bg-bg-subtle rounded p-2 mb-1.5 leading-relaxed whitespace-pre-line">
              {PARAM_DESCRIPTIONS.decayLambda}
            </p>
          )}
          <input
            type="range" min={0.01} max={0.5} step={0.01}
            value={params.decayLambda}
            onChange={(e) => onParamsChange({ decayLambda: parseFloat(e.target.value) })}
          />
          <div className="flex justify-between text-[10px] text-text-tertiary mt-0.5">
            <span>느린 회복 (장기)</span><span>빠른 회복 (단기)</span>
          </div>
        </div>

        {/* ── Time Horizon ── */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1">
              <label className="section-title mb-0">예측 기간</label>
              <button
                type="button"
                onClick={() => setInfoOpen(infoOpen === "timeHorizon" ? null : "timeHorizon")}
                className="text-text-tertiary hover:text-primary transition-colors"
              >
                <Info size={11} />
              </button>
            </div>
            <span className="text-xs font-bold text-primary bg-primary-light px-2 py-0.5 rounded-pill">
              {params.timeHorizon}일
            </span>
          </div>
          <p className="text-[10px] text-text-tertiary mb-1.5">앞으로 며칠치 파급 효과를 예측할까요?</p>
          {infoOpen === "timeHorizon" && (
            <p className="text-[10px] text-text-secondary bg-bg-subtle rounded p-2 mb-1.5 leading-relaxed whitespace-pre-line">
              {PARAM_DESCRIPTIONS.timeHorizon}
            </p>
          )}
          <input
            type="range" min={1} max={90} step={1}
            value={params.timeHorizon}
            onChange={(e) => onParamsChange({ timeHorizon: parseInt(e.target.value) })}
          />
          <div className="flex justify-between text-[10px] text-text-tertiary mt-0.5">
            <span>1일</span><span>1개월</span><span>3개월</span>
          </div>

          {/* ── 타임라인 재생 컨트롤 ── */}
          <div className="mt-2 flex items-center gap-2 p-2 bg-bg-subtle rounded-lg border border-border">
            <button
              type="button"
              onClick={onPlayToggle}
              disabled={!hasSimResult}
              title={isPlaying ? "일시정지" : "재생 — 예측 기간 동안 리스크 변화 애니메이션"}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold transition-colors",
                hasSimResult
                  ? isPlaying
                    ? "bg-amber-500 text-white hover:bg-amber-600"
                    : "bg-primary text-white hover:bg-primary/90"
                  : "bg-bg-subtle text-text-tertiary cursor-not-allowed",
              )}
            >
              {isPlaying
                ? <><Pause size={10} fill="currentColor" /><span>일시정지</span></>
                : <><Play  size={10} fill="currentColor" /><span>재생</span></>
              }
            </button>

            {/* 현재 날짜 표시 */}
            <div className="flex-1 text-center">
              <span className="text-[11px] font-bold text-primary">
                {playbackDay}
              </span>
              <span className="text-[10px] text-text-tertiary">
                /{params.timeHorizon}일
              </span>
              {/* 진행 바 */}
              <div className="w-full h-1 bg-border rounded-pill mt-0.5 overflow-hidden">
                <div
                  className="h-full bg-primary rounded-pill transition-all duration-100"
                  style={{ width: `${Math.min((playbackDay / params.timeHorizon) * 100, 100)}%` }}
                />
              </div>
            </div>

            {/* 리셋 */}
            <button
              type="button"
              onClick={onPlaybackReset}
              disabled={playbackDay === 0 && !isPlaying}
              title="처음으로"
              className="w-7 h-7 flex items-center justify-center rounded-lg
                         text-text-tertiary hover:text-primary hover:bg-bg-hover transition-colors
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <RotateCcw size={12} />
            </button>
          </div>
          {!hasSimResult && (
            <p className="text-[9px] text-text-tertiary text-center mt-0.5">
              시뮬레이션 실행 후 재생 가능
            </p>
          )}
        </div>

        {/* ── Max Hop ── */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1">
              <label className="section-title mb-0">영향 범위</label>
              <button
                type="button"
                onClick={() => setInfoOpen(infoOpen === "maxHop" ? null : "maxHop")}
                className="text-text-tertiary hover:text-primary transition-colors"
              >
                <Info size={11} />
              </button>
            </div>
            <span className="text-xs font-bold text-primary bg-primary-light px-2 py-0.5 rounded-pill">
              {params.maxHop}단계
            </span>
          </div>
          <p className="text-[10px] text-text-tertiary mb-1.5">위기가 공급망을 타고 몇 단계까지 퍼지는지 추적합니다.</p>
          {infoOpen === "maxHop" && (
            <p className="text-[10px] text-text-secondary bg-bg-subtle rounded p-2 mb-1.5 leading-relaxed whitespace-pre-line">
              {PARAM_DESCRIPTIONS.maxHop}
            </p>
          )}
          <input
            type="range" min={1} max={8} step={1}
            value={params.maxHop}
            onChange={(e) => onParamsChange({ maxHop: parseInt(e.target.value) })}
          />
          <div className="flex justify-between text-[10px] text-text-tertiary mt-0.5">
            {[1,2,3,4,5,6,7,8].map((n) => (
              <span key={n} className={cn("text-center w-4", params.maxHop === n && "text-primary font-bold")}>
                {n}
              </span>
            ))}
          </div>
          {/* 단계 설명 */}
          <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-0.5">
            {[
              ["1~2단계", "직접 거래 기업"],
              ["3~4단계", "협력사의 협력사"],
              ["5~6단계", "OEM·물류 업체"],
              ["7~8단계", "글로벌 전체 체인"],
            ].map(([step, desc]) => (
              <div key={step} className="flex items-center gap-1">
                <span className="text-[9px] font-bold text-primary">{step}</span>
                <span className="text-[9px] text-text-tertiary">{desc}</span>
              </div>
            ))}
          </div>
        </div>
        {/* ── AI 공급망 자동 발견 ── */}
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="px-3 py-2.5 bg-gradient-to-r from-primary-light to-blue-50 flex items-center gap-1.5">
            <Sparkles size={12} className="text-primary shrink-0" />
            <span className="text-xs font-bold text-primary">AI 공급망 자동 발견</span>
          </div>
          <div className="px-3 py-3 space-y-2.5">
            <p className="text-[10px] text-text-secondary leading-relaxed">
              LLM이 해당 기업의 주요 공급사·구매사를 자동 추정하여 그래프에 추가합니다.
              <span className="text-blue-600 font-medium"> 한국 주식(6자리)은 DART 사업보고서를 실제로 분석합니다.</span>
              {" "}이후 시뮬레이션 실행 시 발견된 기업들이 포함됩니다.
            </p>

            {/* 발견 버튼 */}
            <button
              type="button"
              onClick={handleDiscover}
              disabled={!params.ticker.trim() || isDiscovering}
              className={cn(
                "w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-colors",
                params.ticker.trim() && !isDiscovering
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-bg-subtle text-text-tertiary cursor-not-allowed",
              )}
            >
              {isDiscovering ? (
                <>
                  <Loader2 size={11} className="animate-spin" />
                  <span>
                    {/^\d{6}$/.test(params.ticker) ? "DART+LLM 분석 중..." : "LLM 분석 중..."}
                  </span>
                </>
              ) : (
                <>
                  <Sparkles size={11} />
                  <span>{params.ticker ? `${params.ticker} 공급망 발견` : "기업 먼저 선택"}</span>
                </>
              )}
            </button>

            {/* 발견 결과 */}
            {discoverResult && (
              <div className="bg-green-50 border border-green-200 rounded-lg px-2.5 py-2 space-y-1.5">
                {/* 헤더: 관계 수 + 데이터 출처 뱃지 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 size={11} className="text-green-600 shrink-0" />
                    <span className="text-[11px] font-semibold text-green-700">
                      {discoverResult.relations_saved}개 관계 저장 완료
                    </span>
                  </div>
                  <span className={cn(
                    "text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0",
                    discoverResult.data_source?.includes("DART")
                      ? "bg-blue-100 text-blue-700"
                      : "bg-gray-100 text-gray-500"
                  )}>
                    {discoverResult.data_source ?? "LLM"}
                  </span>
                </div>

                {/* 공급사 / 구매사 수 */}
                <div className="flex gap-3 text-[10px] text-green-600">
                  <span>↑ 공급사 {discoverResult.suppliers.length}개</span>
                  <span>↓ 구매사 {discoverResult.buyers.length}개</span>
                </div>

                {/* DART 재무 데이터 (한국 주식에서만 표시) */}
                {discoverResult.dart_financial && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg px-2.5 py-2">
                    <p className="text-[9px] font-bold text-blue-700 mb-1.5 uppercase tracking-wide">
                      DART 재무데이터 ({discoverResult.dart_financial.year}년)
                    </p>
                    <div className="space-y-1">
                      {discoverResult.dart_financial.revenue != null && (
                        <div className="flex justify-between text-[9px]">
                          <span className="text-blue-600">매출액</span>
                          <span className="font-bold text-blue-800">
                            {discoverResult.dart_financial.revenue >= 1_000_000
                              ? `${(discoverResult.dart_financial.revenue / 1_000_000).toFixed(1)}조원`
                              : `${Math.round(discoverResult.dart_financial.revenue / 100).toLocaleString()}억원`}
                          </span>
                        </div>
                      )}
                      {discoverResult.dart_financial.operating_income != null && (
                        <div className="flex justify-between text-[9px]">
                          <span className="text-blue-600">영업이익</span>
                          <span className="font-bold text-blue-800">
                            {discoverResult.dart_financial.operating_income >= 1_000_000
                              ? `${(discoverResult.dart_financial.operating_income / 1_000_000).toFixed(1)}조원`
                              : `${Math.round(discoverResult.dart_financial.operating_income / 100).toLocaleString()}억원`}
                          </span>
                        </div>
                      )}
                      {discoverResult.dart_financial.liquidity_score != null && (
                        <div className="flex justify-between text-[9px]">
                          <span className="text-blue-600">유동성 점수 (ROE 기반)</span>
                          <span className={cn(
                            "font-bold",
                            discoverResult.dart_financial.liquidity_score >= 0.6 ? "text-green-600"
                              : discoverResult.dart_financial.liquidity_score >= 0.4 ? "text-amber-600"
                              : "text-red-600"
                          )}>
                            {(discoverResult.dart_financial.liquidity_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 요약 */}
                <p className="text-[10px] text-text-secondary leading-relaxed border-t border-green-200 pt-1">
                  {discoverResult.summary}
                </p>
              </div>
            )}

            {/* 발견 오류 */}
            {discoverError && (
              <div className="flex items-start gap-1.5 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
                <AlertCircle size={11} className="text-red-500 shrink-0 mt-0.5" />
                <p className="text-[10px] text-red-600">{discoverError}</p>
              </div>
            )}

            {/* 뉴스 충격 분석 토글 */}
            <button
              type="button"
              onClick={() => { setNewsOpen(!newsOpen); setNewsResult(null); setNewsError(null); }}
              className="w-full flex items-center justify-between px-2.5 py-1.5
                         rounded-lg text-[10px] font-medium text-text-secondary
                         bg-bg-subtle hover:bg-bg-hover transition-colors border border-border/60"
            >
              <span className="flex items-center gap-1">
                <Newspaper size={10} />
                뉴스 충격 분석
              </span>
              {newsOpen ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            </button>

            {/* 뉴스 분석 패널 */}
            {newsOpen && (
              <div className="space-y-2">
                <textarea
                  value={newsText}
                  onChange={(e) => setNewsText(e.target.value)}
                  placeholder="뉴스 기사 텍스트를 붙여넣으세요...&#10;(예: 러시아-우크라이나 전쟁 확전으로 방산주 급등, 에너지 공급 불안...)"
                  rows={4}
                  className="w-full px-2.5 py-2 text-[10px] bg-white border border-border rounded-lg
                             placeholder:text-text-tertiary focus:outline-none focus:border-primary
                             resize-none leading-relaxed"
                />

                <button
                  type="button"
                  onClick={handleNewsAnalyze}
                  disabled={!newsText.trim() || isAnalyzingNews}
                  className={cn(
                    "w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-semibold transition-colors",
                    newsText.trim() && !isAnalyzingNews
                      ? "bg-amber-500 text-white hover:bg-amber-600"
                      : "bg-bg-subtle text-text-tertiary cursor-not-allowed",
                  )}
                >
                  {isAnalyzingNews ? (
                    <>
                      <Loader2 size={10} className="animate-spin" />
                      <span>분석 중...</span>
                    </>
                  ) : (
                    <>
                      <Newspaper size={10} />
                      <span>충격 기업 분석</span>
                    </>
                  )}
                </button>

                {/* 뉴스 분석 결과 */}
                {newsResult && (
                  <div className="space-y-1.5">
                    <div className="bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2">
                      <p className="text-[10px] font-bold text-amber-700">{newsResult.event_title}</p>
                      <p className="text-[9px] text-amber-600 capitalize">{newsResult.event_category}</p>
                    </div>
                    <p className="text-[9px] font-semibold text-text-tertiary uppercase tracking-wide">
                      영향 기업 클릭 → 자동 설정
                    </p>
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {newsResult.affected_companies.map((c) => (
                        <button
                          key={c.ticker}
                          type="button"
                          onClick={() => onParamsChange({
                            ticker:         c.ticker,
                            shockIntensity: Math.round(c.shock_intensity * 100) / 100,
                          })}
                          className={cn(
                            "w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-left text-[10px]",
                            "hover:bg-amber-50 border border-transparent hover:border-amber-200 transition-colors",
                            params.ticker === c.ticker && "bg-amber-50 border-amber-300 font-semibold",
                          )}
                        >
                          <div
                            className="w-1.5 h-6 rounded-sm shrink-0"
                            style={{
                              backgroundColor:
                                c.shock_intensity >= 0.6 ? "#EF4444"
                                : c.shock_intensity >= 0.3 ? "#F59E0B"
                                : "#10B981",
                            }}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1">
                              <span className="font-mono font-bold text-text-primary">{c.ticker}</span>
                              <span className="text-[9px] text-text-tertiary truncate">{c.name}</span>
                            </div>
                            <p className="text-[9px] text-text-tertiary truncate">{c.reason}</p>
                          </div>
                          <span className="text-[10px] font-bold shrink-0"
                            style={{
                              color: c.shock_intensity >= 0.6 ? "#EF4444"
                                : c.shock_intensity >= 0.3 ? "#F59E0B" : "#10B981"
                            }}
                          >
                            {(c.shock_intensity * 100).toFixed(0)}%
                          </span>
                        </button>
                      ))}
                    </div>
                    <p className="text-[9px] text-text-secondary leading-relaxed border-t border-border pt-1">
                      {newsResult.summary}
                    </p>
                  </div>
                )}

                {/* 뉴스 분석 오류 */}
                {newsError && (
                  <div className="flex items-start gap-1.5 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
                    <AlertCircle size={10} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-[10px] text-red-600">{newsError}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Run 버튼 */}
      <div className="px-4 py-4 border-t border-border">
        <button
          type="button"
          onClick={onRunSimulation}
          disabled={!params.ticker || isLoading}
          className="btn-primary flex items-center justify-center gap-2"
        >
          {isLoading
            ? <RefreshCw size={15} className="animate-spin" />
            : <Play size={15} fill="currentColor" />}
          {isLoading ? "시뮬레이션 중..." : "시뮬레이션 실행"}
        </button>
      </div>
    </div>
  );
}
