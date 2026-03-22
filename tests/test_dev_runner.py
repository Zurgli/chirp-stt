import tempfile
import unittest
from pathlib import Path

from chirp.dev import _detect_changes, _should_watch, _snapshot_repo


class TestDevRunner(unittest.TestCase):
    def test_detect_changes_returns_added_file(self):
        changed = _detect_changes({}, {"src/chirp/main.py": (1, 10)})
        self.assertEqual(changed, "src/chirp/main.py")

    def test_detect_changes_returns_modified_file(self):
        changed = _detect_changes(
            {"src/chirp/main.py": (1, 10)},
            {"src/chirp/main.py": (2, 10)},
        )
        self.assertEqual(changed, "src/chirp/main.py")

    def test_should_watch_ignores_models_dir(self):
        root = Path("/repo")
        path = root / "src" / "chirp" / "assets" / "models" / "model.bin"
        self.assertFalse(_should_watch(path, root))

    def test_should_watch_ignores_virtualenv(self):
        root = Path("/repo")
        path = root / ".venv" / "Lib" / "site-packages" / "pkg.py"
        self.assertFalse(_should_watch(path, root))

    def test_should_watch_includes_python_and_toml(self):
        root = Path("/repo")
        self.assertTrue(_should_watch(root / "src" / "chirp" / "main.py", root))
        self.assertTrue(_should_watch(root / "config.toml", root))

    def test_snapshot_repo_filters_unwatched_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            watched = root / "src" / "chirp" / "main.py"
            watched.parent.mkdir(parents=True)
            watched.write_text("print('ok')", encoding="utf-8")

            ignored = root / "README.md"
            ignored.write_text("docs", encoding="utf-8")

            snapshot = _snapshot_repo(root)

            self.assertIn("src\\chirp\\main.py" if "\\" in str(next(iter(snapshot), "")) else "src/chirp/main.py", snapshot)
            self.assertNotIn("README.md", snapshot)


if __name__ == "__main__":
    unittest.main()
