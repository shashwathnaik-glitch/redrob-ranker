# Redrob Candidate Ranker: System Blueprint & Source of Truth (BRAIN.md)

This document is the absolute single source of truth for the **Redrob Candidate Ranker** system. It details the architecture, module relationships, business logic formulas, data flow transitions, UI state features, test suite structure, and potential failure modes. It is designed to enable any AI agent or developer to understand, debug, extend, refactor, and deploy the system with zero ambiguity.

---

## 1. Executive Summary & Purpose

The **Redrob Candidate Ranker** is a high-performance profile screening and evaluation system. It is designed to stream, parse, and rank large-scale datasets (up to 100,000 candidate profiles in JSONL format) against specific job description specifications.

### Key Goals & Constraints
* **High Performance**: Stream-process 100,000 candidate records in under 5 minutes on a standard CPU (RAM $\le$ 16 GB, no GPU, no network operations during ranking).
* **Robust Scoring**: Implement a detailed multi-category scoring model (weights summing to 1.0) and severe multiplier-based disqualifiers.
* **Honeypot Resilience**: Detect and zero out suspicious profiles (e.g., keyword stuffers, fake experience, chronological anomalies) to ensure less than 10% honeypots appear in the top 100.
* **Recruiter Visibility**: Present findings through a premium, responsive recruiter dashboard and reproducibility panel.
* **Multi-Role Flexibility**: Enable dynamic loading of job specs from disk to easily switch between target roles (e.g., AI Engineer, Backend Engineer) at runtime.

---

## 2. High-Level Architecture & File Map

The codebase is organized cleanly to separate data, core evaluation pipeline logic, testing infrastructure, and web presentation services.

```text
redrob_ranker/
├── data/
│   ├── raw/                        # Raw inputs
│   │   ├── candidates.jsonl                  # Primary dataset (487MB, 100k entries)
│   │   └── sample_candidates_for_sandbox.jsonl  # Mini test dataset (20 entries)
│   └── processed/                  # Processed specifications
│       ├── jd_intent.json                    # Legacy fallback job spec
│       └── [role_name].json                  # Multi-role job specifications
├── outputs/
│   ├── submission.csv              # Standard CSV ranking output (Top 100)
│   └── ranked_candidates.json      # UI-augmented JSON dataset (Top 100)
├── src/
│   ├── __init__.py
│   ├── config.py                   # Global constants, weights, and vocabularies
│   ├── jd_loader.py                # Job specification discovery and loaders
│   ├── feature_extractor.py        # Stream-ready candidate feature mapper
│   ├── honeypot_detector.py        # Fraud, stuffing, and inactive rules
│   ├── scorer.py                   # Categorical scoring and multiplier logic
│   └── submission_auditor.py       # Metrics auditor to verify top-100 quality
├── tests/
│   ├── __init__.py
│   └── test_suite.py               # Comprehensive unit and integration tests
├── frontend/
│   └── index.html                  # Single-page premium dashboard UI
├── rank.py                         # Offline command-line batch runner script
├── app.py                          # FastAPI backend application server
├── Dockerfile                      # Docker image definition
└── requirements.txt                # Python project dependencies
```

### Module Relationship & Execution Graph
```mermaid
graph TD
    %% CLI Batch Pipeline
    subgraph Offline Batch Pipeline (rank.py)
        candidates_raw[data/raw/candidates.jsonl] -->|Stream Line-by-Line| rank_script[rank.py]
        rank_script -->|Parse JSON| feat_ext[src/feature_extractor.py]
        feat_ext -->|Inspect Credentials| honey_det[src/honeypot_detector.py]
        honey_det -->|Return Flags & Reasons| feat_ext
        feat_ext -->|Flat Features Dictionary| scorer_mod[src/scorer.py]
        scorer_mod -->|Return Score & Reasoning| rank_script
        rank_script -->|Sort Descending & Extract Top 100| sort_candidates[Sort & Trim]
        sort_candidates -->|Write Output| sub_csv[outputs/submission.csv]
        sort_candidates -->|Add Avatars & UI Fields| sub_json[outputs/ranked_candidates.json]
        sub_csv -->|Audit Quality| auditor[src/submission_auditor.py]
    end

    %% Web Sandbox / Dashboard
    subgraph Web App Service (app.py)
        dashboard_ui[frontend/index.html] -->|GET /api/candidates| get_cand_route[GET /api/candidates]
        get_cand_route -->|Read JSON| sub_json
        
        dashboard_ui -->|GET /api/candidates/:id| detail_route[GET /api/candidates/:id]
        detail_route -->|Filter Candidate| sub_json
        
        dashboard_ui -->|GET /api/roles| roles_route[GET /api/roles]
        roles_route -->|Discover Roles| spec_loader[src/jd_loader.py]
        
        dashboard_ui -->|GET /api/rerank?role=role_name| rerank_route[GET /api/rerank]
        rerank_route -->|Trigger Extraction & Scoring| candidates_raw
        rerank_route -->|Update JSON| sub_json

        sandbox_panel[app.py: /sandbox] -->|POST /api/rank-sample?role=role_name| upload_route[POST /api/rank-sample]
        upload_route -->|Stream Uploaded JSONL| feat_ext
        upload_route -->|Score & Sort| scorer_mod
        upload_route -->|Generate Download| ranked_csv[ranked_sample.csv]
    end
    
    style rank_script fill:#1e293b,stroke:#a78bfa,stroke-width:2px,color:#fff
    style app.py fill:#0F172A,stroke:#3b82f6,stroke-width:2px,color:#fff
```

---

## 3. Data & State Flow

The system processes data in three operational modes:

### 1. Offline Batch Mode (`rank.py`)
1. Reads candidate files line-by-line using standard Python file streaming (avoiding memory bloat).
2. Converts raw JSON text to candidate dictionaries.
3. Extracted features are scored, then candidates are sorted.
4. **Output Generation**:
   * **`outputs/submission.csv`**: Contains exactly `candidate_id`, `score`, and `reasoning`.
   * **`outputs/ranked_candidates.json`**: Augments candidates with `rank`, `image` (Dicebear Avatars), `risk` flags, and `riskDetail` text.
5. Invokes `submission_auditor.py` to evaluate compliance metrics.

### 2. Multi-Role Spec Discovery (`src/jd_loader.py`)
1. Scans `data/processed/` for any `.json` files.
2. Formats the stem (lowercase, trimmed) to build the role mapping database.
3. `ai_engineer` maps to `ai_engineer.json` (or falls back to legacy `jd_intent.json` if missing).
4. Any unrecognized role string triggers a `ValueError` containing a list of all discovered roles.

### 3. State Persistence in Dashboard UI (`frontend/index.html`)
The frontend dashboard is stateful and tracks candidate progression. 
* **Recruitment Status Strip**: Renders 5 stages: `Uncontacted`, `Shortlisted`, `Interview`, `Offer`, `Rejected`.
* **Synchronization**: On clicking a stage, the client updates the candidate status locally. This is persisted in browser `localStorage` under `candidate_status_{candidate_id}`.
* **Badges**: Updated statuses automatically reflect as colored tags on the candidate list card.

---

## 4. Deep Dive: Scorer & Business Logic Formulas

Candidate evaluation consists of a **weighted sum base score** multiplied by **disqualifier multipliers**.

$$\text{Final Score} = \text{Clip}\left(\left[\sum (\text{Score}_i \times \text{Weight}_i)\right] \times \prod \text{Disqualifier Multipliers},\ 0.0,\ 1.0\right)$$

### 1. Base Score Components (Weights Sum to 1.0)

| Category | Weight | Score Logic | Key Configurations |
| :--- | :---: | :--- | :--- |
| **Title** | 0.20 | `primary` (matches AI/ML titles) = 1.0;<br>`adjacent` (Software/Data Eng) = 0.55;<br>`unrelated` = 0.0 | `TITLE_AI_ML`<br>`TITLE_ADJACENT`<br>`TITLE_UNRELATED` |
| **Skill** | 0.22 | Base: `min(core_count / 6.0, 1.0) + min(pref_count / 8.0, 0.2)`. <br>If has assessments: multiplied by `(1.0 + avg_assessment / 200.0)`. <br>Multiplied by clipped endorsement trust: `clip(0.7 + trust * 0.4, 0.7, 1.1)` | `CORE_NLP_IR_SKILLS`<br>`PREFERRED_SKILLS`<br>`skill_trust_score` |
| **Career** | 0.18 | Product company background & no consulting history = 1.0;<br>Consulting history only = 0.0;<br>Mixed career = 0.6 | `CONSULTING_FIRMS` |
| **Experience** | 0.12 | Ideal range (5-9 yrs) = 1.0;<br>Good range (4-10 yrs) = 0.8;<br>Acceptable range (3-12 yrs) = 0.5;<br>Out of range = 0.2 | `EXP_IDEAL_MIN/MAX`<br>`EXP_GOOD_MIN/MAX`<br>`EXP_ACCEPTABLE_MIN/MAX` |
| **Behavioral** | 0.10 | Sum of signals:<br>- Open to work: `0.15` if True<br>- Active days: `<30d`: `0.35`, `<90d`: `0.245`, `<180d`: `0.14`, else `0.035`<br>- Response rate: `0.20 * rate`<br>- Interview rate: `0.15 * rate`<br>- Offer acceptance: `0.10 * rate` (default 0.5 if -1.0)<br>- GitHub score: `0.05 * (score / 100)` (default 0.0 if -1.0)<br>- Saved by recruiters: `0.15 * (min(count, 20) / 20)` | `ACTIVE_DAYS_GREAT`<br>`ACTIVE_DAYS_GOOD`<br>`ACTIVE_DAYS_WEAK`<br>`RESPONSE_RATE_MIN` |
| **Location** | 0.08 | Preferred cities (Pune/Noida) = 1.0;<br>Tier 1 India cities = 0.85;<br>India based = 0.6;<br>Willing to relocate = 0.35;<br>Else = 0.1 | `PREFERRED_CITIES`<br>`TIER1_INDIA_CITIES`<br>`VISA_SPONSORSHIP_AVAILABLE` |
| **Notice** | 0.06 | notice period $\le 30$ days = 1.0;<br>$\le 60$ days = 0.7;<br>$\le 90$ days = 0.4;<br>Else = 0.2 | `NOTICE_IDEAL`<br>`NOTICE_OK`<br>`NOTICE_WEAK` |
| **Trust** | 0.04 | Average of:<br>- Phone + Email verified = 1.0, else 0.0<br>- LinkedIn connected = 1.0, else 0.0<br>- Profile completeness = score / 100.0 | `profile_completeness` |

### 2. Disqualifier Multipliers (Post-Weighted Score)

Disqualifiers are applied multiplicatively. High risk triggers cause dramatic score reductions:
1. **`is_honeypot`**: **$\times 0.0$** (Instant DQ)
2. **`pure_research_only_flag`**: **$\times 0.05$** (Career spent purely in academic/research settings reduces rank to zero chance of top 100)
3. **`title_chaser_flag`**: **$\times 0.7$** (Frequent job jumps, average tenure $<18$ months with $\ge 3$ jobs and $>4$ years experience)
4. **`no_recent_production_code_flag`**: **$\times 0.6$** (Senior leaders / Tech leads with continuous tenure $>18$ months in a current management role without coding evidence)
5. **`has_cv_speech_without_nlp`**: **$\times 0.5$** (Candidates with Computer Vision/Speech skills but zero NLP/Information Retrieval skills)

---

## 5. Fraud & Anomalous Profile Detection (Honeypots)

Honeypots are deceptive candidate submissions. A candidate is flagged as a honeypot (`is_honeypot = True`) if **any** of the following rules are met:

### Rule 1: Expert Zero-Duration Skills
* **Condition**: Candidate has $\ge 3$ skill entries where `proficiency == "expert"` but `duration_months == 0`.
* **Purpose**: Identifies profile stuffing where developers claim high expertise without actual tenure.

### Rule 2: Chronological Career Excess
* **Condition**: The sum of all career history `duration_months` exceeds the claimed `years_of_experience * 12` by more than 36 months.
* **Purpose**: Blocks candidates who artificially pad historical employment records beyond their overall years of experience.

### Rule 3: Single Skill Duration Limit
* **Condition**: Any individual skill's `duration_months` is strictly greater than the overall `years_of_experience * 12`.
* **Purpose**: Detects logical contradictions where a candidate claims to have worked in a single sub-skill longer than their entire professional career.

### Rule 4: Out-of-Bounds Certifications
* **Condition**: Any certification `year` is older than `2026 - years_of_experience - 5`.
* **Purpose**: Catches profile forgery where old certificates predate the start of the candidate's career.

### Keyword Stuffers
Determined by `is_keyword_stuffer(candidate)` to evaluate search engine optimization (SEO) manipulation:
* **Score = 0.9**: Has $\ge 5$ skills matching `CORE_NLP_IR_SKILLS`, an unrelated current title, and `evidence == 0` (zero core skills mentioned in career history description strings).
* **Score = 0.6**: Has $\ge 3$ core skills and `evidence == 0` (zero matching terms in career history descriptions).
* **Score = 0.0**: Compliant profile.

---

## 6. Web Sandbox & Recruiter Dashboard Features

The web component features two main interfaces hosted on FastAPI:

### 1. Recruiter Dashboard (`/`)
* **Background Layering**: Styled sidebar (`#0F172A`), list cards (`#131929`), and page canvas (`#090d16`) for optimal dark-theme reading.
* **Hover Micro-Animations**: Candidate cards slide up (`translateY(-4px)`) and view buttons slide their right arrows horizontally on mouse over.
* **SVG Radial Progress Rings**: Animates details score ring inside the side drawer. Dynamically changes color based on match level (Green: $\ge 90\%$, Amber: $75\% - 89\%$, Red: $<75\%$).
* **Details Drawer Interaction**: Fully accessible backdrop-blur overlay that closes on background click or `Escape` key.
* **Interactive Skill Badges**: Structured by tiers (Core: Purple solid, Preferred: Blue outline, Adjacent: Gray outline with caution icons). **Vertical Flip**: Badges rotate $180^\circ$ on hover to reveal exact experience duration in months.
* **Debounced Opacity Filtering**: Range sliders use a 150ms debounce. Filters dim non-matching candidate cards (`opacity-30`) instead of deleting elements, eliminating layout jumps. Includes custom empty states.
* **Accessible Focus Trap**: Restricts tab navigation focus inside the active side drawer for screen-readers and keyboard-only recruiters.

### 2. Sandbox Reproducibility Panel (`/sandbox`)
* **Pipeline Auditing**: Allows uploading a raw JSONL file to execute feature extraction, honeypot checks, and scoring on the server.
* **Direct Export**: Outputs the generated ranked list inline as a table and provides a button to download the resulting CSV output.

---

## 7. Potential Breakpoints & Operational Risks

Developers modifying this codebase must be aware of these design choices and constraints:

### 1. Hardcoded Reference Date (`TODAY = "2026-06-20"`)
* **Risk**: All active-date math (`days_since_active`, certification age, ghost candidate flags) is evaluated relative to the static date `"2026-06-20"`. 
* **Impact**: If this date is changed to the actual system date without updating historical test records, all time delta calculations will shift, breaking unit tests and filtering out active candidates.

### 2. Multi-Role Limitations
* **Risk**: Although `jd_loader.py` dynamically discovers role specifications, the core feature extractor (`feature_extractor.py`) and scoring engine (`scorer.py`) rely on hardcoded keyword lists imported directly from `config.py` (e.g. `CORE_NLP_IR_SKILLS`).
* **Impact**: Attempting to rank `backend_engineer` via `/api/rerank` or `/api/rank-sample` validates the role name successfully, but the underlying scoring still evaluates them against the NLP/IR skill definitions. To fully support multiple roles, scorer weights and skill lists must be decoupled from `config.py` and loaded dynamically from the role specifications.

### 3. Dicebear Avatar Dependency
* **Risk**: Avatar icons are fetched from a remote server (`https://api.dicebear.com/`).
* **Impact**: If the network is restricted (or Dicebear's API experiences downtime), avatar graphics will fail to render, causing broken images in the dashboard.

### 4. Memory Allocations
* **Risk**: High-performance batch sorting reads all parsed records into memory before sorting.
* **Impact**: While a 100k array fits comfortably under the 16 GB RAM budget, attempting to scale this to 10M records without using an external database or chunked external merge sort will lead to Out-Of-Memory (OOM) failures.

---

## 8. Verification & Test Suite

The test suite in [test_suite.py](file:///c:/Users/Shashwath%20S%20Naik/Documents/h2shackthon/redrob_ranker/tests/test_suite.py) implements extensive validation for data parsing, API endpoints, and business logic.

```powershell
# Run the test suite
& "C:\Users\Shashwath S Naik\AppData\Local\Python\bin\python.exe" -m pytest
```

### Test Coverage Detail
1. **`test_extract_features_real`**: Evaluates correct translation of profile fields, duration metrics, experience calculations, and city mapping.
2. **`test_is_honeypot_rules`**: Validates each of the four honeypot detection triggers (expert zero duration, career excess, single skill duration limit, certificate age limit).
3. **`test_is_keyword_stuffer`**: Evaluates suspicion scoring (0.9, 0.6, 0.0) based on title mismatch and career history descriptions.
4. **`test_is_consulting_only`**: Checks consulting firm detection logic.
5. **`test_is_ghost_candidate`**: Ensures candidates are accurately flagged as inactive after 90 days of inactivity with low response rates.
6. **`test_score_candidate_flow`**: Validates the overall scoring pipeline, weighted sum math, and immediate honeypot zero-score disqualification.
7. **`test_submission_auditor_flow`**: Audits target outputs and generates console metrics without failing.
8. **`test_jd_loader_dynamic`**: Tests multi-role parsing, missing folder fallbacks, non-existent role ValueErrors, and legacy interface support.
9. **`test_api_rank_sample_validation`**: Asserts endpoint status codes (200 OK / 400 Bad Request) and validates JSON outputs using `TestClient`.
