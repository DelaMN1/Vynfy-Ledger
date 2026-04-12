from __future__ import annotations

import mimetypes
import os
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


def validate_upload(file: FileStorage) -> list[str]:
    errors: list[str] = []
    extension = Path(file.filename or "").suffix.lower()
    mime_type = file.mimetype or mimetypes.guess_type(file.filename or "")[0]
    if extension not in ALLOWED_EXTENSIONS:
        errors.append("Unsupported attachment type.")
    if mime_type not in ALLOWED_MIME_TYPES:
        errors.append("Attachment MIME type is not allowed.")
    return errors


def store_upload(file: FileStorage) -> tuple[str, str]:
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename or "").suffix.lower()
    stored_name = f"{uuid4().hex}{extension}"
    safe_original = secure_filename(file.filename or stored_name)
    file_path = upload_dir / stored_name
    file.save(file_path)
    return safe_original, stored_name


def file_size(path: str) -> int:
    return os.path.getsize(path)
