import json
from pathlib import Path
from typing import Dict, Any
from .config import JD_INTENT_FILE

def get_available_roles() -> Dict[str, Path]:
    """
    Scans the directory of JD_INTENT_FILE to discover available job specifications.
    """
    jd_file_path = Path(JD_INTENT_FILE)
    jd_dir = jd_file_path.parent
    
    roles = {}
    
    # Always ensure 'ai_engineer' is supported as the default/fallback
    roles["ai_engineer"] = jd_dir / "ai_engineer.json"
    
    if jd_dir.exists():
        for file in jd_dir.glob("*.json"):
            if file.name == "jd_intent.json":
                # jd_intent.json is the legacy fallback for ai_engineer
                continue
            role_name = file.stem.lower().strip()
            roles[role_name] = file
            
    return roles

def load_job_spec(role: str = "ai_engineer") -> Dict[str, Any]:
    """
    Loads a job description specification JSON based on a supplied role name.
    """
    if role is None:
        role = "ai_engineer"
        
    role_key = role.lower().strip()
    
    roles_map = get_available_roles()
    
    if role_key not in roles_map:
        available_roles = ", ".join(sorted(roles_map.keys()))
        raise ValueError(
            f"Unsupported role '{role}'. Available roles are: {available_roles}"
        )
        
    file_path = roles_map[role_key]
    
    # Backward compatibility fallback for ai_engineer
    if role_key == "ai_engineer" and not file_path.exists():
        fallback_path = Path(JD_INTENT_FILE)
        if fallback_path.exists():
            file_path = fallback_path
            
    if not file_path.exists():
        if role_key == "ai_engineer":
            # Return empty dict for backwards compatibility if both files are missing
            return {}
        raise FileNotFoundError(
            f"Specification file for role '{role}' not found at {file_path.absolute()}."
        )
        
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_jd_intent(file_path: Path = None) -> Dict[str, Any]:
    """
    Loads the parsed job description intent from a JSON file.
    Preserves original signature and behavior.
    """
    if file_path is not None:
        if not file_path.exists():
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return load_job_spec("ai_engineer")
