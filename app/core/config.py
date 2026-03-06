"""
app/core/config.py
---------------------------------------------------------
환경 변수 기반 전역 설정 관리.

설계 원칙:
- pydantic-settings BaseSettings: .env 파일을 자동 파싱 + 타입 검증
- @lru_cache: 앱 전체에서 싱글턴처럼 동작 (매번 파일 재읽기 방지)
- 각 섹션별로 설정을 묶어 가독성 및 확장성 확보
"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """전역 설정 클래스. .env 파일에서 자동으로 값을 로드한다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,         # NEO4J_URI와 neo4j_uri 동일하게 처리
        extra="ignore",               # .env에 정의되지 않은 변수는 무시
    )

    # App
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=True)
    app_log_level: str = Field(default="INFO")

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password123")
    neo4j_max_connection_pool_size: int = Field(default=50)
    neo4j_connection_timeout: int = Field(default=30)   # seconds

    # PostgreSQL
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="riskuser")
    postgres_password: str = Field(default="riskpass")
    postgres_db: str = Field(default="riskdb")
    postgres_pool_size: int = Field(default=10)
    postgres_max_overflow: int = Field(default=20)

    # LLM (OpenAI)
    openai_api_key: str = Field(default="")
    llm_model: str = Field(default="gpt-4o-mini")   # 테스트: gpt-4o-mini / 운영: gpt-4o
    llm_confidence_threshold: float = Field(default=0.7)

    # DART (금융감독원 전자공시시스템)
    # 발급: https://opendart.fss.or.kr → 인증키 신청
    dart_api_key: str = Field(default="")

    # Risk Engine
    # lambda: 시간 감쇠 계수. 클수록 리스크가 빠르게 소멸
    default_decay_lambda: float = Field(default=0.1)
    # Shock Intensity: 최초 충격 강도 (0~1)
    default_shock_intensity: float = Field(default=1.0)
    # 전파 최대 홉 수
    default_max_hop: int = Field(default=5)
    # 분석 기간 (일)
    default_time_horizon: int = Field(default=30)
    # 이 값 미만 리스크는 전파 중단 (계산 효율화)
    risk_cutoff_threshold: float = Field(default=0.01)

    @property
    def postgres_dsn(self) -> str:
        """asyncpg용 DSN 문자열 조합"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    싱글턴 패턴으로 Settings 인스턴스 반환.
    FastAPI의 Depends()와 함께 사용하거나 직접 호출 가능.

    Usage:
        settings = get_settings()
        print(settings.neo4j_uri)
    """
    return Settings()
