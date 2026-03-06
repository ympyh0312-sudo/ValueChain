// ─────────────────────────────────────────────────────────
// lib/types.ts  ─ 프론트엔드 전역 타입 정의
//
// 구조:
//  1. 시뮬레이션 파라미터
//  2. 백엔드 API 응답 타입 (snake_case 그대로 유지)
//  3. 포스 그래프 전용 타입 (camelCase)
//  4. 기업/관계 CRUD 타입
// ─────────────────────────────────────────────────────────

// ── 1. 시뮬레이션 파라미터 ──────────────────────────────

export interface SimParams {
  ticker:         string;
  shockIntensity: number;  // 0 ~ 1
  decayLambda:    number;  // > 0
  timeHorizon:    number;  // 일(day)
  maxHop:         number;  // 1 ~ 8
}

export const DEFAULT_PARAMS: SimParams = {
  ticker:         "",
  shockIntensity: 1.0,
  decayLambda:    0.1,
  timeHorizon:    30,
  maxHop:         5,
};

// ── 2. 백엔드 API 응답 타입 ────────────────────────────

export type ApiStatus = "healthy" | "degraded" | "loading";

export interface HealthResponse {
  status:   "healthy" | "degraded";
  services: { neo4j: string; postgres: string };
}

/** 리스크 전파 결과 - 노드 */
export interface RiskNode {
  ticker:        string;
  name:          string;
  sector:        string;
  country:       string;
  risk_score:    number;           // 0 ~ 1
  hop_distance:  number;           // 원점에서 몇 홉
  risk_timeline: Record<number, number>; // { 0: 0.9, 1: 0.81, ... }
  is_origin:     boolean;
}

/** 리스크 전파 결과 - 엣지 */
export interface RiskEdge {
  source_ticker:      string;
  target_ticker:      string;
  transmitted_risk:   number;
  dependency_score:   number;
  sector_sensitivity: number;
}

/** POST /api/v1/risk/analyze 응답 */
export interface SimResult {
  origin_ticker:   string;
  params:          Record<string, unknown>;
  affected_count:  number;
  max_risk_ticker: string | null;
  max_risk_score:  number;
  nodes:           RiskNode[];
  edges:           RiskEdge[];
  simulation_id:   number | null;
}

/** GET /api/v1/network/companies/{ticker} 응답 */
export interface CompanyResponse {
  ticker:                 string;
  name:                   string;
  sector:                 string;
  country:                string;
  liquidity_score:        number;
  supplier_concentration: number;
  sector_sensitivity:     number;
  last_updated:           string | null;
}

/** POST /api/v1/network/companies 요청 */
export interface CompanyCreate {
  ticker:                 string;
  name:                   string;
  sector:                 string;
  country:                string;
  liquidity_score?:       number;
  supplier_concentration?: number;
}

/** POST /api/v1/network/relations 응답 */
export interface SupplyRelationResponse {
  supplier_ticker:             string;
  buyer_ticker:                string;
  revenue_share:               number;
  dependency_score:            number;
  geographic_exposure:         number;
  alternative_supplier_score:  number;
  confidence_score:            number;
  last_verified_at:            string | null;
}

/** POST /api/v1/network/relations 요청 */
export interface SupplyRelationCreate {
  supplier_ticker:              string;
  buyer_ticker:                 string;
  revenue_share:                number;
  dependency_score:             number;
  geographic_exposure?:         number;
  alternative_supplier_score?:  number;
  confidence_score?:            number;
}

/** GET /api/v1/network/companies/{ticker}/subgraph 응답 */
export interface SubgraphResponse {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

export interface SubgraphNode {
  ticker:                 string;
  name:                   string;
  sector:                 string;
  country:                string;
  liquidity_score:        number;
  supplier_concentration: number;
}

export interface SubgraphEdge {
  source:           string;
  target:           string;
  dependency_score: number;
  revenue_share:    number;
  confidence_score: number;
}

// ── 3. Force-Graph 전용 타입 ───────────────────────────
// react-force-graph-2d 라이브러리가 요구하는 형태

export interface GraphNode {
  id:           string;   // ticker
  name:         string;
  sector:       string;
  country:      string;
  riskScore:    number;
  hopDistance:  number;
  isOrigin:     boolean;
  // 시각화 속성
  color:        string;   // risk_score → 색상
  nodeSize:     number;   // hop에 따라 크기 조절
}

export interface GraphLink {
  source:          string;  // supplier ticker
  target:          string;  // buyer ticker
  transmittedRisk: number;
  dependencyScore: number;
  revenueShare:    number;  // revenue_share → 선 굵기 기준
  linkWidth:       number;  // dependency_score → 선 굵기 (fallback)
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// ── 4. AI 공급망 발견 타입 ──────────────────────────

export interface DiscoveredCompany {
  ticker:                 string;
  name:                   string;
  sector:                 string;
  country:                string;
  dependency_score:       number;
  revenue_share:          number;
  confidence_score:       number;
  liquidity_score:        number;
  supplier_concentration: number;
}

/** POST /api/v1/ai/discover/{ticker} 응답 */
export interface DiscoverResult {
  origin: {
    ticker:  string;
    name:    string;
    sector:  string;
    country: string;
  };
  suppliers:       DiscoveredCompany[];
  buyers:          DiscoveredCompany[];
  relations_saved: number;
  summary:         string;
  /** 데이터 출처: "DART+LLM" | "DART재무+LLM" | "LLM" */
  data_source:     string;
  /** DART 재무데이터 (한국 주식만, 글로벌은 null) */
  dart_financial?: {
    revenue?:          number;
    operating_income?: number;
    net_income?:       number;
    liquidity_score?:  number;
    year?:             number;
  } | null;
}

export interface AffectedCompany {
  ticker:          string;
  name:            string;
  shock_intensity: number;
  direction:       string;
  reason:          string;
}

/** POST /api/v1/ai/news-shock 응답 */
export interface NewsShockResult {
  event_title:        string;
  event_category:     string;
  affected_companies: AffectedCompany[];
  summary:            string;
}
