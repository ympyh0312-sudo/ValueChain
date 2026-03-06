"""
app/services/llm_extractor.py
---------------------------------------------------------
LangChain + OpenAI 기반 공급망 관계 추출기.

핵심 설계:
1. with_structured_output(ExtractionOutput)
   - LLM 출력을 Pydantic 스키마에 강제 맞춤 (함수 호출 기반)
   - 파싱 오류 없이 타입 보장
2. temperature=0
   - 재현성 보장: 같은 기사 재처리 시 일관된 결과
3. confidence_score를 LLM 스스로 추정
   - 근거가 명확할수록 높게 설정하도록 프롬프트에 명시
   - 0.5 미만은 반환 대상에서 제외 (프롬프트 지시)
4. evidence 필드
   - LLM이 추출 근거를 기록 → 감사 추적에 활용

출력 모델 계층:
    ExtractionOutput
      └─ relations: list[ExtractedRelation]
"""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────
# 시스템 프롬프트
# ─────────────────────────────────────────────────────
# 역할 정의 + 출력 스키마 설명 + 신뢰도 기준 명시
# gpt-4o-mini는 명시적 예시가 있을 때 더 정확한 출력을 냄

SYSTEM_PROMPT = """\
You are a financial supply chain analyst. Extract corporate supply chain relationships from news articles.

A supply chain relationship: Company A (SUPPLIER) provides goods, components, materials, or services to Company B (BUYER).

For each relationship found, provide:
- supplier_name: Official company name of the supplier
- buyer_name: Official company name of the buyer
- revenue_share_estimate: Estimated fraction of supplier's total revenue from this relationship (0.0–1.0, null if unknown)
- dependency_estimate: Buyer's dependency on this supplier (0.0=easily replaceable, 1.0=critical, null if unknown)
- event_type: One of "supply_relationship" | "new_contract" | "supply_disruption" | "supply_expansion" | "supply_termination"
- confidence_score: Your confidence this extraction is correct (0.0–1.0)
    • 0.9–1.0: Explicitly stated with clear supplier/buyer identification
    • 0.7–0.9: Strongly implied by article context
    • 0.5–0.7: Inferred, may be incomplete
    • Below 0.5: Do NOT include — skip uncertain extractions
- evidence: Brief direct quote or paraphrase from the article that supports this extraction

Also provide:
- article_summary: 1–2 sentences describing the article's supply chain relevance

Rules:
- Only include relationships with confidence_score >= 0.5
- Use specific, official company names (e.g. "Taiwan Semiconductor Manufacturing Company", not "a chip maker")
- If the article contains NO supply chain relationships, return an empty relations list
"""


# ─────────────────────────────────────────────────────
# 출력 스키마 (Pydantic)
# ─────────────────────────────────────────────────────

class ExtractedRelation(BaseModel):
    """
    단일 공급망 관계 추출 결과.

    revenue_share_estimate / dependency_estimate 는 LLM이 추정한 값.
    명확한 수치가 기사에 없으면 None으로 반환됨.
    """
    supplier_name:           str   = Field(..., description="Official name of the supplying company")
    buyer_name:              str   = Field(..., description="Official name of the buying company")
    revenue_share_estimate:  Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Estimated fraction of supplier's revenue from this relationship"
    )
    dependency_estimate:     Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Buyer's dependency on this supplier (0=low, 1=critical)"
    )
    event_type:              str   = Field(
        default="supply_relationship",
        description="Type of supply chain event"
    )
    confidence_score:        float = Field(
        ..., ge=0.0, le=1.0,
        description="Extraction confidence (0=uncertain, 1=certain)"
    )
    evidence:                str   = Field(
        default="",
        description="Supporting quote or paraphrase from the article"
    )


class ExtractionOutput(BaseModel):
    """LLM 전체 출력 스키마."""
    relations:       list[ExtractedRelation] = Field(
        default_factory=list,
        description="All supply chain relationships found"
    )
    article_summary: str = Field(
        default="",
        description="Brief summary of the article's supply chain relevance"
    )


# ─────────────────────────────────────────────────────
# 추출기
# ─────────────────────────────────────────────────────

class LLMExtractor:
    """
    공급망 관계 LLM 추출기.

    with_structured_output(): OpenAI Function Calling을 사용해
    LLM 출력을 ExtractionOutput Pydantic 모델로 강제 변환.
    파싱 오류 없이 타입 안전성 보장.

    Usage:
        extractor = LLMExtractor()
        output = await extractor.extract("Apple announced new chip orders from TSMC...")
        for rel in output.relations:
            print(rel.supplier_name, "→", rel.buyer_name, rel.confidence_score)
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        # Lazy init: ChatOpenAI 인스턴스는 첫 extract() 호출 시 생성
        # → 임포트 시점에 API 키 검증 없음, 테스트 친화적
        self._chain = None

    def _get_chain(self):
        """with_structured_output 체인 lazy 초기화."""
        if self._chain is None:
            self._chain = ChatOpenAI(
                model=self._settings.llm_model,
                api_key=self._settings.openai_api_key,
                temperature=0,
                max_retries=2,
            ).with_structured_output(ExtractionOutput)
        return self._chain

    async def extract(self, article_text: str) -> ExtractionOutput:
        """
        뉴스 기사에서 공급망 관계를 추출한다.

        Args:
            article_text: 뉴스 원문 (제목 + 본문 권장)

        Returns:
            ExtractionOutput: 추출된 관계 목록 + 기사 요약

        Raises:
            Exception: LLM API 호출 실패 (max_retries 초과)
        """
        if not self._settings.openai_api_key:
            logger.warning("openai_api_key_not_set")
            return ExtractionOutput()

        logger.info("llm_extraction_started", text_length=len(article_text))

        try:
            result: ExtractionOutput = await self._get_chain().ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=article_text),
            ])
        except Exception as e:
            logger.error("llm_extraction_failed", error=str(e))
            raise

        logger.info(
            "llm_extraction_completed",
            relations_found=len(result.relations),
            summary_length=len(result.article_summary),
        )
        return result

    async def extract_batch(self, articles: list[str]) -> list[ExtractionOutput]:
        """
        복수 기사 순차 추출.
        (병렬화는 API rate limit 고려하여 의도적으로 순차 실행)
        """
        results: list[ExtractionOutput] = []
        for i, text in enumerate(articles):
            logger.info("batch_extraction_progress", current=i + 1, total=len(articles))
            try:
                output = await self.extract(text)
                results.append(output)
            except Exception as e:
                logger.error("batch_extraction_item_failed", index=i, error=str(e))
                results.append(ExtractionOutput())   # 실패 시 빈 결과
        return results


# ── 모듈 레벨 싱글턴 ────────────────────────────────────
llm_extractor = LLMExtractor()
