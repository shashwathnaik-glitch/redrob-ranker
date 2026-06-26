# -- File paths --------------------------------------------------------
DATA_DIR              = "data/raw"
PROCESSED_DIR         = "data/processed"
CANDIDATES_FILE       = "data/raw/candidates.jsonl"
JD_INTENT_FILE        = "data/processed/jd_intent.json"
FEATURES_FILE         = "data/processed/features.jsonl"
SUBMISSION_FILE       = "outputs/submission.csv"
RANKED_JSON_FILE      = "outputs/ranked_candidates.json"

# -- Submission constraints ---------------------------------------------
TOP_K                 = 100
MAX_RUNTIME_SECONDS   = 280        # 280s budget, hard limit is 300s
HONEYPOT_MAX_RATE     = 0.10       # >10% honeypots in top-100 = disqualified
TODAY                 = "2026-06-20"   # fixed reference date for all date-delta math

# -- Scoring weights (must sum to 1.0) -----------------------------------
WEIGHTS = {
    "title":       0.20,
    "skill":       0.22,
    "career":      0.18,
    "experience":  0.12,
    "behavioral":  0.10,
    "location":    0.08,
    "notice":      0.06,
    "trust":       0.04,
}

# -- Disqualifier multipliers, applied after the weighted sum -----------
DISQUALIFIER_MULTIPLIERS = {
    "is_honeypot":                     0.0,
    "pure_research_only_flag":         0.05,
    "title_chaser_flag":               0.7,
    "no_recent_production_code_flag":  0.6,
    "has_cv_speech_without_nlp":       0.5,
}

# -- Experience bands -----------------------------------------------------
EXP_IDEAL_MIN         = 5
EXP_IDEAL_MAX         = 9
EXP_GOOD_MIN          = 4
EXP_GOOD_MAX          = 10
EXP_ACCEPTABLE_MIN    = 3
EXP_ACCEPTABLE_MAX    = 12

# -- Behavioral thresholds -------------------------------------------------
ACTIVE_DAYS_GREAT     = 30
ACTIVE_DAYS_GOOD      = 90
ACTIVE_DAYS_WEAK       = 180
RESPONSE_RATE_MIN     = 0.15
INTERVIEW_RATE_MIN    = 0.50

# -- Notice period bands (JD: sub-30 ideal, 30+ "in scope, bar higher") ----
NOTICE_IDEAL          = 30
NOTICE_OK             = 60
NOTICE_WEAK           = 90

# -- Location ---------------------------------------------------------------
PREFERRED_CITIES = ["pune", "noida"]
TIER1_INDIA_CITIES = [
    "pune", "noida", "hyderabad", "mumbai", "delhi", "ncr",
    "gurgaon", "gurugram", "new delhi",
]
VISA_SPONSORSHIP_AVAILABLE = False

# -- Skill tiers (JD's "skills inventory" section, read literally) ----------
# CORE: production retrieval, vector/hybrid search infra, ranking + evaluation.
# These are what the JD calls "things you absolutely need." Heavily weighted.
CORE_NLP_IR_SKILLS = [
    "sentence-transformers", "sentence transformers", "embeddings", "embedding",
    "bge", "e5", "openai embeddings",
    "vector search", "vector database", "faiss", "qdrant", "pinecone",
    "weaviate", "milvus", "opensearch", "elasticsearch",
    "rag", "retrieval augmented generation", "retrieval-augmented",
    "information retrieval", "bm25", "hybrid search", "dense retrieval",
    "sparse retrieval", "semantic search", "cross-encoder", "bi-encoder",
    "nlp", "natural language processing", "bert", "gpt", "transformers",
    "hugging face", "huggingface",
    "ndcg", "mrr", "map", "learning to rank", "lambdamart", "ltr",
    "ranking", "reranking", "recommendation system", "recommender",
    "a/b testing", "evaluation framework", "python",
]

# PREFERRED: "things we'd like you to have but won't reject you for." Light weight.
PREFERRED_SKILLS = [
    "lora", "qlora", "peft", "fine-tuning", "fine tuning",
    "xgboost", "distributed systems", "large-scale inference",
    "open source", "open-source",
]

# ADJACENT_NOT_CORE: the JD explicitly says CV/speech/robotics WITHOUT NLP/IR
# exposure is not a fit. Never reward these alone as AI/ML signal.
ADJACENT_NOT_CORE_SKILLS = [
    "computer vision", "image classification", "object detection", "yolo",
    "gans", "diffusion models", "speech recognition", "tts", "asr", "robotics",
]

# -- Title keyword groups -----------------------------------------------------
TITLE_AI_ML = [
    "ai engineer", "ml engineer", "machine learning engineer", "nlp engineer",
    "search engineer", "ranking engineer", "recommendation engineer",
    "applied scientist", "ml platform", "llm engineer", "research scientist",
    "data scientist", "ml scientist", "ai researcher", "conversational ai",
]
TITLE_ADJACENT = [
    "data engineer", "software engineer", "backend engineer",
    "platform engineer", "full stack", "cloud engineer",
    "mlops", "devops", "site reliability", "data analyst",
]
TITLE_UNRELATED = [
    "marketing", "hr ", "human resource", "sales", "finance",
    "accountant", "mechanical", "civil", "operations manager",
    "business analyst", "content writer", "graphic designer",
    "supply chain", "logistics", "legal", "compliance", "customer support",
]

# -- Consulting firms (JD: fine if CURRENT employer, bad if ENTIRE career) ----
CONSULTING_FIRMS = [
    "tcs", "tata consultancy", "infosys", "wipro", "accenture",
    "cognizant", "capgemini", "hcl", "hcl technologies",
    "tech mahindra", "mphasis", "hexaware", "l&t infotech",
    "ltimindtree", "mindtree", "persistent systems", "niit technologies",
]

# -- Industries treated as "pure research" for the hard-disqualifier check ----
RESEARCH_ONLY_INDUSTRIES = ["research", "academia", "education"]

# -- Honeypot detection thresholds (validated against real sample data) -------
HONEYPOT_EXPERT_ZERO_SKILLS_MIN = 3     # >=3 expert skills with 0 months = flag
HONEYPOT_CAREER_MONTHS_EXCESS   = 36    # career months > YOE months + 36 = flag
