# 🛡️ Graph-Insight v2  
### Systemic Risk Propagation & Supply Chain Shock Simulation Engine

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Async-green.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-GraphDB-008CC1.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RDBMS-blue.svg)
![OpenAI](https://img.shields.io/badge/LLM-OpenAI-black.svg)
![LangChain](https://img.shields.io/badge/LangChain-Orchestration-purple.svg)
![React](https://img.shields.io/badge/React-Frontend-61DAFB.svg)
![Next.js](https://img.shields.io/badge/Next.js-Framework-black.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)

---

## 📌 Overview

**Graph-Insight v2**는  
전 세계 기업 간 공급망 네트워크를 그래프 구조로 모델링하고,  
특정 기업의 충격(Shock)이 네트워크 전체로 전파되는 과정을  
수학적으로 시뮬레이션하는 **Systemic Risk Intelligence Engine**입니다.

기존 금융 리스크 분석이 개별 기업 중심이었다면,  
Graph-Insight는 **네트워크 기반 전염(contagion) 모델**을 통해  
시스템 리스크(Systemic Risk)를 정량적으로 계산합니다.

---

# 🧠 Core Concept

공급망은 단순 거래 관계가 아니라 **의존 네트워크(Dependency Graph)** 입니다.

한 기업의 파산 위험은 다음 조건에 의해 증폭됩니다:

- 매출 의존도
- 산업 민감도
- 유동성 방어 능력
- 시간에 따른 감쇠 효과
- 다단계 전이 구조

Graph-Insight는 이를 수학적으로 모델링합니다.

---

# 📐 Mathematical Model

리스크 전파는 다음 수식을 기반으로 계산됩니다:

\[
Risk_{dest}(t) =
Risk_{src}(t-1)
\times Dependency
\times SectorSensitivity
\times (1 - LiquidityBuffer)
\times e^{-\lambda t}
\]

---

## 🔍 Variable Definitions

| Variable | Type | Description |
|----------|------|------------|
| `Risk_src(t-1)` | Node | 이전 시점 원천 기업 리스크 |
| `Dependency` | Edge | 기업 간 매출 의존도 |
| `SectorSensitivity` | Node | 산업별 위기 민감도 가중치 |
| `LiquidityBuffer` | Node | 리스크 흡수 능력 |
| `λ` | Constant | 감쇠 계수 |
| `t` | Time Step | 시간 흐름 |

---

# 🚀 Key Features

---

## 1️⃣ Advanced Risk Propagation Engine

### 🔹 Non-linear Contagion Model

단순 합산이 아닌 곱셈 기반 전염 구조 적용

- 재무 의존도
- 산업 취약도
- 유동성 방어력
- 시간 감쇠

---

### 🔹 Multi-hop Contagion

- 1-Hop (직접 거래)
- 2-Hop (간접 공급)
- 3-Hop (연쇄 전이)

Graph Traversal 기반 BFS/DFS 확산 알고리즘 적용

---

### 🔹 Time-Series Risk Simulation

- Discrete Time Step 기반 계산
- 시뮬레이션 단계별 Risk Heatmap 생성
- Shock Intensity (0~1) 조절 가능

---

## 2️⃣ Interactive Simulation Dashboard

### 🎛 Shock Injection Control
특정 기업에 충격 강도 부여:

```
POST /simulate
{
  "ticker": "TSMC",
  "shock_intensity": 0.7,
  "time_steps": 5
}
```

---

### 🌐 Force-Graph Visualization

- React-Force-Graph 기반
- 노드 크기 = Risk Level
- 노드 색상 = Sector
- Edge 두께 = Dependency Strength

---

### 📊 Vulnerability Ranking

- Top 5 위험 기업 자동 계산
- Sector Risk Concentration Index 도출
- Risk Score 정렬 API 제공

---

## 3️⃣ AI-Powered Data Pipeline

### 🧠 Relation Extraction

LLM 기반 비정형 데이터 분석:

- 뉴스
- 공시
- 리서치 보고서

기업 간 공급 관계 자동 추출

---

### 🔎 Entity Alignment

- 기업명 → 표준 Ticker 매칭
- 중복 제거
- Alias 처리

PostgreSQL Master Table과 매핑

---

# 🏗 System Architecture

```
                ┌────────────────────────┐
                │      External Data      │
                │  News / Filings / API   │
                └─────────────┬──────────┘
                              │
                    ┌─────────▼─────────┐
                    │  LLM Extraction    │
                    │  (LangChain)       │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Entity Resolver  │
                    │   (PostgreSQL)     │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │     Neo4j Graph    │
                    │  Supply Network    │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Risk Engine Core   │
                    │ (FastAPI + Async)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ React Dashboard    │
                    └────────────────────┘
```

---

# 🛠 Tech Stack

## Backend

- Python 3.11+
- FastAPI (Async Engine)
- Neo4j (Graph Database)
- PostgreSQL (Metadata & Master Data)
- LangChain
- OpenAI API

---

## Frontend

- React
- Next.js
- D3.js
- React-Force-Graph
- Zustand
- Tailwind CSS
- Shadcn UI

---

# 📦 Installation

## 1️⃣ Clone Repository

```bash
git clone https://github.com/yourname/graph-insight-v2.git
cd graph-insight-v2
```

---

## 2️⃣ Backend Setup

```bash
pip install -r requirements.txt
```

환경 변수 설정:

```bash
export OPENAI_API_KEY=your_key
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
```

---

## 3️⃣ Run Server

```bash
uvicorn app.main:app --reload
```

---

# 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|------------|
| `/simulate` | POST | Shock 시뮬레이션 실행 |
| `/ranking` | GET | 위험도 상위 기업 조회 |
| `/graph/{ticker}` | GET | 기업 공급망 조회 |
| `/sectors` | GET | 산업 리스크 통계 |

---

# 📊 Example Simulation Output

```json
{
  "time_step": 3,
  "top_risks": [
    {"ticker": "NVDA", "risk": 0.82},
    {"ticker": "AAPL", "risk": 0.74},
    {"ticker": "ASML", "risk": 0.68}
  ]
}
```

---

# 🔬 Future Enhancements

- Monte Carlo Simulation
- Sector Correlation Matrix Integration
- Credit Default Swap Spread Integration
- Real-time Streaming Risk Update (Kafka)
- Reinforcement Learning 기반 Shock Optimization

---

# 🎯 Use Cases

- 금융기관 스트레스 테스트
- 국가 산업 리스크 매핑
- 투자 포트폴리오 전염 위험 분석
- ESG 공급망 리스크 평가
- 거시경제 충격 시나리오 분석

---

# 📜 License

MIT License

---

# 👨‍💻 Author

System Architecture & Risk Modeling  
Graph Intelligence Research Project