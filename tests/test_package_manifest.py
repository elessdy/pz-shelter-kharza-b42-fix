"""Offline payload-integrity tests; temporary fixtures only, no game/private assets."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import package_manifest as pm


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pz-manifest-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "mods"
        self.root.mkdir()
        self.put("Alpha/42/mod.info", b"id=Alpha\n")
        self.put("Alpha/common/media/maps/cell.lotpack", b"\x00\x01original-map\xff")
        self.output = self.base / "release.manifest.json"

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def create(self, **changes):
        options = dict(game_version="42.21", converter_version="shelter-converter-v1", mod_ids=["Alpha"])
        options.update(changes)
        return pm.create_manifest(self.root, self.output, **options)

    def record(self, name):
        return {"path": name, "size": 0, "sha256": hashlib.sha256(b"").hexdigest()}

    def with_records(self, records):
        meta = pm.metadata("42.21", "v1", ["Alpha"])
        return {"schema_version": 1, "metadata": meta, "files": records,
                "fingerprint": pm.fingerprint(meta, records)}

    def test_roundtrip_and_binary_digest(self):
        value = self.create()
        result = pm.verify_manifest(self.root, self.output)
        self.assertTrue(result.ready)
        self.assertEqual(result.file_count, 2)
        self.assertEqual(value["files"][1]["sha256"], hashlib.sha256(b"\x00\x01original-map\xff").hexdigest())

    def test_deterministic_across_host_root_mtime_order_and_manifest_location(self):
        first = self.create(mod_ids=["Zulu", "Alpha"])
        other = self.base / "different-host-layout"
        other.mkdir()
        for path in reversed(sorted(self.root.rglob("*"))):
            if path.is_file():
                destination = other / path.relative_to(self.root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(path.read_bytes())
                os.utime(destination, (1000000000, 1000000000))
        inside = other / "portable.json"
        second = pm.create_manifest(other, inside, game_version="42.21", converter_version="shelter-converter-v1", mod_ids=["Alpha", "Zulu"])
        self.assertEqual(first, second)
        self.assertEqual(self.output.read_bytes(), inside.read_bytes())
        self.assertNotIn(str(self.base), inside.read_text())
        self.assertTrue(pm.verify_manifest(other, inside).ready)

    def test_missing_changed_same_size_and_extra_reported_together(self):
        self.create()
        (self.root / "Alpha/42/mod.info").unlink()
        self.put("Alpha/common/media/maps/cell.lotpack", b"\x00\x01modified-map\xff")
        self.put("Alpha/extra.txt", b"unexpected")
        result = pm.verify_manifest(self.root, self.output)
        self.assertFalse(result.ready)
        self.assertEqual(result.missing, ("Alpha/42/mod.info",))
        self.assertEqual(result.changed, ("Alpha/common/media/maps/cell.lotpack",))
        self.assertEqual(result.extra, ("Alpha/extra.txt",))

    def test_only_supplied_in_root_manifest_is_excluded(self):
        self.output = self.root / "release.json"
        self.create()
        self.put("other.manifest.json", b"{}")
        result = pm.verify_manifest(self.root, self.output)
        self.assertEqual(result.extra, ("other.manifest.json",))

    def test_recreating_in_root_manifest_is_stable(self):
        self.output = self.root / "release.json"
        first = self.create()
        self.assertEqual(first, self.create())
        self.assertTrue(pm.verify_manifest(self.root, self.output).ready)

    def test_refuses_overwriting_an_ordinary_payload(self):
        self.output = self.root / "Alpha/42/mod.info"
        original = self.output.read_bytes()
        with self.assertRaises(pm.ManifestError):
            self.create()
        self.assertEqual(self.output.read_bytes(), original)

    def test_expected_identity_and_fingerprint(self):
        value = self.create()
        self.assertTrue(pm.verify_manifest(self.root, self.output, expected_fingerprint=value["fingerprint"],
                        game_version="42.21", converter_version="shelter-converter-v1", mod_ids=["Alpha"]).ready)
        result = pm.verify_manifest(self.root, self.output, expected_fingerprint="0" * 64,
                    game_version="42.22", converter_version="v2", mod_ids=["Other"])
        self.assertEqual(len(result.metadata_mismatches), 4)
        self.assertFalse(result.ready)

    def test_changed_manifest_fingerprint_is_rejected(self):
        value = self.create()
        value["files"][0]["sha256"] = "0" * 64
        self.output.write_text(json.dumps(value))
        with self.assertRaisesRegex(pm.ManifestError, "fingerprint does not match"):
            pm.verify_manifest(self.root, self.output)

    def test_metadata_participates_in_fingerprint(self):
        value = self.create()
        changed = dict(value["metadata"], converter_version="v2")
        self.assertNotEqual(value["fingerprint"], pm.fingerprint(changed, value["files"]))

    def test_duplicate_json_keys_top_level_and_nested(self):
        value = self.create()
        text = json.dumps(value)
        for bad in [text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
                    text.replace('"size": 9', '"size": 9, "size": 9')]:
            self.assertNotEqual(bad, text)
            self.output.write_text(bad)
            with self.assertRaisesRegex(pm.ManifestError, "Duplicate JSON key"):
                pm.load_manifest(self.output)

    def test_unsafe_and_nonportable_paths(self):
        for path in ["", "../escape", "A/../escape", "/absolute", "C:/absolute", "C:relative", r"A\file",
                     "//server/share", "A//file", "A/./file", "A/", "A/trailing.", "A/trailing ",
                     "A/CON.txt", "A/Lpt1", "A/COM\u00b9", "A/colon:ads", "A/what?", "A/\x00file", "A/\nfile"]:
            with self.subTest(path=path), self.assertRaises(pm.ManifestError):
                pm.validate_manifest(self.with_records([self.record(path)]))

    def test_duplicate_case_paths_and_conflicting_parent_case(self):
        for paths in [["A/file", "A/file"], ["A/file", "a/FILE"], ["A/one", "a/two"],
                      ["A", "A/file"], ["A/file", "A"], ["Stra\u00dfe/file", "STRASSE/file"]]:
            with self.subTest(paths=paths), self.assertRaises(pm.ManifestError):
                pm.validate_manifest(self.with_records([self.record(path) for path in paths]))

    def test_unicode_normalization_is_portable_and_manifest_is_canonical(self):
        self.put("Alpha/cafe\u0301.txt", b"unicode")
        value = self.create()
        self.assertIn("Alpha/caf\u00e9.txt", [f["path"] for f in value["files"]])
        self.assertTrue(pm.verify_manifest(self.root, self.output).ready)
        with self.assertRaises(pm.ManifestError):
            pm.validate_manifest(self.with_records([self.record("A/cafe\u0301.txt")]))

    def test_filesystem_case_collision_is_rejected(self):
        root = self.base / "case-root"
        root.mkdir()
        (root / "Thing").write_bytes(b"one")
        context = mock.MagicMock()
        context.__enter__.return_value = [SimpleNamespace(name="Thing"), SimpleNamespace(name="thing")]
        with mock.patch.object(pm.os, "scandir", return_value=context):
            with self.assertRaisesRegex(pm.ManifestError, "Duplicate case"):
                pm.scan_payload(root)

    def test_empty_directories_do_not_change_file_fingerprint(self):
        first = self.create()
        (self.root / "Alpha/common/media/maps").mkdir(exist_ok=True)
        (self.root / "extra-empty-directory").mkdir()
        self.assertTrue(pm.verify_manifest(self.root, self.output).ready)
        self.assertEqual(first["fingerprint"], self.create()["fingerprint"])

    def test_required_empty_directories_are_hashed_and_verified(self):
        first = self.create()
        required = "Alpha/common/media/empty-map-discovery"
        path = self.root / required
        path.mkdir()
        value = self.create(required_directories=[required])
        self.assertEqual(value["files"], first["files"])
        self.assertNotEqual(value["fingerprint"], first["fingerprint"])
        self.assertEqual(value["metadata"]["required_directories"], [required])
        self.assertTrue(pm.verify_manifest(self.root, self.output).ready)
        path.rmdir()
        result = pm.verify_manifest(self.root, self.output)
        self.assertFalse(result.ready)
        self.assertEqual(result.missing_directories, (required,))
        self.assertEqual((result.missing, result.changed, result.extra), ((), (), ()))
        path.write_bytes(b"not a directory")
        result = pm.verify_manifest(self.root, self.output)
        self.assertEqual(result.missing_directories, (required,))
        self.assertEqual(result.extra, (required,))

    def test_create_requires_declared_directories_to_exist(self):
        with self.assertRaisesRegex(pm.ManifestError, "Missing required directories"):
            self.create(required_directories=["Alpha/common/missing"])
        self.assertFalse(self.output.exists())

    def test_required_directory_declarations_reject_unsafe_or_conflicting_paths(self):
        for paths in [["../escape"], ["/absolute"], ["A", "a"], ["A/one", "a/two"],
                      ["Alpha/common", "Alpha/common"], "not-a-list"]:
            with self.subTest(paths=paths), self.assertRaises(pm.ManifestError):
                self.create(required_directories=paths)
        for name in ["Alpha/42/mod.info", "alpha/common"]:
            value = self.create()
            value["metadata"]["required_directories"] = [name]
            value["fingerprint"] = pm.fingerprint(value["metadata"], value["files"])
            with self.subTest(name=name), self.assertRaises(pm.ManifestError):
                pm.validate_manifest(value)

    def test_required_directories_are_canonical_sorted_and_allow_parent_child(self):
        value = self.create(required_directories=["Alpha/common/media/maps", "Alpha"])
        self.assertEqual(value["metadata"]["required_directories"], ["Alpha", "Alpha/common/media/maps"])
        self.assertTrue(pm.verify_manifest(self.root, self.output).ready)
        value["metadata"]["required_directories"].reverse()
        value["fingerprint"] = pm.fingerprint(value["metadata"], value["files"])
        with self.assertRaisesRegex(pm.ManifestError, "canonical sorted"):
            pm.validate_manifest(value)

    def test_required_directory_cli_reports_missing(self):
        required = "Alpha/common/media/empty-map-discovery"
        path = self.root / required
        path.mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = pm.main(["create", str(self.root), "--output", str(self.output),
                "--game-version", "42.21", "--converter-version", "v1", "--mod-id", "Alpha",
                "--required-dir", required, "--required-dir", "Alpha"])
        self.assertEqual(result, 0, out.getvalue())
        path.rmdir()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = pm.main(["verify", str(self.root), "--manifest", str(self.output)])
        self.assertEqual(result, 1)
        self.assertIn("missing-directory: " + required, out.getvalue())

    def test_invalid_file_record_types_and_unknown_fields(self):
        for alteration in [{"size": True}, {"size": -1}, {"sha256": "A" * 64}, {"sha256": None}, {"host_path": "/tmp/x"}]:
            record = self.record("A/file")
            record.update(alteration)
            with self.subTest(alteration=alteration), self.assertRaises(pm.ManifestError):
                pm.validate_manifest(self.with_records([record]))

    def test_unknown_manifest_field_and_schema_boolean(self):
        value = self.create()
        for bad in [dict(value, created_utc="2026-01-01"), dict(value, schema_version=True)]:
            with self.assertRaises(pm.ManifestError):
                pm.validate_manifest(bad)

    def test_metadata_rejects_duplicates_and_hostpaths(self):
        for options in [dict(mod_ids=["Alpha", "alpha"]), dict(game_version="C:\\Game"),
                        dict(converter_version="/home/builder"), dict(mod_ids=[]), dict(mod_ids=["\\Alpha"])]:
            with self.subTest(options=options), self.assertRaises(pm.ManifestError):
                self.create(**options)

    def test_manifest_cannot_list_itself(self):
        self.output = self.root / "release.json"
        value = self.with_records([self.record("release.json")])
        self.output.write_text(json.dumps(value))
        with self.assertRaisesRegex(pm.ManifestError, "list itself"):
            pm.verify_manifest(self.root, self.output)

    def test_reparse_point_rejected_even_when_reported_as_regular_directory(self):
        original = Path.lstat
        def lstat(path):
            if path == self.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=pm.REPARSE_POINT)
            return original(path)
        with mock.patch.object(Path, "lstat", lstat), self.assertRaisesRegex(pm.ManifestError, "reparse"):
            pm.scan_payload(self.root)

    def test_symlink_mode_rejected_without_opening_target(self):
        path = self.root / "Alpha/42/mod.info"
        fake = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        with mock.patch.object(Path, "lstat", return_value=fake), mock.patch.object(pm.os, "open") as opened:
            with self.assertRaisesRegex(pm.ManifestError, "Symlink/reparse"):
                pm._hash_file(path)
            opened.assert_not_called()

    def test_manifest_reparse_file_is_rejected_before_json_read(self):
        self.create()
        original = Path.lstat
        def lstat(path):
            if path == self.output:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_file_attributes=pm.REPARSE_POINT)
            return original(path)
        with mock.patch.object(Path, "lstat", lstat), self.assertRaisesRegex(pm.ManifestError, "reparse"):
            pm.load_manifest(self.output)

    def symlink(self, link, target, is_directory=False):
        try:
            os.symlink(target, link, target_is_directory=is_directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Host does not permit symlink creation: {exc}")

    def test_symlink_payload_file_rejected(self):
        target = self.base / "external"
        target.write_bytes(b"external")
        self.symlink(self.root / "link", target)
        with self.assertRaisesRegex(pm.ManifestError, "Symlink/reparse"):
            self.create()

    def test_symlink_directory_and_root_ancestor_rejected(self):
        target = self.base / "external-dir"
        target.mkdir()
        self.symlink(self.root / "link", target, True)
        with self.assertRaisesRegex(pm.ManifestError, "Symlink/reparse"):
            pm.scan_payload(self.root)
        with self.assertRaisesRegex(pm.ManifestError, "Symlink/reparse"):
            pm.scan_payload(self.root / "link")

    def test_symlink_manifest_rejected(self):
        self.create()
        link = self.base / "manifest-link"
        self.symlink(link, self.output)
        with self.assertRaisesRegex(pm.ManifestError, "Symlink/reparse"):
            pm.verify_manifest(self.root, link)

    def test_hashing_detects_concurrent_file_change(self):
        path = self.root / "Alpha/42/mod.info"
        before = path.lstat()
        changed = SimpleNamespace(**{key: getattr(before, key) for key in
            ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")})
        changed.st_mtime_ns += 1
        with mock.patch.object(pm, "_safe_stat", side_effect=[before, changed]):
            with self.assertRaisesRegex(pm.ManifestError, "changed while hashing"):
                pm._hash_file(path)

    def test_cli_ready_mismatch_and_error_exit_codes(self):
        script = Path(pm.__file__)
        command = [sys.executable, "-B", str(script)]
        created = subprocess.run(command + ["create", str(self.root), "--output", str(self.output),
            "--game-version", "42.21", "--converter-version", "v1", "--mod-id", "Alpha"], capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("READY:", created.stdout)
        verified = subprocess.run(command + ["verify", str(self.root), "--manifest", str(self.output)], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.put("Alpha/extra", b"new")
        mismatch = subprocess.run(command + ["verify", str(self.root), "--manifest", str(self.output)], capture_output=True, text=True)
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn("extra: Alpha/extra", mismatch.stdout)
        self.output.write_text("not JSON")
        invalid = subprocess.run(command + ["verify", str(self.root), "--manifest", str(self.output)], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("ERROR:", invalid.stderr)

    def test_main_does_not_silently_accept_bad_expected_fingerprint(self):
        self.create()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            result = pm.main(["verify", str(self.root), "--manifest", str(self.output), "--expected-fingerprint", "bad"])
        self.assertEqual(result, 2)
        self.assertIn("Expected fingerprint", err.getvalue())


if __name__ == "__main__":
    unittest.main()