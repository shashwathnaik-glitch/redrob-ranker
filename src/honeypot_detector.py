from datetime import date
from typing import Dict, Any, List, Tuple
from src.config import (
    HONEYPOT_EXPERT_ZERO_SKILLS_MIN,
    HONEYPOT_CAREER_MONTHS_EXCESS,
    CORE_NLP_IR_SKILLS,
    TITLE_AI_ML,
    TITLE_ADJACENT,
    TITLE_UNRELATED,
    CONSULTING_FIRMS,
    TODAY,
    RESPONSE_RATE_MIN
)

def is_honeypot(candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Returns (flag, reasons). Flag is True if ANY rule triggers.
    """
    reasons = []
    
    # Real field paths
    profile = candidate.get("profile", {})
    years_of_experience_val = profile.get("years_of_experience")
    years_of_experience = float(years_of_experience_val) if years_of_experience_val is not None else 0.0
    
    skills = candidate.get("skills", [])
    career_history = candidate.get("career_history", [])
    certifications = candidate.get("certifications", [])
    
    # Rule 1: count of candidate["skills"] entries with proficiency == "expert"
    # AND duration_months == 0 >= HONEYPOT_EXPERT_ZERO_SKILLS_MIN
    expert_zero_count = 0
    for skill in skills:
        prof = str(skill.get("proficiency", "")).strip().lower()
        dur = skill.get("duration_months")
        if prof == "expert" and dur == 0:
            expert_zero_count += 1
            
    if expert_zero_count >= HONEYPOT_EXPERT_ZERO_SKILLS_MIN:
        reasons.append(
            f"Expert skills with zero duration ({expert_zero_count}) "
            f"exceeds or equals limit ({HONEYPOT_EXPERT_ZERO_SKILLS_MIN})"
        )
        
    # Rule 2: sum(j["duration_months"] for j in career_history) > (years_of_experience * 12) + HONEYPOT_CAREER_MONTHS_EXCESS
    total_career_months = sum(int(j.get("duration_months") or 0) for j in career_history)
    yoe_months_limit = (years_of_experience * 12) + HONEYPOT_CAREER_MONTHS_EXCESS
    if total_career_months > yoe_months_limit:
        reasons.append(
            f"Total career history duration ({total_career_months} months) "
            f"exceeds YOE limit ({yoe_months_limit:.1f} months)"
        )
        
    # Rule 3: any skill where duration_months > years_of_experience * 12
    yoe_limit_months = years_of_experience * 12
    for skill in skills:
        dur = skill.get("duration_months")
        if dur is not None and dur > yoe_limit_months:
            reasons.append(
                f"Skill '{skill.get('name', 'Unknown')}' duration ({dur} months) "
                f"exceeds YOE limit ({yoe_limit_months:.1f} months)"
            )
            
    # Rule 4: any certification where year < (2026 - years_of_experience - 5)
    cert_year_limit = 2026 - years_of_experience - 5
    for cert in certifications:
        year_val = cert.get("year")
        if year_val is not None:
            try:
                cert_year = int(year_val)
                if cert_year < cert_year_limit:
                    reasons.append(
                        f"Certification '{cert.get('name', 'Unknown')}' year ({cert_year}) "
                        f"is older than the limit ({cert_year_limit:.1f})"
                    )
            except (ValueError, TypeError):
                pass
                
    flag = len(reasons) > 0
    return flag, reasons

def is_keyword_stuffer(candidate: Dict[str, Any]) -> float:
    """
    Returns a 0-1 suspicion score.
    """
    skills = candidate.get("skills", [])
    profile = candidate.get("profile", {})
    current_title = str(profile.get("current_title", "")).strip().lower()
    career_history = candidate.get("career_history", [])
    
    # 1. core_count = count of candidate["skills"] names matching CORE_NLP_IR_SKILLS
    core_skills_set = {s.lower() for s in CORE_NLP_IR_SKILLS}
    core_count = sum(1 for skill in skills if str(skill.get("name", "")).strip().lower() in core_skills_set)
    
    # 2. title_tier = classify candidate["profile"]["current_title"] against TITLE_AI_ML / TITLE_ADJACENT / TITLE_UNRELATED (lowercased substring match)
    title_tier = "unrelated"
    if current_title:
        # Check AI_ML first
        if any(kw.lower() in current_title for kw in TITLE_AI_ML):
            title_tier = "ai_ml"
        # Check ADJACENT next
        elif any(kw.lower() in current_title for kw in TITLE_ADJACENT):
            title_tier = "adjacent"
        # Otherwise, if it matches TITLE_UNRELATED or doesn't match AI_ML / ADJACENT, classify as unrelated
        elif any(kw.lower() in current_title for kw in TITLE_UNRELATED):
            title_tier = "unrelated"
            
    # 3. evidence = count of career_history entries whose "description" field (lowercased) contains any CORE_NLP_IR_SKILLS term
    evidence = 0
    for job in career_history:
        desc = str(job.get("description", "")).strip().lower()
        if any(term.lower() in desc for term in CORE_NLP_IR_SKILLS):
            evidence += 1
            
    # Scoring logic
    if core_count >= 5 and title_tier == "unrelated" and evidence == 0:
        return 0.9
    if core_count >= 3 and evidence == 0:
        return 0.6
        
    return 0.0

def is_consulting_only(candidate: Dict[str, Any]) -> bool:
    """
    Return True if ALL candidate["career_history"] entries have "company"
    case-insensitive-matching any name in CONSULTING_FIRMS.
    """
    career_history = candidate.get("career_history", [])
    if not career_history:
        return False
        
    consulting_set = {firm.lower().strip() for firm in CONSULTING_FIRMS}
    for job in career_history:
        company = str(job.get("company", "")).strip().lower()
        if company not in consulting_set:
            return False
            
    return True

def is_ghost_candidate(candidate: Dict[str, Any]) -> bool:
    """
    Return True if last active date is older than 90 days from TODAY and response rate is weak.
    """
    sig = candidate.get("redrob_signals", {})
    if not sig:
        return False
        
    last_active_val = sig.get("last_active_date")
    if not last_active_val:
        return False
        
    try:
        today_date = date.fromisoformat(TODAY)
        if isinstance(last_active_val, str):
            last_active_date = date.fromisoformat(last_active_val)
        else:
            last_active_date = last_active_val
            
        inactive_days = (today_date - last_active_date).days
    except (ValueError, TypeError):
        return False
        
    recruiter_response_rate = sig.get("recruiter_response_rate")
    if recruiter_response_rate is None:
        return False
        
    return inactive_days > 90 and recruiter_response_rate < RESPONSE_RATE_MIN
