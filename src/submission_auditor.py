import csv
from pathlib import Path
from typing import Dict, Any
from src.config import HONEYPOT_MAX_RATE

def audit_submission(csv_path: str, features: Dict[str, Dict[str, Any]]) -> None:
    """
    Audits the generated submission.csv file against extracted features and 
    displays stats on honeypots, consulting, and disqualifier flags.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"Auditor Error: CSV file {csv_path} does not exist.")
        return
        
    top_100_ids = []
    top_100_scores = []
    
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = row.get("candidate_id")
                # Fallback search if header casing varies
                if not cid:
                    for k, v in row.items():
                        if k and k.lower() in ("candidate_id", "id"):
                            cid = v
                            break
                if cid:
                    top_100_ids.append(cid)
                    
                score_str = row.get("score")
                if score_str:
                    try:
                        top_100_scores.append(float(score_str))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Auditor Error: Failed to parse CSV: {e}")
        return

    print("=== SUBMISSION AUDIT REPORT ===")
    print(f"Total candidates in CSV: {len(top_100_ids)}")
    
    # Audit top 100 records
    audit_ids = top_100_ids[:100]
    audit_scores = top_100_scores[:100]
    
    honeypot_count = 0
    consulting_only_count = 0
    disqualifier_flags_count = 0
    core_skills_sum_10 = 0.0
    core_skills_sum_100 = 0.0
    
    for idx, cid in enumerate(audit_ids):
        # Look up candidate features
        feat = features.get(cid)
        if not feat:
            # Fallback if key format varies (e.g. integer vs string)
            for k, v in features.items():
                if str(k).strip() == str(cid).strip():
                    feat = v
                    break
                    
        if not feat:
            continue
            
        # 1. Honeypots
        if feat.get("is_honeypot"):
            honeypot_count += 1
            
        # 2. Consulting only
        if feat.get("consulting_only_career"):
            consulting_only_count += 1
            
        # 3. Disqualifiers
        dq_triggered = (
            feat.get("is_honeypot") or 
            feat.get("pure_research_only_flag") or 
            feat.get("title_chaser_flag") or 
            feat.get("no_recent_production_code_flag") or 
            feat.get("has_cv_speech_without_nlp")
        )
        if dq_triggered:
            disqualifier_flags_count += 1
            
        # 4. Core skill count average
        core_skills = float(feat.get("core_skill_count", 0) or 0)
        core_skills_sum_100 += core_skills
        if idx < 10:
            core_skills_sum_10 += core_skills
            
    honeypot_rate = honeypot_count / max(len(audit_ids), 1)
    avg_core_skills_10 = core_skills_sum_10 / max(min(len(audit_ids), 10), 1)
    avg_core_skills_100 = core_skills_sum_100 / max(len(audit_ids), 1)
    
    min_score = min(audit_scores) if audit_scores else 0.0
    max_score = max(audit_scores) if audit_scores else 0.0
    
    print(f"Honeypot Count: {honeypot_count} / {len(audit_ids)}")
    print(f"Honeypot Rate: {honeypot_rate:.2%} (Max Allowed: {HONEYPOT_MAX_RATE:.2%})")
    if honeypot_rate > HONEYPOT_MAX_RATE:
        print(">>> WARNING: Honeypot rate is above the maximum allowed limit! <<<")
    else:
        print("Honeypot rate is within safe limits.")
        
    print(f"Consulting-only Career Count: {consulting_only_count} / {len(audit_ids)}")
    print(f"Score Range: [{min_score:.4f}, {max_score:.4f}]")
    print(f"Average Core Skill Count (Top 10): {avg_core_skills_10:.2f}")
    print(f"Average Core Skill Count (Top 100): {avg_core_skills_100:.2f}")
    print(f"Total candidates with any disqualifier flag: {disqualifier_flags_count} / {len(audit_ids)}")
    print("===============================")
