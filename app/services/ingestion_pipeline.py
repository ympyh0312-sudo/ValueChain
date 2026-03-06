"""
app/services/ingestion_pipeline.py
---------------------------------------------------------
뉴스 기사 → 공급망 그래프 업데이트 End-to-End 파이프라인.

처리 흐름:
    ingest_article()       → news_articles 저장 (PENDING)
    process_article()      → LLM 추출 + 그래프 업데이트
      ├─ PENDING → PROCESSING
      ├─ LLMExtractor.extract()
      ├─ TickerRegistry.resolve_pair()
      ├─ confidence 필터링
      ├─ ExtractionResult 저장 (PostgreSQL)
      ├─ [confidence >= threshold] RelationshipVersion 저장
      ├─ [confidence >= threshold] upsert_supply_relation() (Neo4j)
      └─ PROCESSING → COMPLETED / FAILED

설계 원칙:
- PostgreSQL 먼저, Neo4j 나중
  : PostgreSQL는 감사 추적 / 복구 기준점
  : Neo4j 실패해도 추출 이력은 보존됨
- 기사 단위 트랜잭션 격리
  : 한 기사가 실패해도 다른 기사 처리 계속
- 결합된 신뢰도
  : combined_conf = llm_conf × name_resolution_conf
  : 티커 매핑 불확실성까지 반영
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.graph_repository import (
    upsert_company,
    upsert_supply_relation,
    get_supply_relation,
)
from app.db.postgres_client import postgres_client
from app.models.db_models import (
    ArticleStatus,
    ExtractionResult,
    NewsArticle,
    RelationEventType,
    RelationshipVersion,
)
from app.models.graph_models import SupplyRelationCreate
from app.services.llm_extractor import ExtractedRelation, llm_extractor
from app.services.ticker_resolver import ticker_registry

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────
# 결과 컨테이너
# ─────────────────────────────────────────────────────

@dataclass
class RelationProcessingResult:
    """단일 추출 관계의 처리 결과."""
    supplier_name:   str
    buyer_name:      str
    supplier_ticker: Optional[str]
    buyer_ticker:    Optional[str]
    llm_confidence:  float
    name_confidence: float          # 티커 리졸버 최솟값
    combined_confidence: float
    is_applied:      bool           # Neo4j에 반영됐는지
    rejection_reason: Optional[str]


@dataclass
class ArticleProcessingResult:
    """단일 기사 처리의 최종 결과."""
    article_id:         int
    status:             ArticleStatus
    relations_found:    int         # LLM이 추출한 관계 수
    relations_applied:  int         # Neo4j에 반영된 관계 수
    relations_rejected: int         # 신뢰도 미달 등으로 거부된 수
    details:            list[RelationProcessingResult] = field(default_factory=list)
    error:              Optional[str] = None


# ─────────────────────────────────────────────────────
# 파이프라인
# ─────────────────────────────────────────────────────

class IngestionPipeline:
    """
    뉴스 기사 수집 및 공급망 그래프 업데이트 파이프라인.

    Usage:
        pipeline = IngestionPipeline()

        # 1. 기사 저장
        article_id = await pipeline.ingest_article(
            title="Apple orders chips from TSMC",
            content="...",
            source_name="Reuters",
        )

        # 2. LLM 처리 및 그래프 업데이트
        result = await pipeline.process_article(article_id)
        print(result.relations_applied, "relationships added to graph")
    """

    def __init__(self) -> None:
        self._settings = settings
        self._threshold = settings.llm_confidence_threshold

    # ── 기사 저장 ──────────────────────────────────────────────────

    async def ingest_article(
        self,
        title:        str,
        content:      str,
        source_url:   Optional[str]      = None,
        source_name:  Optional[str]      = None,
        published_at: Optional[datetime] = None,
        language:     str                = "en",
    ) -> int:
        """
        뉴스 기사를 PostgreSQL에 저장 (status=PENDING).

        Args:
            title:        기사 제목
            content:      기사 본문 (원문 전체 권장)
            source_url:   원문 URL
            source_name:  출처 이름 (예: "Reuters", "Bloomberg")
            published_at: 발행 시각 (None이면 현재 시각)
            language:     언어 코드 (기본 "en")

        Returns:
            저장된 기사 ID
        """
        async with postgres_client.get_session() as session:
            article = NewsArticle(
                title        = title,
                content      = content,
                source_url   = source_url,
                source_name  = source_name,
                published_at = published_at or datetime.now(timezone.utc),
                language     = language,
                status       = ArticleStatus.PENDING,
            )
            session.add(article)
            await session.flush()
            article_id = article.id

        logger.info("article_ingested", article_id=article_id, source=source_name)
        return article_id

    # ── 기사 처리 ──────────────────────────────────────────────────

    async def process_article(
        self,
        article_id: int,
    ) -> ArticleProcessingResult:
        """
        기사 ID를 받아 LLM 추출 → 신뢰도 필터링 → 그래프 업데이트 수행.

        상태 전이: PENDING → PROCESSING → COMPLETED / FAILED

        Args:
            article_id: news_articles.id

        Returns:
            ArticleProcessingResult (처리 통계 + 개별 관계 결과)
        """
        logger.info("article_processing_started", article_id=article_id)

        # ── 기사 로드 + 상태 → PROCESSING ─────────────────────────
        article_text: str
        async with postgres_client.get_session() as session:
            article: Optional[NewsArticle] = await session.get(NewsArticle, article_id)
            if article is None:
                logger.error("article_not_found", article_id=article_id)
                return ArticleProcessingResult(
                    article_id=article_id,
                    status=ArticleStatus.FAILED,
                    relations_found=0,
                    relations_applied=0,
                    relations_rejected=0,
                    error="Article not found",
                )
            article_text = f"{article.title}\n\n{article.content}"
            article.status = ArticleStatus.PROCESSING

        # ── LLM 추출 ─────────────────────────────────────────────
        try:
            extraction_output = await llm_extractor.extract(article_text)
        except Exception as e:
            await self._update_status(article_id, ArticleStatus.FAILED)
            logger.error("article_llm_failed", article_id=article_id, error=str(e))
            return ArticleProcessingResult(
                article_id=article_id,
                status=ArticleStatus.FAILED,
                relations_found=0,
                relations_applied=0,
                relations_rejected=0,
                error=str(e),
            )

        relations = extraction_output.relations
        logger.info(
            "article_llm_extracted",
            article_id=article_id,
            relations=len(relations),
        )

        # ── 관계별 처리 ───────────────────────────────────────────
        applied  = 0
        rejected = 0
        details: list[RelationProcessingResult] = []

        for rel in relations:
            result = await self._process_relation(article_id, rel)
            details.append(result)
            if result.is_applied:
                applied += 1
            else:
                rejected += 1

        # ── 기사 상태 → COMPLETED ─────────────────────────────────
        final_status = (
            ArticleStatus.COMPLETED
            if applied > 0 or rejected > 0
            else ArticleStatus.COMPLETED   # 관계 없어도 처리 완료로 취급
        )
        await self._update_status(article_id, final_status)

        logger.info(
            "article_processing_completed",
            article_id=article_id,
            relations_found=len(relations),
            applied=applied,
            rejected=rejected,
        )

        return ArticleProcessingResult(
            article_id=article_id,
            status=final_status,
            relations_found=len(relations),
            relations_applied=applied,
            relations_rejected=rejected,
            details=details,
        )

    # ── 단일 관계 처리 ──────────────────────────────────────────────

    async def _process_relation(
        self,
        article_id: int,
        rel: ExtractedRelation,
    ) -> RelationProcessingResult:
        """
        추출된 단일 관계를 처리:
        1. 티커 리졸버로 공급사/구매사 매핑
        2. 복합 신뢰도 계산
        3. PostgreSQL ExtractionResult 저장
        4. [신뢰도 >= threshold] Neo4j 그래프 업데이트 + 버전 이력 저장
        """
        # ── 티커 해결 ─────────────────────────────────────────────
        (supplier_ticker, sup_score), (buyer_ticker, buy_score) = (
            ticker_registry.resolve_pair(rel.supplier_name, rel.buyer_name)
        )
        name_confidence = min(sup_score, buy_score)  # 둘 다 잘 매핑돼야 신뢰

        # combined_confidence: LLM 신뢰도 × 티커 해결 신뢰도
        combined = round(rel.confidence_score * name_confidence, 4)

        # ── 거부 판정 ─────────────────────────────────────────────
        rejection_reason: Optional[str] = None

        if supplier_ticker is None:
            rejection_reason = f"supplier_not_found: '{rel.supplier_name}'"
        elif buyer_ticker is None:
            rejection_reason = f"buyer_not_found: '{rel.buyer_name}'"
        elif combined < self._threshold:
            rejection_reason = (
                f"confidence_below_threshold: "
                f"combined={combined:.3f} < threshold={self._threshold}"
            )

        is_applied = rejection_reason is None

        # ── ExtractionResult 저장 (PostgreSQL 감사 추적) ──────────
        await self._save_extraction_result(
            article_id=article_id,
            rel=rel,
            supplier_ticker=supplier_ticker,
            buyer_ticker=buyer_ticker,
            combined_confidence=combined,
            is_applied=is_applied,
            rejection_reason=rejection_reason,
        )

        # ── Neo4j 업데이트 + 버전 이력 ────────────────────────────
        if is_applied and supplier_ticker and buyer_ticker:
            try:
                await self._apply_to_graph(
                    article_id=article_id,
                    rel=rel,
                    supplier_ticker=supplier_ticker,
                    buyer_ticker=buyer_ticker,
                    combined_confidence=combined,
                )
            except Exception as e:
                logger.error(
                    "graph_update_failed",
                    supplier=supplier_ticker,
                    buyer=buyer_ticker,
                    error=str(e),
                )
                is_applied = False
                rejection_reason = f"graph_update_error: {e}"

        return RelationProcessingResult(
            supplier_name=rel.supplier_name,
            buyer_name=rel.buyer_name,
            supplier_ticker=supplier_ticker,
            buyer_ticker=buyer_ticker,
            llm_confidence=rel.confidence_score,
            name_confidence=name_confidence,
            combined_confidence=combined,
            is_applied=is_applied,
            rejection_reason=rejection_reason,
        )

    # ── PostgreSQL 저장 ────────────────────────────────────────────

    async def _save_extraction_result(
        self,
        article_id:         int,
        rel:                ExtractedRelation,
        supplier_ticker:    Optional[str],
        buyer_ticker:       Optional[str],
        combined_confidence: float,
        is_applied:         bool,
        rejection_reason:   Optional[str],
    ) -> None:
        """ExtractionResult 레코드 저장."""
        async with postgres_client.get_session() as session:
            record = ExtractionResult(
                article_id=article_id,
                extracted_data={
                    "supplier":              rel.supplier_name,
                    "buyer":                 rel.buyer_name,
                    "event_type":            rel.event_type,
                    "revenue_share_estimate": rel.revenue_share_estimate,
                    "dependency_estimate":   rel.dependency_estimate,
                    "evidence":              rel.evidence,
                },
                raw_llm_output=rel.evidence,
                confidence_score=combined_confidence,
                is_applied=is_applied,
                supplier_ticker=supplier_ticker,
                buyer_ticker=buyer_ticker,
                llm_model=settings.llm_model,
                rejection_reason=rejection_reason,
            )
            session.add(record)

    # ── Neo4j + 버전 이력 업데이트 ─────────────────────────────────

    async def _apply_to_graph(
        self,
        article_id:         int,
        rel:                ExtractedRelation,
        supplier_ticker:    str,
        buyer_ticker:       str,
        combined_confidence: float,
    ) -> None:
        """
        Neo4j 그래프 업데이트 + RelationshipVersion 저장.

        순서:
        1. 기존 관계 조회 (previous_state 확보)
        2. upsert_supply_relation() → Neo4j
        3. RelationshipVersion 저장 (PostgreSQL)
        """
        # 기존 관계 조회 (버전 이력의 previous_state)
        previous_state = await get_supply_relation(supplier_ticker, buyer_ticker)
        event_type = (
            RelationEventType.UPDATED if previous_state else RelationEventType.CREATED
        )

        # 추출값 기반 파라미터 결정 (None이면 기존 값 또는 기본값 사용)
        revenue_share  = rel.revenue_share_estimate  or (
            previous_state.get("revenue_share", 0.1) if previous_state else 0.1
        )
        dependency     = rel.dependency_estimate or (
            previous_state.get("dependency_score", 0.5) if previous_state else 0.5
        )
        geo_exposure   = (
            previous_state.get("geographic_exposure", 0.5) if previous_state else 0.5
        )
        alt_supplier   = (
            previous_state.get("alternative_supplier_score", 0.3) if previous_state else 0.3
        )

        # Neo4j upsert
        supply_rel = SupplyRelationCreate(
            supplier_ticker=supplier_ticker,
            buyer_ticker=buyer_ticker,
            revenue_share=float(revenue_share),
            dependency_score=float(dependency),
            geographic_exposure=float(geo_exposure),
            alternative_supplier_score=float(alt_supplier),
            confidence_score=combined_confidence,
        )
        await upsert_supply_relation(supply_rel)

        # RelationshipVersion 저장 (감사 추적)
        new_state = {
            "revenue_share":              float(revenue_share),
            "dependency_score":           float(dependency),
            "geographic_exposure":        float(geo_exposure),
            "alternative_supplier_score": float(alt_supplier),
            "confidence_score":           combined_confidence,
        }
        async with postgres_client.get_session() as session:
            version = RelationshipVersion(
                supplier_ticker=supplier_ticker,
                buyer_ticker=buyer_ticker,
                event_type=event_type,
                previous_state=dict(previous_state) if previous_state else None,
                new_state=new_state,
                source_article_id=article_id,
                confidence_score=combined_confidence,
                event_occurred_at=datetime.now(timezone.utc),
            )
            session.add(version)

        logger.info(
            "graph_relation_applied",
            supplier=supplier_ticker,
            buyer=buyer_ticker,
            event=event_type.value,
            confidence=combined_confidence,
        )

    # ── 상태 업데이트 헬퍼 ────────────────────────────────────────

    async def _update_status(
        self,
        article_id: int,
        status: ArticleStatus,
    ) -> None:
        """기사 처리 상태 업데이트."""
        async with postgres_client.get_session() as session:
            article = await session.get(NewsArticle, article_id)
            if article:
                article.status = status


# ── 모듈 레벨 싱글턴 ────────────────────────────────────
ingestion_pipeline = IngestionPipeline()
