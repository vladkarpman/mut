"""Analysis data save/load functionality.

Provides persistence for AI analysis results so:
1. If preview server fails, we don't lose work
2. We can reload and continue from where we left off
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mut.analysis_io")


@dataclass
class AnalysisData:
    """Analysis data for a test recording.

    Attributes:
        app_package: Android package name
        screen_width: Device screen width in pixels
        screen_height: Device screen height in pixels
        steps: List of step data dicts for approval UI
        created_at: ISO timestamp when analysis was created (optional)
        version: Schema version (default: 1)
    """

    app_package: str
    screen_width: int
    screen_height: int
    steps: list[dict[str, Any]]
    created_at: str | None = None
    version: int = 1


def save_analysis(data: AnalysisData, test_dir: Path) -> Path:
    """Save analysis data to JSON file.

    Args:
        data: AnalysisData to save
        test_dir: Directory to save analysis.json in

    Returns:
        Path to saved file
    """
    # Set created_at if not provided
    created_at = data.created_at
    if created_at is None:
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    json_data = {
        "version": data.version,
        "created_at": created_at,
        "app_package": data.app_package,
        "screen": {
            "width": data.screen_width,
            "height": data.screen_height,
        },
        "steps": data.steps,
    }

    output_path = test_dir / "analysis.json"
    with output_path.open("w") as f:
        json.dump(json_data, f, indent=2)

    logger.debug(f"Saved analysis to {output_path}")
    return output_path


def load_analysis(test_dir: Path) -> AnalysisData | None:
    """Load analysis data from JSON file.

    Args:
        test_dir: Directory containing analysis.json

    Returns:
        AnalysisData if file exists and is valid, None otherwise
    """
    analysis_path = test_dir / "analysis.json"

    if not analysis_path.exists():
        return None

    try:
        with analysis_path.open() as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in {analysis_path}: {e}")
        return None

    # Validate required fields
    required_fields = ["app_package", "screen", "steps"]
    for field in required_fields:
        if field not in json_data:
            logger.warning(f"Missing required field '{field}' in {analysis_path}")
            return None

    screen = json_data.get("screen", {})
    if "width" not in screen or "height" not in screen:
        logger.warning(f"Missing screen dimensions in {analysis_path}")
        return None

    return AnalysisData(
        app_package=json_data["app_package"],
        screen_width=screen["width"],
        screen_height=screen["height"],
        steps=json_data["steps"],
        created_at=json_data.get("created_at"),
        version=json_data.get("version", 1),
    )
