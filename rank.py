#!/usr/bin/env python3
import json
import csv
import os
import time
from pathlib import Path
from src.config import (
    CANDIDATES_FILE,
    SUBMISSION_FILE,
    RANKED_JSON_FILE,
    TOP_K,
    WEIGHTS
)
from src.feature_extractor import extract_features_for_candidate
from src.scorer import score_candidate
from src.submission_auditor import audit_submission

def main():
    print("Starting Redrob AI Candidate Ranking System...")
    start_time = time.time()

    # Make sure output directory exists
    os.makedirs(os.path.dirname(SUBMISSION_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(RANKED_JSON_FILE), exist_ok=True)

    if not os.path.exists(CANDIDATES_FILE):
        print(f"Error: Raw candidates file not found at {CANDIDATES_FILE}")
        return

    # 1 & 2. Load candidates and extract features
    print("Extracting features and scoring candidates...")
    candidates = []
    features_dict = {}

    count = 0
    with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            cand_raw = json.loads(line)
            count += 1
            if count % 10000 == 0:
                print(f"Processed {count} candidates...")
            
            # Extract features
            feats = extract_features_for_candidate(cand_raw)
            cid = feats["candidate_id"]
            features_dict[cid] = feats

            # Score candidate
            score_res = score_candidate(feats)
            
            # Keep trace of raw info needed for UI as well
            profile = cand_raw.get("profile") or {}
            redrob_signals = cand_raw.get("redrob_signals") or {}
            
            candidates.append({
                "candidate_id": cid,
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
                "features": feats
            })

    print(f"Total profiles read: {count}")

    # 3. Sort candidates by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 4. Save results to submission.csv and ranked_candidates.json
    print(f"Saving top {TOP_K} to submission.csv...")
    top_k_candidates = candidates[:TOP_K]

    # Write submission.csv
    with open(SUBMISSION_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "score", "reasoning"])
        for c in top_k_candidates:
            writer.writerow([c["candidate_id"], f"{c['score']:.4f}", c["reasoning"]])

    # Write ranked_candidates.json for dashboard
    # Add ranking index to the list
    for idx, c in enumerate(candidates):
        c["rank"] = idx + 1
        
        # Calculate risk indicator
        feats = c["features"]
        is_hp = feats.get("is_honeypot", False)
        hp_reasons = feats.get("honeypot_reasons", [])
        
        # Risk assessment mapping
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

        # Assign high-quality avatars or fallback placeholder avatars
        c["image"] = f"https://api.dicebear.com/7.x/adventurer/svg?seed={c['candidate_id']}"

    # Save only the top 100 for the dashboard to keep the view highly responsive and clean
    with open(RANKED_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates[:TOP_K], f, indent=2)

    print(f"Saved ranked candidates to {RANKED_JSON_FILE}")

    # 5. Audit the final outputs
    print("Running compliance audit...")
    audit_submission(SUBMISSION_FILE, features_dict)

    elapsed_time = time.time() - start_time
    print(f"Ranking process completed in {elapsed_time:.2f} seconds.")

if __name__ == "__main__":
    main()
