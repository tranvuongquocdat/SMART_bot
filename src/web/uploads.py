"""File upload helper for payment proofs and refund QR codes."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

UPLOAD_ROOT = Path("uploads")
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".pdf"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def save_upload(file: UploadFile, subfolder: str) -> str:
    """Save UploadFile to uploads/<subfolder>/<uuid><ext>. Returns relative path."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            400, f"Unsupported file type '{ext}'. Allowed: jpg, png, pdf"
        )
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")
    dest_dir = UPLOAD_ROOT / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    (dest_dir / filename).write_bytes(content)
    return str(dest_dir / filename)
