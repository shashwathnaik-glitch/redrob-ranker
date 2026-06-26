# Redrob AI Candidate Ranker — High-Performance Talent Matching & Reproducibility Suite

A high-performance Python-based recruitment screening tool designed to process up to 100,000 candidate profiles in under 5 minutes on a standard CPU. It evaluates candidates dynamically against custom job description specifications (JDs), detects suspicious profiles (such as keyword stuffers and honeypot accounts), and renders findings on a premium recruiter dashboard.

---

## Tech Stack Used

- **Backend**: FastAPI (Python 3.10+)
- **Server**: Uvicorn
- **Frontend**: HTML5, Vanilla CSS (Premium styling, Glassmorphism, animations), JavaScript
- **Test Suite**: Pytest

---

## How to Run the Project

Judges can start and evaluate the project with the following commands:

### 1. Install Dependencies
Ensure you have Python 3.10+ installed. In your terminal, run:
```bash
pip install -r requirements.txt
```

### 2. Start the FastAPI Server
Start the development server with live reload enabled:
```bash
uvicorn app:app --reload
```

### 3. Open the Dashboard & Reproducibility Panel
Once started, open your browser and navigate to:
- **Recruiter Dashboard**: [http://localhost:8000/](http://localhost:8000/)
- **Sandbox Reproducibility Panel**: [http://localhost:8000/sandbox](http://localhost:8000/sandbox)

---

## Available Job Roles

The system dynamically scans `data/job_specs` and supports candidate ranking for four primary job specifications:
1. **AI Engineer** (`ai_engineer`) — Matches retrieval-augmented generation (RAG), embeddings, and search-focused talent.
2. **Backend Engineer** (`backend_engineer`) — Evaluates core systems engineering, microservices (Go, Java, Python), database management, and architecture.
3. **Data Engineer** (`data_engineer`) — Identifies pipeline infrastructure, big data tools (Spark, Airflow), and warehousing expertise (Snowflake, BigQuery).
4. **ML Engineer** (`ml_engineer`) — Evaluates deep learning frameworks (PyTorch, TensorFlow), NumPy/Pandas, and model optimization (Triton, Quantization).

---

## How Role-Based Re-ranking Works

The application employs a dynamic evaluation pipeline:
1. **Startup Pre-warming**: During server start, a background daemon thread automatically discovers all valid roles and computes their candidate rankings in the background, ensuring no initial load delays.
2. **Dynamic Spec Loading**: When the recruiter selects a job role, the backend loads the corresponding JSON job specification defining target skills, experience bands, and scoring weights.
3. **In-Memory Caching**: Evaluations are stored in an in-memory role-based cache (`_rerank_cache`). Switching to any previously computed role resolves instantly (**~60ms**) instead of running the full ~23-second screening pipeline.
4. **Differentiation Scoring**: The feature extractor and scoring engine dynamically align titles, core skills, and weights against the selected spec, producing distinct rankings for each profile.

---

## Key API Endpoints & Example Requests

### 1. Get Discovered Roles
Returns all available job specifications configured on disk.
- **Request**: `GET /api/roles`
- **Example Response**:
  ```json
  [
    {"value": "ai_engineer", "label": "AI Engineer"},
    {"value": "backend_engineer", "label": "Backend Engineer"}
  ]
  ```

### 2. Rerank Candidates
Triggers candidate evaluation against a selected role.
- **Request**: `GET /api/rerank?role=backend_engineer`
- **Example Response**:
  ```json
  {
    "status": "ok",
    "role": "backend_engineer",
    "cached": true,
    "total_candidates": 100000,
    "ranked_count": 100,
    "elapsed_seconds": 0.0
  }
  ```

### 3. Retrieve Ranked Candidates
Reads and returns the active top-100 ranked candidate profiles currently displayed in the dashboard.
- **Request**: `GET /api/candidates`

### 4. Cache Status
Check which roles are currently loaded in memory.
- **Request**: `GET /api/cache/status`

### 5. Clear Cache
Purges the cache for a specific role (or all roles if no parameter is provided).
- **Request**: `DELETE /api/cache/clear?role=ai_engineer`
