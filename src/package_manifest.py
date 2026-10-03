"""Portable payload manifests. Standard library only; no game/network operations."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unicodedata

SCHEMA_VERSION = 1
DOMAIN = b"pz-package-manifest-v1\0"
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
RESERVED |= {prefix + number for prefix in ("COM", "LPT") for number in "123456789\u00b9\u00b2\u00b3"}


class ManifestError(ValueError):
    """Unsafe input, malformed manifest, or an unstable/unreadable payload."""


def canonical_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("File paths must be nonempty strings")
    value = unicodedata.normalize("NFC", value)
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ManifestError("Control characters/surrogates are not portable path characters")
    if any(c in value for c in '\\<>:"|?*'):
        raise ManifestError(f"Nonportable or absolute path: {value!r}")
    for part in value.split("/"):
        if not part or part in (".", "..") or part.endswith((".", " ")):
            raise ManifestError(f"Unsafe path component: {value!r}")
        if part.split(".", 1)[0].upper() in RESERVED:
            raise ManifestError(f"Reserved device name in path: {value!r}")
    return value


def label(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 200:
        raise ManifestError(f"{name} must be a nonempty, trimmed label (at most 200 characters)")
    if any(c in value for c in "/\\") or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ManifestError(f"{name} must be a label, not a path or control text")
    return unicodedata.normalize("NFC", value)


def metadata(game_version: str, converter_version: str, mod_ids: list[str],
             required_directories: list[str] | None = None) -> dict:
    if not isinstance(mod_ids, list) or not mod_ids:
        raise ManifestError("At least one declared mod ID is required")
    ids = [label(value, "mod ID") for value in mod_ids]
    if len({value.casefold() for value in ids}) != len(ids):
        raise ManifestError("Duplicate case-normalized mod IDs")
    if required_directories is None:
        required_directories = []
    if not isinstance(required_directories, list):
        raise ManifestError("required_directories must be an array")
    directories = [canonical_path(value) for value in required_directories]
    if len({value.casefold() for value in directories}) != len(directories):
        raise ManifestError("Duplicate case/Unicode-normalized required directories")
    nodes = {}
    for name in directories:
        _register_path(nodes, name, is_file=False)
    return {"game_version": label(game_version, "game version"),
            "converter_version": label(converter_version, "converter version"),
            "mod_ids": sorted(ids), "required_directories": sorted(directories)}


def _safe_stat(path: Path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
        raise ManifestError(f"Symlink/reparse point is forbidden: {path}")
    return info


def safe_absolute(path: os.PathLike | str, *, existing: bool = True) -> Path:
    # abspath normalizes CLI root paths without following symlinks like resolve() would.
    result = Path(os.path.abspath(os.fspath(path)))
    chain = list(reversed(result.parents)) + [result]
    for index, item in enumerate(chain):
        if not existing and index == len(chain) - 1 and not os.path.lexists(item):
            break
        info = _safe_stat(item)
        if index < len(chain) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ManifestError(f"Parent is not a directory: {item}")
    return result


def _hash_file(path: Path) -> tuple[int, str]:
    before = _safe_stat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ManifestError(f"Non-regular payload file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ManifestError(f"File changed while opening: {path}")
        digest = hashlib.sha256()
        count = 0
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
        after = os.fstat(stream.fileno())
    final = _safe_stat(path)
    def signature(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    # Windows lstat and fstat may expose different ctime meanings. Compare ctime
    # only between calls to the same API; inode/size/mtime agree across both.
    if (signature(before) != signature(opened) or signature(opened) != signature(after)
            or signature(after) != signature(final) or count != after.st_size
            or before.st_ctime_ns != final.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns):
        raise ManifestError(f"File changed while hashing: {path}")
    return count, digest.hexdigest()


def _relative_manifest(root: Path, manifest: Path | None) -> str | None:
    if manifest is None:
        return None
    try:
        relative = manifest.relative_to(root)
    except ValueError:
        return None
    return canonical_path(relative.as_posix())


def scan_payload(root: os.PathLike | str, manifest: os.PathLike | str | None = None,
                 *, directories: set[str] | None = None) -> list[dict]:
    root = safe_absolute(root)
    if not stat.S_ISDIR(_safe_stat(root).st_mode):
        raise ManifestError("Payload root must be a directory")
    manifest_path = safe_absolute(manifest, existing=False) if manifest is not None else None
    excluded = _relative_manifest(root, manifest_path)
    found, seen = [], {}
    pending = [root]
    while pending:
        directory = pending.pop()
        _safe_stat(directory)
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            path = directory / entry.name
            relative = canonical_path(path.relative_to(root).as_posix())
            key = relative.casefold()
            if key in seen:
                raise ManifestError(f"Duplicate case/Unicode-normalized path: {seen[key]!r}, {relative!r}")
            seen[key] = relative
            info = _safe_stat(path)
            if stat.S_ISDIR(info.st_mode):
                if directories is not None:
                    directories.add(relative)
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                # Only the actual supplied manifest may be excluded; no name/glob exclusions.
                if excluded is not None and key == excluded.casefold():
                    if path != manifest_path:
                        raise ManifestError(f"Manifest path collides with a differently spelled payload path: {relative}")
                    continue
                size, digest = _hash_file(path)
                found.append({"path": relative, "size": size, "sha256": digest})
            else:
                raise ManifestError(f"Non-regular payload entry: {relative}")
    return sorted(found, key=lambda record: record["path"])


def fingerprint(meta: dict, files: list[dict]) -> str:
    payload = {"schema_version": SCHEMA_VERSION, "metadata": meta,
               "files": sorted(files, key=lambda record: record["path"])}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(DOMAIN + canonical.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _register_path(nodes: dict, name: str, *, is_file: bool) -> None:
    parts = name.split("/")
    for index in range(len(parts)):
        prefix = "/".join(parts[:index + 1])
        leaf_file = is_file and index == len(parts) - 1
        previous = nodes.get(prefix.casefold())
        if previous is not None and (previous != (prefix, False) or leaf_file):
            raise ManifestError(f"Duplicate, case-colliding, or file/directory-conflicting path: {name!r}")
        nodes[prefix.casefold()] = (prefix, leaf_file)


def validate_manifest(value) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema_version", "metadata", "files", "fingerprint"}:
        raise ManifestError("Unexpected manifest fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise ManifestError("Unsupported manifest schema version")
    raw_meta = value["metadata"]
    if not isinstance(raw_meta, dict) or set(raw_meta) != {"game_version", "converter_version", "mod_ids", "required_directories"}:
        raise ManifestError("Unexpected metadata fields")
    meta = metadata(**raw_meta)
    if meta != raw_meta:
        raise ManifestError("Metadata must use canonical sorted mod IDs/directories and NFC text")
    if not isinstance(value["files"], list):
        raise ManifestError("files must be an array")
    nodes, files = {}, []
    for name in meta["required_directories"]:
        _register_path(nodes, name, is_file=False)
    for record in value["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise ManifestError("Unexpected file record fields")
        name = canonical_path(record["path"])
        if name != record["path"]:
            raise ManifestError("Manifest paths must use Unicode NFC")
        _register_path(nodes, name, is_file=True)
        if type(record["size"]) is not int or record["size"] < 0:
            raise ManifestError(f"Invalid size: {name}")
        if not isinstance(record["sha256"], str) or not HEX256.fullmatch(record["sha256"]):
            raise ManifestError(f"Invalid SHA-256: {name}")
        files.append(dict(record))
    expected = value["fingerprint"]
    if not isinstance(expected, str) or not HEX256.fullmatch(expected):
        raise ManifestError("Invalid manifest fingerprint")
    if fingerprint(meta, files) != expected:
        raise ManifestError("Manifest fingerprint does not match its metadata and file records")
    return {"schema_version": SCHEMA_VERSION, "metadata": meta,
            "files": sorted(files, key=lambda record: record["path"]), "fingerprint": expected}


def _reject_constant(token):
    raise ManifestError(f"Invalid JSON constant: {token}")


def load_manifest(path: os.PathLike | str) -> dict:
    path = safe_absolute(path)
    if not stat.S_ISREG(_safe_stat(path).st_mode):
        raise ManifestError("Manifest must be a regular file")
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream, object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError(f"Invalid manifest JSON: {exc}") from exc
    return validate_manifest(value)


def create_manifest(root, output, *, game_version: str, converter_version: str,
                    mod_ids: list[str], required_directories: list[str] | None = None) -> dict:
    meta = metadata(game_version, converter_version, mod_ids, required_directories)
    output = safe_absolute(output, existing=False)
    # Refuse to overwrite an ordinary payload/other file accidentally used as --output.
    if output.exists():
        load_manifest(output)
    directories = set()
    files = scan_payload(root, output, directories=directories)
    missing_directories = sorted(set(meta["required_directories"]) - directories)
    if missing_directories:
        raise ManifestError("Missing required directories: " + ", ".join(missing_directories))
    manifest = {"schema_version": SCHEMA_VERSION, "metadata": meta, "files": files,
                "fingerprint": fingerprint(meta, files)}
    validate_manifest(manifest)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output.parent,
                                         prefix=".manifest-tmp-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        safe_absolute(output, existing=False)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return manifest


@dataclass(frozen=True)
class VerificationResult:
    fingerprint: str
    file_count: int
    missing: tuple[str, ...]
    changed: tuple[str, ...]
    extra: tuple[str, ...]
    metadata_mismatches: tuple[str, ...]
    missing_directories: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (self.missing or self.changed or self.extra or self.metadata_mismatches or self.missing_directories)


def verify_manifest(root, manifest_path, *, expected_fingerprint=None,
                    game_version=None, converter_version=None, mod_ids=None) -> VerificationResult:
    manifest = load_manifest(manifest_path)
    mismatch = []
    if expected_fingerprint is not None:
        if not isinstance(expected_fingerprint, str) or not HEX256.fullmatch(expected_fingerprint):
            raise ManifestError("Expected fingerprint must be 64 lowercase hexadecimal characters")
        if expected_fingerprint != manifest["fingerprint"]:
            mismatch.append("fingerprint differs from the expected release")
    for key, expected in (("game_version", game_version), ("converter_version", converter_version)):
        if expected is not None and label(expected, key) != manifest["metadata"][key]:
            mismatch.append(f"{key} differs from the expected release")
    if mod_ids is not None:
        expected = metadata("unused", "unused", mod_ids)["mod_ids"]
        if expected != manifest["metadata"]["mod_ids"]:
            mismatch.append("mod_ids differ from the expected release")
    directories = set()
    actual = {record["path"]: record for record in scan_payload(root, manifest_path, directories=directories)}
    wanted = {record["path"]: record for record in manifest["files"]}
    excluded = _relative_manifest(safe_absolute(root), safe_absolute(manifest_path))
    if excluded is not None and any(name.casefold() == excluded.casefold() for name in wanted):
        raise ManifestError("Manifest cannot list itself as a payload file")
    return VerificationResult(manifest["fingerprint"], len(wanted),
        tuple(sorted(wanted.keys() - actual.keys())),
        tuple(sorted(name for name in wanted.keys() & actual.keys() if wanted[name] != actual[name])),
        tuple(sorted(actual.keys() - wanted.keys())), tuple(mismatch),
        tuple(sorted(set(manifest["metadata"]["required_directories"]) - directories)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify"):
        sub = commands.add_parser(command)
        sub.add_argument("root", help="Directory containing the payload mod folders")
        sub.add_argument("--output" if command == "create" else "--manifest", required=True)
        for option in ("game-version", "converter-version"):
            sub.add_argument("--" + option, required=command == "create")
        sub.add_argument("--mod-id", action="append", dest="mod_ids", required=command == "create")
        if command == "verify":
            sub.add_argument("--expected-fingerprint")
        else:
            sub.add_argument("--required-dir", action="append", dest="required_directories",
                             help="Required relative directory (repeatable; includes empty folders)")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = create_manifest(args.root, args.output, game_version=args.game_version,
                                    converter_version=args.converter_version, mod_ids=args.mod_ids,
                                    required_directories=args.required_directories)
            print(f"READY: manifest created; {len(value['files'])} payload files; SHA256 {value['fingerprint']}")
            return 0
        result = verify_manifest(args.root, args.manifest, expected_fingerprint=args.expected_fingerprint,
                                 game_version=args.game_version, converter_version=args.converter_version, mod_ids=args.mod_ids)
        if result.ready:
            print(f"READY: {result.file_count} payload files match; SHA256 {result.fingerprint}")
            return 0
        print(f"MISMATCH: missing={len(result.missing)} changed={len(result.changed)} extra={len(result.extra)} metadata={len(result.metadata_mismatches)} missing-directories={len(result.missing_directories)}")
        for kind, values in (("missing", result.missing), ("changed", result.changed),
                             ("extra", result.extra), ("metadata", result.metadata_mismatches),
                             ("missing-directory", result.missing_directories)):
            for value in values:
                print(f"  {kind}: {value}")
        return 1
    except (ManifestError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())