from pathlib import Path
from src.config import DATA_DIR, PROCESSED_DIR
from src.feature_extractor import extract_features_for_candidate
from src.scorer import calculate_score

def test_extract_features_real():
    candidate = {
        "candidate_id": "cand_001",
        "profile": {
            "years_of_experience": 6.5,
            "current_title": "Senior AI Engineer",
            "current_company": "Redrob AI",
            "location": "Pune",
            "country": "India"
        },
        "skills": [
            {"name": "sentence-transformers", "proficiency": "expert", "endorsements": 10, "duration_months": 24},
            {"name": "vector database", "proficiency": "expert", "endorsements": 5, "duration_months": 12},
            {"name": "lora", "proficiency": "intermediate", "endorsements": 2, "duration_months": 6},
            {"name": "computer vision", "proficiency": "intermediate", "endorsements": 1, "duration_months": 12}
        ],
        "career_history": [
            {"company": "Redrob AI", "title": "AI Engineer", "is_current": True, "duration_months": 18, "industry": "Technology"},
            {"company": "TCS", "title": "Software Engineer", "is_current": False, "duration_months": 36, "industry": "Consulting"}
        ],
        "redrob_signals": {
            "profile_completeness_score": 95.0,
            "last_active_date": "2026-06-15",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.85,
            "skill_assessment_scores": {"Python": 90, "Machine Learning": 85},
            "notice_period_days": 30,
            "willing_to_relocate": True,
            "github_activity_score": 75.0,
            "saved_by_recruiters_30d": 5,
            "endorsements_received": 15,
            "verified_email": True,
            "verified_phone": True,
            "linkedin_connected": True,
            "interview_completion_rate": 0.90,
            "offer_acceptance_rate": 0.80
        }
    }
    
    feats = extract_features_for_candidate(candidate)
    
    assert feats["candidate_id"] == "cand_001"
    assert feats["years_of_experience"] == 6.5
    assert feats["current_title"] == "Senior AI Engineer"
    assert feats["current_company"] == "Redrob AI"
    assert feats["title_tier"] == "primary"
    assert feats["core_skill_count"] == 2  # sentence-transformers, vector database
    assert feats["preferred_skill_count"] == 1  # lora
    assert feats["adjacent_skill_count"] == 1  # computer vision
    assert feats["has_cv_speech_without_nlp"] is False
    assert feats["skill_trust_score"] > 0.0
    assert feats["has_assessment_score"] is True
    assert feats["avg_assessment_score"] == 87.5
    assert feats["career_at_product_company"] is True  # Redrob AI is not TCS/consulting
    assert feats["consulting_only_career"] is False
    assert feats["avg_job_tenure_months"] == 27.0
    assert feats["title_chaser_flag"] is False
    assert feats["no_recent_production_code_flag"] is False
    assert feats["pure_research_only_flag"] is False
    assert feats["github_activity_score"] == 75.0
    assert feats["open_to_work"] is True
    assert feats["days_since_active"] == 5  # 2026-06-20 - 2026-06-15
    assert feats["is_preferred_city"] is True  # Pune
    assert feats["is_tier1_india_city"] is True
    assert feats["is_india_based"] is True
    assert feats["verified_both"] is True
    assert feats["linkedin_connected"] is True
    assert feats["is_honeypot"] is False


from src.honeypot_detector import is_honeypot, is_keyword_stuffer, is_consulting_only, is_ghost_candidate

def test_is_honeypot_rules():
    # Base normal candidate
    candidate = {
        "profile": {"years_of_experience": 5.0, "current_title": "AI Engineer"},
        "skills": [{"name": "Python", "proficiency": "expert", "duration_months": 24}],
        "career_history": [{"company": "Google", "duration_months": 24}],
        "certifications": [{"name": "AWS", "year": 2023}],
        "redrob_signals": {"last_active_date": "2026-06-10", "recruiter_response_rate": 0.8}
    }
    flag, reasons = is_honeypot(candidate)
    assert flag is False
    assert len(reasons) == 0

    # Rule 1: expert with 0 months >= 3
    honeypot_1 = candidate.copy()
    honeypot_1["skills"] = [
        {"name": "Python", "proficiency": "expert", "duration_months": 0},
        {"name": "ML", "proficiency": "expert", "duration_months": 0},
        {"name": "NLP", "proficiency": "expert", "duration_months": 0},
    ]
    flag, reasons = is_honeypot(honeypot_1)
    assert flag is True
    assert any("Expert skills with zero duration" in r for r in reasons)

    # Rule 2: sum(career_history duration_months) > YOE * 12 + 36
    honeypot_2 = candidate.copy()
    honeypot_2["career_history"] = [
        {"company": "Google", "duration_months": 50},
        {"company": "Meta", "duration_months": 50},  # sum = 100 > 5 * 12 + 36 (96)
    ]
    flag, reasons = is_honeypot(honeypot_2)
    assert flag is True
    assert any("Total career history duration" in r for r in reasons)

    # Rule 3: any skill duration > YOE * 12 (60 months)
    honeypot_3 = candidate.copy()
    honeypot_3["skills"] = [{"name": "Python", "proficiency": "expert", "duration_months": 70}]
    flag, reasons = is_honeypot(honeypot_3)
    assert flag is True
    assert any("duration" in r and "exceeds YOE limit" in r for r in reasons)

    # Rule 4: certification year < 2026 - YOE - 5 (2016)
    honeypot_4 = candidate.copy()
    honeypot_4["certifications"] = [{"name": "Old Cert", "year": 2015}]
    flag, reasons = is_honeypot(honeypot_4)
    assert flag is True
    assert any("older than the limit" in r for r in reasons)

def test_is_keyword_stuffer():
    # 0.9 case: core_count >= 5, title "unrelated", evidence == 0
    candidate_stuffer_1 = {
        "profile": {"current_title": "Marketing Manager"},
        "skills": [
            {"name": "sentence-transformers"}, {"name": "embeddings"},
            {"name": "vector search"}, {"name": "rag"}, {"name": "nlp"}
        ],
        "career_history": [{"description": "worked in sales"}]
    }
    assert is_keyword_stuffer(candidate_stuffer_1) == 0.9

    # 0.6 case: core_count >= 3, evidence == 0
    candidate_stuffer_2 = {
        "profile": {"current_title": "AI Engineer"},
        "skills": [
            {"name": "sentence-transformers"}, {"name": "embeddings"}, {"name": "vector search"}
        ],
        "career_history": [{"description": "worked in sales"}]
    }
    assert is_keyword_stuffer(candidate_stuffer_2) == 0.6

    # Normal case: core_count >= 3, evidence > 0
    candidate_normal = {
        "profile": {"current_title": "AI Engineer"},
        "skills": [
            {"name": "sentence-transformers"}, {"name": "embeddings"}, {"name": "vector search"}
        ],
        "career_history": [{"description": "implemented sentence-transformers for RAG pipeline"}]
    }
    assert is_keyword_stuffer(candidate_normal) == 0.0

def test_is_consulting_only():
    candidate_consulting = {
        "career_history": [
            {"company": "TCS"},
            {"company": "Infosys"},
            {"company": "wipro"}
        ]
    }
    assert is_consulting_only(candidate_consulting) is True

    candidate_mixed = {
        "career_history": [
            {"company": "TCS"},
            {"company": "Google"}
        ]
    }
    assert is_consulting_only(candidate_mixed) is False

def test_is_ghost_candidate():
    # Inactive > 90 days and response rate < 0.15
    candidate_ghost = {
        "redrob_signals": {
            "last_active_date": "2026-03-01",  # older than 90 days from 2026-06-20
            "recruiter_response_rate": 0.10
        }
    }
    assert is_ghost_candidate(candidate_ghost) is True

    # Active recently
    candidate_active = {
        "redrob_signals": {
            "last_active_date": "2026-06-15",
            "recruiter_response_rate": 0.10
        }
    }
    assert is_ghost_candidate(candidate_active) is False


from src.scorer import score_candidate
from src.submission_auditor import audit_submission

def test_score_candidate_flow():
    # Setup candidate features
    features = {
        "candidate_id": "cand_001",
        "years_of_experience": 6.0,
        "current_title": "AI Engineer",
        "current_company": "Redrob",
        "title_tier": "primary",
        "core_skill_count": 6,
        "preferred_skill_count": 0,
        "adjacent_skill_count": 0,
        "has_cv_speech_without_nlp": False,
        "skill_trust_score": 1.0,
        "has_assessment_score": True,
        "avg_assessment_score": 100.0,
        "career_at_product_company": True,
        "consulting_only_career": False,
        "avg_job_tenure_months": 24.0,
        "title_chaser_flag": False,
        "no_recent_production_code_flag": False,
        "pure_research_only_flag": False,
        "github_activity_score": 80.0,
        "open_to_work": True,
        "days_since_active": 10,
        "recruiter_response_rate": 0.9,
        "interview_completion_rate": 0.9,
        "offer_acceptance_rate": 0.8,
        "notice_period_days": 15,
        "country": "India",
        "location": "Pune",
        "is_preferred_city": True,
        "is_tier1_india_city": True,
        "is_india_based": True,
        "willing_to_relocate": True,
        "profile_completeness": 100.0,
        "verified_both": True,
        "linkedin_connected": True,
        "endorsements_received": 10,
        "saved_by_recruiters_30d": 5,
        "is_honeypot": False,
        "honeypot_reasons": [],
        "keyword_stuffer_risk": 0.0,
        "is_ghost_candidate": False
    }

    res = score_candidate(features)
    assert 0.0 <= res["score"] <= 1.0
    assert "AI Engineer" in res["reasoning"]
    assert "product-company career" in res["reasoning"]

    # Honeypot disqualification test
    honeypot_features = features.copy()
    honeypot_features["is_honeypot"] = True
    honeypot_features["honeypot_reasons"] = ["Expert skills with zero duration"]
    res_hp = score_candidate(honeypot_features)
    assert res_hp["score"] == 0.0
    assert "flagged as a possible honeypot" in res_hp["reasoning"]

def test_submission_auditor_flow(tmp_path):
    # Create a mock CSV file
    csv_file = tmp_path / "submission.csv"
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        f.write("candidate_id,score,reasoning\n")
        f.write("cand_001,0.95,Excellent fit\n")
        f.write("cand_002,0.45,Good fit\n")

    # Mock features lookup
    mock_features = {
        "cand_001": {
            "is_honeypot": False,
            "consulting_only_career": False,
            "core_skill_count": 8,
            "pure_research_only_flag": False,
            "title_chaser_flag": False,
            "no_recent_production_code_flag": False,
            "has_cv_speech_without_nlp": False
        },
        "cand_002": {
            "is_honeypot": True,
            "consulting_only_career": True,
            "core_skill_count": 2,
            "pure_research_only_flag": False,
            "title_chaser_flag": False,
            "no_recent_production_code_flag": False,
            "has_cv_speech_without_nlp": False
        }
    }

    # Execute auditor (should run print statements without raising exceptions)
    audit_submission(str(csv_file), mock_features)


import pytest
import json
from src.jd_loader import load_job_spec, get_available_roles, load_jd_intent
from src.config import JD_INTENT_FILE

def test_jd_loader_dynamic(tmp_path, monkeypatch):
    # Set up mock folder
    mock_processed_dir = tmp_path / "processed"
    mock_processed_dir.mkdir()
    
    # Configure configuration variables using monkeypatch
    mock_jd_intent_file = mock_processed_dir / "jd_intent.json"
    
    # Write a mock legacy jd_intent.json file
    legacy_data = {"role": "legacy_ai_engineer", "skills": ["python", "nlp"]}
    with open(mock_jd_intent_file, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)
        
    # Patch config variable
    monkeypatch.setattr("src.jd_loader.JD_INTENT_FILE", str(mock_jd_intent_file))
    
    # 1. Test fallback when ai_engineer.json does not exist
    # It should fall back to jd_intent.json
    spec = load_job_spec("ai_engineer")
    assert spec["role"] == "legacy_ai_engineer"
    
    # 2. If no argument is provided, it should default to ai_engineer (which falls back to jd_intent.json)
    spec_default = load_job_spec()
    assert spec_default["role"] == "legacy_ai_engineer"
    
    # 3. Test when ai_engineer.json is present
    mock_ai_engineer_file = mock_processed_dir / "ai_engineer.json"
    ai_eng_data = {"role": "new_ai_engineer", "skills": ["python", "nlp", "rag"]}
    with open(mock_ai_engineer_file, "w", encoding="utf-8") as f:
        json.dump(ai_eng_data, f)
        
    spec_new = load_job_spec("ai_engineer")
    assert spec_new["role"] == "new_ai_engineer"
    
    # 4. Expose dynamic roles like backend_engineer when the file exists
    mock_backend_file = mock_processed_dir / "backend_engineer.json"
    backend_data = {"role": "backend_engineer", "skills": ["python", "go"]}
    with open(mock_backend_file, "w", encoding="utf-8") as f:
        json.dump(backend_data, f)
        
    # Check roles discovered
    roles = get_available_roles()
    assert "ai_engineer" in roles
    assert "backend_engineer" in roles
    assert "jd_intent" not in roles  # jd_intent.json should be skipped/excluded
    
    spec_backend = load_job_spec("backend_engineer")
    assert spec_backend["role"] == "backend_engineer"
    
    # 5. Non-existent roles should raise ValueError
    with pytest.raises(ValueError) as excinfo:
        load_job_spec("invalid_role")
    assert "Unsupported role 'invalid_role'" in str(excinfo.value)
    assert "ai_engineer" in str(excinfo.value)
    
    # 6. Existent but missing file on disk (e.g. if we remove backend_engineer.json)
    mock_backend_file.unlink()
    with pytest.raises(ValueError) as excinfo:
        load_job_spec("backend_engineer")
         
    # 7. Test load_jd_intent legacy interface behaves as before
    # With explicit path:
    custom_jd_file = mock_processed_dir / "custom.json"
    custom_data = {"role": "custom_role"}
    with open(custom_jd_file, "w", encoding="utf-8") as f:
        json.dump(custom_data, f)
    assert load_jd_intent(custom_jd_file)["role"] == "custom_role"
    
    # Without path:
    assert load_jd_intent()["role"] == "new_ai_engineer"


from fastapi.testclient import TestClient
from app import app

def test_api_rank_sample_validation(tmp_path, monkeypatch):
    client = TestClient(app)
    
    # Mock data directory for tests
    mock_processed_dir = tmp_path / "processed"
    mock_processed_dir.mkdir()
    
    # Write a mock legacy jd_intent.json file
    mock_jd_intent_file = mock_processed_dir / "jd_intent.json"
    with open(mock_jd_intent_file, "w", encoding="utf-8") as f:
        json.dump({"role": "ai_engineer"}, f)
        
    monkeypatch.setattr("src.jd_loader.JD_INTENT_FILE", str(mock_jd_intent_file))
    
    # 1. Test invalid role parameter (should return 400 Bad Request)
    # Prepare dummy jsonl file content
    dummy_jsonl = '{"candidate_id": "cand_01", "profile": {}, "skills": [], "career_history": [], "redrob_signals": {}}\n'
    response = client.post(
        "/api/rank-sample?role=invalid_role",
        files={"file": ("test.jsonl", dummy_jsonl, "text/plain")}
    )
    assert response.status_code == 400
    res_json = response.json()
    assert "detail" in res_json
    assert res_json["detail"]["requested_role"] == "invalid_role"
    assert "ai_engineer" in res_json["detail"]["available_roles"]
    assert "Invalid job role" in res_json["detail"]["error"]
    
    # 2. Test valid default parameter (ai_engineer, should return 200 OK)
    response_default = client.post(
        "/api/rank-sample",
        files={"file": ("test.jsonl", dummy_jsonl, "text/plain")}
    )
    assert response_default.status_code == 200
    
    # 3. Test valid explicit role parameters (by writing backend_engineer.json to disk)
    mock_backend_file = mock_processed_dir / "backend_engineer.json"
    with open(mock_backend_file, "w", encoding="utf-8") as f:
        json.dump({"role": "backend_engineer"}, f)
        
    response_backend = client.post(
        "/api/rank-sample?role=backend_engineer",
        files={"file": ("test.jsonl", dummy_jsonl, "text/plain")}
    )
    assert response_backend.status_code == 200


def test_api_rerank_caching(tmp_path, monkeypatch):
    client = TestClient(app)

    # Mock data directory for tests
    mock_processed_dir = tmp_path / "processed"
    mock_processed_dir.mkdir()
    
    # Configure mock jd_intent.json for default role validation
    mock_jd_intent_file = mock_processed_dir / "jd_intent.json"
    with open(mock_jd_intent_file, "w", encoding="utf-8") as f:
        json.dump({"role": "ai_engineer"}, f)
        
    monkeypatch.setattr("src.jd_loader.JD_INTENT_FILE", str(mock_jd_intent_file))

    # Mock dynamic role files
    mock_backend_file = mock_processed_dir / "backend_engineer.json"
    with open(mock_backend_file, "w", encoding="utf-8") as f:
        json.dump({"role": "backend_engineer"}, f)

    # Mock candidates file (contains only 1 candidate to keep it extremely fast)
    mock_candidates_file = tmp_path / "candidates.jsonl"
    dummy_jsonl = '{"candidate_id": "cand_01", "profile": {}, "skills": [], "career_history": [], "redrob_signals": {}}\n'
    with open(mock_candidates_file, "w", encoding="utf-8") as f:
        f.write(dummy_jsonl)

    monkeypatch.setattr("app.CANDIDATES_FILE", str(mock_candidates_file))
    
    # Mock RANKED_JSON_FILE path so we don't write to outputs in test
    mock_ranked_json_file = tmp_path / "ranked_candidates.json"
    monkeypatch.setattr("app.RANKED_JSON_FILE", str(mock_ranked_json_file))

    # Ensure cache is clear at start
    client.delete("/api/cache/clear")

    # 1. First call: Cache MISS
    response1 = client.get("/api/rerank?role=AI_Engineer")
    assert response1.status_code == 200
    res1 = response1.json()
    assert res1["cached"] is False
    assert res1["role"] == "ai_engineer"

    # 2. Second call (case-insensitive and trailing space check): Cache HIT
    response2 = client.get("/api/rerank?role=  ai_engineer  ")
    assert response2.status_code == 200
    res2 = response2.json()
    assert res2["cached"] is True
    assert res2["role"] == "ai_engineer"

    # 3. Third call for a different role: Cache MISS
    response3 = client.get("/api/rerank?role=backend_engineer")
    assert response3.status_code == 200
    res3 = response3.json()
    assert res3["cached"] is False
    assert res3["role"] == "backend_engineer"

    # 4. Check cache status
    status_response = client.get("/api/cache/status")
    assert status_response.status_code == 200
    status_json = status_response.json()
    assert status_json["total_cached_roles"] == 2
    cached_roles = [r["role"] for r in status_json["cached_roles"]]
    assert "ai_engineer" in cached_roles
    assert "backend_engineer" in cached_roles

    # 5. Clear specific role cache
    clear_response = client.delete("/api/cache/clear?role=AI_Engineer")
    assert clear_response.status_code == 200
    
    # 6. Verify cleared role is a miss, other role is still a hit
    response1_retry = client.get("/api/rerank?role=ai_engineer")
    assert response1_retry.status_code == 200
    assert response1_retry.json()["cached"] is False

    response3_retry = client.get("/api/rerank?role=backend_engineer")
    assert response3_retry.status_code == 200
    assert response3_retry.json()["cached"] is True


def test_api_rerank_role_differentiation(tmp_path, monkeypatch):
    client = TestClient(app)

    # Mock data directory for tests
    mock_processed_dir = tmp_path / "processed"
    mock_processed_dir.mkdir()
    
    # Configure mock jd_intent.json for default role validation
    mock_jd_intent_file = mock_processed_dir / "jd_intent.json"
    with open(mock_jd_intent_file, "w", encoding="utf-8") as f:
        json.dump({"role": "ai_engineer"}, f)
        
    monkeypatch.setattr("src.jd_loader.JD_INTENT_FILE", str(mock_jd_intent_file))

    # Mock dynamic role files
    mock_ai_file = mock_processed_dir / "ai_engineer.json"
    with open(mock_ai_file, "w", encoding="utf-8") as f:
        json.dump({
            "role": "ai_engineer",
            "title": "Senior AI Engineer",
            "required_skills": ["sentence-transformers", "embeddings", "vector search"],
            "preferred_skills": [],
            "experience_requirements": {"ideal_min": 5, "ideal_max": 9, "good_min": 4, "good_max": 10, "acceptable_min": 3, "acceptable_max": 12},
            "scoring_weights": {"title": 0.20, "skill": 0.22, "career": 0.18, "experience": 0.12, "behavioral": 0.10, "location": 0.08, "notice": 0.06, "trust": 0.04}
        }, f)

    mock_backend_file = mock_processed_dir / "backend_engineer.json"
    with open(mock_backend_file, "w", encoding="utf-8") as f:
        json.dump({
            "role": "backend_engineer",
            "title": "Senior Backend Engineer",
            "required_skills": ["go", "java", "sql"],
            "preferred_skills": [],
            "experience_requirements": {"ideal_min": 5, "ideal_max": 9, "good_min": 4, "good_max": 10, "acceptable_min": 3, "acceptable_max": 12},
            "scoring_weights": {"title": 0.20, "skill": 0.22, "career": 0.18, "experience": 0.12, "behavioral": 0.10, "location": 0.08, "notice": 0.06, "trust": 0.04}
        }, f)

    # Mock candidates file:
    # CAND_AI: Senior AI Engineer with AI skills
    # CAND_BE: Senior Backend Engineer with Backend skills
    cand_ai = {
        "candidate_id": "CAND_AI",
        "profile": {"anonymized_name": "AI Candidate", "current_title": "Senior AI Engineer", "years_of_experience": 6.0},
        "skills": [{"name": "sentence-transformers"}, {"name": "embeddings"}, {"name": "vector search"}],
        "career_history": [],
        "redrob_signals": {"verified_email": True, "verified_phone": True, "linkedin_connected": True}
    }
    cand_be = {
        "candidate_id": "CAND_BE",
        "profile": {"anonymized_name": "BE Candidate", "current_title": "Senior Backend Engineer", "years_of_experience": 6.0},
        "skills": [{"name": "go"}, {"name": "java"}, {"name": "sql"}],
        "career_history": [],
        "redrob_signals": {"verified_email": True, "verified_phone": True, "linkedin_connected": True}
    }
    
    mock_candidates_file = tmp_path / "candidates.jsonl"
    with open(mock_candidates_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(cand_ai) + "\n")
        f.write(json.dumps(cand_be) + "\n")

    monkeypatch.setattr("app.CANDIDATES_FILE", str(mock_candidates_file))
    
    mock_ranked_json_file = tmp_path / "ranked_candidates.json"
    monkeypatch.setattr("app.RANKED_JSON_FILE", str(mock_ranked_json_file))

    # Ensure cache is clear
    client.delete("/api/cache/clear")

    # 1. Rerank for AI Engineer
    res_ai = client.get("/api/rerank?role=ai_engineer")
    assert res_ai.status_code == 200
    
    # Read the written candidates from outputs
    with open(mock_ranked_json_file, "r", encoding="utf-8") as f:
        ranked_ai = json.load(f)
        
    # In AI ranking, CAND_AI must be ranked higher than CAND_BE
    assert ranked_ai[0]["candidate_id"] == "CAND_AI"
    ai_candidate_score = ranked_ai[0]["score"]
    be_candidate_in_ai_score = ranked_ai[1]["score"]
    assert ai_candidate_score > be_candidate_in_ai_score

    # Clear cache so we compute fresh for backend engineer
    client.delete("/api/cache/clear")

    # 2. Rerank for Backend Engineer
    res_be = client.get("/api/rerank?role=backend_engineer")
    assert res_be.status_code == 200
    
    with open(mock_ranked_json_file, "r", encoding="utf-8") as f:
        ranked_be = json.load(f)
        
    # In Backend ranking, CAND_BE must be ranked higher than CAND_AI
    assert ranked_be[0]["candidate_id"] == "CAND_BE"
    be_candidate_score = ranked_be[0]["score"]
    ai_candidate_in_be_score = ranked_be[1]["score"]
    assert be_candidate_score > ai_candidate_in_be_score





