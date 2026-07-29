from __future__ import annotations

import shutil
import stat
import uuid
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.imports.exceptions import PackageValidationError
from app.imports.reader import read_standard_package
from app.imports.schemas import StandardPackage

ALLOWED_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}
MAX_ARCHIVE_MEMBERS = 100


@dataclass(frozen=True, slots=True)
class StagedPackage:
    token: str
    package_root: Path
    package: StandardPackage


def _staging_root(instance_path: str, organization_id: uuid.UUID) -> Path:
    return Path(instance_path).resolve() / "import_staging" / str(organization_id)


def _safe_token(token: str) -> str:
    try:
        return uuid.UUID(token).hex
    except (ValueError, TypeError, AttributeError) as error:
        raise PackageValidationError("Geçici paket anahtarı geçersiz.") from error


def _token_directory(
    instance_path: str,
    organization_id: uuid.UUID,
    token: str,
) -> Path:
    root = _staging_root(instance_path, organization_id)
    candidate = (root / _safe_token(token)).resolve()
    if candidate.parent != root:
        raise PackageValidationError("Geçici paket yolu geçersiz.")
    return candidate


def _validate_upload(file: FileStorage) -> str:
    filename = secure_filename(file.filename or "")
    if not filename or Path(filename).suffix.lower() != ".zip":
        raise PackageValidationError("Yalnız ZIP biçimindeki veri paketleri kabul edilir.")
    if file.mimetype not in ALLOWED_MIME_TYPES:
        raise PackageValidationError("Dosya içerik türü ZIP paketiyle uyumlu değil.")
    signature = file.stream.read(4)
    file.stream.seek(0)
    if signature[:2] != b"PK":
        raise PackageValidationError("Dosya geçerli bir ZIP paketi değil.")
    return filename


def _write_upload(file: FileStorage, target: Path, max_bytes: int) -> None:
    written = 0
    with target.open("xb") as destination:
        while chunk := file.stream.read(64 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise PackageValidationError("Veri paketi izin verilen boyutu aşıyor.")
            destination.write(chunk)


def _safe_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise PackageValidationError("ZIP paketi güvenli olmayan bir dosya yolu içeriyor.")
    return path


def _extract_archive(archive_path: Path, target: Path, max_bytes: int) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise PackageValidationError("ZIP paketi çok fazla dosya içeriyor.")
            total_size = 0
            for member in members:
                relative = _safe_archive_path(member.filename)
                if member.flag_bits & 0x1:
                    raise PackageValidationError("Şifreli ZIP dosyaları desteklenmiyor.")
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise PackageValidationError("ZIP paketi sembolik bağlantı içeremez.")
                total_size += member.file_size
                if total_size > max_bytes:
                    raise PackageValidationError(
                        "Açılmış veri paketi izin verilen boyutu aşıyor."
                    )
                destination = (target / Path(*relative.parts)).resolve()
                if target not in destination.parents and destination != target:
                    raise PackageValidationError("ZIP paketinde yol ihlali tespit edildi.")
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=64 * 1024)
    except (zipfile.BadZipFile, OSError) as error:
        raise PackageValidationError("ZIP paketi güvenli biçimde açılamadı.") from error


def _package_root(extracted: Path) -> Path:
    if (extracted / "manifest.json").is_file():
        return extracted
    candidates = [
        item
        for item in extracted.iterdir()
        if item.is_dir() and (item / "manifest.json").is_file()
    ]
    if len(candidates) != 1:
        raise PackageValidationError("Paket kökünde manifest.json bulunamadı.")
    return candidates[0]


def stage_package(
    file: FileStorage,
    *,
    instance_path: str,
    organization_id: uuid.UUID,
    max_archive_bytes: int,
    max_extracted_bytes: int,
) -> StagedPackage:
    _validate_upload(file)
    token = uuid.uuid4().hex
    directory = _token_directory(instance_path, organization_id, token)
    extracted = directory / "package"
    succeeded = False
    try:
        extracted.mkdir(parents=True, exist_ok=False)
        archive_path = directory / "upload.zip"
        _write_upload(file, archive_path, max_archive_bytes)
        _extract_archive(archive_path, extracted, max_extracted_bytes)
        package_root = _package_root(extracted)
        package = read_standard_package(package_root)
        succeeded = True
    finally:
        if not succeeded:
            cleanup_staged_package(
                instance_path=instance_path,
                organization_id=organization_id,
                token=token,
            )
    archive_path.unlink(missing_ok=True)
    return StagedPackage(token=token, package_root=package_root, package=package)


def load_staged_package(
    *,
    instance_path: str,
    organization_id: uuid.UUID,
    token: str,
) -> StagedPackage:
    directory = _token_directory(instance_path, organization_id, token)
    if not directory.is_dir():
        raise PackageValidationError("Ön kontrol paketi bulunamadı veya süresi doldu.")
    package_root = _package_root(directory / "package")
    return StagedPackage(
        token=_safe_token(token),
        package_root=package_root,
        package=read_standard_package(package_root),
    )


def cleanup_staged_package(
    *,
    instance_path: str,
    organization_id: uuid.UUID,
    token: str,
) -> None:
    directory = _token_directory(instance_path, organization_id, token)
    if directory.is_dir():
        shutil.rmtree(directory)
    organization_root = _staging_root(instance_path, organization_id)
    with suppress(OSError):
        organization_root.rmdir()
    with suppress(OSError):
        organization_root.parent.rmdir()
