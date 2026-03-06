FROM python:3.11-slim

# 시스템 패키지 (psycopg2 빌드용 libpq-dev 포함)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 복사 (레이어 캐싱 최적화 — 코드 변경 시 재설치 방지)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
