"""
Centralized LLM Client Module.
Provides robust local Ollama and Groq cloud execution with model failover,
timeout control, JSON object parsing, and error recovery.
"""
import os
import re
import requests
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv(override=True)

def get_groq_api_key() -> str:
    """Retrieve and clean the Groq API key from environment."""
    return os.getenv("GROQ_API_KEY", "").strip().strip('"\'')

def get_groq_model() -> str:
    """Retrieve and sanitize the preferred Groq model name."""
    model = os.getenv("GROQ_MODEL", "").strip().strip('"\'')
    if not model or any(bad in model for bad in ["llama-3", "gemma2", "mixtral", "gpt-oss-120b"]):
        return "qwen/qwen3.8-27b"
    return model

def execute_llm(
    prompt: str,
    system_message: str = "You are a helpful AI assistant.",
    format_json: bool = False,
    temperature: float = 0.7,
    timeout: float = 25.0
) -> Optional[str]:
    """
    Executes AI completions using local Ollama if active, falling back to
    cloud Groq models (openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.6-27b).
    Handles JSON extraction and code markdown cleaning.
    """
    if format_json:
        if "json" not in system_message.lower():
            system_message = f"{system_message} You must respond with a valid JSON object only."
        if "json" not in prompt.lower():
            prompt = f"{prompt}\n\nPlease respond in valid JSON format."

    # 1. Primary AI Engine: Local Ollama (if running)
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:1b")
    ollama_payload = {
        "model": ollama_model,
        "prompt": f"{system_message}\n\n{prompt}",
        "stream": False,
        "options": {"temperature": temperature}
    }
    if format_json:
        ollama_payload["format"] = "json"
    
    urls_to_try = [
        os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
        "http://127.0.0.1:11434/api/generate"
    ]
    
    for u in list(dict.fromkeys(urls_to_try)):
        try:
            res = requests.post(u, json=ollama_payload, timeout=2.0)
            if res.status_code == 200:
                content = res.json().get("response", "").strip()
                if format_json:
                    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', content)
                    if match:
                        return match.group(0).strip()
                else:
                    if content.startswith("```html"): content = content[7:]
                    elif content.startswith("```json"): content = content[7:]
                    elif content.startswith("```"): content = content[3:]
                    if content.endswith("```"): content = content[:-3]
                if content:
                    return content.strip()
        except Exception:
            pass

    # 2. Cloud AI Engine: Groq
    api_key = get_groq_api_key()
    if api_key:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        preferred = get_groq_model()
        models_to_try = [preferred, "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "groq/compound-mini", "openai/gpt-oss-120b"]
        seen = set()
        deduped_models = [m for m in models_to_try if not (m in seen or seen.add(m))]
        for m in deduped_models:
            try:
                payload = {
                    "model": m,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 4096
                }
                if format_json:
                    payload["response_format"] = {"type": "json_object"}
                resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 400 and format_json and any(err_kw in resp.text for err_kw in ["validate JSON", "generate JSON", "failed_generation"]):
                    retry_payload = {k: v for k, v in payload.items() if k != "response_format"}
                    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=retry_payload, timeout=timeout)
                
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    if format_json:
                        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', content)
                        if match:
                            return match.group(0).strip()
                    else:
                        if content.startswith("```html"): content = content[7:]
                        elif content.startswith("```json"): content = content[7:]
                        elif content.startswith("```"): content = content[3:]
                        if content.endswith("```"): content = content[:-3]
                    return content.strip()
                else:
                    print(f"[NOTICE] Groq model {m} returned HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as groq_err:
                print(f"[NOTICE] Groq model {m} call error: {groq_err}")

    return None
