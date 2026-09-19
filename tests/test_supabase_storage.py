import os
import io
import requests
from dotenv import load_dotenv
from fastapi import UploadFile

load_dotenv()

from utils.supabase_storage import (
    resolve_bucket_name,
    upload_file_to_supabase,
    upload_image_to_supabase,
    upload_video_to_supabase,
    upload_document_to_supabase,
    upload_certificate_to_supabase,
    get_supabase_file_url,
    delete_supabase_file
)
from app.services.storage_service import upload_file_to_storage

def test_resolve_bucket_name():
    print("[RUNNING] test_resolve_bucket_name...")
    assert resolve_bucket_name("avatar.png") == "images"
    assert resolve_bucket_name("photo.jpg") == "images"
    assert resolve_bucket_name("diagram.webp") == "images"
    assert resolve_bucket_name("lesson_video.mp4") == "videos"
    assert resolve_bucket_name("demo.webm") == "videos"
    assert resolve_bucket_name("resume.pdf") == "files"
    assert resolve_bucket_name("notes.docx") == "files"
    assert resolve_bucket_name("cert_123.html") == "certificates"
    assert resolve_bucket_name("certificate_scholar.pdf") == "certificates"
    print("[PASS] test_resolve_bucket_name")

def test_supabase_image_upload():
    print("[RUNNING] test_supabase_image_upload...")
    sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    dest = "test_artifacts/automated_test_avatar.png"
    url = upload_image_to_supabase(sample_png, destination_path=dest)
    assert url != "", "Image upload URL should not be empty"
    assert "images" in url, f"Expected 'images' in URL, got {url}"
    assert url.startswith("https://"), f"Expected https URL, got {url}"
    
    # Verify public accessibility
    res = requests.get(url, timeout=15)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert len(res.content) == len(sample_png), "Content length mismatch"
    print(f"[PASS] test_supabase_image_upload -> {url}")

def test_supabase_video_upload():
    print("[RUNNING] test_supabase_video_upload...")
    sample_mp4 = b"fake-mp4-video-data-bytes-header"
    dest = "test_artifacts/automated_test_demo.mp4"
    url = upload_video_to_supabase(sample_mp4, destination_path=dest)
    assert url != "", "Video upload URL should not be empty"
    assert "videos" in url, f"Expected 'videos' in URL, got {url}"
    
    # Verify public accessibility
    res = requests.get(url, timeout=15)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    print(f"[PASS] test_supabase_video_upload -> {url}")

def test_supabase_document_upload():
    print("[RUNNING] test_supabase_document_upload...")
    sample_pdf = b"%PDF-1.4 sample test resume document content"
    dest = "test_artifacts/automated_test_resume.pdf"
    url = upload_document_to_supabase(sample_pdf, destination_path=dest)
    assert url != "", "Document upload URL should not be empty"
    assert "files" in url, f"Expected 'files' in URL, got {url}"
    
    # Verify public accessibility
    res = requests.get(url, timeout=15)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    print(f"[PASS] test_supabase_document_upload -> {url}")

def test_supabase_certificate_upload():
    print("[RUNNING] test_supabase_certificate_upload...")
    sample_cert_html = b"<!DOCTYPE html><html><body><h1>TruProjects Verified Certificate</h1></body></html>"
    dest = "test_artifacts/automated_test_cert.html"
    url = upload_certificate_to_supabase(sample_cert_html, destination_path=dest)
    assert url != "", "Certificate upload URL should not be empty"
    assert "certificates" in url, f"Expected 'certificates' in URL, got {url}"
    
    # Verify public accessibility
    res = requests.get(url, timeout=15)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    print(f"[PASS] test_supabase_certificate_upload -> {url}")

def test_storage_service_fastapi_uploadfile():
    print("[RUNNING] test_storage_service_fastapi_uploadfile...")
    file_bytes = b"Hello from FastAPI UploadFile simulation"
    upload_file = UploadFile(
        filename="lecture_recording.webm",
        file=io.BytesIO(file_bytes),
        headers={"content-type": "video/webm"}
    )
    url = upload_file_to_storage(upload_file, folder="course_media")
    assert url != "", "Storage service URL should not be empty"
    assert "uploads" in url or "videos" in url or "supabase.co" in url, f"Expected storage URL, got {url}"
    
    if url.startswith("http"):
        res = requests.get(url, timeout=15)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    print(f"[PASS] test_storage_service_fastapi_uploadfile -> {url}")

def test_cleanup_test_artifacts():
    print("[RUNNING] test_cleanup_test_artifacts...")
    delete_supabase_file("images", "test_artifacts/automated_test_avatar.png")
    delete_supabase_file("videos", "test_artifacts/automated_test_demo.mp4")
    delete_supabase_file("files", "test_artifacts/automated_test_resume.pdf")
    delete_supabase_file("certificates", "test_artifacts/automated_test_cert.html")
    print("[PASS] test_cleanup_test_artifacts")

if __name__ == "__main__":
    test_resolve_bucket_name()
    test_supabase_image_upload()
    test_supabase_video_upload()
    test_supabase_document_upload()
    test_supabase_certificate_upload()
    test_storage_service_fastapi_uploadfile()
    test_cleanup_test_artifacts()
    print("\n=======================================================")
    print("ALL SUPABASE STORAGE BUCKET TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
