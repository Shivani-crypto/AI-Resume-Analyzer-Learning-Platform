import os
import uuid
import shutil
from typing import Optional, Union
from fastapi import UploadFile

from utils.supabase_storage import (
    upload_file_to_supabase,
    get_supabase_file_url,
    delete_supabase_file
)

STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

class StorageService:
    @staticmethod
    def get_provider() -> str:
        prov = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
        if prov in ("supabase", "cloud") and os.getenv("SUPABASE_URL"):
            return "supabase"
        if prov in ("aws", "s3", "aws_s3") and S3_BUCKET_NAME:
            return "s3"
        return "local"

    @classmethod
    def upload_video(cls, file: Union[UploadFile, bytes], lesson_id: int) -> str:
        """
        Uploads a lesson video and returns a browser-accessible URL.
        Guarantees URLs are web-accessible (e.g., /uploads/videos/lesson_2_xxx.mp4 or Supabase URL).
        Never returns server OS paths like C:\\...
        """
        ext = ".mp4"
        filename = "video.mp4"
        if hasattr(file, "filename") and file.filename:
            filename = file.filename
            ext = os.path.splitext(filename)[1].lower() or ".mp4"

        safe_name = f"lesson_{lesson_id}_{uuid.uuid4().hex[:8]}{ext}"
        provider = cls.get_provider()

        # 1. Supabase Storage Provider
        if provider == "supabase":
            try:
                if hasattr(file, "file"):
                    file.file.seek(0)
                dest = f"videos/{safe_name}"
                c_type = getattr(file, "content_type", "video/mp4") or "video/mp4"
                url = upload_file_to_supabase(file, bucket_name="videos", destination_path=dest, content_type=c_type)
                if hasattr(file, "file"):
                    file.file.seek(0)
                if url:
                    print(f"[STORAGE] Uploaded video for lesson #{lesson_id} to Supabase: {url}")
                    return url
            except Exception as sb_err:
                print(f"[STORAGE] Supabase video upload error: {sb_err}")

        # 2. AWS S3 Provider
        if provider == "s3":
            try:
                s3_client = get_s3_client()
                if s3_client and hasattr(file, "file"):
                    file.file.seek(0)
                    dest = f"videos/{safe_name}"
                    s3_client.upload_fileobj(
                        file.file,
                        S3_BUCKET_NAME,
                        dest,
                        ExtraArgs={"ContentType": getattr(file, "content_type", "video/mp4")}
                    )
                    file.file.seek(0)
                    s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{dest}"
                    print(f"[STORAGE] Uploaded video for lesson #{lesson_id} to S3: {s3_url}")
                    return s3_url
            except Exception as s3_err:
                print(f"[STORAGE] S3 video upload error: {s3_err}")

        # 3. Local Storage (Guaranteed)
        local_dir = os.path.join("uploads", "videos")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, safe_name)

        if hasattr(file, "file"):
            file.file.seek(0)
            with open(local_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file.file.seek(0)
        elif isinstance(file, bytes):
            with open(local_path, "wb") as buffer:
                buffer.write(file)

        web_url = f"/uploads/videos/{safe_name}"
        print(f"[STORAGE] Saved video for lesson #{lesson_id} locally: {web_url}")
        return web_url

    @classmethod
    def upload_notes(cls, file: Union[UploadFile, bytes], lesson_id: int) -> str:
        """
        Uploads lesson notes/documents and returns a browser-accessible URL.
        """
        ext = ".pdf"
        filename = "notes.pdf"
        if hasattr(file, "filename") and file.filename:
            filename = file.filename
            ext = os.path.splitext(filename)[1].lower() or ".pdf"

        safe_name = f"lesson_{lesson_id}_{uuid.uuid4().hex[:8]}{ext}"
        provider = cls.get_provider()

        # 1. Supabase Storage Provider
        if provider == "supabase":
            try:
                if hasattr(file, "file"):
                    file.file.seek(0)
                dest = f"notes/{safe_name}"
                c_type = getattr(file, "content_type", "application/pdf") or "application/pdf"
                url = upload_file_to_supabase(file, bucket_name="files", destination_path=dest, content_type=c_type)
                if hasattr(file, "file"):
                    file.file.seek(0)
                if url:
                    print(f"[STORAGE] Uploaded notes for lesson #{lesson_id} to Supabase: {url}")
                    return url
            except Exception as sb_err:
                print(f"[STORAGE] Supabase notes upload error: {sb_err}")

        # 2. Local Storage
        local_dir = os.path.join("uploads", "notes")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, safe_name)

        if hasattr(file, "file"):
            file.file.seek(0)
            with open(local_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file.file.seek(0)
        elif isinstance(file, bytes):
            with open(local_path, "wb") as buffer:
                buffer.write(file)

        web_url = f"/uploads/notes/{safe_name}"
        print(f"[STORAGE] Saved notes for lesson #{lesson_id} locally: {web_url}")
        return web_url

    @classmethod
    def delete_file(cls, path_or_url: str) -> bool:
        """
        Deletes a file from storage (local or cloud).
        """
        if not path_or_url:
            return False

        # If Supabase URL
        if "supabase.co" in path_or_url:
            try:
                parts = path_or_url.split("/public/")
                if len(parts) == 2:
                    bucket_and_path = parts[1].split("/", 1)
                    if len(bucket_and_path) == 2:
                        return delete_supabase_file(bucket_and_path[0], bucket_and_path[1])
            except Exception as e:
                print(f"[STORAGE] Delete supabase file error: {e}")
                return False

        # If local URL or path
        clean_path = path_or_url.lstrip("/")
        if clean_path.startswith("uploads/"):
            if os.path.exists(clean_path):
                try:
                    os.remove(clean_path)
                    return True
                except Exception as e:
                    print(f"[STORAGE] Delete local file error: {e}")
        return False

    @classmethod
    def get_public_url(cls, path_or_url: str) -> str:
        """
        Resolves a standardized public URL for the browser.
        """
        if not path_or_url:
            return ""
        if path_or_url.startswith("http://") or path_or_url.startswith("https://") or path_or_url.startswith("/"):
            return path_or_url
        # If relative disk path like uploads/videos/abc.mp4
        normalized = path_or_url.replace("\\", "/").lstrip("/")
        return f"/{normalized}"

def get_s3_client():
    if not all([S3_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY]):
        return None
    try:
        import boto3
        return boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
    except Exception as e:
        print(f"[Storage Service] S3 client init error: {e}")
        return None

def upload_file_to_storage(file: UploadFile, folder: str = "videos") -> str:
    """Convenience function for general uploads."""
    clean_folder = folder.strip().rstrip("/").lower()
    if "video" in clean_folder:
        return StorageService.upload_video(file, lesson_id=1)
    if "note" in clean_folder or "doc" in clean_folder:
        return StorageService.upload_notes(file, lesson_id=1)

    file_extension = os.path.splitext(file.filename or "")[1].lstrip(".") or "bin"
    unique_filename = f"{uuid.uuid4().hex[:12]}.{file_extension}"
    
    local_dir = os.path.join("uploads", clean_folder)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, unique_filename)
    file.file.seek(0)
    with open(local_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file.file.seek(0)
    return f"/uploads/{clean_folder}/{unique_filename}"

def upload_file_to_s3(file: UploadFile, folder: str = "videos") -> str:
    return upload_file_to_storage(file, folder=folder)

