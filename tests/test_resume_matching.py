import pytest
from utils.analyzer import extract_skills, calculate_ml_match, normalize_skill_name, get_missing_skills

def test_skill_extraction_and_alias_normalization():
    sample_text = "I am an experienced Python engineer specializing in Postgres, Docker, Fast API, and JS."
    skills = extract_skills(sample_text)
    
    assert "python" in skills
    assert "postgresql" in skills  # Normalized from 'Postgres'
    assert "fastapi" in skills     # Normalized from 'Fast API'
    assert "javascript" in skills  # Normalized from 'JS'
    assert "docker" in skills

def test_tfidf_similarity_scoring():
    resume = "Senior Python developer with experience building FastAPI REST APIs and PostgreSQL databases."
    job_desc = "Looking for a Python developer proficient in FastAPI and Postgres database design."
    
    score = calculate_ml_match(resume, job_desc)
    assert score > 15.0  # TF-IDF similarity score expected

def test_missing_skills_calculation():
    resume_skills = ["python", "fastapi"]
    job_skills = ["python", "fastapi", "docker", "aws"]
    
    missing = get_missing_skills(resume_skills, job_skills)
    assert "docker" in missing
    assert "aws" in missing
    assert "python" not in missing
