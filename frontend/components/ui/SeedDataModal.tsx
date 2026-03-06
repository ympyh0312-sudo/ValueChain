"use client";

import { useState } from "react";
import { X, Database, CheckCircle, AlertTriangle, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { createCompany, createRelation } from "@/lib/api";
import type { CompanyCreate, SupplyRelationCreate } from "@/lib/types";

// ═══════════════════════════════════════════════════════════════════════════
// 미국 전 섹터 공급망 샘플 데이터 (8-hop 체인 지원)
// EMN→SHNEY→TSMC→NVDA→HNHPF→DELL→MSFT→SAP (7홉)
// SLB→XOM→NEE→VRT→AMZN→CRM (5홉 · 에너지→클라우드)
// IQVIA→LLY→CVS→MSFT→NOW (4홉 · 헬스케어→SaaS)
// MMC→GS→V→AMZN→ORCL (4홉 · 금융→클라우드)
// ═══════════════════════════════════════════════════════════════════════════

const SAMPLE_COMPANIES: CompanyCreate[] = [
  // ── Lv0 원자재·특수가스 ───────────────────────────────
  { ticker: "APD",    name: "Air Products & Chemicals",  sector: "Chemicals",               country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.30 },
  { ticker: "LIN",    name: "Linde plc",                 sector: "Chemicals",               country: "UK",          liquidity_score: 0.67, supplier_concentration: 0.25 },
  { ticker: "EMN",    name: "Eastman Chemical",          sector: "Chemicals",               country: "USA",         liquidity_score: 0.58, supplier_concentration: 0.32 },
  // ── Lv1 웨이퍼·소재 ──────────────────────────────────
  { ticker: "SHNEY",  name: "Shin-Etsu Chemical",        sector: "Semiconductor Materials", country: "Japan",       liquidity_score: 0.60, supplier_concentration: 0.28 },
  { ticker: "SUOPY",  name: "SUMCO Corporation",         sector: "Semiconductor Materials", country: "Japan",       liquidity_score: 0.56, supplier_concentration: 0.35 },
  { ticker: "WFRD",   name: "Merck KGaA (Semicon)",      sector: "Semiconductor Materials", country: "Germany",     liquidity_score: 0.58, supplier_concentration: 0.38 },
  // ── Lv2 반도체 장비 ───────────────────────────────────
  { ticker: "ASML",   name: "ASML Holding",              sector: "Semiconductor Equipment", country: "Netherlands", liquidity_score: 0.65, supplier_concentration: 0.30 },
  { ticker: "AMAT",   name: "Applied Materials",         sector: "Semiconductor Equipment", country: "USA",         liquidity_score: 0.66, supplier_concentration: 0.33 },
  { ticker: "LRCX",   name: "Lam Research",              sector: "Semiconductor Equipment", country: "USA",         liquidity_score: 0.64, supplier_concentration: 0.36 },
  { ticker: "KLAC",   name: "KLA Corporation",           sector: "Semiconductor Equipment", country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.33 },
  { ticker: "TOELY",  name: "Tokyo Electron",            sector: "Semiconductor Equipment", country: "Japan",       liquidity_score: 0.60, supplier_concentration: 0.32 },
  // ── Lv3 파운드리·메모리 ──────────────────────────────
  { ticker: "TSMC",   name: "Taiwan Semiconductor Mfg",  sector: "Semiconductors",         country: "Taiwan",      liquidity_score: 0.70, supplier_concentration: 0.38 },
  { ticker: "INTC",   name: "Intel Corporation",         sector: "Semiconductors",          country: "USA",         liquidity_score: 0.58, supplier_concentration: 0.48 },
  { ticker: "UMC",    name: "United Microelectronics",   sector: "Semiconductors",          country: "Taiwan",      liquidity_score: 0.54, supplier_concentration: 0.52 },
  { ticker: "005930", name: "Samsung Electronics",       sector: "Technology",              country: "South Korea", liquidity_score: 0.72, supplier_concentration: 0.42 },
  { ticker: "000660", name: "SK Hynix",                  sector: "Semiconductors",          country: "South Korea", liquidity_score: 0.63, supplier_concentration: 0.55 },
  { ticker: "MU",     name: "Micron Technology",         sector: "Semiconductors",          country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.58 },
  // ── Lv4 팹리스 반도체 ────────────────────────────────
  { ticker: "NVDA",   name: "NVIDIA Corporation",        sector: "Semiconductors",          country: "USA",         liquidity_score: 0.75, supplier_concentration: 0.78 },
  { ticker: "AMD",    name: "Advanced Micro Devices",    sector: "Semiconductors",          country: "USA",         liquidity_score: 0.66, supplier_concentration: 0.80 },
  { ticker: "QCOM",   name: "Qualcomm Inc.",             sector: "Semiconductors",          country: "USA",         liquidity_score: 0.67, supplier_concentration: 0.60 },
  { ticker: "AVGO",   name: "Broadcom Inc.",             sector: "Semiconductors",          country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.55 },
  { ticker: "MRVL",   name: "Marvell Technology",        sector: "Semiconductors",          country: "USA",         liquidity_score: 0.59, supplier_concentration: 0.70 },
  { ticker: "ADI",    name: "Analog Devices Inc.",       sector: "Semiconductors",          country: "USA",         liquidity_score: 0.64, supplier_concentration: 0.45 },
  { ticker: "TXN",    name: "Texas Instruments",         sector: "Semiconductors",          country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.40 },
  { ticker: "SWKS",   name: "Skyworks Solutions",        sector: "Semiconductors",          country: "USA",         liquidity_score: 0.60, supplier_concentration: 0.65 },
  { ticker: "NXPI",   name: "NXP Semiconductors",        sector: "Semiconductors",          country: "Netherlands", liquidity_score: 0.61, supplier_concentration: 0.50 },
  { ticker: "ON",     name: "ON Semiconductor",          sector: "Semiconductors",          country: "USA",         liquidity_score: 0.58, supplier_concentration: 0.48 },
  { ticker: "STM",    name: "STMicroelectronics",        sector: "Semiconductors",          country: "Switzerland", liquidity_score: 0.59, supplier_concentration: 0.50 },
  { ticker: "IFNNY",  name: "Infineon Technologies",     sector: "Semiconductors",          country: "Germany",     liquidity_score: 0.60, supplier_concentration: 0.49 },
  // ── Lv5 전자부품·소재 ────────────────────────────────
  { ticker: "MRAAY",  name: "Murata Manufacturing",      sector: "Electronic Components",   country: "Japan",       liquidity_score: 0.59, supplier_concentration: 0.40 },
  { ticker: "TTDKY",  name: "TDK Corporation",           sector: "Electronic Components",   country: "Japan",       liquidity_score: 0.57, supplier_concentration: 0.44 },
  { ticker: "GLW",    name: "Corning Inc.",               sector: "Electronic Components",   country: "USA",         liquidity_score: 0.61, supplier_concentration: 0.38 },
  { ticker: "APH",    name: "Amphenol Corporation",      sector: "Electronic Components",   country: "USA",         liquidity_score: 0.63, supplier_concentration: 0.35 },
  { ticker: "034220", name: "LG Display",                sector: "Electronic Components",   country: "South Korea", liquidity_score: 0.55, supplier_concentration: 0.55 },
  { ticker: "009150", name: "Samsung Electro-Mechanics", sector: "Electronic Components",   country: "South Korea", liquidity_score: 0.59, supplier_concentration: 0.48 },
  { ticker: "051910", name: "LG Chem",                   sector: "Chemicals",               country: "South Korea", liquidity_score: 0.61, supplier_concentration: 0.44 },
  { ticker: "373220", name: "LG Energy Solution",        sector: "Automotive Components",   country: "South Korea", liquidity_score: 0.63, supplier_concentration: 0.60 },
  { ticker: "006400", name: "Samsung SDI",               sector: "Automotive Components",   country: "South Korea", liquidity_score: 0.62, supplier_concentration: 0.58 },
  { ticker: "HNHPF",  name: "Hon Hai (Foxconn)",         sector: "Electronic Manufacturing",country: "Taiwan",      liquidity_score: 0.58, supplier_concentration: 0.65 },
  { ticker: "JBL",    name: "Jabil Inc.",                 sector: "Electronic Manufacturing",country: "USA",         liquidity_score: 0.56, supplier_concentration: 0.60 },
  { ticker: "FLEX",   name: "Flex Ltd.",                  sector: "Electronic Manufacturing",country: "Singapore",   liquidity_score: 0.55, supplier_concentration: 0.63 },
  // ── Lv6 OEM·네트워크 ──────────────────────────────────
  { ticker: "AAPL",   name: "Apple Inc.",                 sector: "Technology",              country: "USA",         liquidity_score: 0.80, supplier_concentration: 0.50 },
  { ticker: "DELL",   name: "Dell Technologies",          sector: "Technology",              country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.60 },
  { ticker: "HPQ",    name: "HP Inc.",                    sector: "Technology",              country: "USA",         liquidity_score: 0.63, supplier_concentration: 0.57 },
  { ticker: "066570", name: "LG Electronics",             sector: "Technology",              country: "South Korea", liquidity_score: 0.61, supplier_concentration: 0.55 },
  { ticker: "005380", name: "Hyundai Motor",              sector: "Automotive",              country: "South Korea", liquidity_score: 0.63, supplier_concentration: 0.53 },
  { ticker: "TSLA",   name: "Tesla Inc.",                 sector: "Automotive",              country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.60 },
  { ticker: "F",      name: "Ford Motor Company",         sector: "Automotive",              country: "USA",         liquidity_score: 0.57, supplier_concentration: 0.55 },
  { ticker: "RIVN",   name: "Rivian Automotive",          sector: "Automotive",              country: "USA",         liquidity_score: 0.48, supplier_concentration: 0.75 },
  { ticker: "CSCO",   name: "Cisco Systems",              sector: "Networking",              country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.40 },
  { ticker: "JNPR",   name: "Juniper Networks",           sector: "Networking",              country: "USA",         liquidity_score: 0.63, supplier_concentration: 0.47 },
  // ── Lv7 클라우드·빅테크 ──────────────────────────────
  { ticker: "MSFT",   name: "Microsoft Corporation",      sector: "Technology",              country: "USA",         liquidity_score: 0.78, supplier_concentration: 0.32 },
  { ticker: "AMZN",   name: "Amazon.com Inc.",            sector: "Technology",              country: "USA",         liquidity_score: 0.76, supplier_concentration: 0.35 },
  { ticker: "GOOGL",  name: "Alphabet Inc.",              sector: "Technology",              country: "USA",         liquidity_score: 0.77, supplier_concentration: 0.30 },
  { ticker: "META",   name: "Meta Platforms Inc.",        sector: "Technology",              country: "USA",         liquidity_score: 0.75, supplier_concentration: 0.38 },
  // ── Lv8 엔터프라이즈 SaaS ─────────────────────────────
  { ticker: "SAP",    name: "SAP SE",                     sector: "Enterprise Software",     country: "Germany",     liquidity_score: 0.68, supplier_concentration: 0.35 },
  { ticker: "ORCL",   name: "Oracle Corporation",         sector: "Enterprise Software",     country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.32 },
  { ticker: "CRM",    name: "Salesforce Inc.",            sector: "Enterprise Software",     country: "USA",         liquidity_score: 0.67, supplier_concentration: 0.38 },
  { ticker: "NOW",    name: "ServiceNow Inc.",            sector: "Enterprise Software",     country: "USA",         liquidity_score: 0.66, supplier_concentration: 0.40 },
  { ticker: "WDAY",   name: "Workday Inc.",               sector: "Enterprise Software",     country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.37 },
  { ticker: "ADBE",   name: "Adobe Inc.",                 sector: "Enterprise Software",     country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.34 },

  // ══════════════════ 에너지·전력 ══════════════════════
  { ticker: "XOM",    name: "ExxonMobil Corporation",     sector: "Oil & Gas",               country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.30 },
  { ticker: "CVX",    name: "Chevron Corporation",        sector: "Oil & Gas",               country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.32 },
  { ticker: "COP",    name: "ConocoPhillips",             sector: "Oil & Gas",               country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.35 },
  { ticker: "SLB",    name: "SLB (Schlumberger)",         sector: "Oil & Gas Services",      country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.40 },
  { ticker: "ENPH",   name: "Enphase Energy",             sector: "Renewable Energy",        country: "USA",         liquidity_score: 0.60, supplier_concentration: 0.55 },
  { ticker: "FSLR",   name: "First Solar Inc.",           sector: "Renewable Energy",        country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.50 },
  { ticker: "BEPC",   name: "Brookfield Renewable",       sector: "Renewable Energy",        country: "Canada",      liquidity_score: 0.63, supplier_concentration: 0.45 },
  { ticker: "ETN",    name: "Eaton Corporation",          sector: "Electrical Equipment",    country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.38 },
  { ticker: "GEV",    name: "GE Vernova Inc.",            sector: "Electrical Equipment",    country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.42 },
  { ticker: "VRT",    name: "Vertiv Holdings",            sector: "Electrical Equipment",    country: "USA",         liquidity_score: 0.58, supplier_concentration: 0.50 },
  { ticker: "ABB",    name: "ABB Ltd.",                   sector: "Electrical Equipment",    country: "Switzerland", liquidity_score: 0.65, supplier_concentration: 0.40 },
  { ticker: "NEE",    name: "NextEra Energy Inc.",        sector: "Utilities",               country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.28 },
  { ticker: "DUK",    name: "Duke Energy Corporation",    sector: "Utilities",               country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.30 },
  { ticker: "SO",     name: "Southern Company",           sector: "Utilities",               country: "USA",         liquidity_score: 0.67, supplier_concentration: 0.32 },
  { ticker: "EXC",    name: "Exelon Corporation",         sector: "Utilities",               country: "USA",         liquidity_score: 0.66, supplier_concentration: 0.33 },
  { ticker: "AES",    name: "AES Corporation",            sector: "Power Generation",        country: "USA",         liquidity_score: 0.58, supplier_concentration: 0.45 },
  { ticker: "VST",    name: "Vistra Energy Corp.",        sector: "Power Generation",        country: "USA",         liquidity_score: 0.55, supplier_concentration: 0.50 },

  // ══════════════════ 헬스케어 ══════════════════════════
  { ticker: "AMGN",   name: "Amgen Inc.",                 sector: "Biotechnology",           country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.38 },
  { ticker: "REGN",   name: "Regeneron Pharmaceuticals",  sector: "Biotechnology",           country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.42 },
  { ticker: "VRTX",   name: "Vertex Pharmaceuticals",     sector: "Biotechnology",           country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.40 },
  { ticker: "LLY",    name: "Eli Lilly and Company",      sector: "Pharmaceuticals",         country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.42 },
  { ticker: "ABBV",   name: "AbbVie Inc.",                sector: "Pharmaceuticals",         country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.48 },
  { ticker: "PFE",    name: "Pfizer Inc.",                sector: "Pharmaceuticals",         country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.44 },
  { ticker: "JNJ",    name: "Johnson & Johnson",          sector: "Pharmaceuticals",         country: "USA",         liquidity_score: 0.75, supplier_concentration: 0.38 },
  { ticker: "MRK",    name: "Merck & Co. Inc.",           sector: "Pharmaceuticals",         country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.40 },
  { ticker: "MDT",    name: "Medtronic plc",              sector: "Medical Devices",         country: "USA",         liquidity_score: 0.67, supplier_concentration: 0.42 },
  { ticker: "ABT",    name: "Abbott Laboratories",        sector: "Medical Devices",         country: "USA",         liquidity_score: 0.69, supplier_concentration: 0.40 },
  { ticker: "SYK",    name: "Stryker Corporation",        sector: "Medical Devices",         country: "USA",         liquidity_score: 0.67, supplier_concentration: 0.44 },
  { ticker: "ISRG",   name: "Intuitive Surgical Inc.",    sector: "Medical Devices",         country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.38 },
  { ticker: "UNH",    name: "UnitedHealth Group Inc.",    sector: "Health Services",         country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.30 },
  { ticker: "HCA",    name: "HCA Healthcare Inc.",        sector: "Health Services",         country: "USA",         liquidity_score: 0.60, supplier_concentration: 0.45 },
  { ticker: "CVS",    name: "CVS Health Corporation",     sector: "Health Services",         country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.40 },
  { ticker: "IQVIA",  name: "IQVIA Holdings Inc.",        sector: "Health Services",         country: "USA",         liquidity_score: 0.63, supplier_concentration: 0.42 },

  // ══════════════════ 금융 ══════════════════════════════
  { ticker: "JPM",    name: "JPMorgan Chase & Co.",       sector: "Banking",                 country: "USA",         liquidity_score: 0.82, supplier_concentration: 0.25 },
  { ticker: "BAC",    name: "Bank of America Corp.",      sector: "Banking",                 country: "USA",         liquidity_score: 0.78, supplier_concentration: 0.28 },
  { ticker: "GS",     name: "Goldman Sachs Group Inc.",   sector: "Financial Services",      country: "USA",         liquidity_score: 0.80, supplier_concentration: 0.30 },
  { ticker: "MS",     name: "Morgan Stanley",             sector: "Financial Services",      country: "USA",         liquidity_score: 0.78, supplier_concentration: 0.32 },
  { ticker: "V",      name: "Visa Inc.",                  sector: "Financial Services",      country: "USA",         liquidity_score: 0.82, supplier_concentration: 0.22 },
  { ticker: "MA",     name: "Mastercard Incorporated",    sector: "Financial Services",      country: "USA",         liquidity_score: 0.81, supplier_concentration: 0.24 },
  { ticker: "PYPL",   name: "PayPal Holdings Inc.",       sector: "Financial Services",      country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.38 },
  { ticker: "AXP",    name: "American Express Company",   sector: "Financial Services",      country: "USA",         liquidity_score: 0.73, supplier_concentration: 0.35 },
  { ticker: "BLK",    name: "BlackRock Inc.",             sector: "Financial Services",      country: "USA",         liquidity_score: 0.80, supplier_concentration: 0.28 },
  { ticker: "MMC",    name: "Marsh McLennan Companies",   sector: "Insurance",               country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.35 },

  // ══════════════════ 소비·유통 ══════════════════════════
  { ticker: "WMT",    name: "Walmart Inc.",               sector: "Retail",                  country: "USA",         liquidity_score: 0.72, supplier_concentration: 0.22 },
  { ticker: "COST",   name: "Costco Wholesale Corp.",     sector: "Retail",                  country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.25 },
  { ticker: "TGT",    name: "Target Corporation",         sector: "Retail",                  country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.30 },
  { ticker: "HD",     name: "The Home Depot Inc.",        sector: "Retail",                  country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.28 },
  { ticker: "KO",     name: "The Coca-Cola Company",      sector: "Consumer Goods",          country: "USA",         liquidity_score: 0.75, supplier_concentration: 0.20 },
  { ticker: "PEP",    name: "PepsiCo Inc.",               sector: "Consumer Goods",          country: "USA",         liquidity_score: 0.73, supplier_concentration: 0.22 },
  { ticker: "PG",     name: "Procter & Gamble Co.",       sector: "Consumer Goods",          country: "USA",         liquidity_score: 0.74, supplier_concentration: 0.23 },
  { ticker: "NKE",    name: "NIKE Inc.",                  sector: "Consumer Goods",          country: "USA",         liquidity_score: 0.70, supplier_concentration: 0.35 },

  // ══════════════════ 산업·항공우주·방산 ════════════════
  { ticker: "BA",     name: "The Boeing Company",         sector: "Aerospace & Defense",     country: "USA",         liquidity_score: 0.55, supplier_concentration: 0.45 },
  { ticker: "RTX",    name: "RTX Corporation",            sector: "Aerospace & Defense",     country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.40 },
  { ticker: "LMT",    name: "Lockheed Martin Corp.",      sector: "Aerospace & Defense",     country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.38 },
  { ticker: "GE",     name: "GE Aerospace",               sector: "Industrial",              country: "USA",         liquidity_score: 0.62, supplier_concentration: 0.42 },
  { ticker: "HON",    name: "Honeywell International",    sector: "Industrial",              country: "USA",         liquidity_score: 0.68, supplier_concentration: 0.38 },
  { ticker: "CAT",    name: "Caterpillar Inc.",            sector: "Industrial",              country: "USA",         liquidity_score: 0.65, supplier_concentration: 0.40 },
  { ticker: "MMM",    name: "3M Company",                 sector: "Industrial",              country: "USA",         liquidity_score: 0.63, supplier_concentration: 0.38 },

  // ══════════════════ 한국 추가 기업 ════════════════════
  // 자동차·부품
  { ticker: "000270", name: "Kia Motors",                 sector: "Automotive",              country: "South Korea", liquidity_score: 0.60, supplier_concentration: 0.52 },
  { ticker: "012330", name: "Hyundai Mobis",              sector: "Automotive Components",   country: "South Korea", liquidity_score: 0.62, supplier_concentration: 0.48 },
  // 철강·소재
  { ticker: "005490", name: "POSCO Holdings",             sector: "Materials",               country: "South Korea", liquidity_score: 0.60, supplier_concentration: 0.38 },
  // 화학·에너지
  { ticker: "096770", name: "SK Innovation",              sector: "Oil & Gas",               country: "South Korea", liquidity_score: 0.58, supplier_concentration: 0.45 },
  // 바이오
  { ticker: "068270", name: "Celltrion Inc.",             sector: "Biotechnology",           country: "South Korea", liquidity_score: 0.65, supplier_concentration: 0.50 },
  // 방산·에너지설비
  { ticker: "034020", name: "Doosan Enerbility",          sector: "Industrial",              country: "South Korea", liquidity_score: 0.52, supplier_concentration: 0.55 },
  { ticker: "012450", name: "Hanwha Aerospace",           sector: "Aerospace & Defense",     country: "South Korea", liquidity_score: 0.55, supplier_concentration: 0.48 },
  // IT·인터넷
  { ticker: "035420", name: "NAVER Corporation",          sector: "Technology",              country: "South Korea", liquidity_score: 0.68, supplier_concentration: 0.40 },
  // 금융
  { ticker: "086790", name: "Hana Financial Group",       sector: "Banking",                 country: "South Korea", liquidity_score: 0.72, supplier_concentration: 0.30 },
  { ticker: "105560", name: "KB Financial Group",         sector: "Banking",                 country: "South Korea", liquidity_score: 0.73, supplier_concentration: 0.28 },
];

const SAMPLE_RELATIONS: SupplyRelationCreate[] = [
  // ══════════════ 반도체·테크 공급망 ════════════════════
  // Lv0→Lv1 원자재→웨이퍼
  { supplier_ticker: "APD",    buyer_ticker: "SHNEY",  revenue_share: 0.14, dependency_score: 0.68, geographic_exposure: 0.45, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "APD",    buyer_ticker: "SUOPY",  revenue_share: 0.10, dependency_score: 0.62, geographic_exposure: 0.45, alternative_supplier_score: 0.35, confidence_score: 0.85 },
  { supplier_ticker: "LIN",    buyer_ticker: "SHNEY",  revenue_share: 0.12, dependency_score: 0.65, geographic_exposure: 0.45, alternative_supplier_score: 0.32, confidence_score: 0.86 },
  { supplier_ticker: "EMN",    buyer_ticker: "SHNEY",  revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.30, alternative_supplier_score: 0.40, confidence_score: 0.78 },
  { supplier_ticker: "EMN",    buyer_ticker: "WFRD",   revenue_share: 0.12, dependency_score: 0.50, geographic_exposure: 0.35, alternative_supplier_score: 0.45, confidence_score: 0.76 },
  // Lv0→Lv2/Lv3 (직접 공급)
  { supplier_ticker: "APD",    buyer_ticker: "ASML",   revenue_share: 0.08, dependency_score: 0.58, geographic_exposure: 0.40, alternative_supplier_score: 0.38, confidence_score: 0.84 },
  { supplier_ticker: "APD",    buyer_ticker: "TSMC",   revenue_share: 0.12, dependency_score: 0.72, geographic_exposure: 0.60, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "APD",    buyer_ticker: "005930", revenue_share: 0.10, dependency_score: 0.68, geographic_exposure: 0.50, alternative_supplier_score: 0.30, confidence_score: 0.85 },
  { supplier_ticker: "APD",    buyer_ticker: "INTC",   revenue_share: 0.08, dependency_score: 0.62, geographic_exposure: 0.20, alternative_supplier_score: 0.35, confidence_score: 0.83 },
  { supplier_ticker: "APD",    buyer_ticker: "000660", revenue_share: 0.06, dependency_score: 0.58, geographic_exposure: 0.50, alternative_supplier_score: 0.38, confidence_score: 0.82 },
  { supplier_ticker: "LIN",    buyer_ticker: "TSMC",   revenue_share: 0.10, dependency_score: 0.70, geographic_exposure: 0.60, alternative_supplier_score: 0.30, confidence_score: 0.86 },
  { supplier_ticker: "LIN",    buyer_ticker: "005930", revenue_share: 0.08, dependency_score: 0.65, geographic_exposure: 0.50, alternative_supplier_score: 0.32, confidence_score: 0.84 },
  // Lv1→Lv3 웨이퍼→파운드리
  { supplier_ticker: "SHNEY",  buyer_ticker: "TSMC",   revenue_share: 0.28, dependency_score: 0.80, geographic_exposure: 0.55, alternative_supplier_score: 0.20, confidence_score: 0.92 },
  { supplier_ticker: "SHNEY",  buyer_ticker: "005930", revenue_share: 0.22, dependency_score: 0.75, geographic_exposure: 0.48, alternative_supplier_score: 0.22, confidence_score: 0.90 },
  { supplier_ticker: "SHNEY",  buyer_ticker: "INTC",   revenue_share: 0.18, dependency_score: 0.72, geographic_exposure: 0.20, alternative_supplier_score: 0.25, confidence_score: 0.88 },
  { supplier_ticker: "SHNEY",  buyer_ticker: "000660", revenue_share: 0.14, dependency_score: 0.70, geographic_exposure: 0.48, alternative_supplier_score: 0.25, confidence_score: 0.87 },
  { supplier_ticker: "SUOPY",  buyer_ticker: "TSMC",   revenue_share: 0.20, dependency_score: 0.75, geographic_exposure: 0.55, alternative_supplier_score: 0.22, confidence_score: 0.90 },
  { supplier_ticker: "SUOPY",  buyer_ticker: "MU",     revenue_share: 0.10, dependency_score: 0.65, geographic_exposure: 0.25, alternative_supplier_score: 0.32, confidence_score: 0.84 },
  { supplier_ticker: "WFRD",   buyer_ticker: "ASML",   revenue_share: 0.18, dependency_score: 0.68, geographic_exposure: 0.40, alternative_supplier_score: 0.28, confidence_score: 0.85 },
  { supplier_ticker: "WFRD",   buyer_ticker: "TSMC",   revenue_share: 0.12, dependency_score: 0.62, geographic_exposure: 0.55, alternative_supplier_score: 0.35, confidence_score: 0.83 },
  // Lv2→Lv3 장비→파운드리
  { supplier_ticker: "ASML",   buyer_ticker: "TSMC",   revenue_share: 0.30, dependency_score: 0.93, geographic_exposure: 0.55, alternative_supplier_score: 0.04, confidence_score: 0.96 },
  { supplier_ticker: "ASML",   buyer_ticker: "005930", revenue_share: 0.22, dependency_score: 0.88, geographic_exposure: 0.48, alternative_supplier_score: 0.05, confidence_score: 0.93 },
  { supplier_ticker: "ASML",   buyer_ticker: "INTC",   revenue_share: 0.18, dependency_score: 0.85, geographic_exposure: 0.20, alternative_supplier_score: 0.06, confidence_score: 0.91 },
  { supplier_ticker: "AMAT",   buyer_ticker: "TSMC",   revenue_share: 0.24, dependency_score: 0.78, geographic_exposure: 0.55, alternative_supplier_score: 0.18, confidence_score: 0.89 },
  { supplier_ticker: "AMAT",   buyer_ticker: "005930", revenue_share: 0.18, dependency_score: 0.72, geographic_exposure: 0.48, alternative_supplier_score: 0.22, confidence_score: 0.87 },
  { supplier_ticker: "AMAT",   buyer_ticker: "000660", revenue_share: 0.10, dependency_score: 0.62, geographic_exposure: 0.48, alternative_supplier_score: 0.35, confidence_score: 0.83 },
  { supplier_ticker: "LRCX",   buyer_ticker: "TSMC",   revenue_share: 0.22, dependency_score: 0.76, geographic_exposure: 0.55, alternative_supplier_score: 0.20, confidence_score: 0.88 },
  { supplier_ticker: "KLAC",   buyer_ticker: "TSMC",   revenue_share: 0.16, dependency_score: 0.72, geographic_exposure: 0.55, alternative_supplier_score: 0.22, confidence_score: 0.87 },
  { supplier_ticker: "TOELY",  buyer_ticker: "TSMC",   revenue_share: 0.18, dependency_score: 0.74, geographic_exposure: 0.58, alternative_supplier_score: 0.22, confidence_score: 0.87 },
  { supplier_ticker: "TOELY",  buyer_ticker: "005930", revenue_share: 0.14, dependency_score: 0.70, geographic_exposure: 0.50, alternative_supplier_score: 0.26, confidence_score: 0.85 },
  // Lv3→Lv4 파운드리→팹리스
  { supplier_ticker: "TSMC",   buyer_ticker: "NVDA",   revenue_share: 0.23, dependency_score: 0.90, geographic_exposure: 0.65, alternative_supplier_score: 0.10, confidence_score: 0.94 },
  { supplier_ticker: "TSMC",   buyer_ticker: "AMD",    revenue_share: 0.11, dependency_score: 0.85, geographic_exposure: 0.65, alternative_supplier_score: 0.15, confidence_score: 0.91 },
  { supplier_ticker: "TSMC",   buyer_ticker: "QCOM",   revenue_share: 0.12, dependency_score: 0.80, geographic_exposure: 0.65, alternative_supplier_score: 0.18, confidence_score: 0.90 },
  { supplier_ticker: "TSMC",   buyer_ticker: "AVGO",   revenue_share: 0.09, dependency_score: 0.72, geographic_exposure: 0.65, alternative_supplier_score: 0.24, confidence_score: 0.88 },
  { supplier_ticker: "TSMC",   buyer_ticker: "MRVL",   revenue_share: 0.04, dependency_score: 0.78, geographic_exposure: 0.65, alternative_supplier_score: 0.20, confidence_score: 0.86 },
  { supplier_ticker: "TSMC",   buyer_ticker: "ADI",    revenue_share: 0.03, dependency_score: 0.58, geographic_exposure: 0.65, alternative_supplier_score: 0.38, confidence_score: 0.82 },
  { supplier_ticker: "UMC",    buyer_ticker: "STM",    revenue_share: 0.22, dependency_score: 0.60, geographic_exposure: 0.60, alternative_supplier_score: 0.38, confidence_score: 0.80 },
  { supplier_ticker: "UMC",    buyer_ticker: "ON",     revenue_share: 0.15, dependency_score: 0.50, geographic_exposure: 0.60, alternative_supplier_score: 0.45, confidence_score: 0.78 },
  { supplier_ticker: "000660", buyer_ticker: "NVDA",   revenue_share: 0.20, dependency_score: 0.82, geographic_exposure: 0.50, alternative_supplier_score: 0.15, confidence_score: 0.92 },
  { supplier_ticker: "005930", buyer_ticker: "NVDA",   revenue_share: 0.08, dependency_score: 0.62, geographic_exposure: 0.55, alternative_supplier_score: 0.32, confidence_score: 0.85 },
  { supplier_ticker: "MU",     buyer_ticker: "NVDA",   revenue_share: 0.05, dependency_score: 0.45, geographic_exposure: 0.25, alternative_supplier_score: 0.50, confidence_score: 0.80 },
  // Lv4→Lv5 팹리스→EMS (★8홉 체인 핵심 연결★)
  { supplier_ticker: "NVDA",   buyer_ticker: "HNHPF",  revenue_share: 0.12, dependency_score: 0.72, geographic_exposure: 0.60, alternative_supplier_score: 0.25, confidence_score: 0.90 },
  { supplier_ticker: "AMD",    buyer_ticker: "HNHPF",  revenue_share: 0.10, dependency_score: 0.65, geographic_exposure: 0.60, alternative_supplier_score: 0.30, confidence_score: 0.87 },
  { supplier_ticker: "INTC",   buyer_ticker: "HNHPF",  revenue_share: 0.15, dependency_score: 0.70, geographic_exposure: 0.60, alternative_supplier_score: 0.27, confidence_score: 0.88 },
  // Lv4→Lv6/Lv7 직접 공급
  { supplier_ticker: "NVDA",   buyer_ticker: "MSFT",   revenue_share: 0.18, dependency_score: 0.70, geographic_exposure: 0.20, alternative_supplier_score: 0.22, confidence_score: 0.91 },
  { supplier_ticker: "NVDA",   buyer_ticker: "AMZN",   revenue_share: 0.16, dependency_score: 0.68, geographic_exposure: 0.20, alternative_supplier_score: 0.25, confidence_score: 0.90 },
  { supplier_ticker: "NVDA",   buyer_ticker: "GOOGL",  revenue_share: 0.12, dependency_score: 0.58, geographic_exposure: 0.20, alternative_supplier_score: 0.38, confidence_score: 0.88 },
  { supplier_ticker: "NVDA",   buyer_ticker: "META",   revenue_share: 0.14, dependency_score: 0.75, geographic_exposure: 0.20, alternative_supplier_score: 0.20, confidence_score: 0.90 },
  { supplier_ticker: "NVDA",   buyer_ticker: "DELL",   revenue_share: 0.10, dependency_score: 0.65, geographic_exposure: 0.20, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "AMD",    buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.48, geographic_exposure: 0.20, alternative_supplier_score: 0.48, confidence_score: 0.86 },
  { supplier_ticker: "AMD",    buyer_ticker: "AMZN",   revenue_share: 0.12, dependency_score: 0.58, geographic_exposure: 0.20, alternative_supplier_score: 0.38, confidence_score: 0.87 },
  { supplier_ticker: "INTC",   buyer_ticker: "DELL",   revenue_share: 0.24, dependency_score: 0.68, geographic_exposure: 0.20, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "INTC",   buyer_ticker: "MSFT",   revenue_share: 0.22, dependency_score: 0.65, geographic_exposure: 0.20, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "QCOM",   buyer_ticker: "AAPL",   revenue_share: 0.15, dependency_score: 0.50, geographic_exposure: 0.30, alternative_supplier_score: 0.48, confidence_score: 0.86 },
  { supplier_ticker: "AVGO",   buyer_ticker: "AAPL",   revenue_share: 0.20, dependency_score: 0.60, geographic_exposure: 0.30, alternative_supplier_score: 0.35, confidence_score: 0.88 },
  { supplier_ticker: "AVGO",   buyer_ticker: "CSCO",   revenue_share: 0.25, dependency_score: 0.72, geographic_exposure: 0.22, alternative_supplier_score: 0.24, confidence_score: 0.90 },
  { supplier_ticker: "MRVL",   buyer_ticker: "AMZN",   revenue_share: 0.18, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "SWKS",   buyer_ticker: "AAPL",   revenue_share: 0.50, dependency_score: 0.55, geographic_exposure: 0.32, alternative_supplier_score: 0.40, confidence_score: 0.87 },
  { supplier_ticker: "TXN",    buyer_ticker: "TSLA",   revenue_share: 0.08, dependency_score: 0.40, geographic_exposure: 0.22, alternative_supplier_score: 0.55, confidence_score: 0.82 },
  { supplier_ticker: "NXPI",   buyer_ticker: "TSLA",   revenue_share: 0.12, dependency_score: 0.48, geographic_exposure: 0.28, alternative_supplier_score: 0.48, confidence_score: 0.83 },
  { supplier_ticker: "NXPI",   buyer_ticker: "005380", revenue_share: 0.14, dependency_score: 0.52, geographic_exposure: 0.45, alternative_supplier_score: 0.44, confidence_score: 0.84 },
  { supplier_ticker: "STM",    buyer_ticker: "TSLA",   revenue_share: 0.10, dependency_score: 0.45, geographic_exposure: 0.32, alternative_supplier_score: 0.50, confidence_score: 0.82 },
  { supplier_ticker: "ON",     buyer_ticker: "TSLA",   revenue_share: 0.14, dependency_score: 0.52, geographic_exposure: 0.25, alternative_supplier_score: 0.44, confidence_score: 0.83 },
  { supplier_ticker: "IFNNY",  buyer_ticker: "005380", revenue_share: 0.10, dependency_score: 0.45, geographic_exposure: 0.45, alternative_supplier_score: 0.50, confidence_score: 0.81 },
  // Lv5 부품→OEM
  { supplier_ticker: "MRAAY",  buyer_ticker: "AAPL",   revenue_share: 0.20, dependency_score: 0.58, geographic_exposure: 0.55, alternative_supplier_score: 0.38, confidence_score: 0.87 },
  { supplier_ticker: "TTDKY",  buyer_ticker: "AAPL",   revenue_share: 0.14, dependency_score: 0.50, geographic_exposure: 0.55, alternative_supplier_score: 0.45, confidence_score: 0.85 },
  { supplier_ticker: "GLW",    buyer_ticker: "AAPL",   revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.25, alternative_supplier_score: 0.42, confidence_score: 0.86 },
  { supplier_ticker: "APH",    buyer_ticker: "DELL",   revenue_share: 0.12, dependency_score: 0.48, geographic_exposure: 0.22, alternative_supplier_score: 0.48, confidence_score: 0.85 },
  { supplier_ticker: "034220", buyer_ticker: "AAPL",   revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.48, alternative_supplier_score: 0.35, confidence_score: 0.88 },
  { supplier_ticker: "009150", buyer_ticker: "AAPL",   revenue_share: 0.22, dependency_score: 0.62, geographic_exposure: 0.48, alternative_supplier_score: 0.32, confidence_score: 0.88 },
  { supplier_ticker: "051910", buyer_ticker: "373220", revenue_share: 0.40, dependency_score: 0.88, geographic_exposure: 0.45, alternative_supplier_score: 0.10, confidence_score: 0.92 },
  { supplier_ticker: "051910", buyer_ticker: "006400", revenue_share: 0.25, dependency_score: 0.80, geographic_exposure: 0.45, alternative_supplier_score: 0.15, confidence_score: 0.90 },
  { supplier_ticker: "373220", buyer_ticker: "TSLA",   revenue_share: 0.22, dependency_score: 0.68, geographic_exposure: 0.50, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "373220", buyer_ticker: "005380", revenue_share: 0.28, dependency_score: 0.72, geographic_exposure: 0.45, alternative_supplier_score: 0.24, confidence_score: 0.89 },
  { supplier_ticker: "373220", buyer_ticker: "RIVN",   revenue_share: 0.30, dependency_score: 0.80, geographic_exposure: 0.45, alternative_supplier_score: 0.18, confidence_score: 0.87 },
  { supplier_ticker: "006400", buyer_ticker: "TSLA",   revenue_share: 0.10, dependency_score: 0.40, geographic_exposure: 0.50, alternative_supplier_score: 0.55, confidence_score: 0.82 },
  { supplier_ticker: "005930", buyer_ticker: "AAPL",   revenue_share: 0.10, dependency_score: 0.35, geographic_exposure: 0.48, alternative_supplier_score: 0.60, confidence_score: 0.82 },
  { supplier_ticker: "HNHPF",  buyer_ticker: "AAPL",   revenue_share: 0.45, dependency_score: 0.80, geographic_exposure: 0.60, alternative_supplier_score: 0.18, confidence_score: 0.92 },
  { supplier_ticker: "HNHPF",  buyer_ticker: "DELL",   revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.60, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "JBL",    buyer_ticker: "AAPL",   revenue_share: 0.20, dependency_score: 0.55, geographic_exposure: 0.50, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "FLEX",   buyer_ticker: "MSFT",   revenue_share: 0.18, dependency_score: 0.50, geographic_exposure: 0.45, alternative_supplier_score: 0.45, confidence_score: 0.83 },
  // Lv6→Lv7 OEM→클라우드
  { supplier_ticker: "DELL",   buyer_ticker: "MSFT",   revenue_share: 0.20, dependency_score: 0.62, geographic_exposure: 0.20, alternative_supplier_score: 0.35, confidence_score: 0.88 },
  { supplier_ticker: "DELL",   buyer_ticker: "AMZN",   revenue_share: 0.18, dependency_score: 0.58, geographic_exposure: 0.20, alternative_supplier_score: 0.38, confidence_score: 0.87 },
  { supplier_ticker: "HPQ",    buyer_ticker: "AMZN",   revenue_share: 0.14, dependency_score: 0.52, geographic_exposure: 0.20, alternative_supplier_score: 0.44, confidence_score: 0.85 },
  { supplier_ticker: "CSCO",   buyer_ticker: "AMZN",   revenue_share: 0.18, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.89 },
  { supplier_ticker: "CSCO",   buyer_ticker: "MSFT",   revenue_share: 0.16, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.32, confidence_score: 0.88 },
  { supplier_ticker: "MU",     buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.38, geographic_exposure: 0.25, alternative_supplier_score: 0.57, confidence_score: 0.81 },
  { supplier_ticker: "MU",     buyer_ticker: "AMZN",   revenue_share: 0.12, dependency_score: 0.42, geographic_exposure: 0.25, alternative_supplier_score: 0.53, confidence_score: 0.83 },
  // Lv7→Lv8 클라우드→SaaS
  { supplier_ticker: "MSFT",   buyer_ticker: "SAP",    revenue_share: 0.22, dependency_score: 0.70, geographic_exposure: 0.22, alternative_supplier_score: 0.25, confidence_score: 0.90 },
  { supplier_ticker: "MSFT",   buyer_ticker: "CRM",    revenue_share: 0.18, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.32, confidence_score: 0.88 },
  { supplier_ticker: "MSFT",   buyer_ticker: "NOW",    revenue_share: 0.20, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.89 },
  { supplier_ticker: "MSFT",   buyer_ticker: "WDAY",   revenue_share: 0.18, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "MSFT",   buyer_ticker: "ADBE",   revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.86 },
  { supplier_ticker: "AMZN",   buyer_ticker: "CRM",    revenue_share: 0.24, dependency_score: 0.72, geographic_exposure: 0.22, alternative_supplier_score: 0.22, confidence_score: 0.91 },
  { supplier_ticker: "AMZN",   buyer_ticker: "ORCL",   revenue_share: 0.16, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.38, confidence_score: 0.86 },
  { supplier_ticker: "AMZN",   buyer_ticker: "SAP",    revenue_share: 0.18, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "AMZN",   buyer_ticker: "NOW",    revenue_share: 0.14, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "GOOGL",  buyer_ticker: "SAP",    revenue_share: 0.10, dependency_score: 0.42, geographic_exposure: 0.22, alternative_supplier_score: 0.52, confidence_score: 0.82 },
  { supplier_ticker: "GOOGL",  buyer_ticker: "WDAY",   revenue_share: 0.12, dependency_score: 0.48, geographic_exposure: 0.22, alternative_supplier_score: 0.48, confidence_score: 0.83 },
  { supplier_ticker: "META",   buyer_ticker: "ADBE",   revenue_share: 0.14, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.37, confidence_score: 0.85 },

  // ══════════════ 에너지·전력 공급망 ════════════════════
  { supplier_ticker: "SLB",    buyer_ticker: "XOM",    revenue_share: 0.22, dependency_score: 0.65, geographic_exposure: 0.45, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "SLB",    buyer_ticker: "CVX",    revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.45, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "SLB",    buyer_ticker: "COP",    revenue_share: 0.12, dependency_score: 0.55, geographic_exposure: 0.42, alternative_supplier_score: 0.40, confidence_score: 0.84 },
  { supplier_ticker: "XOM",    buyer_ticker: "NEE",    revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.25, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "XOM",    buyer_ticker: "DUK",    revenue_share: 0.12, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.42, confidence_score: 0.84 },
  { supplier_ticker: "CVX",    buyer_ticker: "AES",    revenue_share: 0.14, dependency_score: 0.58, geographic_exposure: 0.38, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "CVX",    buyer_ticker: "VST",    revenue_share: 0.18, dependency_score: 0.62, geographic_exposure: 0.35, alternative_supplier_score: 0.34, confidence_score: 0.86 },
  { supplier_ticker: "COP",    buyer_ticker: "EXC",    revenue_share: 0.16, dependency_score: 0.58, geographic_exposure: 0.28, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "ENPH",   buyer_ticker: "NEE",    revenue_share: 0.30, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.32, confidence_score: 0.87 },
  { supplier_ticker: "FSLR",   buyer_ticker: "NEE",    revenue_share: 0.25, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "FSLR",   buyer_ticker: "AES",    revenue_share: 0.20, dependency_score: 0.58, geographic_exposure: 0.30, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "BEPC",   buyer_ticker: "AES",    revenue_share: 0.22, dependency_score: 0.62, geographic_exposure: 0.35, alternative_supplier_score: 0.34, confidence_score: 0.84 },
  { supplier_ticker: "GEV",    buyer_ticker: "NEE",    revenue_share: 0.28, dependency_score: 0.68, geographic_exposure: 0.28, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "GEV",    buyer_ticker: "DUK",    revenue_share: 0.22, dependency_score: 0.62, geographic_exposure: 0.25, alternative_supplier_score: 0.33, confidence_score: 0.86 },
  { supplier_ticker: "GEV",    buyer_ticker: "AES",    revenue_share: 0.18, dependency_score: 0.58, geographic_exposure: 0.32, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "ETN",    buyer_ticker: "NEE",    revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.87 },
  { supplier_ticker: "ETN",    buyer_ticker: "DUK",    revenue_share: 0.16, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "ABB",    buyer_ticker: "NEE",    revenue_share: 0.15, dependency_score: 0.58, geographic_exposure: 0.30, alternative_supplier_score: 0.37, confidence_score: 0.85 },
  { supplier_ticker: "VRT",    buyer_ticker: "MSFT",   revenue_share: 0.25, dependency_score: 0.72, geographic_exposure: 0.22, alternative_supplier_score: 0.25, confidence_score: 0.90 },
  { supplier_ticker: "VRT",    buyer_ticker: "AMZN",   revenue_share: 0.28, dependency_score: 0.75, geographic_exposure: 0.22, alternative_supplier_score: 0.22, confidence_score: 0.91 },
  { supplier_ticker: "VRT",    buyer_ticker: "GOOGL",  revenue_share: 0.22, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.89 },
  { supplier_ticker: "NEE",    buyer_ticker: "AMZN",   revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "DUK",    buyer_ticker: "MSFT",   revenue_share: 0.15, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "AES",    buyer_ticker: "AMZN",   revenue_share: 0.20, dependency_score: 0.62, geographic_exposure: 0.28, alternative_supplier_score: 0.33, confidence_score: 0.87 },
  { supplier_ticker: "EXC",    buyer_ticker: "GOOGL",  revenue_share: 0.14, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.84 },

  // ══════════════ 헬스케어 공급망 ════════════════════════
  { supplier_ticker: "IQVIA",  buyer_ticker: "PFE",    revenue_share: 0.22, dependency_score: 0.65, geographic_exposure: 0.30, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "IQVIA",  buyer_ticker: "LLY",    revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.28, alternative_supplier_score: 0.35, confidence_score: 0.87 },
  { supplier_ticker: "IQVIA",  buyer_ticker: "JNJ",    revenue_share: 0.20, dependency_score: 0.62, geographic_exposure: 0.30, alternative_supplier_score: 0.33, confidence_score: 0.87 },
  { supplier_ticker: "IQVIA",  buyer_ticker: "MRK",    revenue_share: 0.16, dependency_score: 0.58, geographic_exposure: 0.28, alternative_supplier_score: 0.37, confidence_score: 0.86 },
  { supplier_ticker: "AMGN",   buyer_ticker: "LLY",    revenue_share: 0.14, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "AMGN",   buyer_ticker: "ABBV",   revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "REGN",   buyer_ticker: "ABBV",   revenue_share: 0.22, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.87 },
  { supplier_ticker: "VRTX",   buyer_ticker: "PFE",    revenue_share: 0.16, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "LLY",    buyer_ticker: "CVS",    revenue_share: 0.20, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.33, confidence_score: 0.87 },
  { supplier_ticker: "PFE",    buyer_ticker: "CVS",    revenue_share: 0.22, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "ABBV",   buyer_ticker: "CVS",    revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "MRK",    buyer_ticker: "CVS",    revenue_share: 0.16, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.37, confidence_score: 0.86 },
  { supplier_ticker: "JNJ",    buyer_ticker: "HCA",    revenue_share: 0.18, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.33, confidence_score: 0.87 },
  { supplier_ticker: "MDT",    buyer_ticker: "HCA",    revenue_share: 0.25, dependency_score: 0.70, geographic_exposure: 0.22, alternative_supplier_score: 0.25, confidence_score: 0.90 },
  { supplier_ticker: "ABT",    buyer_ticker: "HCA",    revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "SYK",    buyer_ticker: "HCA",    revenue_share: 0.22, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.27, confidence_score: 0.89 },
  { supplier_ticker: "ISRG",   buyer_ticker: "HCA",    revenue_share: 0.28, dependency_score: 0.75, geographic_exposure: 0.22, alternative_supplier_score: 0.22, confidence_score: 0.91 },
  { supplier_ticker: "CVS",    buyer_ticker: "MSFT",   revenue_share: 0.12, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "UNH",    buyer_ticker: "MSFT",   revenue_share: 0.14, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.37, confidence_score: 0.86 },
  { supplier_ticker: "HCA",    buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.84 },

  // ══════════════ 금융 공급망 ════════════════════════════
  { supplier_ticker: "MMC",    buyer_ticker: "JPM",    revenue_share: 0.14, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "MMC",    buyer_ticker: "GS",     revenue_share: 0.12, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.43, confidence_score: 0.84 },
  { supplier_ticker: "BLK",    buyer_ticker: "JPM",    revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "V",      buyer_ticker: "JPM",    revenue_share: 0.18, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.90 },
  { supplier_ticker: "MA",     buyer_ticker: "GS",     revenue_share: 0.16, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.33, confidence_score: 0.87 },
  { supplier_ticker: "GS",     buyer_ticker: "V",      revenue_share: 0.10, dependency_score: 0.48, geographic_exposure: 0.22, alternative_supplier_score: 0.48, confidence_score: 0.83 },
  { supplier_ticker: "GS",     buyer_ticker: "AAPL",   revenue_share: 0.12, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.85 },
  { supplier_ticker: "JPM",    buyer_ticker: "AMZN",   revenue_share: 0.14, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "V",      buyer_ticker: "AMZN",   revenue_share: 0.22, dependency_score: 0.70, geographic_exposure: 0.22, alternative_supplier_score: 0.26, confidence_score: 0.90 },
  { supplier_ticker: "MA",     buyer_ticker: "AMZN",   revenue_share: 0.18, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "PYPL",   buyer_ticker: "AMZN",   revenue_share: 0.25, dependency_score: 0.72, geographic_exposure: 0.22, alternative_supplier_score: 0.24, confidence_score: 0.89 },
  { supplier_ticker: "AXP",    buyer_ticker: "AAPL",   revenue_share: 0.14, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "JPM",    buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.84 },

  // ══════════════ 소비·유통 공급망 ══════════════════════
  { supplier_ticker: "PG",     buyer_ticker: "WMT",    revenue_share: 0.25, dependency_score: 0.72, geographic_exposure: 0.22, alternative_supplier_score: 0.24, confidence_score: 0.92 },
  { supplier_ticker: "KO",     buyer_ticker: "WMT",    revenue_share: 0.22, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.90 },
  { supplier_ticker: "PEP",    buyer_ticker: "WMT",    revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.89 },
  { supplier_ticker: "NKE",    buyer_ticker: "AMZN",   revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.30, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "WMT",    buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.60, geographic_exposure: 0.22, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  { supplier_ticker: "HD",     buyer_ticker: "GOOGL",  revenue_share: 0.09, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.84 },
  { supplier_ticker: "COST",   buyer_ticker: "AMZN",   revenue_share: 0.08, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.84 },

  // ══════════════ 산업·항공우주 공급망 ══════════════════
  { supplier_ticker: "GE",     buyer_ticker: "BA",     revenue_share: 0.30, dependency_score: 0.75, geographic_exposure: 0.22, alternative_supplier_score: 0.22, confidence_score: 0.91 },
  { supplier_ticker: "HON",    buyer_ticker: "BA",     revenue_share: 0.20, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.89 },
  { supplier_ticker: "RTX",    buyer_ticker: "BA",     revenue_share: 0.18, dependency_score: 0.65, geographic_exposure: 0.22, alternative_supplier_score: 0.30, confidence_score: 0.88 },
  { supplier_ticker: "MMM",    buyer_ticker: "HON",    revenue_share: 0.15, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.37, confidence_score: 0.86 },
  { supplier_ticker: "CAT",    buyer_ticker: "GE",     revenue_share: 0.12, dependency_score: 0.52, geographic_exposure: 0.25, alternative_supplier_score: 0.44, confidence_score: 0.84 },
  { supplier_ticker: "BA",     buyer_ticker: "AMZN",   revenue_share: 0.15, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.38, confidence_score: 0.85 },
  { supplier_ticker: "HON",    buyer_ticker: "MSFT",   revenue_share: 0.12, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.85 },
  { supplier_ticker: "LMT",    buyer_ticker: "MSFT",   revenue_share: 0.10, dependency_score: 0.52, geographic_exposure: 0.22, alternative_supplier_score: 0.44, confidence_score: 0.84 },

  // ══════════════ 한국 추가 공급망 관계 ════════════════
  // POSCO → 배터리·자동차 (철강 공급)
  { supplier_ticker: "005490", buyer_ticker: "006400",  revenue_share: 0.22, dependency_score: 0.68, geographic_exposure: 0.45, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "005490", buyer_ticker: "373220",  revenue_share: 0.20, dependency_score: 0.65, geographic_exposure: 0.45, alternative_supplier_score: 0.30, confidence_score: 0.87 },
  { supplier_ticker: "005490", buyer_ticker: "005380",  revenue_share: 0.25, dependency_score: 0.72, geographic_exposure: 0.40, alternative_supplier_score: 0.24, confidence_score: 0.90 },
  { supplier_ticker: "005490", buyer_ticker: "000270",  revenue_share: 0.20, dependency_score: 0.68, geographic_exposure: 0.40, alternative_supplier_score: 0.28, confidence_score: 0.88 },
  { supplier_ticker: "005490", buyer_ticker: "012330",  revenue_share: 0.15, dependency_score: 0.60, geographic_exposure: 0.42, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  // SK이노베이션 → 배터리 소재
  { supplier_ticker: "096770", buyer_ticker: "051910",  revenue_share: 0.30, dependency_score: 0.75, geographic_exposure: 0.45, alternative_supplier_score: 0.22, confidence_score: 0.90 },
  { supplier_ticker: "096770", buyer_ticker: "006400",  revenue_share: 0.18, dependency_score: 0.60, geographic_exposure: 0.45, alternative_supplier_score: 0.35, confidence_score: 0.86 },
  // 현대모비스 → 현대차·기아 (자동차 부품)
  { supplier_ticker: "012330", buyer_ticker: "005380",  revenue_share: 0.55, dependency_score: 0.88, geographic_exposure: 0.42, alternative_supplier_score: 0.10, confidence_score: 0.94 },
  { supplier_ticker: "012330", buyer_ticker: "000270",  revenue_share: 0.40, dependency_score: 0.82, geographic_exposure: 0.42, alternative_supplier_score: 0.14, confidence_score: 0.92 },
  // 두산에너빌리티 → 전력 유틸리티 (발전설비 공급)
  { supplier_ticker: "034020", buyer_ticker: "NEE",     revenue_share: 0.20, dependency_score: 0.58, geographic_exposure: 0.30, alternative_supplier_score: 0.38, confidence_score: 0.82 },
  { supplier_ticker: "034020", buyer_ticker: "AES",     revenue_share: 0.15, dependency_score: 0.52, geographic_exposure: 0.35, alternative_supplier_score: 0.44, confidence_score: 0.80 },
  // 한화에어로스페이스 → 방산 OEM
  { supplier_ticker: "012450", buyer_ticker: "RTX",     revenue_share: 0.18, dependency_score: 0.55, geographic_exposure: 0.30, alternative_supplier_score: 0.40, confidence_score: 0.82 },
  { supplier_ticker: "012450", buyer_ticker: "BA",      revenue_share: 0.12, dependency_score: 0.48, geographic_exposure: 0.28, alternative_supplier_score: 0.46, confidence_score: 0.80 },
  // 셀트리온 → 글로벌 의약품 유통
  { supplier_ticker: "068270", buyer_ticker: "CVS",     revenue_share: 0.12, dependency_score: 0.48, geographic_exposure: 0.28, alternative_supplier_score: 0.48, confidence_score: 0.82 },
  { supplier_ticker: "068270", buyer_ticker: "ABBV",    revenue_share: 0.10, dependency_score: 0.42, geographic_exposure: 0.25, alternative_supplier_score: 0.52, confidence_score: 0.80 },
  // NAVER → 클라우드 의존 (AI/클라우드 인프라)
  { supplier_ticker: "035420", buyer_ticker: "MSFT",    revenue_share: 0.15, dependency_score: 0.62, geographic_exposure: 0.22, alternative_supplier_score: 0.33, confidence_score: 0.85 },
  { supplier_ticker: "035420", buyer_ticker: "AMZN",    revenue_share: 0.20, dependency_score: 0.68, geographic_exposure: 0.22, alternative_supplier_score: 0.28, confidence_score: 0.86 },
  // 하나·KB금융 → 글로벌 금융 인프라
  { supplier_ticker: "086790", buyer_ticker: "MSFT",    revenue_share: 0.10, dependency_score: 0.55, geographic_exposure: 0.22, alternative_supplier_score: 0.40, confidence_score: 0.84 },
  { supplier_ticker: "105560", buyer_ticker: "AMZN",    revenue_share: 0.12, dependency_score: 0.58, geographic_exposure: 0.22, alternative_supplier_score: 0.37, confidence_score: 0.85 },
];

// ── 카테고리 정의 ─────────────────────────────────────────────────────────
const CATEGORIES = [
  { label: "🔬 Lv0 원자재·가스",       tickers: ["APD","LIN","EMN"] },
  { label: "💎 Lv1 웨이퍼·소재",       tickers: ["SHNEY","SUOPY","WFRD"] },
  { label: "🔧 Lv2 반도체장비",         tickers: ["ASML","AMAT","LRCX","KLAC","TOELY"] },
  { label: "🏭 Lv3 파운드리·메모리",    tickers: ["TSMC","INTC","UMC","005930","000660","MU"] },
  { label: "💡 Lv4 팹리스칩",           tickers: ["NVDA","AMD","QCOM","AVGO","MRVL","ADI","TXN","SWKS","NXPI","ON","STM","IFNNY"] },
  { label: "🔌 Lv5 부품·조립·배터리",  tickers: ["MRAAY","TTDKY","GLW","APH","034220","009150","051910","373220","006400","HNHPF","JBL","FLEX"] },
  { label: "📱 Lv6 OEM·네트워크",       tickers: ["AAPL","DELL","HPQ","066570","005380","TSLA","F","RIVN","CSCO","JNPR"] },
  { label: "☁️ Lv7 클라우드·빅테크",   tickers: ["MSFT","AMZN","GOOGL","META"] },
  { label: "🖥️ Lv8 엔터프라이즈SaaS",  tickers: ["SAP","ORCL","CRM","NOW","WDAY","ADBE"] },
  { label: "⛽ 에너지·석유가스",        tickers: ["XOM","CVX","COP","SLB"] },
  { label: "🌱 재생에너지",             tickers: ["ENPH","FSLR","BEPC"] },
  { label: "⚡ 전력설비",               tickers: ["ETN","GEV","VRT","ABB"] },
  { label: "🔋 전력유틸리티",           tickers: ["NEE","DUK","SO","EXC","AES","VST"] },
  { label: "🧬 바이오테크",             tickers: ["AMGN","REGN","VRTX"] },
  { label: "💊 제약",                   tickers: ["LLY","ABBV","PFE","JNJ","MRK"] },
  { label: "🏥 의료기기·서비스",        tickers: ["MDT","ABT","SYK","ISRG","UNH","HCA","CVS","IQVIA"] },
  { label: "🏦 은행·금융",              tickers: ["JPM","BAC","GS","MS"] },
  { label: "💳 결제·핀테크",            tickers: ["V","MA","PYPL","AXP","BLK","MMC"] },
  { label: "🛒 리테일·소비재",          tickers: ["WMT","COST","TGT","HD","KO","PEP","PG","NKE"] },
  { label: "✈️ 항공우주·방산·산업",     tickers: ["BA","RTX","LMT","GE","HON","CAT","MMM"] },
  { label: "🇰🇷 한국 추가기업",          tickers: ["000270","012330","005490","096770","068270","034020","012450","035420","086790","105560"] },
];

type ItemStatus = "pending" | "success" | "error";
interface ItemState { label: string; status: ItemStatus; error?: string; }
interface SeedDataModalProps { onClose: () => void; }

export default function SeedDataModal({ onClose }: SeedDataModalProps) {
  const [phase, setPhase] = useState<"idle" | "running" | "done">("idle");
  const [companyStates, setCompanyStates] = useState<ItemState[]>([]);
  const [relationStates, setRelationStates] = useState<ItemState[]>([]);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState({ companies: 0, relations: 0 });

  const totalCompanies = SAMPLE_COMPANIES.length;
  const totalRelations = SAMPLE_RELATIONS.length;

  const updateCompany = (idx: number, status: ItemStatus, error?: string) =>
    setCompanyStates(prev => { const next = [...prev]; next[idx] = { ...next[idx], status, error }; return next; });
  const updateRelation = (idx: number, status: ItemStatus, error?: string) =>
    setRelationStates(prev => { const next = [...prev]; next[idx] = { ...next[idx], status, error }; return next; });

  const handleRun = async () => {
    setPhase("running");
    setCompanyStates(SAMPLE_COMPANIES.map(c => ({ label: c.ticker, status: "pending" })));
    setRelationStates(SAMPLE_RELATIONS.map(r => ({ label: `${r.supplier_ticker}→${r.buyer_ticker}`, status: "pending" })));
    setProgress({ companies: 0, relations: 0 });

    for (let i = 0; i < SAMPLE_COMPANIES.length; i++) {
      try { await createCompany(SAMPLE_COMPANIES[i]); updateCompany(i, "success"); }
      catch (e: unknown) { updateCompany(i, "error", e instanceof Error ? e.message : String(e)); }
      setProgress(p => ({ ...p, companies: i + 1 }));
    }
    for (let i = 0; i < SAMPLE_RELATIONS.length; i++) {
      try { await createRelation(SAMPLE_RELATIONS[i]); updateRelation(i, "success"); }
      catch (e: unknown) { updateRelation(i, "error", e instanceof Error ? e.message : String(e)); }
      setProgress(p => ({ ...p, relations: i + 1 }));
    }
    setPhase("done");
  };

  const toggleCat = (label: string) =>
    setExpandedCats(prev => { const next = new Set(prev); next.has(label) ? next.delete(label) : next.add(label); return next; });

  const successCount = (states: ItemState[]) => states.filter(s => s.status === "success").length;
  const errorCount   = (states: ItemState[]) => states.filter(s => s.status === "error").length;
  const totalDone = progress.companies + progress.relations;
  const totalAll  = totalCompanies + totalRelations;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <Database size={20} className="text-primary" />
            <div>
              <p className="font-bold text-text-primary">샘플 데이터 추가</p>
              <p className="text-xs text-text-secondary">
                미국 전 섹터 공급망 · {totalCompanies}개 기업 · {totalRelations}개 관계
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-bg-hover rounded-lg transition-colors">
            <X size={16} className="text-text-tertiary" />
          </button>
        </div>

        {/* 진행 바 */}
        {phase !== "idle" && (
          <div className="px-6 py-3 bg-bg-subtle border-b border-border space-y-2">
            <div className="flex justify-between text-xs text-text-secondary">
              <span>기업 {progress.companies}/{totalCompanies}{phase==="done" && <> · ✅{successCount(companyStates)} ❌{errorCount(companyStates)}</>}</span>
              <span>관계 {progress.relations}/{totalRelations}{phase==="done" && <> · ✅{successCount(relationStates)} ❌{errorCount(relationStates)}</>}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div className="bg-primary h-1.5 rounded-full transition-all" style={{ width: `${(totalDone / totalAll) * 100}%` }} />
            </div>
          </div>
        )}

        {/* 8홉 체인 설명 */}
        {phase === "idle" && (
          <div className="px-6 py-3 bg-blue-50 border-b border-border">
            <p className="text-xs font-semibold text-blue-700 mb-1">8홉 체인 예시 (데이터 추가 후 시뮬레이션 가능)</p>
            <p className="text-[11px] text-blue-600 leading-relaxed font-mono">
              EMN → SHNEY → TSMC → NVDA → HNHPF → DELL → MSFT → SAP (7홉)<br/>
              SLB → XOM → NEE → VRT → AMZN → CRM (5홉 · 에너지→클라우드)<br/>
              IQVIA → LLY → CVS → MSFT → NOW (4홉 · 헬스케어→SaaS)<br/>
              MMC → GS → V → AMZN → ORCL (4홉 · 금융→클라우드)
            </p>
          </div>
        )}

        {/* 카테고리 목록 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {CATEGORIES.map(cat => {
            const isOpen = expandedCats.has(cat.label);
            const catStates = phase !== "idle" ? companyStates.filter(s => cat.tickers.includes(s.label)) : [];
            return (
              <div key={cat.label} className="border border-border rounded-lg overflow-hidden">
                <button
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-bg-subtle hover:bg-bg-hover transition-colors"
                  onClick={() => toggleCat(cat.label)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-text-primary">{cat.label}</span>
                    <span className="text-xs text-text-tertiary bg-white px-1.5 py-0.5 rounded-pill border border-border">{cat.tickers.length}개</span>
                    {phase !== "idle" && catStates.length > 0 && (
                      <span className="text-xs">✅{catStates.filter(s=>s.status==="success").length}{catStates.filter(s=>s.status==="error").length>0&&` ❌${catStates.filter(s=>s.status==="error").length}`}</span>
                    )}
                  </div>
                  {isOpen ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
                </button>
                {isOpen && (
                  <div className="px-4 py-3 flex flex-wrap gap-1.5">
                    {cat.tickers.map(t => {
                      const st = companyStates.find(s => s.label === t);
                      return (
                        <span key={t} className={`text-xs px-2 py-0.5 rounded-pill border font-mono ${
                          !st||st.status==="pending" ? "bg-white border-border text-text-secondary" :
                          st.status==="success"      ? "bg-green-50 border-green-300 text-green-700" :
                                                       "bg-red-50 border-red-300 text-red-700"
                        }`}>
                          {st?.status==="success"&&"✓ "}{st?.status==="error"&&"✗ "}{t}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* 푸터 */}
        <div className="px-6 py-4 border-t border-border flex items-center justify-between">
          {phase === "done" ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                {errorCount(companyStates)+errorCount(relationStates)===0
                  ? <><CheckCircle size={16} className="text-success"/><span className="text-success font-semibold">완료! 좌측에서 기업을 선택하고 시뮬레이션을 실행하세요.</span></>
                  : <><AlertTriangle size={16} className="text-warning"/><span className="text-warning font-semibold">일부 실패 (이미 존재하는 데이터는 정상입니다)</span></>
                }
              </div>
              <button onClick={onClose} className="btn-primary text-sm px-4 py-2">닫기</button>
            </>
          ) : (
            <>
              <p className="text-xs text-text-tertiary">기존 데이터는 UPSERT(덮어쓰기)됩니다</p>
              <button onClick={handleRun} disabled={phase==="running"} className="btn-primary flex items-center gap-2 text-sm px-4 py-2">
                {phase==="running" ? <><Loader2 size={14} className="animate-spin"/>추가 중…</> : <><Database size={14}/>샘플 데이터 추가</>}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
