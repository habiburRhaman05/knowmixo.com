"""Private local-storage adapter, replacing the old S3/boto3 path
(docs/03-TRD.md step 2: "Stream upload into a private temporary file,
validate size/type, then atomically finalize storage").

Layout under PRIVATE_STORAGE_DIR:
  tmp/{grant_id}.part       -- in-progress upload, not yet validated
  companies/{company_id}/documents/{document_id}/v{version}{ext}  -- finalized

Never serves these paths directly to the browser; the API only ever
returns opaque grant IDs / document IDs, never filesystem paths.
"""
import hashlib
import secrets
import time
from pathlib import Path

from app.config import settings

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
GRANT_TTL_SECONDS = 300

# In-memory grant registry: scoped-upload metadata keyed by grant_id. This
# is a known, explicitly-flagged Phase 3 simplification -- it only works
# within a single API process. Multi-instance deployment needs this moved
# to Redis/Postgres (tracked for Phase 6+ hardening, not silently assumed
# to already be distributed-safe).
_GRANTS: dict[str, dict] = {}


class UploadError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _base_dir() -> Path:
    base = Path(settings().private_storage_dir)
    base.mkdir(parents=True, exist_ok=True)
    (base / "tmp").mkdir(exist_ok=True)
    return base


def create_upload_grant(company_id: str, document_id: str, version: int, filename: str, size_bytes: int) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError("unsupported_file_type", "Allowed types: PDF, DOCX, TXT, MD.")
    if size_bytes <= 0 or size_bytes > settings().max_file_bytes:
        raise UploadError("file_too_large", f"File must be between 1 byte and {settings().max_file_bytes} bytes.")

    grant_id = secrets.token_urlsafe(24)
    expires_at = time.time() + GRANT_TTL_SECONDS
    _GRANTS[grant_id] = {
        "company_id": company_id,
        "document_id": document_id,
        "version": version,
        "suffix": suffix,
        "max_bytes": size_bytes,
        "expires_at": expires_at,
    }
    return {"grant_id": grant_id, "suffix": suffix, "expires_at": expires_at, "max_bytes": size_bytes}


def _get_grant(grant_id: str) -> dict:
    grant = _GRANTS.get(grant_id)
    if not grant:
        raise UploadError("grant_not_found", "This upload grant does not exist or was already used.")
    if time.time() > grant["expires_at"]:
        _GRANTS.pop(grant_id, None)
        raise UploadError("grant_expired", "This upload grant has expired.")
    return grant


def write_upload_chunk(grant_id: str, data: bytes) -> int:
    """Streams data into the temp file, enforcing the size cap as bytes
    arrive rather than trusting a client-declared Content-Length."""
    grant = _get_grant(grant_id)
    tmp_path = _base_dir() / "tmp" / f"{grant_id}.part"
    existing_size = tmp_path.stat().st_size if tmp_path.exists() else 0
    if existing_size + len(data) > grant["max_bytes"]:
        tmp_path.unlink(missing_ok=True)
        raise UploadError("file_too_large", "Upload exceeded the declared size cap.")
    with open(tmp_path, "ab") as f:
        f.write(data)
    return existing_size + len(data)


def finalize_upload(grant_id: str) -> dict:
    """Validates the temp file by magic bytes (not just extension) and
    atomically moves it into its permanent, company-scoped location."""
    grant = _get_grant(grant_id)
    suffix = grant["suffix"]
    tmp_path = _base_dir() / "tmp" / f"{grant_id}.part"
    if not tmp_path.exists():
        raise UploadError("upload_not_found", "No upload data found for this grant.")

    data_head = tmp_path.read_bytes()[:8]
    if not _signature_matches(suffix, data_head):
        tmp_path.unlink(missing_ok=True)
        _GRANTS.pop(grant_id, None)
        raise UploadError("file_signature_mismatch", "File content does not match its declared type.")

    checksum = hashlib.sha256(tmp_path.read_bytes()).hexdigest()

    dest_dir = _base_dir() / "companies" / grant["company_id"] / "documents" / grant["document_id"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"v{grant['version']}{suffix}"
    tmp_path.replace(dest_path)  # atomic on the same filesystem
    _GRANTS.pop(grant_id, None)  # single-use: a grant cannot be finalized twice

    return {"storage_key": str(dest_path.relative_to(_base_dir())), "checksum": checksum, "size_bytes": dest_path.stat().st_size}


def write_text_content(company_id: str, document_id: str, version: int, content: str, suffix: str = ".txt") -> dict:
    """Direct-write path for text/FAQ sources that arrive inline in a
    request body (not via the streamed upload-grant flow) -- treated as a
    virtual file so the rest of the pipeline has one uniform
    storage_key-based read path regardless of source kind."""
    dest_dir = _base_dir() / "companies" / company_id / "documents" / document_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"v{version}{suffix}"
    data = content.encode("utf-8")
    dest_path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    return {"storage_key": str(dest_path.relative_to(_base_dir())), "checksum": checksum, "size_bytes": len(data)}


def read_file(storage_key: str) -> bytes:
    path = _base_dir() / storage_key
    if not path.is_relative_to(_base_dir()):
        raise UploadError("invalid_storage_key", "Refusing to read outside the storage root.")
    return path.read_bytes()


def _signature_matches(suffix: str, head: bytes) -> bool:
    if suffix == ".pdf":
        return head.startswith(b"%PDF")
    if suffix == ".docx":
        return head.startswith(b"PK\x03\x04")  # DOCX is a zip archive
    if suffix in (".txt", ".md"):
        return True  # no reliable magic bytes for plain text
    return False
