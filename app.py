from fastapi import FastAPI, UploadFile, File, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import json
import os
import io
import csv
import time
import threading

# Import ranking pipeline functions
from src.feature_extractor import extract_features_for_candidate
from src.scorer import score_candidate
from src.jd_loader import load_job_spec, get_available_roles
from src.config import CANDIDATES_FILE, RANKED_JSON_FILE, SUBMISSION_FILE, TOP_K

app = FastAPI(
    title="Redrob AI Candidate Ranker Sandbox",
    description="API Sandbox for evaluating candidate profiles and viewing ranking results.",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-Memory Role-Based Ranking Cache
# ---------------------------------------------------------------------------
# Structure: { role_key: { "candidates": [...], "total": int, "elapsed_seconds": float } }
# Cache persists for the lifetime of the server process. Call /api/cache/clear to reset.
_rerank_cache: dict = {}

# ----------------- PURPOSE 1: Dashboard Data API -----------------

@app.get("/api/candidates")
def get_candidates():
    """Reads outputs/ranked_candidates.json and returns it as JSON."""
    ranked_candidates_path = "outputs/ranked_candidates.json"
    if not os.path.exists(ranked_candidates_path):
        return []
    with open(ranked_candidates_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/candidates/export")
def export_candidates():
    """Download the final full submission.csv file."""
    csv_path = "outputs/submission.csv"
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="Submission CSV not found")
    return FileResponse(csv_path, media_type="text/csv", filename="submission.csv")

@app.get("/api/candidates/{candidate_id}")
def get_candidate_detail(candidate_id: str):
    """Returns one candidate's full detail from the ranked list."""
    ranked_candidates_path = "outputs/ranked_candidates.json"
    if not os.path.exists(ranked_candidates_path):
        raise HTTPException(status_code=404, detail="Ranked candidates data not found.")
        
    with open(ranked_candidates_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)
        
    # Search for candidate_id case-insensitively
    for c in candidates:
        if str(c.get("candidate_id")).strip().lower() == candidate_id.strip().lower():
            return c
            
    raise HTTPException(status_code=404, detail=f"Candidate with ID {candidate_id} not found.")

@app.get("/api/roles")
def list_roles():
    """Returns available job roles discovered from the job spec directory."""
    roles = get_available_roles()
    # Build a list with display labels
    label_map = {
        "ai_engineer": "AI Engineer",
        "backend_engineer": "Backend Engineer",
        "data_engineer": "Data Engineer",
        "ml_engineer": "ML Engineer",
    }
    result = []
    for role_key in roles.keys():
        result.append({
            "value": role_key,
            "label": label_map.get(role_key, role_key.replace("_", " ").title())
        })
    return result


@app.get("/api/rerank")
def rerank_candidates(role: str = "ai_engineer"):
    """
    Re-runs the ranking pipeline on the existing candidates file using the
    specified job role, then overwrites ranked_candidates.json so the dashboard
    can refresh its view without a server restart.

    Results are cached in memory per role after the first computation so that
    subsequent requests for the same role return instantly (~0s vs ~100s).
    """
    # Validate role
    try:
        job_spec = load_job_spec(role)
    except ValueError as e:
        available_roles = list(get_available_roles().keys())
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid job role specified",
                "requested_role": role,
                "available_roles": available_roles,
                "message": str(e)
            }
        )

    if not os.path.exists(CANDIDATES_FILE):
        raise HTTPException(
            status_code=404,
            detail=f"Candidates data file not found at {CANDIDATES_FILE}"
        )

    # --- Cache hit: serve from memory, skip the full pipeline ---
    role_key = role.lower().strip()
    if role_key in _rerank_cache:
        cached = _rerank_cache[role_key]
        top_k = cached["candidates"]
        print(f"[Cache HIT] Serving cached ranking for role='{role_key}' ({len(top_k)} candidates)")

        # Refresh ranked_candidates.json so /api/candidates stays in sync
        os.makedirs(os.path.dirname(RANKED_JSON_FILE), exist_ok=True)
        with open(RANKED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(top_k, f, indent=2)

        return {
            "status": "ok",
            "role": role_key,
            "cached": True,
            "total_candidates": cached["total"],
            "ranked_count": len(top_k),
            "elapsed_seconds": 0.0,
        }

    # --- Cache miss: run the full ranking pipeline ---
    print(f"[Cache MISS] Running full ranking pipeline for role='{role_key}'...")
    start_time = time.time()
    candidates = []

    with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                cand_raw = json.loads(line)
                feats = extract_features_for_candidate(cand_raw, job_spec)
                score_res = score_candidate(feats, job_spec)

                profile = cand_raw.get("profile") or {}
                redrob_signals = cand_raw.get("redrob_signals") or {}

                candidates.append({
                    "candidate_id": feats["candidate_id"],
                    "name": profile.get("anonymized_name", "Anonymous"),
                    "role": profile.get("current_title", "Software Engineer"),
                    "company": profile.get("current_company", "N/A"),
                    "location": profile.get("location", "India"),
                    "country": profile.get("country", "India"),
                    "score": score_res["score"],
                    "reasoning": score_res["reasoning"],
                    "skills": [s.get("name") for s in cand_raw.get("skills", []) if s.get("name")],
                    "raw_skills": cand_raw.get("skills", []),
                    "experience": profile.get("years_of_experience", 0),
                    "notice_period_days": redrob_signals.get("notice_period_days", 30),
                    "last_active_date": redrob_signals.get("last_active_date", "2026-06-20"),
                    "career_history": cand_raw.get("career_history", []),
                    "redrob_signals": redrob_signals,
                    "features": feats,
                })
            except Exception as e:
                print(f"Rerank warning: Failed to process candidate: {e}")
                continue

    # Sort descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Add rank, risk, and avatar
    for idx, c in enumerate(candidates):
        c["rank"] = idx + 1
        feats = c["features"]
        is_hp = feats.get("is_honeypot", False)
        hp_reasons = feats.get("honeypot_reasons", [])

        if is_hp:
            c["risk"] = "Honeypot Flagged"
            c["riskDetail"] = f"Anomalous profile detected: {', '.join(hp_reasons)}"
        elif feats.get("pure_research_only_flag", False):
            c["risk"] = "Pure Research Flagged"
            c["riskDetail"] = "Candidate background is primarily academic/pure research."
        elif feats.get("is_ghost_candidate", False):
            c["risk"] = "Inactive Flagged"
            c["riskDetail"] = "Candidate response rate is low and has been inactive."
        else:
            c["risk"] = "Clean"
            c["riskDetail"] = "Verified technical profile with standard signals."

        c["image"] = f"https://api.dicebear.com/7.x/adventurer/svg?seed={c['candidate_id']}"

    top_k = candidates[:TOP_K]
    elapsed = round(time.time() - start_time, 2)

    # --- Store result in cache ---
    _rerank_cache[role_key] = {
        "candidates": top_k,
        "total": len(candidates),
        "elapsed_seconds": elapsed,
    }
    print(f"[Cache STORE] Cached {len(top_k)} candidates for role='{role_key}' (took {elapsed}s)")

    # Write to ranked_candidates.json
    os.makedirs(os.path.dirname(RANKED_JSON_FILE), exist_ok=True)
    with open(RANKED_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(top_k, f, indent=2)

    return {
        "status": "ok",
        "role": role_key,
        "cached": False,
        "total_candidates": len(candidates),
        "ranked_count": len(top_k),
        "elapsed_seconds": elapsed,
    }


@app.delete("/api/cache/clear")
def clear_cache(role: str = None):
    """
    Clears the in-memory ranking cache.
    - If `role` query param is provided, clears only that role's cache.
    - If omitted, clears all cached roles.
    """
    if role:
        role_key = role.lower().strip()
        removed = _rerank_cache.pop(role_key, None)
        if removed is None:
            return {"status": "ok", "message": f"No cache entry found for role '{role_key}'"}
        return {"status": "ok", "message": f"Cache cleared for role '{role_key}'"}
    else:
        cleared = list(_rerank_cache.keys())
        _rerank_cache.clear()
        return {"status": "ok", "message": f"All cache cleared", "cleared_roles": cleared}


@app.get("/api/cache/status")
def cache_status():
    """
    Returns the current state of the in-memory ranking cache:
    which roles are cached and how many candidates each holds.
    """
    return {
        "cached_roles": [
            {
                "role": r,
                "ranked_count": len(v["candidates"]),
                "total_candidates": v["total"],
                "original_elapsed_seconds": v["elapsed_seconds"],
            }
            for r, v in _rerank_cache.items()
        ],
        "total_cached_roles": len(_rerank_cache),
    }


# ----------------- PURPOSE 2: Sandbox Reproducibility Endpoint -----------------

@app.post("/api/rank-sample")
async def rank_sample(role: str = "ai_engineer", file: UploadFile = File(...)):
    """
    Accepts an uploaded .jsonl file, runs the feature extraction and scorer,
    sorts candidates by score descending, and returns a ranked CSV.
    """
    try:
        job_spec = load_job_spec(role)
    except ValueError as e:
        available_roles = list(get_available_roles().keys())
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid job role specified",
                "requested_role": role,
                "available_roles": available_roles,
                "message": str(e)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error loading job specification: {str(e)}"
        )

    if not file.filename.endswith('.jsonl'):
        raise HTTPException(status_code=400, detail="Only .jsonl files are allowed.")
        
    contents = await file.read()
    lines = contents.decode("utf-8").splitlines()
    
    candidates = []
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            cand_raw = json.loads(line)
            feats = extract_features_for_candidate(cand_raw, job_spec)
            score_res = score_candidate(feats, job_spec)
            candidates.append({
                "candidate_id": feats["candidate_id"],
                "score": score_res["score"],
                "reasoning": score_res["reasoning"]
            })
        except Exception as e:
            # Skip invalid lines with a warning print, maintaining endpoint robustness
            print(f"Sandbox warning: Failed to parse line {line_num}: {e}")
            continue
            
    # Sort descending by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    # Generate CSV response
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["candidate_id", "rank", "score", "reasoning"])
    for idx, c in enumerate(candidates):
        writer.writerow([c["candidate_id"], idx + 1, f"{c['score']:.4f}", c["reasoning"]])
        
    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ranked_sample.csv"}
    )

@app.get("/data/raw/sample_candidates_for_sandbox.jsonl")
def download_sandbox_sample():
    """Allows downloading the pre-generated sandbox sample file."""
    sample_path = "data/raw/sample_candidates_for_sandbox.jsonl"
    if not os.path.exists(sample_path):
        raise HTTPException(status_code=404, detail="Sample candidates file not found.")
    return FileResponse(sample_path, media_type="text/plain", filename="sample_candidates_for_sandbox.jsonl")

@app.get("/sandbox", response_class=HTMLResponse)
def get_sandbox():
    """Serves the plain HTML sandbox verification interface."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Redrob Sandbox Reproducibility Panel</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Outfit:wght@600;700;800;900&display=swap" rel="stylesheet"/>
        <style>
            body {
                font-family: 'Plus Jakarta Sans', sans-serif;
                background-color: #090d16;
                color: #f1f5f9;
            }
            h1, h2, h3 {
                font-family: 'Outfit', sans-serif;
            }
        </style>
    </head>
    <body class="p-6 md:p-12 min-h-screen flex flex-col justify-between">
        <div class="max-w-4xl mx-auto w-full bg-slate-900 border border-slate-800 p-8 rounded-3xl shadow-xl">
            <header class="mb-8 flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-purple-500/30">
                    <span class="text-white text-xl font-bold">🛠️</span>
                </div>
                <div>
                    <h1 class="text-2xl font-black text-white">Redrob AI Sandbox</h1>
                    <p class="text-xs text-slate-400">Section 10.5 Reproducibility & Pipeline Verification</p>
                </div>
            </header>
            
            <div class="space-y-6">
                <p class="text-sm text-slate-300">
                    Upload a sample JSONL file (schema-compliant, up to 100 candidates) to execute the candidate ranking pipeline end-to-end on our server. The sandbox will run feature extraction, honeypot filters, and match scoring, returning the sorted ranking result.
                </p>
                
                <!-- File Upload Form -->
                <form id="upload-form" class="border-2 border-dashed border-slate-800 hover:border-purple-500/50 rounded-2xl p-8 flex flex-col items-center justify-center gap-4 bg-slate-950/40 transition-all cursor-pointer">
                    <input type="file" id="file-input" name="file" accept=".jsonl" class="hidden">
                    <div class="text-center space-y-2" onclick="document.getElementById('file-input').click()">
                        <p class="text-lg font-bold text-white">Select JSONL File</p>
                        <p class="text-xs text-slate-400">Click to browse or drag and drop</p>
                        <p id="file-name" class="text-xs text-purple-400 font-bold mt-2"></p>
                    </div>
                    <button type="submit" class="mt-4 bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold px-6 py-3 rounded-xl transition-all shadow-lg shadow-purple-600/20 active:scale-95">
                        Execute Ranking
                    </button>
                </form>
                
                <!-- Demo Sample Link -->
                <div class="bg-slate-950/20 p-4 rounded-xl border border-slate-800 text-xs flex justify-between items-center">
                    <span class="text-slate-400 font-medium">Need a sample file? Use our pre-generated 20-profile sandbox dataset:</span>
                    <a href="/data/raw/sample_candidates_for_sandbox.jsonl" download class="text-purple-400 hover:text-purple-300 font-bold flex items-center gap-1">
                        Download Sample
                    </a>
                </div>
                
                <!-- Loading State -->
                <div id="loading" class="hidden flex flex-col justify-center items-center py-10 gap-3">
                    <div class="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                    <p class="text-xs text-slate-400 font-semibold">Running intelligence pipeline...</p>
                </div>
                
                <!-- Error Alert -->
                <div id="error" class="hidden p-4 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs flex items-center gap-2">
                    <span class="font-bold">Error:</span>
                    <span id="error-msg"></span>
                </div>
                
                <!-- Results Inline Section -->
                <div id="results-section" class="hidden space-y-4">
                    <div class="flex justify-between items-center">
                       <h2 class="text-lg font-extrabold text-white">Pipeline Execution Results</h2>
                       <button id="download-results-btn" class="bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold px-4 py-2 rounded-lg border border-slate-700 flex items-center gap-1 transition-all">
                           Download CSV
                       </button>
                    </div>
                    
                    <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="border-b border-slate-800 bg-slate-900 text-xs font-bold text-slate-300">
                                    <th class="p-4">Rank</th>
                                    <th class="p-4">Candidate ID</th>
                                    <th class="p-4">Match Score</th>
                                    <th class="p-4">Reasoning</th>
                                </tr>
                            </thead>
                            <tbody id="results-table-body" class="text-xs text-slate-300 divide-y divide-slate-800/50">
                                <!-- Appended dynamically -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <footer class="mt-8 text-center text-slate-500 text-xs">
            <p>&copy; 2026 Redrob AI | Anti-Gravity Coding Assistant</p>
        </footer>

        <script>
            const fileInput = document.getElementById("file-input");
            const fileName = document.getElementById("file-name");
            const form = document.getElementById("upload-form");
            const loading = document.getElementById("loading");
            const error = document.getElementById("error");
            const errorMsg = document.getElementById("error-msg");
            const resultsSection = document.getElementById("results-section");
            const tableBody = document.getElementById("results-table-body");
            const downloadBtn = document.getElementById("download-results-btn");
            
            let latestCsvData = "";

            fileInput.addEventListener("change", (e) => {
                if (e.target.files.length > 0) {
                    fileName.textContent = e.target.files[0].name;
                }
            });
            
            form.addEventListener("dragover", (e) => {
                e.preventDefault();
                form.classList.add("border-purple-500/50");
            });
            form.addEventListener("dragleave", () => {
                form.classList.remove("border-purple-500/50");
            });
            form.addEventListener("drop", (e) => {
                e.preventDefault();
                form.classList.remove("border-purple-500/50");
                if (e.dataTransfer.files.length > 0) {
                    fileInput.files = e.dataTransfer.files;
                    fileName.textContent = e.dataTransfer.files[0].name;
                }
            });

            form.addEventListener("submit", async (e) => {
                e.preventDefault();
                
                if (fileInput.files.length === 0) {
                    showError("Please select a .jsonl candidates file first.");
                    return;
                }
                
                hideError();
                hideResults();
                showLoading();
                
                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                
                try {
                    const response = await fetch("/api/rank-sample", {
                        method: "POST",
                        body: formData
                    });
                    
                    if (!response.ok) {
                        const text = await response.text();
                        throw new Error(text || "Failed to execute pipeline ranking");
                    }
                    
                    const csvText = await response.text();
                    latestCsvData = csvText;
                    displayResults(csvText);
                } catch (err) {
                    showError(err.message);
                } finally {
                    hideLoading();
                }
            });

            function displayResults(csvText) {
                tableBody.innerHTML = "";
                const lines = csvText.split("\\n");
                
                let count = 0;
                for (let i = 1; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;
                    
                    const rowData = [];
                    let insideQuote = false;
                    let currentVal = "";
                    
                    for (let c = 0; c < line.length; c++) {
                        const char = line[c];
                        if (char === '"') {
                            insideQuote = !insideQuote;
                        } else if (char === ',' && !insideQuote) {
                            rowData.push(currentVal.replace(/^"|"$/g, ''));
                            currentVal = "";
                        } else {
                            currentVal += char;
                        }
                    }
                    rowData.push(currentVal.replace(/^"|"$/g, ''));
                    
                    if (rowData.length >= 4) {
                        const [candidate_id, rank, score, reasoning] = rowData;
                        
                        const tr = document.createElement("tr");
                        tr.className = "hover:bg-slate-900/40 border-b border-slate-800/40";
                        tr.innerHTML = `
                            <td class="p-4 font-bold text-purple-300">#${rank}</td>
                            <td class="p-4 font-mono font-bold text-white">${candidate_id}</td>
                            <td class="p-4"><span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 font-bold">${score}</span></td>
                            <td class="p-4 text-slate-400 truncate max-w-sm md:max-w-md" title="${reasoning}">${reasoning}</td>
                        `;
                        tableBody.appendChild(tr);
                        count++;
                    }
                }
                
                if (count > 0) {
                    resultsSection.classList.remove("hidden");
                } else {
                    showError("No valid rows were parsed from the ranking output CSV.");
                }
            }

            downloadBtn.addEventListener("click", () => {
                const blob = new Blob([latestCsvData], { type: "text/csv;charset=utf-8;" });
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.setAttribute("download", "ranked_sample_results.csv");
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            });

            function showLoading() { loading.classList.remove("hidden"); }
            function hideLoading() { loading.classList.add("hidden"); }
            
            function showError(msg) {
                errorMsg.textContent = msg;
                error.classList.remove("hidden");
            }
            function hideError() { error.classList.add("hidden"); }
            function hideResults() { resultsSection.classList.add("hidden"); }
        </script>
    </body>
    </html>
    """

def pre_warm_cache():
    try:
        roles = get_available_roles()
        for role in roles.keys():
            print(f"Pre-warming cache for role: {role}", flush=True)
            rerank_candidates(role)
            print(f"Cache ready for role: {role}", flush=True)
    except Exception as e:
        print(f"Error during cache pre-warming: {e}", flush=True)

@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=pre_warm_cache, daemon=True)
    thread.start()

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Serve frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
