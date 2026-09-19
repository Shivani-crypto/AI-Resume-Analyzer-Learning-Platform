"""
Centralized Skill Normalization & Extraction Module.
Maintains canonical skill taxonomies, aliases, and normalization routines.
"""
import re
from typing import List, Set, Dict

# Predefined skill database
SKILLS_DB: List[str] = [
    "python", "java", "c", "c++", "sql", "mysql", "postgresql", "mongodb", "nosql",
    "flask", "django", "fastapi", "html", "css", "javascript", "typescript",
    "react", "node", "express", "angular", "vue", "next.js", "pandas", "numpy", "machine learning", "ml", "ai",
    "deep learning", "tensorflow", "keras", "pytorch", "api", "golang", "go", "rust",
    "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux", "flutter", "dart",
    "swift", "kotlin", "android", "ios", "react native", "php", "ruby", "rails",
    "oracle", "pl/sql", "plsql", "soa", "osb", "bpel", "xml", "xsd", "xslt", "xpath",
    "xquery", "wsdl", "soap", "rest", "restful", "j2ee", "unix", "shell", "bpm", "owsm", "sap",
    "rag", "graphql", "redis", "kafka", "snowflake", "spark", "hadoop", "devops", "ci/cd", "terraform"
]

# Aliases mapped to canonical skill names
SKILL_ALIASES: Dict[str, str] = {
    "postgres": "postgresql",
    "postgres sql": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node",
    "node.js": "node",
    "expressjs": "express",
    "express.js": "express",
    "vuejs": "vue",
    "vue.js": "vue",
    "angularjs": "angular",
    "py": "python",
    "python3": "python",
    "fast api": "fastapi",
    "nextjs": "next.js",
    "amazon web services": "aws",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "k8s": "kubernetes",
    "retrieval augmented generation": "rag",
    "retrieval-augmented generation": "rag",
    "mongo": "mongodb",
    "ror": "rails"
}

def normalize_skill_name(s: str) -> str:
    """Normalize skill name string to its canonical lowercase equivalent."""
    if not s:
        return ""
    cleaned = s.strip().lower()
    return SKILL_ALIASES.get(cleaned, cleaned)

def extract_skills(text: str) -> List[str]:
    """Extract and normalize all recognized skills from a body of text."""
    if not text:
        return []
    text_lower = text.lower()
    found_skills: Set[str] = set()

    for skill in SKILLS_DB:
        if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
            found_skills.add(normalize_skill_name(skill))
            
    for alias, main_skill in SKILL_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", text_lower):
            found_skills.add(main_skill)
            
    return sorted(list(found_skills))

def get_missing_skills(resume_skills: List[str], job_skills: List[str]) -> List[str]:
    """Identify skills present in the job requirements but missing from the resume."""
    norm_resume = {normalize_skill_name(s) for s in resume_skills if s}
    missing = []
    for skill in job_skills:
        if not skill:
            continue
        norm_s = normalize_skill_name(skill)
        if norm_s not in norm_resume:
            missing.append(skill.strip())
    return missing
