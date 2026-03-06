"""
app/services/supply_chain_discoverer.py
---------------------------------------------------------
LLM 기반 공급망 자동 발견 서비스.

기능:
1. 임의의 티커에 대해 yfinance로 기업 메타데이터 조회
2. LLM에게 공급망 관계 질의 (상위 공급사 + 하위 구매사)
3. 발견된 기업과 관계를 Neo4j에 자동 저장
4. 뉴스 텍스트 → 영향받는 기업 + 충격 강도 추정

흐름:
  ticker
    → yfinance (기업정보) or LLM fallback
    → 섹터 감지 → 섹터별 시스템 프롬프트 선택
    → [한국 6자리] DART 사업보고서 텍스트 추출 (컨텍스트)
    → LLM (공급망 발견, 구조화 출력)
    → Neo4j (MERGE로 idempotent 저장)
    → DiscoveryResult 반환

뉴스 충격 분석:
  news_text → LLM → [{ticker, shock_intensity, event_type}]
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.graph_repository import upsert_company, upsert_supply_relation
from app.models.graph_models import CompanyCreate, SupplyRelationCreate

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────
# Pydantic 스키마: LLM 구조화 출력 (supply chain discovery)
# ─────────────────────────────────────────────────────

class DiscoveredCompany(BaseModel):
    """LLM이 발견한 관계사 기업."""
    ticker:               str   = Field(description="Stock ticker (NYSE/NASDAQ for US, 6-digit KRX for Korea e.g. 005930)")
    name:                 str   = Field(description="Official full company name")
    sector:               str   = Field(description="GICS sector e.g. Technology, Semiconductors, Pharmaceuticals")
    country:              str   = Field(description="HQ country e.g. USA, South Korea, Taiwan, Japan, Germany")
    dependency_score:     float = Field(ge=0.0, le=1.0, description="Buyer dependency on this specific supplier (0=replaceable, 1=critical)")
    revenue_share:        float = Field(ge=0.0, le=1.0, description="Fraction of supplier's total revenue from this relationship")
    confidence_score:     float = Field(ge=0.0, le=1.0, description="Confidence this relationship is accurate (skip if < 0.6)")
    liquidity_score:      float = Field(default=0.60, ge=0.0, le=1.0, description="Financial liquidity (ability to absorb shocks)")
    supplier_concentration: float = Field(default=0.50, ge=0.0, le=1.0)


class DiscoveryOutput(BaseModel):
    """LLM 공급망 발견 전체 출력."""
    origin_ticker:    str
    origin_name:      str
    origin_sector:    str
    origin_country:   str
    origin_liquidity: float = 0.60
    suppliers: list[DiscoveredCompany] = Field(
        default_factory=list,
        description="Key upstream suppliers (max 5)"
    )
    buyers: list[DiscoveredCompany] = Field(
        default_factory=list,
        description="Key downstream customers/buyers (max 5)"
    )
    summary: str = Field(description="1-2 sentence summary of supply chain position")


# ─────────────────────────────────────────────────────
# Pydantic 스키마: 뉴스 충격 분석
# ─────────────────────────────────────────────────────

class AffectedCompany(BaseModel):
    ticker:          str   = Field(description="Stock ticker of affected company")
    name:            str   = Field(description="Company name")
    shock_intensity: float = Field(ge=0.0, le=1.0, description="Estimated shock (0=none, 1=catastrophic)")
    direction:       str   = Field(description="Impact type: supply_disruption | demand_shock | regulatory | geopolitical | financial")
    reason:          str   = Field(description="Brief explanation of why this company is affected")

class NewsShockOutput(BaseModel):
    event_title:    str   = Field(description="Brief title for this news event")
    event_category: str   = Field(description="Category: war | sanctions | natural_disaster | tech_ban | financial_crisis | other")
    affected_companies: list[AffectedCompany] = Field(
        default_factory=list,
        description="Companies directly or indirectly affected (max 10)"
    )
    summary: str = Field(description="2-3 sentence analysis of systemic supply chain impact")


# ─────────────────────────────────────────────────────
# 섹터별 시스템 프롬프트 + 공통 출력 규칙
# ─────────────────────────────────────────────────────

_BASE_RULES = """\
CRITICAL OUTPUT RULES (apply to ALL sectors):
- Include ONLY relationships with confidence_score >= 0.6
- Maximum 5 suppliers + 5 buyers (prioritize by strategic importance)
- Use correct tickers: NYSE/NASDAQ for US, 6-digit code for KRX Korea (e.g. 005930), Japan ADR (e.g. SHNEY for Shin-Etsu)
- dependency_score: how much the BUYER depends on this supplier (0.9=irreplaceable, 0.3=easily switched)
- revenue_share: fraction of the SUPPLIER's total revenue from this relationship
- Well-known confirmed: confidence_score=0.90-0.95 | Commonly reported: 0.75-0.89 | Estimated: 0.60-0.74
- Sector must be GICS-compliant: Semiconductors, Technology, Oil & Gas, Pharmaceuticals, Automotive, etc.
- Country: "USA", "South Korea", "Taiwan", "Japan", "Germany", "Netherlands", "Switzerland", etc.
- Provide realistic liquidity_score (large stable companies ~0.7, smaller/volatile ~0.5)
"""

SECTOR_SYSTEM_PROMPTS: dict[str, str] = {
    "semiconductor": """\
You are a world-class semiconductor supply chain analyst (2024).

Focus on: wafer fab equipment, EDA tools, photomasks, specialty chemicals, substrates, test & packaging, foundry.
SUPPLIERS: ASML (ASML), Applied Materials (AMAT), Lam Research (LRCX), KLA (KLAC),
           Shin-Etsu (SHNEY), SUMCO, Entegris (ENTG), JSR, Tokyo Electron (TOELY).
BUYERS: major chip buyers — NVDA, AMD, INTC, QCOM, AAPL, GOOG, AMZN, MSFT,
        Samsung (005930), SK하이닉스 (000660).
STRICTLY EXCLUDE: generic software vendors (CRM, WDAY, NOW), retailers, financial companies.
""",

    "financial": """\
You are a financial services supply chain analyst specializing in banking ecosystems (2024).

For FINANCIAL COMPANIES (banks, insurance, asset managers):
- SUPPLIERS = financial infrastructure providers:
  * Payment networks: Visa (V), Mastercard (MA)
  * Core banking software: FIS (FIS), Fiserv (FISV), Jack Henry (JKHY)
  * Market data: Bloomberg (private), LSEG (LSEG.L)
  * Cloud: AWS (AMZN), Azure (MSFT), GCP (GOOG)
  * Cybersecurity: Palo Alto (PANW), CrowdStrike (CRWD)
- Korean banks specifically use: 삼성SDS (018260), LG CNS (private), SK(주) C&C (034730),
  금융결제원 (private), SWIFT network, 한국거래소 결제시스템 (KRX settlement)
- BUYERS = large corporations using banking services (loans, FX, investment banking)

STRICTLY EXCLUDE: Salesforce (CRM), Workday (WDAY), ServiceNow (NOW) — these are NOT supply chain partners.
DO NOT assign manufacturing or component suppliers to financial companies.
DO NOT hallucinate IT vendor relationships with confidence > 0.6 unless clearly confirmed.
""",

    "automotive": """\
You are a world-class automotive supply chain analyst (2024).

Focus on: Tier-1 suppliers (seats, electronics, drivetrain), Tier-2 (steel, aluminum, chips),
          EV battery cells, charging infrastructure.
SUPPLIERS: Bosch, Continental, Denso (DNZOY), Magna (MGA), BorgWarner (BWA),
           CATL (300750), LG에너지솔루션 (373220), 삼성SDI (006400), Aptiv (APTV), Autoliv (ALV).
BUYERS (OEMs): Tesla (TSLA), Toyota (TM), Ford (F), GM, Hyundai (005380), Kia (000270), BMW, Mercedes.
STRICTLY EXCLUDE: generic software vendors, financial companies.
""",

    "pharma": """\
You are a pharmaceutical supply chain analyst (2024).

Focus on: API manufacturers, CROs, CDMOs, specialty chemicals, medical devices, distribution.
SUPPLIERS: Lonza (LZAGY), Samsung Biologics (207940), WuXi AppTec, Catalent,
           Thermo Fisher (TMO), Danaher (DHR), Bachem.
BUYERS: major pharma — PFE, JNJ, MRK, AZN, NVO, Celltrion (068270), 유한양행 (000661).
STRICTLY EXCLUDE: generic IT companies, financial services.
""",

    "energy": """\
You are an energy sector supply chain analyst (2024).

Focus on: upstream (exploration equipment, drilling), midstream (pipelines, LNG terminals),
          downstream (refinery equipment, petrochemicals), renewables (solar, wind).
SUPPLIERS: Schlumberger (SLB), Halliburton (HAL), Baker Hughes (BKR), Technip, Siemens Energy, Vestas.
STRICTLY EXCLUDE: generic software/IT vendors, retailers.
""",

    "consumer": """\
You are a consumer goods supply chain analyst (2024).

Focus on: raw materials (agricultural, packaging), contract manufacturing, logistics, retail distribution.
BUYERS include major retailers: Walmart (WMT), Amazon (AMZN), Costco (COST),
                                롯데쇼핑 (023530), 이마트 (139480).
STRICTLY EXCLUDE: semiconductor companies, financial services.
""",

    "software": """\
You are a software/SaaS ecosystem analyst (2024).

For SOFTWARE COMPANIES:
- SUPPLIERS = cloud infrastructure (AWS/Azure/GCP), CDN providers, security vendors, data providers
- BUYERS = enterprise customers, SMBs, government agencies using the software

STRICTLY EXCLUDE: physical manufacturing suppliers (steel, chemicals, auto parts).
""",

    "telecom": """\
You are a telecommunications supply chain analyst (2024).

Focus on: network equipment (RAN, core, fiber), handset supply chain, tower companies, spectrum.
SUPPLIERS: Ericsson (ERIC), Nokia (NOK), Samsung Networks (005930 subsegment),
           Qualcomm (QCOM for chips), CommScope (COMM).
BUYERS: operators — T-Mobile (TMUS), Verizon (VZ), AT&T (T),
        SKT (017670), KT (030200), LGU+ (032640).
STRICTLY EXCLUDE: generic office software vendors.
""",

    "battery_materials": """\
You are a battery materials supply chain analyst (2024).

Focus on: lithium/nickel/cobalt mining → cathode/anode materials → cell manufacturing → battery pack.
SUPPLIERS: 포스코홀딩스 (005490), 에코프로비엠 (247540), 엘앤에프 (066970),
           Umicore, SQM (SQM), Albemarle (ALB).
BUYERS: cell makers — CATL (300750), LG에너지솔루션 (373220), 삼성SDI (006400), Panasonic.
STRICTLY EXCLUDE: software companies, financial services.
""",

    "defense": """\
You are a defense industry supply chain analyst (2024).

Focus on: prime contractors, sub-contractors (electronics, propulsion, structures), government procurement.
SUPPLIERS: Raytheon (RTX), L3Harris (LHX), Northrop Grumman (NOC), General Dynamics (GD),
           한화에어로스페이스 (012450), LIG넥스원 (079550).
BUYERS: government (DoD, NATO, 방위사업청 DAPA), prime contractors as system integrators.
STRICTLY EXCLUDE: consumer software, financial services.
""",

    "default": """\
You are a world-class supply chain analyst with comprehensive knowledge of global corporate supply chains (2024).

Identify ACTUAL supply chain relationships:
1. Key SUPPLIERS (upstream): companies providing critical components, materials, or services TO the target company
2. Key BUYERS/CUSTOMERS (downstream): companies purchasing products/services FROM the target company

STRICTLY EXCLUDE relationships you are not confident about.
DO NOT guess IT vendor relationships for non-tech companies.
""",
}

SECTOR_DART_KEYWORDS: dict[str, list[str]] = {
    "semiconductor": [
        "주요 매출처", "주요매출처", "원재료 공급", "웨이퍼", "장비 공급업체",
        "원재료 구매", "핵심 원재료", "소재 공급", "파운드리",
    ],
    "financial": [
        "주요 거래처", "주요고객", "IT 서비스", "전산 시스템", "결제 인프라",
        "외부 위탁", "아웃소싱", "제휴사", "주요 조달처", "정보시스템",
    ],
    "automotive": [
        "주요 매출처", "원재료 공급", "부품 구매", "1차 협력사", "2차 협력사",
        "핵심 원재료", "배터리 공급", "반도체 공급",
    ],
    "pharma": [
        "원료의약품", "CMO", "CRO", "주요 공급업체", "원재료 조달",
        "의약품 원료", "주요 매출처", "납품처",
    ],
    "energy": [
        "주요 매출처", "원유 조달", "천연가스 공급", "플랜트 공급업체",
        "자원 개발", "에너지 공급계약",
    ],
    "default": [
        "주요 매출처", "주요매출처", "주요 고객", "주요고객",
        "주요 공급업체", "주요공급업체", "원재료 공급", "원재료공급",
        "주요 거래처", "주요거래처", "원재료 구매", "부품 구매",
        "핵심 원재료", "원재료 현황", "매출처별", "공급사 현황",
        "매출처 구성", "원재료 조달",
    ],
}


def _detect_sector_type(sector: str, industry: str = "") -> str:
    """yfinance sector/industry 문자열 → 내부 섹터 타입 변환."""
    s = (sector + " " + industry).lower()
    if any(w in s for w in ["semiconductor", "chip", "wafer", "electronic component"]):
        return "semiconductor"
    if any(w in s for w in ["bank", "financial service", "insurance", "asset management", "capital market", "금융"]):
        return "financial"
    if any(w in s for w in ["auto", "vehicle", "automobile", "motor vehicle"]):
        return "automotive"
    if any(w in s for w in ["pharma", "biotech", "drug", "medical device", "health care"]):
        return "pharma"
    if any(w in s for w in ["oil", "gas", "energy", "refin", "petroleum", "coal"]):
        return "energy"
    if any(w in s for w in ["consumer", "retail", "food", "beverage", "staple"]):
        return "consumer"
    if any(w in s for w in ["software", "saas", "cloud", "internet", "platform"]):
        return "software"
    if any(w in s for w in ["telecom", "communication", "wireless", "broadband"]):
        return "telecom"
    if any(w in s for w in ["defense", "aerospace", "military", "weapon"]):
        return "defense"
    if any(w in s for w in ["battery", "cathode", "anode", "lithium"]):
        return "battery_materials"
    return "default"


def _build_system_prompt(sector_type: str) -> str:
    """섹터별 시스템 프롬프트 + 공통 출력 규칙 결합."""
    sector_prompt = SECTOR_SYSTEM_PROMPTS.get(sector_type, SECTOR_SYSTEM_PROMPTS["default"])
    return sector_prompt + "\n" + _BASE_RULES


NEWS_SHOCK_SYSTEM_PROMPT = """\
You are a systemic risk analyst specializing in supply chain contagion from geopolitical and economic shocks.

Analyze the provided news and identify which LISTED COMPANIES would be affected through supply chain channels.

RULES:
- Focus on supply chain impact (not just stock price speculation)
- Consider: direct exposure, 1st-degree supply chain, industry-wide effects
- shock_intensity: 1.0=company effectively shut down, 0.7=severe disruption, 0.4=significant but manageable, 0.2=mild impact
- direction categories:
  * supply_disruption: company cannot get key inputs
  * demand_shock: company loses major customers
  * regulatory: new regulations/bans affecting company
  * geopolitical: trade war, sanctions, country-level risk
  * financial: credit, payment, insurance disruption
- Include both US and Korean stocks with correct tickers
- Maximum 10 companies, minimum shock_intensity 0.15 to be included
- For war/sanctions: defense companies get positive (opportunity), not shock (set shock_intensity low)
- For defense/war context: BA, RTX, LMT, 012450 (Hanwha) benefit → use shock_intensity 0.1 but mark as demand_shock positive
"""


# ─────────────────────────────────────────────────────
# yfinance 기업 정보 조회 (선택적 의존성)
# ─────────────────────────────────────────────────────

def _fetch_yfinance_info(ticker: str) -> dict:
    """
    yfinance로 기업 메타데이터 조회.
    한국 주식: 6자리 숫자 → {ticker}.KS 변환
    실패 시 빈 dict 반환 (LLM fallback).
    """
    try:
        import yfinance as yf  # optional dependency

        yf_ticker = ticker
        # 한국 코스피/코스닥: 6자리 숫자 → KRX suffix
        if ticker.isdigit() and len(ticker) == 6:
            yf_ticker = f"{ticker}.KS"

        info = yf.Ticker(yf_ticker).info
        return {
            "name":     info.get("longName") or info.get("shortName", ""),
            "sector":   info.get("sector", ""),
            "industry": info.get("industry", ""),
            "country":  info.get("country", ""),
        }
    except Exception as e:
        logger.debug("yfinance_lookup_failed", ticker=ticker, error=str(e))
        return {}


# ─────────────────────────────────────────────────────
# 공급망 자동 발견 서비스
# ─────────────────────────────────────────────────────

class SupplyChainDiscoverer:
    """
    LLM 기반 공급망 자동 발견 + Neo4j 저장.

    Usage:
        discoverer = SupplyChainDiscoverer()
        result = await discoverer.discover("NVDA")
        result = await discoverer.discover("105560")   # KB금융 (DART 경로)
        result = await discoverer.analyze_news("Ukraine war escalates...")
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm: Optional[ChatOpenAI] = None

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self._settings.llm_model,
                temperature=0,
                api_key=self._settings.openai_api_key,
            )
        return self._llm

    async def _call_llm_structured(
        self,
        human_prompt: str,
        system_prompt: str,
    ) -> DiscoveryOutput:
        """섹터별 시스템 프롬프트를 받아 LLM 구조화 출력 호출."""
        llm = self._get_llm()
        structured_llm = llm.with_structured_output(DiscoveryOutput)
        return await structured_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])

    # ── 1. 공급망 발견 (라우팅) ────────────────────────

    async def discover(
        self,
        ticker: str,
        save_to_db: bool = True,
    ) -> dict:
        """
        임의 티커의 공급망을 LLM으로 발견하고 Neo4j에 저장.

        한국 6자리 코드 → DART 사업보고서 텍스트 활용 경로
        해외 티커 → 글로벌 LLM 지식 경로

        Returns:
            {
              "origin": {...},
              "suppliers": [...],
              "buyers": [...],
              "relations_saved": int,
              "summary": "...",
              "data_source": "DART+LLM" | "LLM",
              "dart_financial": {...},
            }
        """
        ticker = ticker.upper().strip()
        logger.info("supply_chain_discovery_started", ticker=ticker)

        # yfinance로 기업 기본정보 + 섹터 감지
        yf_info = _fetch_yfinance_info(ticker)
        sector_type = _detect_sector_type(
            yf_info.get("sector", ""),
            yf_info.get("industry", ""),
        )
        logger.info("sector_detected", ticker=ticker, sector_type=sector_type)

        is_korean = ticker.isdigit() and len(ticker) == 6

        if is_korean:
            return await self._discover_kr_dart(ticker, yf_info, sector_type, save_to_db)
        else:
            return await self._discover_global_llm(ticker, yf_info, sector_type, save_to_db)

    # ── 2. 한국 주식: DART + LLM ──────────────────────

    async def _discover_kr_dart(
        self,
        ticker: str,
        yf_info: dict,
        sector_type: str,
        save_to_db: bool,
    ) -> dict:
        """한국 주식: DART 사업보고서 텍스트를 LLM 컨텍스트로 주입."""
        from app.services.dart_client import dart_client

        dart_text = ""
        dart_financial: dict = {}
        data_source = "LLM"

        if dart_client.is_available:
            try:
                company_info = await dart_client.get_company_info(ticker)
                corp_code = company_info.get("corp_code", "")
                if corp_code:
                    keywords = SECTOR_DART_KEYWORDS.get(sector_type, SECTOR_DART_KEYWORDS["default"])
                    dart_text = await dart_client.extract_supply_chain_text(corp_code, keywords=keywords)
                    dart_financial = await dart_client.get_financial_data(corp_code)
                    if dart_text:
                        data_source = "DART+LLM"
                        logger.info("dart_text_extracted", ticker=ticker, chars=len(dart_text))
            except Exception as e:
                logger.warning("dart_pipeline_failed", ticker=ticker, error=str(e))

        system_prompt = _build_system_prompt(sector_type)

        known_info = ""
        if yf_info.get("name"):
            known_info = (
                f"Known info:\n"
                f"  Company: {yf_info['name']}\n"
                f"  Sector: {yf_info.get('sector', 'Unknown')}\n"
                f"  Industry: {yf_info.get('industry', 'Unknown')}\n"
                f"  Country: {yf_info.get('country', 'Unknown')}\n"
            )

        dart_context = (
            f"\n\n=== DART 사업보고서 공급망 관련 텍스트 ===\n{dart_text}\n"
            if dart_text else ""
        )

        human_prompt = (
            f"Discover the supply chain for Korean company ticker: {ticker}\n"
            f"{known_info}"
            f"{dart_context}\n"
            f"Based on the above business report text AND your knowledge, "
            f"identify the top suppliers and buyers for this company. "
            f"Fill in origin_ticker='{ticker}' in your response."
        )

        output = await self._call_llm_structured(human_prompt, system_prompt)

        logger.info(
            "supply_chain_discovery_completed",
            ticker=ticker,
            suppliers=len(output.suppliers),
            buyers=len(output.buyers),
            data_source=data_source,
        )

        relations_saved = 0
        if save_to_db:
            relations_saved = await self._save_to_neo4j(ticker, yf_info, output, dart_financial)

        return {
            "origin": {
                "ticker":  ticker,
                "name":    yf_info.get("name") or output.origin_name,
                "sector":  yf_info.get("sector") or output.origin_sector,
                "country": yf_info.get("country") or output.origin_country,
            },
            "suppliers":       [c.model_dump() for c in output.suppliers],
            "buyers":          [c.model_dump() for c in output.buyers],
            "relations_saved": relations_saved,
            "summary":         output.summary,
            "data_source":     data_source,
            "dart_financial":  dart_financial,
        }

    # ── 3. 해외 주식: 글로벌 LLM ───────────────────────

    async def _discover_global_llm(
        self,
        ticker: str,
        yf_info: dict,
        sector_type: str,
        save_to_db: bool,
    ) -> dict:
        """해외 주식: yfinance 정보 + 섹터별 LLM 프롬프트."""
        system_prompt = _build_system_prompt(sector_type)

        known_info = ""
        if yf_info.get("name"):
            known_info = (
                f"Known info from financial data:\n"
                f"  Company Name: {yf_info['name']}\n"
                f"  Sector: {yf_info.get('sector', 'Unknown')}\n"
                f"  Industry: {yf_info.get('industry', 'Unknown')}\n"
                f"  Country: {yf_info.get('country', 'Unknown')}\n"
            )

        human_prompt = (
            f"Discover the supply chain for ticker: {ticker}\n"
            f"{known_info}\n"
            f"Identify the top suppliers and buyers for this company. "
            f"Fill in origin_ticker='{ticker}' in your response."
        )

        output = await self._call_llm_structured(human_prompt, system_prompt)

        logger.info(
            "supply_chain_discovery_completed",
            ticker=ticker,
            suppliers=len(output.suppliers),
            buyers=len(output.buyers),
            data_source="LLM",
        )

        relations_saved = 0
        if save_to_db:
            relations_saved = await self._save_to_neo4j(ticker, yf_info, output, {})

        return {
            "origin": {
                "ticker":  ticker,
                "name":    yf_info.get("name") or output.origin_name,
                "sector":  yf_info.get("sector") or output.origin_sector,
                "country": yf_info.get("country") or output.origin_country,
            },
            "suppliers":       [c.model_dump() for c in output.suppliers],
            "buyers":          [c.model_dump() for c in output.buyers],
            "relations_saved": relations_saved,
            "summary":         output.summary,
            "data_source":     "LLM",
            "dart_financial":  {},
        }

    # ── 4. Neo4j 저장 ──────────────────────────────────

    async def _save_to_neo4j(
        self,
        ticker: str,
        yf_info: dict,
        output: DiscoveryOutput,
        dart_financial: dict,
    ) -> int:
        """원점 기업 + 공급사/구매사 + 관계 저장. 저장된 관계 수 반환."""
        # DART 재무데이터에서 liquidity_score 우선 적용
        liquidity = dart_financial.get("liquidity_score", output.origin_liquidity)

        origin_company = CompanyCreate(
            ticker=ticker,
            name=yf_info.get("name") or output.origin_name,
            sector=yf_info.get("sector") or output.origin_sector or "Unknown",
            country=yf_info.get("country") or output.origin_country or "Unknown",
            liquidity_score=liquidity,
            supplier_concentration=0.50,
        )
        try:
            await upsert_company(origin_company)
        except Exception as e:
            logger.warning("origin_upsert_failed", ticker=ticker, error=str(e))

        relations_saved = 0

        for supplier in output.suppliers:
            if supplier.confidence_score < 0.6:
                continue
            await self._upsert_company_and_relation(
                company=supplier,
                supplier_ticker=supplier.ticker,
                buyer_ticker=ticker,
                revenue_share=supplier.revenue_share,
                dependency_score=supplier.dependency_score,
                confidence=supplier.confidence_score,
            )
            relations_saved += 1

        for buyer in output.buyers:
            if buyer.confidence_score < 0.6:
                continue
            await self._upsert_company_and_relation(
                company=buyer,
                supplier_ticker=ticker,
                buyer_ticker=buyer.ticker,
                revenue_share=buyer.revenue_share,
                dependency_score=buyer.dependency_score,
                confidence=buyer.confidence_score,
            )
            relations_saved += 1

        return relations_saved

    async def _upsert_company_and_relation(
        self,
        company:          DiscoveredCompany,
        supplier_ticker:  str,
        buyer_ticker:     str,
        revenue_share:    float,
        dependency_score: float,
        confidence:       float,
    ) -> None:
        """기업 노드 upsert + SUPPLY_TO 관계 생성."""
        try:
            company_create = CompanyCreate(
                ticker=company.ticker.upper(),
                name=company.name,
                sector=company.sector or "Unknown",
                country=company.country or "Unknown",
                liquidity_score=company.liquidity_score,
                supplier_concentration=company.supplier_concentration,
            )
            await upsert_company(company_create)

            relation = SupplyRelationCreate(
                supplier_ticker=supplier_ticker.upper(),
                buyer_ticker=buyer_ticker.upper(),
                revenue_share=round(revenue_share, 4),
                dependency_score=round(dependency_score, 4),
                geographic_exposure=0.40,
                alternative_supplier_score=round(1.0 - dependency_score * 0.8, 4),
                confidence_score=round(confidence, 4),
            )
            await upsert_supply_relation(relation)

        except Exception as e:
            logger.warning(
                "relation_save_failed",
                supplier=supplier_ticker,
                buyer=buyer_ticker,
                error=str(e),
            )

    # ── 5. 뉴스 충격 분석 ──────────────────────────────

    async def analyze_news(self, news_text: str) -> dict:
        """
        뉴스 텍스트 → 영향받는 기업 + 충격 강도 추정.

        Returns:
            {
              "event_title": "...",
              "event_category": "war | sanctions | ...",
              "affected_companies": [{ticker, name, shock_intensity, direction, reason}, ...],
              "summary": "..."
            }
        """
        logger.info("news_shock_analysis_started", text_len=len(news_text))

        llm = self._get_llm()
        structured_llm = llm.with_structured_output(NewsShockOutput)

        output: NewsShockOutput = await structured_llm.ainvoke([
            SystemMessage(content=NEWS_SHOCK_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze this news:\n\n{news_text}"),
        ])

        logger.info(
            "news_shock_analysis_completed",
            event=output.event_title,
            affected=len(output.affected_companies),
        )

        return {
            "event_title":        output.event_title,
            "event_category":     output.event_category,
            "affected_companies": [c.model_dump() for c in output.affected_companies],
            "summary":            output.summary,
        }


# 싱글턴 인스턴스
supply_chain_discoverer = SupplyChainDiscoverer()
