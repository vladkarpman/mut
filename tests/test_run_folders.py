"""Tests for run folder creation."""

from datetime import datetime
from unittest.mock import patch


class TestRunFolderCreation:
    """Tests for timestamped run folder creation."""

    def test_creates_runs_directory(self, tmp_path):
        """Creates runs/ subdirectory if missing."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        run_folder = _create_run_folder(test_dir)

        assert (test_dir / "runs").exists()
        assert run_folder.parent == test_dir / "runs"

    def test_creates_timestamped_folder(self, tmp_path):
        """Creates folder with timestamp format."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        with patch("mutcli.cli.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 17, 14, 30, 25)
            run_folder = _create_run_folder(test_dir)

        assert run_folder.name == "2026-01-17_14-30-25"

    def test_run_folder_is_created(self, tmp_path):
        """Run folder directory actually exists."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        run_folder = _create_run_folder(test_dir)

        assert run_folder.exists()
        assert run_folder.is_dir()

    def test_handles_duplicate_timestamps(self, tmp_path):
        """Handles multiple calls with same timestamp gracefully."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        with patch("mutcli.cli.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 17, 14, 30, 25)
            run_folder1 = _create_run_folder(test_dir)
            run_folder2 = _create_run_folder(test_dir)

        # Should not crash - both return same folder with exist_ok=True
        assert run_folder1.exists()
        assert run_folder2.exists()
        assert run_folder1 == run_folder2
