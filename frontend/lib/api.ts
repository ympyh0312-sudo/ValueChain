// ─────────────────────────────────────────────────────────
// lib/api.ts  ─ 백엔드 API 클라이언트
//
// 모든 fetch 호출을 여기서 관리.
// Next.js rewrite(/api/* → localhost:8000/api/*)가 적용되어
// 브라우저에서 /api/v1/... 로 호출하면 백엔드로 프록시됨.
// ─────────────────────────────────────────────────────────

import type {
  HealthResponse,
  SimParams,
  SimResult,
  CompanyResponse,
  CompanyCreate,
  SupplyRelationResponse,
  SupplyRelationCreate,
  SubgraphResponse,
  DiscoverResult,
  NewsShockResult,
} from "@/lib/types";

const BASE = "/api/v1";

// ── 공통 fetch 래퍼 ────────────────────────────────────

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // JSON 파싱 실패 시 기본 메시지 사용
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content 등 응답 바디가 없는 경우
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ── System ─────────────────────────────────────────────

/** 백엔드 헬스 체크 */
export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ── Risk Analysis ───────────────────────────────────────

/** 리스크 전파 시뮬레이션 실행 */
export async function analyzeRisk(params: SimParams): Promise<SimResult> {
  return request<SimResult>(`${BASE}/risk/analyze`, {
    method: "POST",
    body: JSON.stringify({
      ticker:          params.ticker.toUpperCase(),
      shock_intensity: params.shockIntensity,
      decay_lambda:    params.decayLambda,
      time_horizon:    params.timeHorizon,
      max_hop:         params.maxHop,
    }),
  });
}

// ── Network: Company CRUD ───────────────────────────────

/** 기업 목록 조회 (섹터 필터 선택) */
export async function getCompanies(sector?: string): Promise<CompanyResponse[]> {
  const qs = sector ? `?sector=${encodeURIComponent(sector)}` : "";
  return request<CompanyResponse[]>(`${BASE}/network/companies${qs}`);
}

/** 기업 단건 조회 */
export async function getCompany(ticker: string): Promise<CompanyResponse | null> {
  try {
    return await request<CompanyResponse>(
      `${BASE}/network/companies/${ticker.toUpperCase()}`
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** 기업 생성/업데이트 */
export async function createCompany(data: CompanyCreate): Promise<CompanyResponse> {
  return request<CompanyResponse>(`${BASE}/network/companies`, {
    method: "POST",
    body:   JSON.stringify(data),
  });
}

/** 기업 삭제 */
export async function deleteCompany(ticker: string): Promise<void> {
  return request<void>(
    `${BASE}/network/companies/${ticker.toUpperCase()}`,
    { method: "DELETE" }
  );
}

// ── Network: Relations ──────────────────────────────────

/** 공급 관계 생성/업데이트 */
export async function createRelation(
  data: SupplyRelationCreate
): Promise<SupplyRelationResponse> {
  return request<SupplyRelationResponse>(`${BASE}/network/relations`, {
    method: "POST",
    body:   JSON.stringify(data),
  });
}

/** 직접 공급사 목록 */
export async function getSuppliers(ticker: string): Promise<Record<string, unknown>[]> {
  return request<Record<string, unknown>[]>(
    `${BASE}/network/companies/${ticker.toUpperCase()}/suppliers`
  );
}

/** 직접 구매사 목록 */
export async function getBuyers(ticker: string): Promise<Record<string, unknown>[]> {
  return request<Record<string, unknown>[]>(
    `${BASE}/network/companies/${ticker.toUpperCase()}/buyers`
  );
}

/** 서브그래프 조회 (Force Graph 초기 데이터용) */
export async function getSubgraph(
  ticker:  string,
  maxHop:  number = 3
): Promise<SubgraphResponse> {
  return request<SubgraphResponse>(
    `${BASE}/network/companies/${ticker.toUpperCase()}/subgraph?max_hop=${maxHop}`
  );
}

// ── AI Analysis ─────────────────────────────────────────

/**
 * LLM으로 임의 티커의 공급망을 자동 발견하고 Neo4j에 저장.
 * 저장 후 analyzeRisk() 호출 시 발견된 기업들이 시뮬레이션에 포함됨.
 */
export async function discoverSupplyChain(
  ticker:    string,
  saveToDb:  boolean = true,
): Promise<DiscoverResult> {
  return request<DiscoverResult>(
    `${BASE}/ai/discover/${ticker.toUpperCase()}?save_to_db=${saveToDb}`,
    { method: "POST" },
  );
}

/**
 * 뉴스 텍스트 → 공급망 채널을 통해 영향받는 기업 + 충격 강도 추정.
 * 결과의 ticker/shock_intensity로 시뮬레이션 파라미터를 설정 가능.
 */
export async function analyzeNewsShock(newsText: string): Promise<NewsShockResult> {
  return request<NewsShockResult>(`${BASE}/ai/news-shock`, {
    method: "POST",
    body:   JSON.stringify({ news_text: newsText }),
  });
}

export { ApiError };
