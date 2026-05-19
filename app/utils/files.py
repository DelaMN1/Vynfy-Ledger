from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/csv",
    "application/vnd.ms-excel",
}
PDF_SIGNATURE = b"%PDF-"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURES = (b"\xff\xd8\xff",)


def _read_head(file: FileStorage, size: int = 512) -> bytes:
    file.stream.seek(0)
    head = file.stream.read(size)
    file.stream.seek(0)
    return head


def _matches_signature(extension: str, head: bytes) -> bool:
    if extension == ".pdf":
        return head.startswith(PDF_SIGNATURE)
    if extension == ".png":
        return head.startswith(PNG_SIGNATURE)
    if extension in {".jpg", ".jpeg"}:
        return any(head.startswith(signature) for signature in JPEG_SIGNATURES)
    if extension == ".csv":
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                head.decode("latin-1")
                return True
            except UnicodeDecodeError:
                return False
    return False


def validate_upload(file: FileStorage) -> list[str]:
    errors: list[str] = []
    extension = Path(file.filename or "").suffix.lower()
    mime_type = file.mimetype or mimetypes.guess_type(file.filename or "")[0]
    head = _read_head(file)
    if extension not in ALLOWED_EXTENSIONS:
        errors.append("Unsupported attachment type.")
    if mime_type not in ALLOWED_MIME_TYPES:
        errors.append("Attachment MIME type is not allowed.")
    if extension in ALLOWED_EXTENSIONS and not _matches_signature(extension, head):
        errors.append("Attachment content does not match the declared file type.")
    return errors


def store_upload(file: FileStorage) -> tuple[str, str, str]:
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename or "").suffix.lower()
    stored_name = f"{uuid4().hex}{extension}"
    safe_original = secure_filename(file.filename or stored_name)
    file_path = upload_dir / stored_name
    file.stream.seek(0)
    sha256_hash = hashlib.sha256(file.stream.read()).hexdigest()
    file.stream.seek(0)
    file.save(file_path)
    return safe_original, stored_name, sha256_hash
