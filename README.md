<h1 align="center">Recalce</h1>
<p align="center">
  <b>Automated Bank Reconciliation & ML Anomaly Detection Engine</b><br>
  Replacing manual spreadsheet bookkeeping with distributed task pipelines, deterministic matching, and unsupervised machine learning.
</p>

<p align="center">
  <a href="#the-problem--market-demand">Problem</a> •
  <a href="#the-solution">Solution</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#the-reconciliation-engine">Matching Engine</a> •
  <a href="#machine-learning-pipeline">Machine Learning</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#getting-started">Getting Started</a>
</p>

---

## The Problem & Market Demand

Every business handling payments (e-commerce, marketplaces, SaaS) maintains two records of financial reality: an **Internal Ledger** (what the business recorded) and a **Bank Statement** (what the bank deposited). 

In the real world, these two ledgers **never line up 1:1**.
* **Processing Fees**: A $100 sale settles as $97.10 after gateway fees.
* **Settlement Delays**: Transactions take 1–3 business days or span weekends to clear.
* **Lumped Payouts**: Payment gateways (like Stripe or Square) batch hundreds of orders into a single net deposit.

**The Result**: Small-to-mid-market companies employ accounting teams who spend hundreds of hours manually cross-referencing Excel sheets. Standard SQL equality matches fail. Human error leads to uncollected fees, undetected bank errors, compliance failures, and hidden fraud.

---

## The Solution

**Recalce** is a high-throughput, distributed financial reconciliation platform that automates this process. You upload your internal ledger and bank statement, and the system does the rest.

### Core Capabilities
* **Distributed Task Pipeline**: Asynchronous batch ingestion via FastAPI, Celery, and Redis, decoupling API request handling from compute-heavy algorithmic processing.
* **Financial Precision**: Eliminates floating-point rounding errors by strictly using integer-cent and Python `Decimal` arithmetic.
* **Fault-Tolerant Ingestion**: Validates massive CSVs row-by-row using Pydantic. Corrupted rows are isolated and tracked in audit tables without failing the entire batch workflow.
* **Interactive Dashboard**: A React 19 / Vite frontend featuring live lifecycle polling, amount sorting, server-side search, and CSV exports.

---

## Architecture

Recalce uses a modern, distributed microservices architecture to ensure the API remains ultra-responsive while heavy algorithmic processing happens in the background.

```mermaid
graph LR
    subgraph Client
        UI[React Dashboard]
    end

    subgraph API Gateway
        API[FastAPI]
    end

    subgraph Task Queue
        Broker[(Redis)]
        Worker[Celery Worker]
    end

    subgraph Storage
        DB[(PostgreSQL)]
        B2[(Backblaze B2)]
    end

    subgraph Core Engine
        Recon[5-Pass Reconciliation]
        ML[Dual Isolation Forest]
    end

    UI -->|1. Upload CSVs| API
    API -->|2. Stream files| B2
    API -->|3. Enqueue Tasks| Broker
    API -->|4. HTTP 202 Accepted| UI
    
    Broker -->|5. Consume Tasks| Worker
    Worker -->|6. Fetch CSVs| B2
    
    Worker -->|7a. Run Matcher| Recon
    Worker -->|7b. Score Anomalies| ML
    
    Recon -->|Save Matches| DB
    ML -->|Flag Anomalies| DB
    
    UI -.->|8. Poll Results| API
    API -.->|9. Query Status| DB
```

---

## The Reconciliation Engine

The matching engine is deterministic and operates via a strict, cascading 5-pass waterfall directly against PostgreSQL. Once a transaction is claimed, it is removed from the active pool.

1. **Pass 1 (Exact)**: Matches identical IDs, amounts, and calendar days.
2. **Pass 2 (Date-Shifted)**: Matches identical amounts delayed by 1 to 3 business days (configurable).
3. **Pass 3 (Fee-Adjusted)**: Matches transactions where the bank deposit is reduced by a standard gateway processing fee (e.g., 2.9%).
4. **Pass 4 (Many-to-One / N:1)**: Solves for lumped gateway payouts. Uses RapidFuzz for merchant clustering and a **Branch-and-Bound Subset Sum Algorithm (DFS)** to find internal transactions that exactly sum to a single bank deposit. Ambiguous combinations are safely routed to manual review.
5. **Pass 5 (Unreconciled)**: Flags remaining orphaned rows for investigation.

---

## Machine Learning Pipeline

Deterministic rules catch predictable accounting behavior but miss unpredictable anomalies (e.g., unexpected fee spikes, highly unusual settlement delays, or velocity surges). Recalce implements an unsupervised Machine Learning layer using dual **Isolation Forest** models to flag these edge cases.

* **Matched Model (6D)**: Evaluates features like `fee_ratio` and `settle_delay` on successfully matched transactions to catch suspicious deviations from normal merchant processor behavior.
* **Unmatched Model (5D)**: Evaluates `amount_zscore` to detect if an un-settled transaction is statistically anomalous compared to the merchant's historical distribution.
* **Why Isolation Forest?**: It handles varying density clusters without spherical assumptions, scales beautifully to large datasets ($O(n \log n)$), and requires no ground-truth fraud labels.
* **Evaluation Metrics**: Models are explicitly calibrated on **Precision**, **Recall Floors**, and **PR-AUC** to protect finance teams from alert fatigue while strictly catching true anomalies. Standard accuracy is discarded as a metric due to extreme class imbalance.

---

## Tech Stack

### Backend & Distributed Systems
* **Python 3.10+**
* **FastAPI** (Async API Gateway)
* **Celery** (Distributed Task Queue)
* **Redis** (Message Broker)
* **Uvicorn** (ASGI Server)

### Data & Machine Learning
* **PostgreSQL / Neon** (ACID Relational Database)
* **SQLAlchemy & Alembic** (ORM & Migrations)
* **Scikit-Learn, Pandas, NumPy** (ML Feature extraction & Isolation Forest)
* **Backblaze B2** (S3-Compatible Object Storage)
* **Pydantic v2** (Row-level schema validation)

### Frontend
* **React 19**
* **Vite** (Build Tool)
* **CSS Modules**

---

## Getting Started

### Prerequisites
Ensure you have a `.env` file in the root directory containing your credentials:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/recalce
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
B2_APPLICATION_KEY_ID=your_b2_key_id
B2_APPLICATION_KEY=your_b2_key
B2_BUCKET_NAME=your_b2_bucket
B2_ENDPOINT_URL=your_b2_endpoint
```

### 1. Install Dependencies
Activate your virtual environment and install backend/frontend dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
pip install -r backend/requirements-ml.txt

cd frontend
npm install
```

### 2. Apply Database Migrations
```bash
cd backend
alembic upgrade head
```

### 3. Run the Services (Separate Terminals)
**Terminal 1: FastAPI Server**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Celery Worker**
```bash
cd backend
celery -A app.core.celery_app worker --pool=solo --loglevel=info
```

**Terminal 3: React Frontend**
```bash
cd frontend
npm run dev
```

The dashboard will be available at `http://localhost:5173`. Swagger API docs can be viewed at `http://localhost:8000/docs`.

### 4. Running the Machine Learning Pipeline Locally
To generate synthetic demo datasets and train the Isolation Forest models on your machine:
```bash
cd backend
python scripts/generate_test_csvs.py
python ml/generate_data.py --split train --seed 42 --rows 5000
python ml/train.py
python ml/evaluate.py
```