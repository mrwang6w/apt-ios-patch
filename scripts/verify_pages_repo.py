#!/usr/bin/env python3
"""Verify the generated GitHub Pages APT repository before deployment."""

from __future__ import annotations

import gzip
import hashlib
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_pages_repo import (  # noqa: E402
    CONTROL_PASSTHROUGH_FIELDS,
    PATCHED_PACKAGES,
    PUBLISH_AUTHOR,
    PUBLISH_MAINTAINER,
    extract_control,
    parse_deb_control_text,
    validate_deb_archive,
)


PAGES_ROOT = ROOT / "pages-repo"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"
RELEASE_ALGORITHMS = {"MD5Sum": "md5", "SHA1": "sha1", "SHA256": "sha256"}


def digest(path: Path, algorithm: str) -> str:
    result = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"required Pages file is missing or empty: {path}")


def referenced_file(value: str, directory: str, suffix: str) -> Path:
    prefix = f"./{directory}/"
    if not value.startswith(prefix):
        raise RuntimeError(f"unsafe {directory} reference: {value!r}")
    name = value.removeprefix(prefix)
    if not name.endswith(suffix) or Path(name).name != name or "/" in name or "\\" in name:
        raise RuntimeError(f"unsafe {directory} reference: {value!r}")
    return PAGES_ROOT / directory / name


def parse_release(text: str) -> tuple[dict[str, str], dict[str, list[tuple[str, int, str]]]]:
    fields: dict[str, str] = {}
    hashes = {title: [] for title in RELEASE_ALGORITHMS}
    current_hash: str | None = None
    for line in text.splitlines():
        if line.startswith(" "):
            if current_hash is None:
                raise RuntimeError(f"unexpected Release continuation: {line!r}")
            parts = line.split()
            if len(parts) != 3:
                raise RuntimeError(f"invalid Release hash entry: {line!r}")
            expected, size, name = parts
            hashes[current_hash].append((expected, int(size), name))
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise RuntimeError(f"invalid Release field: {line!r}")
        if key in RELEASE_ALGORITHMS:
            current_hash = key
        else:
            current_hash = None
            if key in fields:
                raise RuntimeError(f"duplicate Release field: {key}")
            fields[key] = value.strip()
    return fields, hashes


def verify_release(records: list[dict[str, str]]) -> None:
    release_path = PAGES_ROOT / "Release"
    require_file(release_path)
    fields, hash_sections = parse_release(release_path.read_text(encoding="utf-8"))
    required_fields = {"Origin", "Label", "Suite", "Version", "Codename", "Architectures", "Components", "Description", "Date"}
    missing_fields = sorted(required_fields - fields.keys())
    if missing_fields:
        raise RuntimeError(f"Release fields missing: {missing_fields}")

    expected_architectures = {record["Architecture"] for record in records}
    actual_architectures = set(fields.get("Architectures", "").split())
    if actual_architectures != expected_architectures:
        raise RuntimeError(
            f"Release Architectures mismatch: expected={sorted(expected_architectures)} "
            f"actual={sorted(actual_architectures)}"
        )

    expected_names = {"Packages", "Packages.gz"}
    for title, algorithm in RELEASE_ALGORITHMS.items():
        entries = hash_sections[title]
        if {name for _, _, name in entries} != expected_names or len(entries) != len(expected_names):
            raise RuntimeError(f"Release {title} must contain Packages and Packages.gz exactly once")
        for expected_digest, expected_size, name in entries:
            path = PAGES_ROOT / name
            require_file(path)
            actual_size = path.stat().st_size
            actual_digest = digest(path, algorithm)
            if expected_size != actual_size or expected_digest != actual_digest:
                raise RuntimeError(
                    f"Release {title} mismatch for {name}: "
                    f"expected={expected_digest}/{expected_size} actual={actual_digest}/{actual_size}"
                )


def verify_deb(record: dict[str, str], index_html: str) -> Path:
    required_fields = {
        "Package",
        "Version",
        "Architecture",
        "Section",
        "Maintainer",
        "Name",
        "Author",
        "Filename",
        "Size",
        "MD5sum",
        "SHA1",
        "SHA256",
        "Depiction",
        "Icon",
        "Description",
    }
    missing = sorted(required_fields - record.keys())
    if missing:
        raise RuntimeError(f"{record.get('Package', '<unknown>')}: Packages fields missing: {missing}")

    deb_path = referenced_file(record["Filename"], "debs", ".deb")
    require_file(deb_path)
    if str(deb_path.stat().st_size) != record["Size"]:
        raise RuntimeError(f"Size mismatch for {deb_path}")
    for field, algorithm in (("MD5sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")):
        actual = digest(deb_path, algorithm)
        if actual != record[field]:
            raise RuntimeError(f"{field} mismatch for {deb_path}: expected={record[field]} actual={actual}")

    depiction_path = referenced_file(record["Depiction"], "depictions", ".html")
    require_file(depiction_path)
    depiction = depiction_path.read_text(encoding="utf-8")
    if record["Package"] not in depiction or record["SHA256"] not in depiction:
        raise RuntimeError(f"depiction does not identify its package and SHA256: {depiction_path}")
    if record["Icon"] != "./CydiaIcon.png":
        raise RuntimeError(f"unexpected Icon reference for {record['Package']}: {record['Icon']!r}")
    require_file(PAGES_ROOT / "CydiaIcon.png")
    if f'href="{record["Filename"]}"' not in index_html:
        raise RuntimeError(f"index.html does not link {record['Filename']}")

    with tempfile.TemporaryDirectory(prefix="pages-deb-verify-") as tmp:
        tmp_path = Path(tmp)
        validate_deb_archive(deb_path, tmp_path / "archive")
        control = extract_control(deb_path, tmp_path / "control")
    for field in CONTROL_PASSTHROUGH_FIELDS:
        if field in control and record.get(field) != control[field]:
            raise RuntimeError(
                f"{deb_path}: {field} mismatch: control={control[field]!r} Packages={record.get(field)!r}"
            )

    print(f"{deb_path}: OK")
    return deb_path


def verify() -> None:
    for name in (
        ".gitattributes",
        ".nojekyll",
        "index.html",
        "Packages",
        "Packages.gz",
        "Release",
        "README.md",
        "CydiaIcon.png",
        "favicon.ico",
    ):
        path = PAGES_ROOT / name
        if name == ".nojekyll":
            if not path.is_file():
                raise RuntimeError(f"required Pages file is missing: {path}")
        else:
            require_file(path)

    attributes = (PAGES_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.deb -filter -diff -merge -text", "*.gz -filter -diff -merge -text"):
        if rule not in attributes.splitlines():
            raise RuntimeError(f"pages-repo/.gitattributes is missing rule: {rule}")

    for path in PAGES_ROOT.rglob("*"):
        if path.is_file():
            with path.open("rb") as fh:
                if fh.read(128).startswith(LFS_POINTER_PREFIX):
                    raise RuntimeError(f"Git LFS pointer detected under pages-repo: {path}")

    packages_bytes = (PAGES_ROOT / "Packages").read_bytes()
    if gzip.decompress((PAGES_ROOT / "Packages.gz").read_bytes()) != packages_bytes:
        raise RuntimeError("Packages.gz does not decompress to pages-repo/Packages")
    records = parse_deb_control_text(packages_bytes.decode("utf-8"))

    expected_configs = {str(config["package_id"]): config for config in PATCHED_PACKAGES}
    expected_ids = [str(config["package_id"]) for config in PATCHED_PACKAGES]
    if len(expected_ids) != len(set(expected_ids)):
        raise RuntimeError(f"duplicate package_id in PATCHED_PACKAGES: {expected_ids}")
    for field in ("deb_name", "depiction_name"):
        names = [str(config[field]) for config in PATCHED_PACKAGES]
        if len(names) != len(set(names)):
            raise RuntimeError(f"duplicate {field} in PATCHED_PACKAGES: {names}")
    seen_ids = [record.get("Package", "") for record in records]
    if len(seen_ids) != len(set(seen_ids)):
        raise RuntimeError(f"duplicate Package records: {seen_ids}")
    if set(seen_ids) != set(expected_ids) or len(seen_ids) != len(expected_ids):
        raise RuntimeError(f"unexpected Packages records: expected={sorted(expected_ids)} actual={sorted(seen_ids)}")
    for field in ("Filename", "Depiction"):
        references = [record.get(field, "") for record in records]
        if len(references) != len(set(references)):
            raise RuntimeError(f"duplicate {field} references in Packages: {references}")

    for record in records:
        config = expected_configs[record["Package"]]
        source = Path(config["source"])
        require_file(source)
        source_size = str(source.stat().st_size)
        source_sha256 = digest(source, "sha256")
        if source_size != record.get("Size") or source_sha256 != record.get("SHA256"):
            raise RuntimeError(
                f"{record['Package']}: configured patched source differs from Pages deb: "
                f"source={source_sha256}/{source_size} "
                f"pages={record.get('SHA256')}/{record.get('Size')}"
            )
        expected_metadata = {
            "Section": str(config["publish_section"]),
            "Maintainer": PUBLISH_MAINTAINER,
            "Name": str(config["publish_name"]),
            "Author": PUBLISH_AUTHOR,
            "Filename": f"./debs/{config['deb_name']}",
            "Depiction": f"./depictions/{config['depiction_name']}",
            "Icon": "./CydiaIcon.png",
            "Description": str(config["publish_desc"]),
        }
        for field, expected in expected_metadata.items():
            if record.get(field) != expected:
                raise RuntimeError(
                    f"{record['Package']}: stale {field}: expected={expected!r} actual={record.get(field)!r}"
                )

    index_html = (PAGES_ROOT / "index.html").read_text(encoding="utf-8")
    if f"<strong>{len(records)}</strong> patched packages mounted" not in index_html:
        raise RuntimeError("index.html mounted package count is stale")
    readme = (PAGES_ROOT / "README.md").read_text(encoding="utf-8")
    for record in records:
        if record["Package"] not in readme or record["Filename"].removeprefix("./") not in readme or record["SHA256"] not in readme:
            raise RuntimeError(f"README.md is stale for {record['Package']}")

    referenced_debs = {verify_deb(record, index_html).resolve() for record in records}
    actual_debs = {path.resolve() for path in (PAGES_ROOT / "debs").glob("*.deb") if path.is_file()}
    if referenced_debs != actual_debs or len(actual_debs) != len(records):
        missing = sorted(str(path) for path in referenced_debs - actual_debs)
        orphaned = sorted(str(path) for path in actual_debs - referenced_debs)
        raise RuntimeError(f"Packages/debs mismatch: missing={missing} orphaned={orphaned}")

    referenced_depictions = {
        referenced_file(record["Depiction"], "depictions", ".html").resolve() for record in records
    }
    actual_depictions = {
        path.resolve() for path in (PAGES_ROOT / "depictions").glob("*.html") if path.is_file()
    }
    if referenced_depictions != actual_depictions or len(actual_depictions) != len(records):
        raise RuntimeError("Packages/depictions mismatch")

    verify_release(records)
    print(f"Verified {len(records)} Packages records and {len(actual_debs)} deb files")


if __name__ == "__main__":
    verify()
