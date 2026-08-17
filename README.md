# Recalce

Recalce is a distributed automated bank reconciliation system. It ingests internal ledgers and bank statements, applies a deterministic matching engine, and utilizes unsupervised machine learning to detect anomalies in processing fees, settlement delays, and transaction velocities.

## Architecture and Capabilities

* **Distributed Task Pipeline**: Asynchronous batch ingestion and processing via FastAPI, Celery, and Redis, decoupling HTTP request handling from compute-heavy tasks.
* **Deterministic Matching Engine**: Rule-based engine resolving Exact, Date-Shifted (1 to 3 days), and Fee-Adjusted matches.
* **Financial Precision**: Maintains balance integrity by using integer-cent and Decimal arithmetic, eliminating floating-point rounding errors.
* **ML Anomaly Triage**: Dual Isolation Forest models evaluate matched and unmatched feature vectors (z-scores, velocity, settlement delays) to flag suspicious transactions.
* **Fault-Tolerant Ingestion**: Pydantic validation isolates row-level formatting corruptions without failing the entire batch workflow.
* **Dashboard**: React 19 and Vite frontend featuring live polling, dynamic skeleton loaders, pagination, amount sorting, server-side search, and CSV exports.

## Tech Stack

* **Backend**: Python, FastAPI, Celery, Redis, SQLAlchemy, Alembic, Pydantic, Uvicorn
* **Machine Learning**: Scikit-Learn, Pandas, NumPy, Joblib
* **Database and Storage**: PostgreSQL, Backblaze B2 Object Storage
* **Frontend**: React 19, Vite, CSS Modules

## Setup and Installation

### Prerequisites

Ensure you have a `.env` file in the root directory containing your service credentials:
* `DATABASE_URL` (PostgreSQL connection string)
* `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (Redis instance)
* Backblaze B2 credentials (`B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`, `B2_ENDPOINT_URL`)

### 1. Install Dependencies

Activate your virtual environment and install backend and frontend dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install -r backend\requirements-ml.txt
pip install -r backend\requirements-dev.txt

cd frontend
npm install
```

### 2. Apply Database Migrations

```powershell
cd backend
..\.venv\Scripts\activate
alembic upgrade head
```

### 3. Run the Services

Use separate terminals to start each component.

**Terminal 1: FastAPI Server**
```powershell
cd backend
..\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
The API will be available at `http://localhost:8000` and Swagger documentation at `http://localhost:8000/docs`.

**Terminal 2: Celery Worker**
```powershell
cd backend
..\.venv\Scripts\activate
celery -A app.core.celery_app worker --pool=solo --loglevel=info
```

**Terminal 3: React Frontend**
```powershell
cd frontend
npm run dev
```
The dashboard will be available at `http://localhost:5173`.

## Running the Machine Learning Pipeline

To generate synthetic demo datasets and train the Isolation Forest models locally:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts/generate_test_csvs.py
..\.venv\Scripts\python.exe ml\generate_data.py --split train --seed 42 --rows 5000
..\.venv\Scripts\python.exe ml\train.py
..\.venv\Scripts\python.exe ml\evaluate.py
```
