"""
app/services/dart_client.py
---------------------------------------------------------
금융감독원 전자공시시스템 (DART) OpenAPI 비동기 클라이언트.

DART API 공식 문서: https://opendart.fss.or.kr
API 키 발급: https://opendart.fss.or.kr → 로그인 → 인증키 신청/관리

주요 기능:
1. 기업 기본정보 조회 (6자리 주식코드 → DART corp_code 변환)
2. 재무제표 데이터 조회 (매출액, 영업이익, 자본 → LiquidityBuffer 계산)
3. 사업보고서 원문에서 공급망 관련 텍스트 추출 (LLM 컨텍스트용)
4. 전체 상장사 목록 조회 (KOSPI + KOSDAQ)

DART 코드 체계:
- stock_code: 6자리 KRX 주식코드 (예: 005930 = 삼성전자)
- corp_code:  8자리 DART 고유코드 (예: 00126380 = 삼성전자)
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

# 사업보고서 종류 코드
REPRT_ANNUAL = "11011"   # 사업보고서
REPRT_Q1     = "11013"   # 1분기보고서
REPRT_HALF   = "11012"   # 반기보고서
REPRT_Q3     = "11014"   # 3분기보고서

# 재무제표 계정과목 → 영문 키 매핑
ACCOUNT_MAP: dict[str, str] = {
    "매출액":           "revenue",
    "영업이익":         "operating_income",
    "당기순이익":       "net_income",
    "자산총계":         "total_assets",
    "자본총계":         "total_equity",
    "부채총계":         "total_liabilities",
    "현금및현금성자산": "cash",
}

# 사업보고서 공급망 관련 키워드 (원문 파싱용)
SUPPLY_CHAIN_KEYWORDS: list[str] = [
    "주요 매출처", "주요매출처",
    "주요 고객", "주요고객",
    "주요 공급업체", "주요공급업체",
    "원재료 공급", "원재료공급",
    "주요 거래처", "주요거래처",
    "원재료 구매", "부품 구매",
    "핵심 원재료", "원재료 현황",
    "매출처별", "공급사 현황",
    "매출처 구성", "원재료 조달",
]


class DartClient:
    """
    DART OpenAPI 비동기 HTTP 클라이언트.

    Usage:
        info    = await dart_client.get_company_info("005930")
        fin     = await dart_client.get_financial_data(info["corp_code"])
        sc_text = await dart_client.extract_supply_chain_text(info["corp_code"])
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._key      = self._settings.dart_api_key
        self._http: Optional[httpx.AsyncClient] = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    @property
    def is_available(self) -> bool:
        """DART API 키가 설정되어 있는지 확인."""
        return bool(self._key and self._key != "여기에_발급받은_DART_API_키_입력")

    # ── 1. 기업 기본정보 ──────────────────────────────────────

    async def get_company_info(self, stock_code: str) -> dict:
        """
        6자리 주식코드 → DART 기업 기본정보 조회.

        Returns:
            {
              "corp_code":  "00126380",
              "name":       "삼성전자",
              "industry":   "전자부품, 컴퓨터, 영상...",
              "stock_code": "005930",
              "market":     "KOSPI",   # KOSPI | KOSDAQ
            }
            실패 시 빈 dict 반환.
        """
        if not self.is_available:
            return {}
        try:
            resp = await self._client().get(
                f"{DART_BASE}/company.json",
                params={"crtfc_key": self._key, "stock_code": stock_code},
            )
            data = resp.json()
            if data.get("status") == "000":
                corp_cls = data.get("corp_cls", "")
                return {
                    "corp_code":  data.get("corp_code", ""),
                    "name":       data.get("corp_name", ""),
                    "industry":   data.get("induty_code", ""),
                    "stock_code": stock_code,
                    "market":     "KOSPI" if corp_cls == "Y" else "KOSDAQ",
                }
        except Exception as e:
            logger.warning("dart_company_info_failed", stock_code=stock_code, error=str(e))
        return {}

    # ── 2. 재무제표 데이터 ────────────────────────────────────

    async def get_financial_data(
        self,
        corp_code: str,
        year: Optional[int] = None,
    ) -> dict:
        """
        DART 단일 재무제표 조회. CFS(연결) → OFS(개별) 순서로 시도.

        Args:
            corp_code: DART 8자리 기업코드
            year:      회계연도 (기본값: 전년도)

        Returns:
            {
              "revenue":          302_231_억원,
              "operating_income": 6_566_억원,
              "net_income":       14_730_억원,
              "total_assets":     4_263_억원,
              "total_equity":     2_941_억원,
              "liquidity_score":  0.62,   # ROE 기반 계산
              "debt_ratio":       0.31,
              "year":             2023,
            }
            실패 시 빈 dict 반환.
        """
        if not self.is_available or not corp_code:
            return {}

        target_year = year or (datetime.now().year - 1)

        for fs_div in ("CFS", "OFS"):   # 연결재무제표 → 개별재무제표 순
            try:
                resp = await self._client().get(
                    f"{DART_BASE}/fnlttSinglAcnt.json",
                    params={
                        "crtfc_key":  self._key,
                        "corp_code":  corp_code,
                        "bsns_year":  str(target_year),
                        "reprt_code": REPRT_ANNUAL,
                        "fs_div":     fs_div,
                    },
                )
                data = resp.json()
                if data.get("status") == "000" and data.get("list"):
                    return self._parse_financial_items(data["list"], target_year)
            except Exception as e:
                logger.debug(
                    "dart_financial_attempt_failed",
                    corp_code=corp_code, fs_div=fs_div, error=str(e),
                )

        return {}

    def _parse_financial_items(self, items: list, year: int) -> dict:
        """재무 항목 리스트 → 필요한 값 추출 + LiquidityScore 계산."""
        result: dict = {"year": year}

        for item in items:
            account_nm = item.get("account_nm", "")
            for kr_name, en_key in ACCOUNT_MAP.items():
                if kr_name in account_nm and en_key not in result:
                    try:
                        val_str = (
                            item.get("thstrm_amount", "0")
                            .replace(",", "").strip()
                        )
                        if val_str and val_str not in ("-", ""):
                            result[en_key] = int(val_str)
                    except (ValueError, AttributeError):
                        pass

        # LiquidityScore = ROE 기반 (당기순이익 / 자본총계)
        net_income   = result.get("net_income", 0)
        total_equity = result.get("total_equity", 0)
        if total_equity and total_equity > 0 and net_income:
            roe = net_income / total_equity
            # ROE를 [0.15, 0.85] 범위 LiquidityScore로 변환
            result["liquidity_score"] = round(
                max(0.15, min(0.85, 0.50 + roe * 0.35)), 4
            )

        # 부채비율 (재무 건전성 참고용)
        total_assets      = result.get("total_assets", 0)
        total_liabilities = result.get("total_liabilities", 0)
        if total_assets and total_assets > 0 and total_liabilities:
            result["debt_ratio"] = round(total_liabilities / total_assets, 4)

        return result

    # ── 3. 사업보고서 원문 공급망 텍스트 추출 ────────────────

    async def get_latest_rcept_no(self, corp_code: str) -> Optional[str]:
        """최신 사업보고서 접수번호(rcept_no) 조회."""
        if not self.is_available or not corp_code:
            return None
        try:
            resp = await self._client().get(
                f"{DART_BASE}/list.json",
                params={
                    "crtfc_key":        self._key,
                    "corp_code":        corp_code,
                    "pblntf_ty":        "A",       # 정기공시
                    "pblntf_detail_ty": "A001",    # 사업보고서
                    "page_no":          "1",
                    "page_count":       "5",
                },
            )
            data = resp.json()
            if data.get("status") == "000" and data.get("list"):
                for report in data["list"]:
                    if "사업보고서" in report.get("report_nm", ""):
                        return report.get("rcept_no")
        except Exception as e:
            logger.warning("dart_list_failed", corp_code=corp_code, error=str(e))
        return None

    async def extract_supply_chain_text(
        self,
        corp_code: str,
        keywords: list[str] | None = None,
    ) -> str:
        """
        사업보고서 원문 zip 다운로드 → XML 파싱 → 섹터별 키워드로 텍스트 추출.

        Args:
            corp_code: DART 8자리 기업코드
            keywords:  섹터별 검색 키워드 리스트.
                       None이면 기본 SUPPLY_CHAIN_KEYWORDS 사용.

        반환값: 키워드 주변 텍스트 (LLM 프롬프트 컨텍스트용, 최대 3000자)
        실패 시 빈 문자열 반환 (LLM만 단독 사용으로 자동 폴백).
        """
        rcept_no = await self.get_latest_rcept_no(corp_code)
        if not rcept_no:
            logger.debug("dart_no_annual_report", corp_code=corp_code)
            return ""

        search_keywords = keywords if keywords is not None else SUPPLY_CHAIN_KEYWORDS

        try:
            resp = await self._client().get(
                f"{DART_BASE}/document.xml",
                params={"crtfc_key": self._key, "rcept_no": rcept_no},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return ""
            return self._parse_zip_for_supply_chain(resp.content, search_keywords)
        except Exception as e:
            logger.warning(
                "dart_doc_extract_failed", corp_code=corp_code, error=str(e)
            )
            return ""

    def _parse_zip_for_supply_chain(
        self, zip_bytes: bytes, keywords: list[str]
    ) -> str:
        """zip 바이트 → XML 파싱 → 키워드 섹션 추출."""
        snippets: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                xml_files = [
                    f for f in zf.namelist()
                    if f.lower().endswith(".xml") and not f.startswith(".")
                ]
                for fname in xml_files[:8]:   # 파일 수 제한 (타임아웃 방지)
                    try:
                        raw  = zf.read(fname).decode("utf-8", errors="ignore")
                        text = self._xml_to_plain_text(raw)
                        snippets.extend(self._extract_keyword_sections(text, keywords))
                        if len(snippets) >= 6:
                            break
                    except Exception:
                        continue
        except zipfile.BadZipFile:
            return ""

        combined = "\n\n".join(snippets)
        return combined[:3000]   # LLM 토큰 제한 고려

    def _xml_to_plain_text(self, xml_str: str) -> str:
        """XML/HTML 태그 제거 → 순수 텍스트."""
        text = re.sub(r"<[^>]+>", " ", xml_str)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_keyword_sections(self, text: str, keywords: list[str]) -> list[str]:
        """지정된 키워드 주변 텍스트 섹션 추출 (중복 제거)."""
        sections: list[str] = []
        seen_positions: set[int] = set()

        for kw in keywords:
            pos = 0
            while True:
                idx = text.find(kw, pos)
                if idx == -1:
                    break
                # 근처 위치에서 이미 추출한 경우 skip
                if any(abs(idx - p) < 200 for p in seen_positions):
                    pos = idx + 1
                    continue
                start   = max(0, idx - 100)
                end     = min(len(text), idx + 700)
                snippet = text[start:end].strip()
                if len(snippet) > 40:
                    sections.append(f"[{kw}]\n{snippet}")
                    seen_positions.add(idx)
                pos = idx + 1

        return sections[:6]   # 섹션 수 제한

    # ── 4. 전체 상장사 목록 ───────────────────────────────────

    async def get_listed_companies(self) -> list[dict]:
        """
        DART 전체 상장사 목록 (corpCode.xml) 조회.
        KOSPI + KOSDAQ 상장 법인만 반환.

        Returns:
            [
              {
                "corp_code":  "00126380",
                "name":       "삼성전자",
                "stock_code": "005930",
                "market":     "KOSPI",
              },
              ...
            ]
        """
        if not self.is_available:
            return []
        try:
            resp = await self._client().get(
                f"{DART_BASE}/corpCode.xml",
                params={"crtfc_key": self._key},
            )
            if resp.status_code != 200:
                return []

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_data = zf.read("CORPCODE.xml").decode("utf-8", errors="ignore")

            root = ET.fromstring(xml_data)
            companies: list[dict] = []
            for item in root.findall(".//list"):
                stock_code = (item.findtext("stock_code") or "").strip()
                corp_cls   = (item.findtext("corp_cls")   or "").strip()
                # 상장 법인만 포함 (Y=KOSPI, K=KOSDAQ)
                if stock_code and corp_cls in ("Y", "K"):
                    companies.append({
                        "corp_code":  (item.findtext("corp_code")  or "").strip(),
                        "name":       (item.findtext("corp_name")  or "").strip(),
                        "stock_code": stock_code,
                        "market":     "KOSPI" if corp_cls == "Y" else "KOSDAQ",
                    })

            logger.info("dart_listed_companies_loaded", count=len(companies))
            return companies
        except Exception as e:
            logger.warning("dart_corp_list_failed", error=str(e))
            return []


# 싱글턴 인스턴스 (앱 전역 공유)
dart_client = DartClient()
