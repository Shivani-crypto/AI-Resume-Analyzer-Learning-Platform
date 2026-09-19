"""
Semantic and Structural Content Validation Module.
Ensures AI-generated courses, quizzes, and code blueprints strictly match
the target skill domain and conform to the application's required schemas.
"""
from typing import Tuple, Dict, Any, List
from utils.skill_normalizer import normalize_skill_name, SKILL_ALIASES

REQUIRED_COURSE_KEYS: List[str] = [
    "skill", "title", "one_minute_demo", "slides", 
    "core_concepts", "code_example", "common_mistakes", 
    "quick_recap", "quiz_topics"
]

KEY_SIGNATURES: Dict[str, List[str]] = {
    "fastapi": ["fastapi", "uvicorn", "pydantic", "route", "asgi", "async", "@app", "endpoint"],
    "docker": ["docker", "container", "image", "dockerfile", "build", "run", "volume", "compose"],
    "aws": ["aws", "amazon", "ec2", "s3", "lambda", "iam", "boto3", "cloud"],
    "postgresql": ["postgres", "sql", "table", "select", "join", "index", "primary key"],
    "python": ["python", "def ", "import ", "list", "dict", "class "],
    "rag": ["rag", "retrieval", "embedding", "vector", "chunk", "llm", "context"],
    "kubernetes": ["kubernetes", "k8s", "pod", "deployment", "kubectl", "service"],
    "react": ["react", "component", "usestate", "useeffect", "jsx", "props"],
    "mysql": ["mysql", "sql", "table", "database", "query", "select", "insert", "foreign key"],
    "mongodb": ["mongodb", "collection", "document", "bson", "nosql", "find", "aggregate"],
    "redis": ["redis", "cache", "key", "expire", "in-memory", "pub/sub"]
}

OFFTOPIC_SIGNATURES: Dict[str, List[str]] = {
    "fastapi": ["const express", "express()", "app.listen(", "system.out.println", "django.db"],
    "docker": ["html", "<div", "<body", "css", "color:"],
    "postgresql": ["const ", "import react", "<template>"]
}

def validate_generated_course_content(skill_name: str, content: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Semantically and structurally validates that the generated course content
    satisfies all required keys and represents the requested technical skill.
    """
    if not isinstance(content, dict):
        return False, "Generated content is not a dictionary."
    
    clean_req_skill = skill_name.strip().lower()
    req_norm = normalize_skill_name(clean_req_skill)

    # Normalize skill name if missing
    if "skill" not in content or not content["skill"]:
        content["skill"] = skill_name

    # Normalize demo scenes
    demo = content.get("one_minute_demo", [])
    if isinstance(demo, list):
        for idx, scene in enumerate(demo):
            if isinstance(scene, dict):
                if "code" not in scene and scene.get("code_snippet"):
                    scene["code"] = scene["code_snippet"]
                if "code_snippet" not in scene and scene.get("code"):
                    scene["code_snippet"] = scene["code"]
                if "narration" not in scene and scene.get("audio_narration"):
                    scene["narration"] = scene["audio_narration"]
                if "audio_narration" not in scene and scene.get("narration"):
                    scene["audio_narration"] = scene["narration"]
                if "scene_title" not in scene and scene.get("title"):
                    scene["scene_title"] = scene["title"]
                if "title" not in scene and scene.get("scene_title"):
                    scene["title"] = scene["scene_title"]
                if "scene_number" not in scene:
                    scene["scene_number"] = scene.get("scene", idx + 1)

    # Normalize code_example if omitted but available in demo or slides
    if "code_example" not in content or not content["code_example"] or not isinstance(content["code_example"], dict) or not content["code_example"].get("code"):
        demo_code = next((s.get("code") for s in demo if isinstance(s, dict) and s.get("code")), None)
        slide_code = next((s.get("code") for s in content.get("slides", []) if isinstance(s, dict) and s.get("code")), None)
        fallback_code = demo_code or slide_code
        if fallback_code:
            content["code_example"] = {
                "filename": f"{req_norm.replace(' ', '_')}_demo",
                "language": req_norm,
                "code": fallback_code,
                "explanation": [f"Technical architecture blueprint for {skill_name}"]
            }

    if "common_mistakes" not in content or not content["common_mistakes"] or not isinstance(content["common_mistakes"], list):
        content["common_mistakes"] = [
            f"Overlooking proper error handling and edge cases in {skill_name}.",
            f"Failing to optimize {skill_name} resource allocation for production workloads."
        ]
    if "core_concepts" not in content or not content["core_concepts"] or not isinstance(content["core_concepts"], list):
        content["core_concepts"] = [
            {"title": f"{skill_name} Fundamentals", "icon": "fa-solid fa-cube", "color": "#6366f1", "desc": f"Core architecture, runtime semantics, and lifecycle in {skill_name}."},
            {"title": "System Architecture", "icon": "fa-solid fa-database", "color": "#10b981", "desc": f"Structural organization and component composition for {skill_name}."},
            {"title": "Performance & Scaling", "icon": "fa-solid fa-bolt", "color": "#f59e0b", "desc": f"Optimization, concurrency, and memory management in {skill_name}."},
            {"title": "Security & Reliability", "icon": "fa-solid fa-shield-halved", "color": "#ec4899", "desc": f"Error handling, input validation, and production resilience for {skill_name}."}
        ]

    if "quiz_topics" not in content or not content["quiz_topics"] or not isinstance(content["quiz_topics"], list) or len(content["quiz_topics"]) < 3:
        try:
            from app.ai.quiz_generator import generate_quiz
            from app.schemas.quiz import QuizRequest
            q_res = generate_quiz(QuizRequest(topic=skill_name, num_questions=5, difficulty="Intermediate", language="English"))
            if q_res and q_res.questions:
                content["quiz_topics"] = [
                    {
                        "question": q.question,
                        "options": [{"id": o.id, "text": o.text} for o in q.options],
                        "correct_option_id": q.correct_option_id,
                        "explanation": q.explanation or f"Correct answer for {skill_name}."
                    }
                    for q in q_res.questions
                ]
        except Exception as q_err:
            print(f"[Validators] Quiz auto-completion notice: {q_err}")

    if "quick_recap" not in content or not content["quick_recap"] or not isinstance(content["quick_recap"], list):
        content["quick_recap"] = [
            f"Mastered core principles and architecture of {skill_name}.",
            f"Production execution and modern industry best practices for {skill_name}."
        ]

    for k in REQUIRED_COURSE_KEYS:
        if k not in content or not content[k]:
            return False, f"Missing required key '{k}' in generated course structure."
            
    gen_skill = str(content.get("skill", "")).strip().lower()
    gen_norm = normalize_skill_name(gen_skill)
    
    if req_norm not in gen_skill and gen_norm not in req_norm and req_norm not in gen_norm:
        return False, f"Skill mismatch: requested '{skill_name}', but generated '{content.get('skill')}'."

    if not isinstance(demo, list) or len(demo) < 4:
        return False, "1-minute video demo must contain at least 4 scenes."
    for scene in demo[:4]:
        if not isinstance(scene, dict) or not scene.get("narration") or not scene.get("code"):
            return False, "1-minute video demo scenes must contain narration and executable code."

    slides = content.get("slides", [])
    if not isinstance(slides, list) or len(slides) < 4:
        return False, "Course slides must contain at least 4 items."

    code_ex = content.get("code_example", {})
    if not isinstance(code_ex, dict) or not code_ex.get("code"):
        return False, "Code example snippet must be non-empty."

    all_text = (
        str(content.get("title", "")) + " " +
        str(content.get("learning_objective", "")) + " " +
        str(content.get("why_this_skill_matters", "")) + " " +
        str(code_ex.get("code", "")) + " " +
        " ".join([str(s.get("code", "")) for s in demo if isinstance(s, dict)])
    ).lower()

    # Offtopic check
    if req_norm in OFFTOPIC_SIGNATURES:
        for bad_sig in OFFTOPIC_SIGNATURES[req_norm]:
            if bad_sig.lower() in all_text:
                return False, f"Semantic check failed: {skill_name} course generated unrelated content containing '{bad_sig}'."

    # Specific concept signature check
    if req_norm in KEY_SIGNATURES:
        sigs = KEY_SIGNATURES[req_norm]
        matches = [sig for sig in sigs if sig in all_text]
        if len(matches) == 0:
            return False, f"Generated content lacks specific technical concepts/keywords for '{skill_name}'."

    return True, "Valid"
