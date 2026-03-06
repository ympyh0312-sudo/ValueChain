"""
app/services/ticker_resolver.py
---------------------------------------------------------
회사명 → 티커 퍼지 매칭 리졸버.

뉴스에는 동일 기업이 여러 형태로 등장:
    "Apple" / "Apple Inc." / "AAPL" / "애플" (번역 포함 가능)

3단계 매칭 전략:
    1. 정확 매칭 (exact)        → confidence=1.0
    2. 대소문자 무시 (casefold) → confidence=0.95
    3. rapidfuzz 퍼지 매칭     → confidence=score/100

최소 신뢰도(min_score) 미만이면 None 반환.
기본 min_score=0.70 (너무 낮으면 오매핑 위험)

레지스트리 구조:
    _name_to_ticker: dict[normalized_name, ticker]
    - 티커 자체도 키로 등록 ("aapl" → "AAPL")
    - 회사명도 키로 등록 ("apple inc." → "AAPL")

TTL 캐시:
    _loaded_at: 마지막 로드 시각
    refresh()를 명시적으로 호출하거나, 앱 시작 시 1회 호출
"""

import time
from typing import Optional

from rapidfuzz import fuzz, process

from app.core.logging import get_logger

logger = get_logger(__name__)

# 매칭 최소 임계값 (0~100 스케일)
_FUZZY_MIN_SCORE = 70


class TickerRegistry:
    """
    Neo4j 기업 목록 기반 티커 리졸버.

    Neo4j에 등록된 기업의 ticker / name을 인메모리 인덱스로 캐싱.
    rapidfuzz로 O(n) 퍼지 매칭 수행.

    Usage:
        await ticker_registry.refresh()           # 앱 시작 시 or 주기적 갱신
        ticker, score = ticker_registry.resolve("Apple Inc.")
        # → ("AAPL", 0.98)
    """

    def __init__(self) -> None:
        # normalized_name → ticker (소문자 키)
        self._name_to_ticker: dict[str, str] = {}
        # rapidfuzz 검색 대상 (choices)
        self._choices: list[str] = []
        self._loaded_at: float = 0.0
        self._company_count: int = 0

    async def refresh(self) -> int:
        """
        Neo4j에서 전체 기업 목록을 로드하여 인덱스 재구성.

        Returns:
            로드된 기업 수

        Note:
            import를 함수 안에서 수행하는 이유: 순환 임포트 방지
            (graph_repository → neo4j_client → ... 의존 체인)
        """
        from app.db.graph_repository import get_all_companies

        companies = await get_all_companies()

        self._name_to_ticker = {}
        for company in companies:
            ticker = company["ticker"]
            name   = (company.get("name") or "").strip()

            # 티커 자체를 키로 등록 (대소문자 무시)
            self._name_to_ticker[ticker.lower()] = ticker

            # 회사명을 키로 등록
            if name:
                self._name_to_ticker[name.lower()] = ticker

                # 약어 변형 등록: "Inc.", "Corp.", "Ltd." 제거 버전
                simplified = (
                    name.lower()
                    .replace(" inc.", "").replace(" inc", "")
                    .replace(" corp.", "").replace(" corp", "")
                    .replace(" ltd.", "").replace(" ltd", "")
                    .replace(" co.", "").replace(" co", "")
                    .replace(" corporation", "")
                    .replace(" limited", "")
                    .strip()
                )
                if simplified and simplified != name.lower():
                    self._name_to_ticker[simplified] = ticker

        self._choices    = list(self._name_to_ticker.keys())
        self._loaded_at  = time.time()
        self._company_count = len(companies)

        logger.info(
            "ticker_registry_refreshed",
            companies=len(companies),
            index_entries=len(self._name_to_ticker),
        )
        return len(companies)

    def resolve(
        self,
        company_name: str,
        min_score: float = 0.70,
    ) -> tuple[Optional[str], float]:
        """
        회사명 → (ticker, confidence) 반환.

        3단계 매칭:
            1. exact match (정확 일치)
            2. casefold match (대소문자 무시)
            3. rapidfuzz WRatio 퍼지 매칭

        Args:
            company_name: 매칭할 회사명 또는 티커
            min_score:    최소 신뢰도 (기본 0.70)

        Returns:
            (ticker, confidence) 또는 (None, 0.0)
        """
        if not company_name or not self._choices:
            return None, 0.0

        query = company_name.strip()

        # ── 1단계: 정확 매칭 ───────────────────────────────────────
        if query in self._name_to_ticker:
            return self._name_to_ticker[query], 1.0

        # ── 2단계: 대소문자 무시 ───────────────────────────────────
        query_lower = query.lower()
        if query_lower in self._name_to_ticker:
            return self._name_to_ticker[query_lower], 0.95

        # ── 3단계: rapidfuzz 퍼지 매칭 (WRatio: 어순 무관) ─────────
        match = process.extractOne(
            query_lower,
            self._choices,
            scorer=fuzz.WRatio,
        )
        if match is None:
            return None, 0.0

        best_name, raw_score, _ = match
        confidence = raw_score / 100.0

        if confidence < min_score:
            logger.debug(
                "ticker_resolve_failed",
                query=company_name,
                best_match=best_name,
                score=round(confidence, 3),
                min_score=min_score,
            )
            return None, confidence

        ticker = self._name_to_ticker[best_name]
        logger.debug(
            "ticker_resolved",
            query=company_name,
            ticker=ticker,
            via=best_name,
            score=round(confidence, 3),
        )
        return ticker, round(confidence, 4)

    def resolve_pair(
        self,
        supplier_name: str,
        buyer_name:    str,
        min_score:     float = 0.70,
    ) -> tuple[
        tuple[Optional[str], float],
        tuple[Optional[str], float],
    ]:
        """
        공급사 + 구매사 이름을 동시에 해결.

        Returns:
            ((supplier_ticker, score), (buyer_ticker, score))
        """
        return (
            self.resolve(supplier_name, min_score),
            self.resolve(buyer_name,    min_score),
        )

    @property
    def is_loaded(self) -> bool:
        """레지스트리가 로드됐는지 여부."""
        return bool(self._choices)

    @property
    def company_count(self) -> int:
        """등록된 기업 수."""
        return self._company_count

    def add_entry(self, ticker: str, name: str) -> None:
        """
        단일 기업을 레지스트리에 즉시 추가 (refresh 없이).

        새 기업을 upsert_company()로 Neo4j에 추가한 직후 호출해
        레지스트리를 동기화할 때 사용.
        """
        ticker_up = ticker.upper()
        self._name_to_ticker[ticker_up.lower()] = ticker_up
        if name:
            self._name_to_ticker[name.lower()] = ticker_up
        # choices 재빌드
        self._choices = list(self._name_to_ticker.keys())


# ── 모듈 레벨 싱글턴 ────────────────────────────────────
ticker_registry = TickerRegistry()
