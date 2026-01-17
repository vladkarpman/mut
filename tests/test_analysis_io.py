"""Tests for analysis save/load functionality."""

import json
from datetime import UTC, datetime, timedelta

from mutcli.core.analysis_io import AnalysisData, load_analysis, save_analysis


class TestAnalysisData:
    """Test AnalysisData dataclass."""

    def test_creation_with_all_fields(self):
        """AnalysisData should store all fields correctly."""
        steps = [{"index": 0, "element_text": "Submit"}]
        data = AnalysisData(
            app_package="com.example.app",
            screen_width=1080,
            screen_height=2400,
            steps=steps,
            created_at="2026-01-17T21:57:12Z",
            version=1,
        )

        assert data.app_package == "com.example.app"
        assert data.screen_width == 1080
        assert data.screen_height == 2400
        assert data.steps == steps
        assert data.created_at == "2026-01-17T21:57:12Z"
        assert data.version == 1

    def test_creation_with_defaults(self):
        """AnalysisData should use defaults for optional fields."""
        data = AnalysisData(
            app_package="com.test",
            screen_width=720,
            screen_height=1280,
            steps=[],
        )

        assert data.created_at is None
        assert data.version == 1


class TestSaveAnalysis:
    """Test save_analysis function."""

    def test_save_creates_valid_json(self, tmp_path):
        """Should create valid JSON file with correct structure."""
        data = AnalysisData(
            app_package="com.example.app",
            screen_width=1080,
            screen_height=2400,
            steps=[
                {"index": 0, "element_text": "Login"},
                {"index": 1, "element_text": "Submit"},
            ],
            created_at="2026-01-17T21:57:12Z",
        )

        result_path = save_analysis(data, tmp_path)

        assert result_path == tmp_path / "analysis.json"
        assert result_path.exists()

        # Verify JSON structure
        with result_path.open() as f:
            saved = json.load(f)

        assert saved["version"] == 1
        assert saved["created_at"] == "2026-01-17T21:57:12Z"
        assert saved["app_package"] == "com.example.app"
        assert saved["screen"]["width"] == 1080
        assert saved["screen"]["height"] == 2400
        assert len(saved["steps"]) == 2
        assert saved["steps"][0]["element_text"] == "Login"

    def test_save_sets_created_at_if_not_provided(self, tmp_path):
        """Should set created_at to current UTC time if not provided."""
        data = AnalysisData(
            app_package="com.test",
            screen_width=720,
            screen_height=1280,
            steps=[],
        )

        before = datetime.now(UTC)
        save_analysis(data, tmp_path)
        after = datetime.now(UTC)

        with (tmp_path / "analysis.json").open() as f:
            saved = json.load(f)

        # Parse the saved timestamp
        created_at = datetime.fromisoformat(saved["created_at"].replace("Z", "+00:00"))

        # Allow 1 second tolerance since format truncates microseconds
        assert before - timedelta(seconds=1) <= created_at <= after + timedelta(seconds=1)

    def test_save_preserves_existing_created_at(self, tmp_path):
        """Should not overwrite existing created_at."""
        original_time = "2025-06-15T10:30:00Z"
        data = AnalysisData(
            app_package="com.test",
            screen_width=720,
            screen_height=1280,
            steps=[],
            created_at=original_time,
        )

        save_analysis(data, tmp_path)

        with (tmp_path / "analysis.json").open() as f:
            saved = json.load(f)

        assert saved["created_at"] == original_time


class TestLoadAnalysis:
    """Test load_analysis function."""

    def test_load_returns_analysis_data(self, tmp_path):
        """Should load and return AnalysisData from valid JSON."""
        json_data = {
            "version": 1,
            "created_at": "2026-01-17T21:57:12Z",
            "app_package": "com.example.app",
            "screen": {"width": 1080, "height": 2400},
            "steps": [{"index": 0, "element_text": "Button"}],
        }

        analysis_file = tmp_path / "analysis.json"
        with analysis_file.open("w") as f:
            json.dump(json_data, f)

        result = load_analysis(tmp_path)

        assert result is not None
        assert result.app_package == "com.example.app"
        assert result.screen_width == 1080
        assert result.screen_height == 2400
        assert result.steps == [{"index": 0, "element_text": "Button"}]
        assert result.created_at == "2026-01-17T21:57:12Z"
        assert result.version == 1

    def test_load_returns_none_if_missing(self, tmp_path):
        """Should return None if analysis.json doesn't exist."""
        result = load_analysis(tmp_path)

        assert result is None

    def test_load_returns_none_on_invalid_json(self, tmp_path):
        """Should return None if JSON is invalid."""
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text("not valid json {{{")

        result = load_analysis(tmp_path)

        assert result is None

    def test_load_returns_none_on_missing_required_fields(self, tmp_path):
        """Should return None if required fields are missing."""
        json_data = {
            "version": 1,
            # Missing app_package, screen, steps
        }

        analysis_file = tmp_path / "analysis.json"
        with analysis_file.open("w") as f:
            json.dump(json_data, f)

        result = load_analysis(tmp_path)

        assert result is None


class TestRoundtrip:
    """Test save/load roundtrip."""

    def test_roundtrip_preserves_data(self, tmp_path):
        """Should preserve all data through save/load cycle."""
        original = AnalysisData(
            app_package="com.example.roundtrip",
            screen_width=1440,
            screen_height=3200,
            steps=[
                {
                    "index": 0,
                    "element_text": "Search",
                    "before_description": "Home screen",
                    "after_description": "Search opened",
                },
                {
                    "index": 1,
                    "element_text": None,
                    "before_description": "Search bar",
                    "after_description": "Typing",
                },
            ],
            created_at="2026-01-17T12:00:00Z",
            version=1,
        )

        save_analysis(original, tmp_path)
        loaded = load_analysis(tmp_path)

        assert loaded is not None
        assert loaded.app_package == original.app_package
        assert loaded.screen_width == original.screen_width
        assert loaded.screen_height == original.screen_height
        assert loaded.steps == original.steps
        assert loaded.created_at == original.created_at
        assert loaded.version == original.version
