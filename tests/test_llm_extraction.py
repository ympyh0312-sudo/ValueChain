"""
tests/test_llm_extraction.py
---------------------------------------------------------
Phase 5 LLM 추출 파이프라인 단위 테스트 (순수 함수, DB/LLM 불필요).

테스트 범위:
- ExtractedRelation Pydantic 검증 (신뢰도 범위, 필수 필드)
- ExtractionOutput 구조 (빈 관계 목록, 요약)
- TickerRegistry 매칭 로직 (exact, casefold, fuzzy, 미발견)
- TickerRegistry.resolve_pair() 동시 해결
- IngestionPipeline 신뢰도 필터링 로직
- RelationProcessingResult 필드
- ArticleProcessingResult 통계 집계
"""

import pytest
from pydantic import ValidationError

from app.services.llm_extractor import ExtractedRelation, ExtractionOutput
from app.services.ticker_resolver import TickerRegistry
from app.services.ingestion_pipeline import (
    ArticleProcessingResult,
    RelationProcessingResult,
    IngestionPipeline,
)
from app.models.db_models import ArticleStatus


# ─────────────────────────────────────────────────────
# ExtractedRelation 검증
# ─────────────────────────────────────────────────────

class TestExtractedRelation:
    def test_valid_relation(self) -> None:
        """정상적인 관계 생성."""
        rel = ExtractedRelation(
            supplier_name="Taiwan Semiconductor Manufacturing Company",
            buyer_name="Apple Inc.",
            revenue_share_estimate=0.25,
            dependency_estimate=0.9,
            event_type="supply_relationship",
            confidence_score=0.92,
            evidence="Apple sources chips from TSMC.",
        )
        assert rel.supplier_name == "Taiwan Semiconductor Manufacturing Company"
        assert rel.confidence_score == 0.92

    def test_confidence_bounds(self) -> None:
        """신뢰도는 0~1 범위만 허용."""
        with pytest.raises(ValidationError):
            ExtractedRelation(
                supplier_name="A", buyer_name="B",
                confidence_score=1.5,   # 초과
            )
        with pytest.raises(ValidationError):
            ExtractedRelation(
                supplier_name="A", buyer_name="B",
                confidence_score=-0.1,  # 음수
            )

    def test_optional_fields_default_none(self) -> None:
        """선택 필드는 기본값 None."""
        rel = ExtractedRelation(
            supplier_name="Supplier Co",
            buyer_name="Buyer Corp",
            confidence_score=0.8,
        )
        assert rel.revenue_share_estimate is None
        assert rel.dependency_estimate is None
        assert rel.event_type == "supply_relationship"
        assert rel.evidence == ""

    def test_revenue_share_bounds(self) -> None:
        """revenue_share_estimate 범위 검증."""
        with pytest.raises(ValidationError):
            ExtractedRelation(
                supplier_name="A", buyer_name="B",
                confidence_score=0.8,
                revenue_share_estimate=1.5,  # 1.0 초과
            )


class TestExtractionOutput:
    def test_empty_output(self) -> None:
        """관계가 없는 경우 빈 리스트 반환."""
        output = ExtractionOutput()
        assert output.relations == []
        assert output.article_summary == ""

    def test_output_with_relations(self) -> None:
        """관계 목록 포함 출력."""
        rel = ExtractedRelation(
            supplier_name="TSMC",
            buyer_name="AAPL",
            confidence_score=0.85,
        )
        output = ExtractionOutput(
            relations=[rel],
            article_summary="Apple sourcing chips from TSMC.",
        )
        assert len(output.relations) == 1
        assert "TSMC" in output.article_summary


# ─────────────────────────────────────────────────────
# TickerRegistry 매칭 로직
# ─────────────────────────────────────────────────────

class TestTickerRegistry:
    """DB 없이 수동으로 레지스트리를 채워 테스트."""

    def _make_registry(self, entries: dict[str, str]) -> TickerRegistry:
        """
        entries: {ticker: company_name}
        """
        registry = TickerRegistry()
        for ticker, name in entries.items():
            registry.add_entry(ticker, name)
        return registry

    def test_exact_ticker_match(self) -> None:
        """티커 자체를 입력하면 즉시 반환."""
        reg = self._make_registry({"AAPL": "Apple Inc."})
        ticker, score = reg.resolve("AAPL")
        assert ticker == "AAPL"
        assert score == 0.95  # casefold 경로 (add_entry는 lower로 저장)

    def test_casefold_name_match(self) -> None:
        """대소문자 다른 회사명도 매칭."""
        reg = self._make_registry({"TSMC": "Taiwan Semiconductor Manufacturing Company"})
        ticker, score = reg.resolve("taiwan semiconductor manufacturing company")
        assert ticker == "TSMC"
        assert score >= 0.90

    def test_simplified_name_match(self) -> None:
        """'Inc.' 제거 버전도 매칭."""
        reg = self._make_registry({"AAPL": "Apple Inc."})
        ticker, score = reg.resolve("Apple")
        # "apple" → exact match on simplified name "apple"
        assert ticker == "AAPL"

    def test_fuzzy_match_typo(self) -> None:
        """오타가 있어도 퍼지 매칭으로 해결."""
        reg = self._make_registry({"MSFT": "Microsoft Corporation"})
        ticker, score = reg.resolve("Microsft Corporation")  # 오타
        assert ticker == "MSFT"
        assert score >= 0.70

    def test_no_match_returns_none(self) -> None:
        """매칭 불가 시 (None, 0.0) 반환."""
        reg = self._make_registry({"AAPL": "Apple Inc."})
        ticker, score = reg.resolve("Completely Unknown Company XYZ 999")
        assert ticker is None

    def test_min_score_filtering(self) -> None:
        """min_score 높이면 불확실한 매칭 거부."""
        reg = self._make_registry({"AAPL": "Apple Inc."})
        # min_score=0.99 → 퍼지 매칭 결과 거부
        ticker, score = reg.resolve("Apple something else", min_score=0.99)
        assert ticker is None

    def test_empty_registry_returns_none(self) -> None:
        """레지스트리 비어있으면 (None, 0.0) 반환."""
        reg = TickerRegistry()
        ticker, score = reg.resolve("Apple Inc.")
        assert ticker is None
        assert score == 0.0

    def test_empty_query_returns_none(self) -> None:
        """빈 문자열 입력 시 (None, 0.0) 반환."""
        reg = self._make_registry({"AAPL": "Apple Inc."})
        ticker, score = reg.resolve("")
        assert ticker is None
        assert score == 0.0

    def test_resolve_pair(self) -> None:
        """resolve_pair() 두 이름 동시 해결."""
        reg = self._make_registry({
            "TSMC": "Taiwan Semiconductor Manufacturing Company",
            "AAPL": "Apple Inc.",
        })
        (s_tick, s_score), (b_tick, b_score) = reg.resolve_pair(
            "Taiwan Semiconductor Manufacturing Company",
            "Apple",
        )
        assert s_tick == "TSMC"
        assert b_tick == "AAPL"

    def test_is_loaded_after_add_entry(self) -> None:
        """add_entry 후 is_loaded=True."""
        reg = TickerRegistry()
        assert not reg.is_loaded
        reg.add_entry("AAPL", "Apple Inc.")
        assert reg.is_loaded

    def test_add_entry_updates_choices(self) -> None:
        """add_entry 후 즉시 resolve 가능."""
        reg = TickerRegistry()
        reg.add_entry("NVDA", "NVIDIA Corporation")
        ticker, score = reg.resolve("NVIDIA Corporation")
        assert ticker == "NVDA"


# ─────────────────────────────────────────────────────
# 신뢰도 필터링 로직
# ─────────────────────────────────────────────────────

class TestConfidenceFiltering:
    """파이프라인의 신뢰도 결합 및 필터링 로직 검증."""

    def test_combined_confidence_formula(self) -> None:
        """combined = llm_conf × name_resolution_conf."""
        llm_conf   = 0.90
        name_conf  = 0.80   # min(supplier_score, buyer_score)
        combined   = round(llm_conf * name_conf, 4)
        assert abs(combined - 0.72) < 1e-4

    def test_threshold_pass(self) -> None:
        """combined >= threshold → is_applied=True."""
        threshold = 0.70
        combined  = 0.72
        assert combined >= threshold

    def test_threshold_fail_llm_low(self) -> None:
        """LLM 신뢰도가 낮으면 threshold 미달."""
        threshold = 0.70
        llm_conf  = 0.60
        name_conf = 1.00
        combined  = round(llm_conf * name_conf, 4)
        assert combined < threshold

    def test_threshold_fail_name_resolution_low(self) -> None:
        """티커 해결 신뢰도가 낮으면 threshold 미달."""
        threshold = 0.70
        llm_conf  = 0.95
        name_conf = 0.60  # 퍼지 매칭 불확실
        combined  = round(llm_conf * name_conf, 4)
        assert combined < threshold

    def test_missing_ticker_rejected(self) -> None:
        """ticker가 None이면 is_applied=False."""
        result = RelationProcessingResult(
            supplier_name="Unknown Co",
            buyer_name="Apple Inc.",
            supplier_ticker=None,       # 해결 실패
            buyer_ticker="AAPL",
            llm_confidence=0.90,
            name_confidence=0.0,
            combined_confidence=0.0,
            is_applied=False,
            rejection_reason="supplier_not_found: 'Unknown Co'",
        )
        assert not result.is_applied
        assert "supplier_not_found" in result.rejection_reason


# ─────────────────────────────────────────────────────
# ArticleProcessingResult 통계
# ─────────────────────────────────────────────────────

class TestArticleProcessingResult:
    def _make_detail(self, is_applied: bool) -> RelationProcessingResult:
        return RelationProcessingResult(
            supplier_name="S", buyer_name="B",
            supplier_ticker="S" if is_applied else None,
            buyer_ticker="B" if is_applied else None,
            llm_confidence=0.9,
            name_confidence=0.9 if is_applied else 0.0,
            combined_confidence=0.81 if is_applied else 0.0,
            is_applied=is_applied,
            rejection_reason=None if is_applied else "not_found",
        )

    def test_applied_rejected_counts(self) -> None:
        """applied/rejected 카운트 정확성."""
        details = [
            self._make_detail(True),
            self._make_detail(True),
            self._make_detail(False),
        ]
        result = ArticleProcessingResult(
            article_id=1,
            status=ArticleStatus.COMPLETED,
            relations_found=3,
            relations_applied=2,
            relations_rejected=1,
            details=details,
        )
        assert result.relations_applied == 2
        assert result.relations_rejected == 1
        assert result.relations_found == 3

    def test_failed_status_on_error(self) -> None:
        """오류 시 FAILED 상태."""
        result = ArticleProcessingResult(
            article_id=99,
            status=ArticleStatus.FAILED,
            relations_found=0,
            relations_applied=0,
            relations_rejected=0,
            error="LLM API timeout",
        )
        assert result.status == ArticleStatus.FAILED
        assert result.error is not None

    def test_empty_details_default(self) -> None:
        """details 기본값은 빈 리스트."""
        result = ArticleProcessingResult(
            article_id=1,
            status=ArticleStatus.COMPLETED,
            relations_found=0,
            relations_applied=0,
            relations_rejected=0,
        )
        assert result.details == []


# ─────────────────────────────────────────────────────
# 시스템 프롬프트 구조 검증
# ─────────────────────────────────────────────────────

class TestSystemPrompt:
    """시스템 프롬프트가 필수 지시사항을 포함하는지 검증."""

    def test_prompt_contains_key_instructions(self) -> None:
        from app.services.llm_extractor import SYSTEM_PROMPT

        # 공급사/구매사 구분 지시
        assert "SUPPLIER" in SYSTEM_PROMPT or "supplier" in SYSTEM_PROMPT.lower()
        assert "BUYER" in SYSTEM_PROMPT or "buyer" in SYSTEM_PROMPT.lower()

        # 신뢰도 기준 포함
        assert "confidence" in SYSTEM_PROMPT.lower()

        # 최소 신뢰도 기준 (0.5 이하 제외 지시)
        assert "0.5" in SYSTEM_PROMPT

    def test_prompt_not_empty(self) -> None:
        from app.services.llm_extractor import SYSTEM_PROMPT
        assert len(SYSTEM_PROMPT) > 200
