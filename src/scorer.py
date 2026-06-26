from typing import Dict, Any, List
from src.config import (
    WEIGHTS,
    DISQUALIFIER_MULTIPLIERS,
    EXP_IDEAL_MIN,
    EXP_IDEAL_MAX,
    EXP_GOOD_MIN,
    EXP_GOOD_MAX,
    EXP_ACCEPTABLE_MIN,
    EXP_ACCEPTABLE_MAX,
    ACTIVE_DAYS_GREAT,
    ACTIVE_DAYS_GOOD,
    ACTIVE_DAYS_WEAK,
    NOTICE_IDEAL,
    NOTICE_OK,
    NOTICE_WEAK
)

def clip(val: float, low: float, high: float) -> float:
    """Clips a value to [low, high] bounds."""
    return max(low, min(val, high))

def score_candidate(features: Dict[str, Any], job_spec: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Computes a weighted sum match score, applies disqualifiers, 
    and returns score and reasoning.
    """
    # Load dynamic config values if job_spec is provided
    weights = job_spec.get("scoring_weights", WEIGHTS) if job_spec else WEIGHTS
    
    exp_reqs = job_spec.get("experience_requirements", {}) if job_spec else {}
    exp_ideal_min = exp_reqs.get("ideal_min", EXP_IDEAL_MIN)
    exp_ideal_max = exp_reqs.get("ideal_max", EXP_IDEAL_MAX)
    exp_good_min = exp_reqs.get("good_min", EXP_GOOD_MIN)
    exp_good_max = exp_reqs.get("good_max", EXP_GOOD_MAX)
    exp_acceptable_min = exp_reqs.get("acceptable_min", EXP_ACCEPTABLE_MIN)
    exp_acceptable_max = exp_reqs.get("acceptable_max", EXP_ACCEPTABLE_MAX)

    # 1. Title Score
    title_tier = features.get("title_tier", "unrelated")
    if title_tier == "primary":
        title_score = 1.0
    elif title_tier == "adjacent":
        title_score = 0.55
    else:
        title_score = 0.0

    # 2. Skill Score
    core_skill_count = features.get("core_skill_count", 0)
    preferred_skill_count = features.get("preferred_skill_count", 0)
    avg_assessment_score = features.get("avg_assessment_score", 0.0)
    has_assessment_score = features.get("has_assessment_score", False)
    skill_trust_score = features.get("skill_trust_score", 0.0)

    base_skill = min(core_skill_count / 6.0, 1.0)
    base_skill += min(preferred_skill_count / 8.0, 0.2)
    if has_assessment_score:
        base_skill *= (1.0 + avg_assessment_score / 200.0)
    base_skill *= clip(0.7 + skill_trust_score * 0.4, 0.7, 1.1)
    skill_score = clip(base_skill, 0.0, 1.0)

    # 3. Career Score
    career_at_product = features.get("career_at_product_company", False)
    consulting_only = features.get("consulting_only_career", False)
    if career_at_product and not consulting_only:
        career_score = 1.0
    elif consulting_only:
        career_score = 0.0
    else:
        career_score = 0.6

    # 4. Experience Score
    yoe = features.get("years_of_experience", 0.0)
    if exp_ideal_min <= yoe <= exp_ideal_max:
        exp_score = 1.0
    elif exp_good_min <= yoe <= exp_good_max:
        exp_score = 0.8
    elif exp_acceptable_min <= yoe <= exp_acceptable_max:
        exp_score = 0.5
    else:
        exp_score = 0.2

    # 5. Behavioral Score
    open_to_work_val = 0.15 if features.get("open_to_work") else 0.0
    
    days = features.get("days_since_active", 9999)
    if days < ACTIVE_DAYS_GREAT:
        act_val = 1.0
    elif days < ACTIVE_DAYS_GOOD:
        act_val = 0.7
    elif days < ACTIVE_DAYS_WEAK:
        act_val = 0.4
    else:
        act_val = 0.1
    days_val = 0.35 * act_val
    
    resp_val = 0.20 * features.get("recruiter_response_rate", 0.0)
    int_val = 0.15 * features.get("interview_completion_rate", 0.0)
    offer_val = 0.10 * features.get("offer_acceptance_rate", 0.5)
    github_val = 0.05 * (features.get("github_activity_score", 0.0) / 100.0)
    
    saved_count = features.get("saved_by_recruiters_30d", 0)
    saved_val = 0.15 * (clip(saved_count, 0, 20) / 20.0)
    
    behavioral_score = open_to_work_val + days_val + resp_val + int_val + offer_val + github_val + saved_val

    # 6. Location Score
    is_pref = features.get("is_preferred_city", False)
    is_t1 = features.get("is_tier1_india_city", False)
    is_india = features.get("is_india_based", False)
    willing_reloc = features.get("willing_to_relocate", False)

    if is_pref:
        location_score = 1.0
    elif is_t1:
        location_score = 0.85
    elif is_india:
        location_score = 0.6
    elif willing_reloc:
        location_score = 0.35
    else:
        location_score = 0.1

    # 7. Notice Score
    notice_days = features.get("notice_period_days", 0)
    if notice_days <= NOTICE_IDEAL:
        notice_score = 1.0
    elif notice_days <= NOTICE_OK:
        notice_score = 0.7
    elif notice_days <= NOTICE_WEAK:
        notice_score = 0.4
    else:
        notice_score = 0.2

    # 8. Trust Score
    verified_val = 1.0 if features.get("verified_both") else 0.0
    linkedin_val = 1.0 if features.get("linkedin_connected") else 0.0
    completeness_val = features.get("profile_completeness", 0.0) / 100.0
    trust_score = (verified_val + linkedin_val + completeness_val) / 3.0

    # Weighted sum calculation
    weighted_sum = (
        title_score * weights["title"] +
        skill_score * weights["skill"] +
        career_score * weights["career"] +
        exp_score * weights["experience"] +
        behavioral_score * weights["behavioral"] +
        location_score * weights["location"] +
        notice_score * weights["notice"] +
        trust_score * weights["trust"]
    )

    # Apply Disqualifier Multipliers
    mult = 1.0
    if features.get("is_honeypot"):
        mult *= DISQUALIFIER_MULTIPLIERS.get("is_honeypot", 0.0)
    if features.get("pure_research_only_flag"):
        mult *= DISQUALIFIER_MULTIPLIERS.get("pure_research_only_flag", 0.05)
    if features.get("title_chaser_flag"):
        mult *= DISQUALIFIER_MULTIPLIERS.get("title_chaser_flag", 0.7)
    if features.get("no_recent_production_code_flag"):
        mult *= DISQUALIFIER_MULTIPLIERS.get("no_recent_production_code_flag", 0.6)
    if features.get("has_cv_speech_without_nlp"):
        mult *= DISQUALIFIER_MULTIPLIERS.get("has_cv_speech_without_nlp", 0.5)

    final_score = clip(weighted_sum * mult, 0.0, 1.0)

    # Build reasoning text
    if career_at_product and not consulting_only:
        career_phrase = "product-company career"
    elif consulting_only:
        career_phrase = "consulting-only career"
    else:
        career_phrase = "mixed product/consulting career"

    # Match reasoning keywords
    role_name = job_spec.get("role", "ai_engineer") if job_spec else "ai_engineer"
    skills_label = "core AI/ML skills" if role_name in ["ai_engineer", "ml_engineer"] else "core skills"

    reasoning = (
        f"{features.get('current_title', '')}, {yoe:.1f} yrs experience, "
        f"{core_skill_count} {skills_label}, {career_phrase}, "
        f"notice period {notice_days} days, active {days} days ago."
    )

    # Append disqualifier concerns
    concerns = []
    if features.get("is_honeypot"):
        reasons = features.get("honeypot_reasons", [])
        reason_str = reasons[0] if reasons else "unknown honeypot signature"
        concerns.append(f"flagged as a possible honeypot: {reason_str}")
    if features.get("pure_research_only_flag"):
        concerns.append("primarily pure-research career background")
    if features.get("title_chaser_flag"):
        concerns.append("title-chaser pattern in career history")
    if features.get("no_recent_production_code_flag"):
        concerns.append("no recent hands-on production code experience")
    if features.get("has_cv_speech_without_nlp"):
        concerns.append("primarily computer-vision/speech background without core NLP/IR exposure")

    if concerns:
        reasoning += " Concerns: " + "; ".join(concerns) + "."

    return {
        "score": final_score,
        "reasoning": reasoning
    }

def calculate_score(features: Dict[str, Any], jd_intent: Dict[str, Any] = None) -> float:
    """Helper function mapping to score_candidate score."""
    return score_candidate(features, jd_intent)["score"]

def rank_candidates(candidates_features: List[Dict[str, Any]], jd_intent: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Helper function to score and sort candidates."""
    scored = []
    for candidate in candidates_features:
        res = score_candidate(candidate, jd_intent)
        candidate_copy = candidate.copy()
        candidate_copy["score"] = res["score"]
        candidate_copy["reasoning"] = res["reasoning"]
        scored.append(candidate_copy)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
