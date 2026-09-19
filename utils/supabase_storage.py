import os
import mimetypes
import requests
from typing import Optional, Union
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".m4v"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".csv", ".json"}

def resolve_bucket_name(filename_or_path: str, content_type: str = "") -> str:
    """
    Infers the target Supabase storage bucket based on filename extension and content type.
    Options: 'images', 'videos', 'files', 'certificates'
    """
    clean_path = str(filename_or_path).lower()
    ext = os.path.splitext(clean_path)[1]
    
    if "cert" in clean_path or "certificate" in clean_path:
        return "certificates"
    if ext in IMAGE_EXTENSIONS or (content_type and content_type.startswith("image/")):
        return "images"
    if ext in VIDEO_EXTENSIONS or (content_type and content_type.startswith("video/")):
        return "videos"
    return "files"

def ensure_bucket_exists(supabase_url: str, supabase_key: str, bucket_name: str) -> bool:
    """
    Ensures a public bucket exists on Supabase; creates it if missing.
    """
    try:
        create_url = f"{supabase_url}/storage/v1/bucket"
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "apiKey": supabase_key,
            "Content-Type": "application/json"
        }
        res = requests.post(create_url, headers=headers, json={"id": bucket_name, "name": bucket_name, "public": True}, timeout=15)
        return res.status_code in (200, 201) or "already exists" in res.text.lower()
    except Exception as e:
        print(f"[Supabase Storage] Notice checking/creating bucket '{bucket_name}': {e}")
        return False

def upload_file_to_supabase(
    file_path_or_bytes: Union[str, bytes, Path, any], 
    bucket_name: Optional[str] = None, 
    destination_path: str = "", 
    content_type: Optional[str] = None
) -> str:
    """
    Uploads a file, bytes, or FastAPI UploadFile to a Supabase Storage bucket via REST API.
    Returns the public/accessible URL of the uploaded file on Supabase.
    If Supabase is not configured or offline, returns empty string for local fallback.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or 
        os.getenv("SUPABASE_KEY", "").strip() or 
        os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    
    if not supabase_url or not supabase_key:
        print("[Supabase Storage] SUPABASE_URL or SUPABASE_KEY not configured. Using local fallback.")
        return ""

    # Extract raw data and determine filename/content_type
    file_data = b""
    filename_hint = ""

    # Check if file_path_or_bytes is a FastAPI/Starlette UploadFile
    if hasattr(file_path_or_bytes, "file") and hasattr(file_path_or_bytes, "filename"):
        filename_hint = file_path_or_bytes.filename or "upload"
        try:
            file_path_or_bytes.file.seek(0)
            file_data = file_path_or_bytes.file.read()
            file_path_or_bytes.file.seek(0)
        except Exception:
            file_data = b""
        if not content_type and hasattr(file_path_or_bytes, "content_type") and file_path_or_bytes.content_type:
            content_type = file_path_or_bytes.content_type
    elif isinstance(file_path_or_bytes, (str, Path, os.PathLike)):
        str_path = str(file_path_or_bytes)
        filename_hint = os.path.basename(str_path)
        if os.path.exists(str_path):
            with open(str_path, "rb") as f:
                file_data = f.read()
        else:
            print(f"[Supabase Storage] File path not found: {str_path}")
            return ""
    elif isinstance(file_path_or_bytes, bytes):
        file_data = file_path_or_bytes
        filename_hint = "binary_file"
    else:
        print(f"[Supabase Storage] Unsupported file type: {type(file_path_or_bytes)}")
        return ""

    if not file_data:
        print("[Supabase Storage] Warning: File data is empty.")
        return ""

    # Infer content type if not provided
    if not content_type and filename_hint:
        guessed_type, _ = mimetypes.guess_type(filename_hint)
        content_type = guessed_type or "application/octet-stream"
    elif not content_type:
        content_type = "application/octet-stream"

    # Infer bucket if not provided
    if not bucket_name:
        bucket_name = resolve_bucket_name(destination_path or filename_hint, content_type)

    if not destination_path:
        destination_path = filename_hint or "file_upload"

    destination_path = destination_path.lstrip("/")

    try:
        endpoint = f"{supabase_url}/storage/v1/object/{bucket_name}/{destination_path}"
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "apiKey": supabase_key,
            "x-upsert": "true",
            "Content-Type": content_type
        }

        response = requests.post(endpoint, headers=headers, data=file_data, timeout=30)

        if response.status_code in (200, 201):
            public_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{destination_path}"
            print(f"[Supabase Storage] Uploaded to {public_url}")
            return public_url
        elif response.status_code in (404, 400) and ("not found" in response.text.lower() or "nosuchbucket" in response.text.lower()):
            # Auto-create bucket if missing
            ensure_bucket_exists(supabase_url, supabase_key, bucket_name)
            
            # Retry upload
            retry_res = requests.post(endpoint, headers=headers, data=file_data, timeout=30)
            if retry_res.status_code in (200, 201):
                public_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{destination_path}"
                print(f"[Supabase Storage] Uploaded (After Bucket Creation) to {public_url}")
                return public_url
            else:
                print(f"[Supabase Storage] Retry failed ({retry_res.status_code}): {retry_res.text}")
        else:
            print(f"[Supabase Storage] Upload notice ({response.status_code}): {response.text}")
    except Exception as err:
        print(f"[Supabase Storage] Exception uploading to {bucket_name}: {err}")

    return ""

def upload_image_to_supabase(file_obj, destination_path: str = "") -> str:
    """Uploads an image file to the 'images' Supabase bucket."""
    return upload_file_to_supabase(file_obj, bucket_name="images", destination_path=destination_path)

def upload_video_to_supabase(file_obj, destination_path: str = "") -> str:
    """Uploads a video file to the 'videos' Supabase bucket."""
    return upload_file_to_supabase(file_obj, bucket_name="videos", destination_path=destination_path)

def upload_document_to_supabase(file_obj, destination_path: str = "") -> str:
    """Uploads a document file to the 'files' Supabase bucket."""
    return upload_file_to_supabase(file_obj, bucket_name="files", destination_path=destination_path)

def upload_certificate_to_supabase(file_obj, destination_path: str = "") -> str:
    """Uploads a certificate file to the 'certificates' Supabase bucket."""
    return upload_file_to_supabase(file_obj, bucket_name="certificates", destination_path=destination_path)

def get_supabase_file_url(bucket_name: str, destination_path: str) -> str:
    """Returns the direct public URL for a file in a public Supabase bucket."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not supabase_url:
        return ""
    clean_path = destination_path.lstrip("/")
    return f"{supabase_url}/storage/v1/object/public/{bucket_name}/{clean_path}"

def delete_supabase_file(bucket_name: str, destination_path: str) -> bool:
    """Deletes a file from Supabase storage."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or 
        os.getenv("SUPABASE_KEY", "").strip() or 
        os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    if not supabase_url or not supabase_key:
        return False
    try:
        clean_path = destination_path.lstrip("/")
        url = f"{supabase_url}/storage/v1/object/{bucket_name}/{clean_path}"
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "apiKey": supabase_key
        }
        res = requests.delete(url, headers=headers, timeout=15)
        return res.status_code in (200, 204)
    except Exception as e:
        print(f"[Supabase Storage] Delete error: {e}")
        return False
