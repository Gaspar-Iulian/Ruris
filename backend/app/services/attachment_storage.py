from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
from secrets import compare_digest, token_hex
import tempfile
import unicodedata

from flask import current_app


MAX_FILE_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
MEDIA_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class AttachmentTooLarge(ValueError):
    pass


class AttachmentStorageError(OSError):
    pass


@dataclass(frozen=True)
class StagedAttachment:
    path: Path
    original_name: str
    media_type: str
    size_bytes: int
    content_sha256: str


def storage_directories(*, create=False):
    try:
        root = Path(current_app.config["ATTACHMENT_STORAGE_PATH"]).resolve()
        objects, staging = root / "objects", root / "staging"
        if create:
            root.mkdir(parents=True, exist_ok=True)
        for directory in (objects, staging):
            if directory.is_symlink() or directory.resolve().parent != root:
                raise AttachmentStorageError("Spatiul de documente nu este disponibil.")
            if create:
                directory.mkdir(exist_ok=True)
        return objects, staging
    except OSError as error:
        raise AttachmentStorageError("Spatiul de documente nu este disponibil.") from error


def file_name(value):
    if not isinstance(value, str):
        raise ValueError("Selecteaza un fisier PDF, PNG sau JPG.")
    name = unicodedata.normalize("NFC", value.strip())
    if (not 1 <= len(name) <= 200 or any(character in name for character in '/\\:')
            or any(unicodedata.category(character).startswith("C") for character in name)
            or not Path(name).stem.strip('. ')):
        raise ValueError("Numele fisierului trebuie sa aiba cel mult 200 de caractere, fara cai sau caractere de control.")
    extension = Path(name).suffix.lower()
    if extension not in MEDIA_TYPES:
        raise ValueError("Sunt acceptate numai fisiere PDF, PNG si JPG.")
    return name, MEDIA_TYPES[extension]


def validate_signature(data, media_type):
    if media_type == "application/pdf":
        valid = re.match(rb"%PDF-(?:1\.[0-7]|2\.0)(?:\s|$)", data[:16]) is not None and data.rstrip().endswith(b"%%EOF")
    elif media_type == "image/png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR") and len(data) >= 57 and data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    else:
        valid = len(data) >= 16 and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if not valid:
        raise ValueError("Continutul fisierului nu corespunde unui PDF, PNG sau JPG acceptat.")


@contextmanager
def stage_attachment(upload):
    name, media_type = file_name(upload.filename)
    if upload.mimetype not in ("", "application/octet-stream", media_type):
        raise ValueError("Tipul declarat al fisierului nu corespunde extensiei.")
    _, staging = storage_directories(create=True)
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+b", dir=staging, prefix="incoming-", delete=False) as target:
            path = Path(target.name)
            digest, size = sha256(), 0
            while chunk := upload.stream.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise AttachmentTooLarge("Fisierul poate avea cel mult 10 MB.")
                target.write(chunk)
                digest.update(chunk)
            if size == 0:
                raise ValueError("Fisierul este gol.")
            target.flush()
            os.fsync(target.fileno())
            target.seek(0)
            validate_signature(target.read(MAX_FILE_BYTES + 1), media_type)
        yield StagedAttachment(path, name, media_type, size, digest.hexdigest())
    except OSError as error:
        raise AttachmentStorageError("Fisierul nu a putut fi pastrat. Reincarca documentele inainte de o noua incercare.") from error
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def publish_attachment(staged):
    objects, _ = storage_directories(create=True)
    storage_key = token_hex(32)
    path = objects / storage_key
    try:
        # Create a complete file without overwriting an existing object.
        os.link(staged.path, path)
        if os.name != "nt":
            descriptor = os.open(objects, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError as error:
        raise AttachmentStorageError("Fisierul nu a putut fi salvat in spatiul de documente.") from error
    return storage_key, path


def read_attachment(record):
    objects, _ = storage_directories()
    if not re.fullmatch(r"[a-f0-9]{64}", record.storage_key):
        raise AttachmentStorageError("Identificatorul fisierului nu este valid.")
    path = objects / record.storage_key
    try:
        if path.is_symlink() or path.resolve().parent != objects:
            raise AttachmentStorageError("Fisierul nu este disponibil.")
        with path.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        if len(data) != record.size_bytes or not compare_digest(sha256(data).hexdigest(), record.content_sha256):
            raise AttachmentStorageError("Integritatea fisierului nu a putut fi confirmata.")
        return data
    except OSError as error:
        raise AttachmentStorageError("Fisierul nu este disponibil sau integritatea lui nu a putut fi confirmata.") from error
