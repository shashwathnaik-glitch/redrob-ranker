import json
import math
import time
from pathlib import Path
from typing import Dict, Any

from src.config import (
    CANDIDATES_FILE,
    FEATURES_FILE,
    TITLE_AI_ML,
    TITLE_ADJACENT,
    TITLE_UNRELATED,
    CORE_NLP_IR_SKILLS,
    PREFERRED_SKILLS,
    ADJACENT_NOT_CORE_SKILLS,
    CONSULTING_FIRMS,
    RESEARCH_ONLY_INDUSTRIES,
    TODAY,
    PREFERRED_CITIES,
    TIER1_INDIA_CITIES,
)

# Guarded imports from honeypot_detector
try:
    from src.honeypot_detector import is_honeypot, is_keyword_stuffer, is_ghost_candidate, is_consulting_only
except ImportError:
    def is_honeypot(cand):
        return False, []
    def is_keyword_stuffer(cand):
        return 0.0
    def is_ghost_candidate(cand):
        return False
    def is_consulting_only(cand):
        return False

ROLE_TITLE_GROUPS = {
    "ai_engineer": {
        "primary": TITLE_AI_ML,
        "adjacent": TITLE_ADJACENT
    },
    "ml_engineer": {
        "primary": [
            "ml engineer", "machine learning engineer", "ai engineer", "nlp engineer",
            "search engineer", "ranking engineer", "recommendation engineer",
            "applied scientist", "ml platform", "llm engineer", "research scientist",
            "ml scientist", "ai researcher", "deep learning engineer", "computer vision engineer"
        ],
        "adjacent": [
            "data scientist", "data engineer", "software engineer", "backend engineer",
            "platform engineer", "full stack", "mlops", "devops", "site reliability"
        ]
    },
    "backend_engineer": {
        "primary": [
            "backend engineer", "software engineer", "full stack", "platform engineer",
            "systems engineer", "cloud engineer", "backend developer", "software developer"
        ],
        "adjacent": [
            "devops", "site reliability", "sre", "mlops", "data engineer",
            "ai engineer", "ml engineer", "engineering manager", "architect"
        ]
    },
    "data_engineer": {
        "primary": [
            "data engineer", "big data engineer", "database administrator", "etl engineer",
            "data platform", "analytics engineer", "data warehouse engineer"
        ],
        "adjacent": [
            "backend engineer", "software engineer", "data scientist", "data analyst",
            "ml engineer", "systems engineer", "platform engineer", "full stack"
        ]
    }
}

def extract_features_for_candidate(candidate: Dict[str, Any], job_spec: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Extracts a flat feature dictionary for a single candidate profile.
    """
    profile = candidate.get("profile") or {}
    redrob_signals = candidate.get("redrob_signals") or {}
    skills_list = candidate.get("skills") or []
    career_history = candidate.get("career_history") or []
    
    candidate_id = str(candidate.get("candidate_id", ""))
    years_of_experience_val = profile.get("years_of_experience")
    years_of_experience = float(years_of_experience_val) if years_of_experience_val is not None else 0.0
    current_title = str(profile.get("current_title", ""))
    current_company = str(profile.get("current_company", ""))
    
    # Title tier dynamic matching
    role = job_spec.get("role", "ai_engineer") if job_spec else "ai_engineer"
    title_groups = ROLE_TITLE_GROUPS.get(role, {
        "primary": TITLE_AI_ML,
        "adjacent": TITLE_ADJACENT
    })
    primary_titles = title_groups["primary"]
    adjacent_titles = title_groups["adjacent"]
    
    current_title_lower = current_title.lower()
    if any(kw.lower() in current_title_lower for kw in primary_titles):
        title_tier = "primary"
    elif any(kw.lower() in current_title_lower for kw in adjacent_titles):
        title_tier = "adjacent"
    else:
        title_tier = "unrelated"
        
    # Skill counts dynamic matching
    core_skills = job_spec.get("required_skills", CORE_NLP_IR_SKILLS) if job_spec else CORE_NLP_IR_SKILLS
    preferred_skills = job_spec.get("preferred_skills", PREFERRED_SKILLS) if job_spec else PREFERRED_SKILLS
    
    core_count = 0
    preferred_count = 0
    adjacent_count = 0
    
    for skill in skills_list:
        name = str(skill.get("name", "")).strip().lower()
        if any(core.lower() in name for core in core_skills):
            core_count += 1
        if any(pref.lower() in name for pref in preferred_skills):
            preferred_count += 1
        if any(adj.lower() in name for adj in ADJACENT_NOT_CORE_SKILLS):
            adjacent_count += 1
            
    has_cv_speech_without_nlp = adjacent_count > 0 and core_count == 0
    
    # Skill trust score
    trust_sum = 0.0
    for skill in skills_list:
        name = str(skill.get("name", "")).strip().lower()
        if any(core.lower() in name for core in core_skills):
            endorsements = float(skill.get("endorsements", 0.0) or 0.0)
            dur = float(skill.get("duration_months", 0.0) or 0.0)
            trust_sum += endorsements * math.log(1.0 + max(0.0, dur))
    skill_trust_score = min(trust_sum / 500.0, 1.0)
    
    # Assessments
    skill_assessment_scores = redrob_signals.get("skill_assessment_scores") or {}
    has_assessment_score = len(skill_assessment_scores) > 0
    if has_assessment_score:
        avg_assessment_score = sum(float(v) for v in skill_assessment_scores.values()) / len(skill_assessment_scores)
    else:
        avg_assessment_score = 0.0
        
    # Consulting/Product career
    consulting_firms_lower = {firm.lower().strip() for firm in CONSULTING_FIRMS}
    career_at_product_company = False
    for job in career_history:
        comp = str(job.get("company", "")).strip().lower()
        if comp and comp not in consulting_firms_lower:
            career_at_product_company = True
            break
            
    consulting_only_career = is_consulting_only(candidate)
    
    # Tenure & title chaser
    if career_history:
        avg_job_tenure_months = sum(float(job.get("duration_months", 0) or 0) for job in career_history) / len(career_history)
    else:
        avg_job_tenure_months = 0.0
        
    title_chaser_flag = len(career_history) >= 3 and avg_job_tenure_months < 18.0 and years_of_experience > 4.0
    
    # Recent production code flag
    no_recent_production_code_flag = False
    if any(role in current_title_lower for role in ["architect", "tech lead", "engineering manager", "director"]):
        for job in career_history:
            if job.get("is_current") is True:
                dur = float(job.get("duration_months", 0) or 0)
                if dur > 18.0:
                    no_recent_production_code_flag = True
                    break
                    
    # Pure research
    research_industries = {ind.lower().strip() for ind in RESEARCH_ONLY_INDUSTRIES}
    if career_history:
        pure_research_only_flag = all(str(job.get("industry", "")).strip().lower() in research_industries for job in career_history)
    else:
        pure_research_only_flag = False
        
    # Redrob signals
    gh_score = float(redrob_signals.get("github_activity_score", 0.0) or 0.0)
    github_activity_score = 0.0 if gh_score == -1.0 else gh_score
    
    open_to_work = bool(redrob_signals.get("open_to_work_flag", False))
    
    # Days since active
    days_since_active = 9999
    last_active_date_str = redrob_signals.get("last_active_date")
    if last_active_date_str:
        try:
            from datetime import date
            today_date = date.fromisoformat(TODAY)
            if isinstance(last_active_date_str, str):
                last_active_date = date.fromisoformat(last_active_date_str)
            else:
                last_active_date = last_active_date_str
            days_since_active = (today_date - last_active_date).days
        except Exception:
            pass
            
    recruiter_response_rate = float(redrob_signals.get("recruiter_response_rate", 0.0) or 0.0)
    interview_completion_rate = float(redrob_signals.get("interview_completion_rate", 0.0) or 0.0)
    offer_acc = float(redrob_signals.get("offer_acceptance_rate", 0.5) or 0.5)
    offer_acceptance_rate = 0.5 if offer_acc == -1.0 else offer_acc
    notice_period_days = int(redrob_signals.get("notice_period_days", 0) or 0)
    
    # Location & Relocation
    country = str(profile.get("country", "")).strip()
    location = str(profile.get("location", "")).strip()
    location_lower = location.lower()
    is_preferred_city = any(city.lower() in location_lower for city in PREFERRED_CITIES)
    is_tier1_india_city = any(city.lower() in location_lower for city in TIER1_INDIA_CITIES)
    is_india_based = country.lower() == "india"
    willing_to_relocate = bool(redrob_signals.get("willing_to_relocate", False))
    
    # Engagement & trust
    profile_completeness = float(redrob_signals.get("profile_completeness_score", 0.0) or 0.0)
    verified_both = bool(redrob_signals.get("verified_email", False)) and bool(redrob_signals.get("verified_phone", False))
    linkedin_connected = bool(redrob_signals.get("linkedin_connected", False))
    endorsements_received = int(redrob_signals.get("endorsements_received", 0) or 0)
    saved_by_recruiters_30d = int(redrob_signals.get("saved_by_recruiters_30d", 0) or 0)
    
    # Honeypot checks
    honeypot_flag, reasons = is_honeypot(candidate)
    keyword_stuffer = is_keyword_stuffer(candidate)
    ghost_flag = is_ghost_candidate(candidate)
    
    return {
        "candidate_id": candidate_id,
        "years_of_experience": years_of_experience,
        "current_title": current_title,
        "current_company": current_company,
        "title_tier": title_tier,
        "core_skill_count": core_count,
        "preferred_skill_count": preferred_count,
        "adjacent_skill_count": adjacent_count,
        "has_cv_speech_without_nlp": has_cv_speech_without_nlp,
        "skill_trust_score": skill_trust_score,
        "has_assessment_score": has_assessment_score,
        "avg_assessment_score": avg_assessment_score,
        "career_at_product_company": career_at_product_company,
        "consulting_only_career": consulting_only_career,
        "avg_job_tenure_months": avg_job_tenure_months,
        "title_chaser_flag": title_chaser_flag,
        "no_recent_production_code_flag": no_recent_production_code_flag,
        "pure_research_only_flag": pure_research_only_flag,
        "github_activity_score": github_activity_score,
        "open_to_work": open_to_work,
        "days_since_active": days_since_active,
        "recruiter_response_rate": recruiter_response_rate,
        "interview_completion_rate": interview_completion_rate,
        "offer_acceptance_rate": offer_acceptance_rate,
        "notice_period_days": notice_period_days,
        "country": country,
        "location": location,
        "is_preferred_city": is_preferred_city,
        "is_tier1_india_city": is_tier1_india_city,
        "is_india_based": is_india_based,
        "willing_to_relocate": willing_to_relocate,
        "profile_completeness": profile_completeness,
        "verified_both": verified_both,
        "linkedin_connected": linkedin_connected,
        "endorsements_received": endorsements_received,
        "saved_by_recruiters_30d": saved_by_recruiters_30d,
        "is_honeypot": honeypot_flag,
        "honeypot_reasons": reasons,
        "keyword_stuffer_risk": keyword_stuffer,
        "is_ghost_candidate": ghost_flag,
    }

def process_candidates(candidates_file: str = CANDIDATES_FILE, features_file: str = FEATURES_FILE):
    """
    Streams raw candidate profiles, extracts features, and writes to features.jsonl.
    """
    start_time = time.time()
    
    input_path = Path(candidates_file)
    output_path = Path(features_file)
    
    # Ensure processed directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not input_path.exists():
        print(f"Candidates file {candidates_file} does not exist. Skipping extraction.")
        return
        
    count = 0
    with open(input_path, "r", encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:
        for line in f_in:
            if not line.strip():
                continue
            candidate = json.loads(line)
            features = extract_features_for_candidate(candidate)
            f_out.write(json.dumps(features) + "\n")
            count += 1
            if count % 10000 == 0:
                elapsed = time.time() - start_time
                print(f"Processed {count} candidates... ({elapsed:.2f}s elapsed)")
                
    elapsed = time.time() - start_time
    print(f"Extraction completed. Total candidates processed: {count} in {elapsed:.2f}s.")

if __name__ == "__main__":
    process_candidates()
