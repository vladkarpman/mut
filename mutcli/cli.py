"""CLI commands for mutcli."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from mutcli import __version__

if TYPE_CHECKING:
    from mutcli.core.executor import TestResult

# Load .env file from current directory or parent directories
load_dotenv()

app = typer.Typer(
    name="mut",
    help="Mobile UI Testing CLI - Run YAML-based mobile tests anywhere",
    no_args_is_help=True,
)
console = Console()


def _create_run_folder(test_dir: Path) -> Path:
    """Create timestamped run folder for test execution.

    Args:
        test_dir: Test directory (e.g., tests/my_test/)

    Returns:
        Path to created run folder (e.g., tests/my_test/runs/2026-01-17_14-30-25/)
    """
    runs_dir = test_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_folder = runs_dir / timestamp
    run_folder.mkdir(exist_ok=True)

    return run_folder


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"mut version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """mut - Mobile UI Testing CLI."""
    pass


@app.command()
def run(
    test_file: Path = typer.Argument(..., help="YAML test file to execute"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output directory"),
    junit: Path | None = typer.Option(None, "--junit", help="JUnit XML output path"),
) -> None:
    """Execute a YAML test file."""
    from mutcli.core.config import ConfigLoader, setup_logging
    from mutcli.core.device_controller import DeviceController
    from mutcli.core.executor import TestExecutor
    from mutcli.core.parser import ParseError, TestParser
    from mutcli.core.report import ReportGenerator

    # Check test file exists
    if not test_file.exists():
        console.print(f"[red]Error:[/red] Test file not found: {test_file}")
        raise typer.Exit(2)

    # Load config (API key required for AI-based testing)
    try:
        config = ConfigLoader.load(require_api_key=True)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    # Determine test directory from test file path
    test_dir = test_file.parent

    # Create run folder for this execution
    run_folder = _create_run_folder(test_dir)

    # Setup verbose logging if enabled
    if config.verbose:
        log_file = setup_logging(verbose=True, log_dir=run_folder)
        if log_file:
            console.print(f"[dim]Verbose logging → {log_file}[/dim]")

    # Override device from CLI
    if device:
        config.device = device

    # Determine device
    if not config.device:
        # Try to find a device
        devices_list = DeviceController.list_devices()
        if not devices_list:
            console.print("[red]Error:[/red] No devices found. Run 'mut devices' to check.")
            raise typer.Exit(2)
        config.device = devices_list[0]["id"]
        console.print(f"[dim]Using device: {config.device}[/dim]")

    # Parse test file
    try:
        test = TestParser.parse(test_file)
    except ParseError as e:
        console.print(f"[red]Parse error:[/red] {e}")
        raise typer.Exit(2)

    console.print(f"[blue]Running test:[/blue] {test_file}")

    # Execute test
    executor = TestExecutor(device_id=config.device, config=config)
    result = executor.execute_test(test)

    # Generate report
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Determine output directory
    if output:
        report_dir = output
    else:
        # Default: tests/{name}/reports/{timestamp}/
        report_dir = test_file.parent / "reports" / timestamp

    generator = ReportGenerator(report_dir)
    generator.generate_json(result)
    html_path = generator.generate_html(result)

    # Show result
    if result.status == "passed":
        console.print(f"[green]PASSED[/green] ({result.duration:.1f}s)")
    else:
        console.print(f"[red]FAILED[/red] ({result.duration:.1f}s)")
        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")

    console.print(f"\n[dim]Report: {html_path}[/dim]")

    # Generate JUnit if requested
    if junit:
        _generate_junit(result, junit)
        console.print(f"[dim]JUnit: {junit}[/dim]")

    # Exit code
    if result.status == "passed":
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


@app.command()
def record(
    name: str = typer.Argument(..., help="Test name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
    app: str | None = typer.Option(None, "--app", "-a", help="App package name"),
) -> None:
    """Start recording user interactions."""
    from mutcli.core.config import ConfigLoader, setup_logging
    from mutcli.core.device_controller import DeviceController
    from mutcli.core.recorder import Recorder

    # Load config for verbose setting
    try:
        config = ConfigLoader.load(require_api_key=False)
    except Exception:
        config = None

    # Determine device
    device_id = device
    if not device_id:
        devices_list = DeviceController.list_devices()
        if not devices_list:
            console.print("[red]Error:[/red] No devices found. Run 'mut devices' to check.")
            raise typer.Exit(2)
        device_id = devices_list[0]["id"]

    console.print(f"[blue]Starting recording:[/blue] {name}")
    console.print(f"[dim]Device: {device_id}[/dim]")
    if app:
        console.print(f"[dim]App: {app}[/dim]")
    console.print()

    # Create and start recorder
    recorder = Recorder(name=name, device_id=device_id)

    # Setup verbose logging after recorder is created (so we have the output directory)
    if config and config.verbose:
        log_file = setup_logging(verbose=True, log_dir=recorder.output_dir)
        if log_file:
            console.print(f"[dim]Verbose logging → {log_file}[/dim]")
    result = recorder.start()

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('error', 'Failed to start recording')}")
        raise typer.Exit(2)

    console.print("[green]Recording started![/green]")
    console.print("Interact with your device now.")
    console.print()

    # Wait for user input
    try:
        console.print("Press Enter when done recording...")
        console.print("[dim](or Ctrl+C to cancel)[/dim]")
        sys.stdout.flush()
        sys.stderr.flush()

        # Use select for more reliable input handling on Unix
        import select
        while True:
            # Check if stdin has data available (timeout 0.5s)
            readable, _, _ = select.select([sys.stdin], [], [], 0.5)
            if readable:
                sys.stdin.readline()
                break
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Recording interrupted[/yellow]")

    # Stop recording
    stop_result = recorder.stop()

    if not stop_result.get("success"):
        console.print(f"[red]Error:[/red] {stop_result.get('error', 'Failed to stop recording')}")
        raise typer.Exit(1)

    # Show results
    console.print()
    console.print("[green]Recording saved![/green]")
    console.print(f"  Events: {stop_result.get('event_count', 0)}")
    duration = stop_result.get("duration_seconds")
    if duration is not None:
        console.print(f"  Duration: {duration:.1f}s")
    console.print()

    # Automatically proceed to preview UI for approval
    _process_recording(recorder.output_dir / "recording", recorder.output_dir, name, app)


@app.command()
def stop(
    test_dir: Path | None = typer.Argument(
        None, help="Test directory (optional, uses most recent)"
    ),
) -> None:
    """Process recording and generate YAML test."""
    # Find recording directory
    recording_dir: Path
    if test_dir:
        recording_dir = test_dir / "recording"
        if not recording_dir.exists():
            # Maybe test_dir is the recording dir itself
            recording_dir = test_dir
    else:
        maybe_recording_dir = _find_most_recent_recording()
        if maybe_recording_dir is None:
            console.print("[red]Error:[/red] No recordings found in tests/ directory")
            console.print("\nRecord a test first with: mut record <name>")
            raise typer.Exit(2)
        recording_dir = maybe_recording_dir
        # Get parent (test_dir) from recording_dir
        test_dir = recording_dir.parent

    # Derive test name from directory
    test_name = test_dir.name

    _process_recording(recording_dir, test_dir, test_name)


def _process_recording(
    recording_dir: Path,
    test_dir: Path,
    test_name: str,
    app_package: str | None = None,
) -> None:
    """Process a recording and generate YAML test via approval UI.

    Pipeline:
    1. Check for existing analysis.json (recovery)
    2. Load touch_events.json
    3. Detect typing sequences
    4. Collapse steps (merge typing sequences)
    5. Extract frames for collapsed steps
    6. AI analysis on collapsed steps
    7. Save analysis.json
    8. Build preview_steps from analysis data
    9. Start preview server
    10. Generate YAML

    Args:
        recording_dir: Path to the recording directory (contains touch_events.json)
            Note: For flattened structure, this is the same as test_dir
        test_dir: Path to the test directory
        test_name: Name of the test
        app_package: App package name (optional, will try to detect)
    """
    import json

    from mutcli.core.ai_analyzer import AIAnalyzer
    from mutcli.core.analysis_io import load_analysis, save_analysis
    from mutcli.core.config import ConfigLoader
    from mutcli.core.frame_extractor import FrameExtractor
    from mutcli.core.step_analyzer import AnalyzedStep, StepAnalyzer
    from mutcli.core.step_collapsing import collapse_steps
    from mutcli.core.typing_detector import TypingDetector
    from mutcli.core.verification_suggester import VerificationSuggester

    console.print("[blue]Processing recording...[/blue]")

    # Get app package and config early (needed for analysis.json)
    if not app_package:
        try:
            config = ConfigLoader.load(require_api_key=False)
            app_package = config.app or "com.example.app"
        except Exception:
            config = None
            app_package = "com.example.app"
    else:
        try:
            config = ConfigLoader.load(require_api_key=False)
        except Exception:
            config = None

    # 1. Check for existing analysis.json (recovery feature)
    existing_analysis = load_analysis(test_dir)
    if existing_analysis:
        console.print("[dim]Found existing analysis.json, skipping AI analysis...[/dim]")
        # Use existing analysis data directly
        screen_width = existing_analysis.screen_width
        screen_height = existing_analysis.screen_height
        # Build preview_steps from saved analysis
        preview_steps = _build_preview_steps_from_analysis(existing_analysis, test_dir)
        # Get video duration for preview
        video_path = test_dir / "video.mp4"
        video_duration = "0:00"
        if video_path.exists():
            extractor = FrameExtractor(video_path)
            duration_secs = extractor.get_duration()
            if duration_secs > 0:
                mins = int(duration_secs // 60)
                secs = int(duration_secs % 60)
                video_duration = f"{mins}:{secs:02d}"
        # Skip to preview server (step 9)
        _start_preview_and_generate_yaml(
            preview_steps=preview_steps,
            test_name=test_name,
            app_package=app_package,
            recording_dir=test_dir,
            test_dir=test_dir,
            screen_width=screen_width,
            screen_height=screen_height,
            video_duration=video_duration,
            typing_sequences=[],  # Not needed for recovery
        )
        return

    # 2. Load touch events
    touch_events_path = test_dir / "touch_events.json"
    if not touch_events_path.exists():
        # Fall back to recording_dir for backward compatibility
        touch_events_path = recording_dir / "touch_events.json"
    if not touch_events_path.exists():
        console.print(f"[red]Error:[/red] touch_events.json not found in {test_dir}")
        console.print("\nMake sure recording completed successfully.")
        raise typer.Exit(2)

    try:
        with open(touch_events_path) as f:
            touch_events = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON in touch_events.json: {e}")
        raise typer.Exit(2)

    console.print(f"  Found {len(touch_events)} touch events")

    if not touch_events:
        console.print("[yellow]Warning:[/yellow] No touch events found in recording")
        console.print("The generated test will only contain app launch/terminate steps.")

    # Get screen dimensions for typing detection and preview
    screen_width = touch_events[0].get("screen_width", 1080) if touch_events else 1080
    screen_height = touch_events[0].get("screen_height", 2400) if touch_events else 2400

    # Load keyboard states if available (from ADB monitoring)
    keyboard_states_path = test_dir / "keyboard_states.json"
    keyboard_states: list[tuple[float, bool]] | None = None
    if keyboard_states_path.exists():
        try:
            with open(keyboard_states_path) as f:
                keyboard_states = [tuple(item) for item in json.load(f)]
            console.print(f"  Loaded {len(keyboard_states)} keyboard states")
        except Exception as e:
            console.print(f"  [dim]Could not load keyboard states: {e}[/dim]")

    # 3. Detect typing sequences
    console.print("  [dim]Detecting typing patterns...[/dim]")
    typing_detector = TypingDetector(screen_height, keyboard_states=keyboard_states)
    typing_sequences = typing_detector.detect(touch_events)

    if typing_sequences:
        console.print(f"    Found {len(typing_sequences)} typing sequence(s)")

    # 4. Collapse steps (merge typing sequences into single "type" steps)
    console.print("  [dim]Collapsing steps...[/dim]")
    collapsed_steps = collapse_steps(touch_events, typing_sequences)
    console.print(f"    {len(touch_events)} events -> {len(collapsed_steps)} steps")

    # 5. Extract frames for collapsed steps
    video_path = test_dir / "video.mp4"
    if not video_path.exists():
        # Fall back to recording_dir for backward compatibility
        video_path = recording_dir / "video.mp4"
    screenshots_dir = test_dir / "screenshots"
    video_duration = "0:00"
    if video_path.exists():
        console.print("  [dim]Extracting frames...[/dim]")
        extractor = FrameExtractor(video_path)
        extracted = extractor.extract_for_collapsed_steps(
            collapsed_steps, touch_events, screenshots_dir
        )
        console.print(f"    Extracted {len(extracted)} frames")
        # Get video duration
        duration_secs = extractor.get_duration()
        if duration_secs > 0:
            mins = int(duration_secs // 60)
            secs = int(duration_secs % 60)
            video_duration = f"{mins}:{secs:02d}"
    else:
        console.print("  [dim]No video found, skipping frame extraction[/dim]")

    # 6. AI analysis on collapsed steps (if API key available)
    analyzed_steps: list[AnalyzedStep] = []
    verifications_raw: list[dict] = []

    # Load ADB state data for enhanced analysis
    adb_data: dict = {}
    activity_path = test_dir / "activity_states.json"
    if activity_path.exists():
        try:
            with open(activity_path) as f:
                adb_data["activity_states"] = json.load(f)
        except Exception as e:
            console.print(f"  [dim]Could not load activity states: {e}[/dim]")

    window_path = test_dir / "window_states.json"
    if window_path.exists():
        try:
            with open(window_path) as f:
                adb_data["window_states"] = json.load(f)
        except Exception as e:
            console.print(f"  [dim]Could not load window states: {e}[/dim]")

    # keyboard_states already loaded earlier for typing detection
    if keyboard_states:
        adb_data["keyboard_states"] = keyboard_states

    if adb_data:
        console.print("  Loaded ADB state data for enhanced analysis")

    try:
        if config and config.google_api_key:
            ai = AIAnalyzer(api_key=config.google_api_key)
            step_analyzer = StepAnalyzer(ai)

            # Run async analysis with progress bar
            async def run_analysis() -> list[AnalyzedStep]:
                with Progress(
                    TextColumn("  Analyzing..."),
                    BarColumn(),
                    TextColumn("{task.percentage:>3.0f}%"),
                    console=console,
                ) as progress:
                    task = progress.add_task("", total=len(collapsed_steps))

                    def on_progress(completed: int, total: int) -> None:
                        progress.update(task, completed=completed)

                    return await step_analyzer.analyze_collapsed_steps_parallel(
                        collapsed_steps,
                        screenshots_dir,
                        on_progress,
                        adb_data=adb_data if adb_data else None,
                    )

            analyzed_steps = asyncio.run(run_analysis())

            suggester = VerificationSuggester(ai)
            verifications_obj = suggester.suggest(analyzed_steps)
            # Convert to dicts for preview server
            verifications_raw = [
                {"description": v.description, "after_step": v.after_step_index, "enabled": True}
                for v in verifications_obj
            ]

            element_count = sum(1 for s in analyzed_steps if s.element_text)
            console.print(f"    Extracted {element_count} element names")
            console.print(f"    Suggested {len(verifications_raw)} verifications")
        else:
            console.print("  [dim]AI analysis skipped (no API key)[/dim]")
    except Exception as e:
        console.print(f"  [yellow]AI analysis skipped: {e}[/yellow]")

    # 7. Build preview steps from collapsed steps and analysis
    preview_steps = _build_preview_steps(
        collapsed_steps, analyzed_steps, screenshots_dir, test_dir
    )

    # 8. Save analysis.json for recovery
    if analyzed_steps or collapsed_steps:
        analysis_data = _build_analysis_data(
            collapsed_steps=collapsed_steps,
            analyzed_steps=analyzed_steps,
            app_package=app_package,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        save_analysis(analysis_data, test_dir)
        console.print("  [dim]Saved analysis.json[/dim]")

    # 9. Start preview server and generate YAML
    _start_preview_and_generate_yaml(
        preview_steps=preview_steps,
        test_name=test_name,
        app_package=app_package,
        recording_dir=test_dir,
        test_dir=test_dir,
        screen_width=screen_width,
        screen_height=screen_height,
        video_duration=video_duration,
        typing_sequences=typing_sequences,
        verifications_raw=verifications_raw,
    )


def _build_preview_steps(
    collapsed_steps: list,
    analyzed_steps: list,
    screenshots_dir: Path,
    test_dir: Path,
) -> list:
    """Build preview steps from collapsed steps and analysis.

    Args:
        collapsed_steps: List of CollapsedStep objects
        analyzed_steps: List of AnalyzedStep objects (may be empty)
        screenshots_dir: Directory containing screenshots
        test_dir: Test directory for path references

    Returns:
        List of PreviewStep objects
    """
    from mutcli.core.preview_server import PreviewStep

    preview_steps: list[PreviewStep] = []

    # Add initial state (app launched) as step 0
    initial_screenshot = screenshots_dir / "step_001_before.png"
    preview_steps.append(PreviewStep(
        index=0,
        action="app_launched",
        element_text=None,
        coordinates=(0, 0),
        screenshot_path=str(initial_screenshot) if initial_screenshot.exists() else None,
        enabled=True,
        before_description="Initial app state after launch",
        after_description="",
        timestamp=0.0,
        frames=(
            {"before": "recording/screenshots/step_001_before.png"}
            if initial_screenshot.exists() else {}
        ),
    ))

    # Build a lookup from step index to analyzed step
    analyzed_lookup = {a.index: a for a in analyzed_steps}

    # Add collapsed steps
    for step in collapsed_steps:
        step_num = step.index
        step_str = f"{step_num:03d}"

        # Find matching analyzed step if available
        analyzed = analyzed_lookup.get(step_num - 1)  # analyzed_steps use 0-based index
        element_text = analyzed.element_text if analyzed else None
        before_desc = analyzed.before_description if analyzed else ""
        after_desc = analyzed.after_description if analyzed else ""
        suggested_verification = analyzed.suggested_verification if analyzed else None

        # Get coordinates based on action type
        if step.coordinates:
            coords = (step.coordinates["x"], step.coordinates["y"])
        elif step.start:
            coords = (step.start["x"], step.start["y"])
        else:
            coords = (0, 0)

        # Screenshots use step_NNN_before.png and step_NNN_after.png
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        # Build frames dict
        frames: dict[str, str | None] = {}
        if before_path.exists():
            frames["before"] = f"recording/screenshots/step_{step_str}_before.png"
        if after_path.exists():
            frames["after"] = f"recording/screenshots/step_{step_str}_after.png"

        preview_steps.append(PreviewStep(
            index=step_num,
            action=step.action,
            element_text=element_text,
            coordinates=coords,
            screenshot_path=str(before_path) if before_path.exists() else None,
            enabled=True,
            before_description=before_desc,
            after_description=after_desc,
            direction=step.direction,
            timestamp=step.timestamp,
            frames=frames,
            suggested_verification=suggested_verification,
        ))

    return preview_steps


def _build_preview_steps_from_analysis(
    analysis_data,
    test_dir: Path,
) -> list:
    """Build preview steps from saved analysis.json data.

    Args:
        analysis_data: AnalysisData loaded from analysis.json
        test_dir: Test directory for path references

    Returns:
        List of PreviewStep objects
    """
    from mutcli.core.preview_server import PreviewStep

    preview_steps: list[PreviewStep] = []
    screenshots_dir = test_dir / "screenshots"

    # Add initial state (app launched) as step 0
    initial_screenshot = screenshots_dir / "step_001_before.png"
    preview_steps.append(PreviewStep(
        index=0,
        action="app_launched",
        element_text=None,
        coordinates=(0, 0),
        screenshot_path=str(initial_screenshot) if initial_screenshot.exists() else None,
        enabled=True,
        before_description="Initial app state after launch",
        after_description="",
        timestamp=0.0,
        frames=(
            {"before": "recording/screenshots/step_001_before.png"}
            if initial_screenshot.exists() else {}
        ),
    ))

    # Add steps from analysis data
    for step_data in analysis_data.steps:
        step_num = step_data.get("index", 0)
        step_str = f"{step_num:03d}"

        coords = step_data.get("coordinates", (0, 0))
        if isinstance(coords, dict):
            coords = (coords.get("x", 0), coords.get("y", 0))
        elif isinstance(coords, list):
            coords = tuple(coords) if len(coords) >= 2 else (0, 0)

        # Screenshots use step_NNN_before.png and step_NNN_after.png
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        # Build frames dict
        frames: dict[str, str | None] = {}
        if before_path.exists():
            frames["before"] = f"recording/screenshots/step_{step_str}_before.png"
        if after_path.exists():
            frames["after"] = f"recording/screenshots/step_{step_str}_after.png"

        preview_steps.append(PreviewStep(
            index=step_num,
            action=step_data.get("action", "tap"),
            element_text=step_data.get("element_text"),
            coordinates=coords,
            screenshot_path=str(before_path) if before_path.exists() else None,
            enabled=step_data.get("enabled", True),
            before_description=step_data.get("before_description", ""),
            after_description=step_data.get("after_description", ""),
            direction=step_data.get("direction"),
            timestamp=step_data.get("timestamp", 0.0),
            frames=frames,
            suggested_verification=step_data.get("suggested_verification"),
        ))

    return preview_steps


def _build_analysis_data(
    collapsed_steps: list,
    analyzed_steps: list,
    app_package: str,
    screen_width: int,
    screen_height: int,
):
    """Build AnalysisData from collapsed steps and analysis.

    Args:
        collapsed_steps: List of CollapsedStep objects
        analyzed_steps: List of AnalyzedStep objects
        app_package: Android package name
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels

    Returns:
        AnalysisData object
    """
    from mutcli.core.analysis_io import AnalysisData

    # Build a lookup from step index to analyzed step
    analyzed_lookup = {a.index: a for a in analyzed_steps}

    steps_data = []
    for step in collapsed_steps:
        # Get coordinates based on action type
        if step.coordinates:
            coords = {"x": step.coordinates["x"], "y": step.coordinates["y"]}
        elif step.start:
            coords = {"x": step.start["x"], "y": step.start["y"]}
        else:
            coords = {"x": 0, "y": 0}

        # Find matching analyzed step (analyzed_steps use 0-based index)
        analyzed = analyzed_lookup.get(step.index - 1)

        step_dict = {
            "index": step.index,
            "action": step.action,
            "timestamp": step.timestamp,
            "coordinates": coords,
            "direction": step.direction,
            "element_text": analyzed.element_text if analyzed else None,
            "before_description": analyzed.before_description if analyzed else "",
            "after_description": analyzed.after_description if analyzed else "",
            "suggested_verification": analyzed.suggested_verification if analyzed else None,
            "enabled": True,
        }

        # Add type-specific fields
        if step.action == "type":
            step_dict["tap_count"] = step.tap_count
            step_dict["text"] = step.text
        elif step.action == "swipe" and step.end:
            step_dict["end_coordinates"] = {"x": step.end["x"], "y": step.end["y"]}
        elif step.action == "long_press" and step.duration_ms:
            step_dict["duration_ms"] = step.duration_ms

        steps_data.append(step_dict)

    return AnalysisData(
        app_package=app_package,
        screen_width=screen_width,
        screen_height=screen_height,
        steps=steps_data,
    )


def _start_preview_and_generate_yaml(
    preview_steps: list,
    test_name: str,
    app_package: str,
    recording_dir: Path,
    test_dir: Path,
    screen_width: int,
    screen_height: int,
    video_duration: str,
    typing_sequences: list | None = None,
    verifications_raw: list | None = None,
) -> None:
    """Start preview server and generate YAML on approval.

    Args:
        preview_steps: List of PreviewStep objects
        test_name: Name of the test
        app_package: Android package name
        recording_dir: Directory containing video/screenshots
        test_dir: Directory to save test.yaml
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        video_duration: Video duration string (e.g., "1:30")
        typing_sequences: List of typing sequences (for YAML generation)
        verifications_raw: List of verification dicts for preview
    """
    from mutcli.core.preview_server import PreviewServer
    from mutcli.core.yaml_generator import YAMLGenerator

    if typing_sequences is None:
        typing_sequences = []
    if verifications_raw is None:
        verifications_raw = []

    console.print()
    console.print("[blue]Opening approval UI in browser...[/blue]")
    console.print("[dim]Review and edit steps, then click 'Generate YAML'[/dim]")

    server = PreviewServer(
        steps=preview_steps,
        verifications=verifications_raw,
        test_name=test_name,
        app_package=app_package,
        recording_dir=recording_dir,
        screen_width=screen_width,
        screen_height=screen_height,
        video_duration=video_duration,
    )

    result = server.start_and_wait()

    if result is None or not result.approved:
        console.print("[yellow]Cancelled[/yellow] - no YAML generated")
        return

    # Generate YAML from approved steps
    console.print()
    console.print("[blue]Generating YAML from approved steps...[/blue]")

    generator = YAMLGenerator(name=test_name, app_package=app_package)
    generator.add_launch_app()

    # Get enabled steps from approval result (skip app_launched which is index 0)
    enabled_steps = [
        s for s in result.steps
        if s.get("enabled", True) and s.get("action") != "app_launched"
    ]

    for step_data in enabled_steps:
        action = step_data.get("action", "tap")
        element = step_data.get("element_text")
        coords = step_data.get("coordinates", [0, 0])

        if action == "tap":
            if element:
                generator.add_tap(0, 0, element=element)
            else:
                generator.add_tap(coords[0], coords[1])
        elif action == "type":
            # Type action - text field was already tapped in a separate step
            text = step_data.get("text", "")
            submit = step_data.get("submit", False)
            if text:
                generator.add_type(text, submit=submit)
        elif action == "swipe":
            direction = step_data.get("direction", "up")
            generator.add_swipe(direction)
        elif action == "long_press":
            # Long press is not directly supported in YAML format
            # For now, generate a tap with the element/coordinates
            # TODO: Add proper long_press support to YAML format
            if element:
                generator.add_tap(0, 0, element=element)
            else:
                generator.add_tap(coords[0], coords[1])

    # Add approved verifications
    for v in result.verifications:
        if v.get("enabled", True) and v.get("description"):
            generator.add_verify_screen(v["description"])

    generator.add_terminate_app()

    # Save YAML
    yaml_path = test_dir / "test.yaml"
    generator.save(yaml_path)

    # Show results
    console.print()
    console.print("[green]Test generated![/green]")
    console.print(f"  Output: {yaml_path}")
    console.print()
    console.print(f"[dim]Run with: mut run {yaml_path}[/dim]")


def _find_most_recent_recording() -> Path | None:
    """Find the most recent recording directory.

    Looks for directories in tests/ that contain recording/touch_events.json.

    Returns:
        Path to the recording directory (tests/{name}/recording), or None if not found.
    """
    tests_dir = Path("tests")
    if not tests_dir.exists():
        return None

    candidates: list[Path] = []
    for d in tests_dir.iterdir():
        if d.is_dir():
            recording_dir = d / "recording"
            touch_events = recording_dir / "touch_events.json"
            if touch_events.exists():
                candidates.append(recording_dir)

    if not candidates:
        return None

    # Sort by modification time, return most recent
    return max(candidates, key=lambda p: p.stat().st_mtime)


@app.command()
def devices() -> None:
    """List connected devices."""
    from mutcli.core.device_controller import DeviceController

    try:
        devices_list = DeviceController.list_devices()

        if not devices_list:
            console.print("[yellow]No devices found[/yellow]")
            console.print("\nEnsure your device is connected:")
            console.print("  Android: adb devices")
            raise typer.Exit(1)

        table = Table(title="Connected Devices")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Status", style="yellow")

        for device in devices_list:
            table.add_row(
                device.get("id", "unknown"),
                device.get("name", "unknown"),
                device.get("status", "unknown"),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def report(
    results_dir: Path = typer.Argument(..., help="Results directory with report.json"),
) -> None:
    """Generate HTML report from JSON results."""
    import json

    from mutcli.core.executor import StepResult, TestResult
    from mutcli.core.report import ReportGenerator

    if not results_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {results_dir}")
        raise typer.Exit(1)

    json_file = results_dir / "report.json"
    if not json_file.exists():
        console.print(f"[red]Error:[/red] report.json not found in {results_dir}")
        raise typer.Exit(1)

    console.print(f"Generating report from: {json_file}")

    # Load JSON data
    with open(json_file) as f:
        data = json.load(f)

    # Convert to TestResult
    step_results = [
        StepResult(
            step_number=s.get("number", i + 1),
            action=s.get("action", "unknown"),
            status=s.get("status", "passed"),
            duration=_parse_duration(s.get("duration", "0.0s")),
            error=s.get("error"),
        )
        for i, s in enumerate(data.get("steps", []))
    ]

    result = TestResult(
        name=data.get("test", "unknown"),
        status=data.get("status", "passed"),
        duration=_parse_duration(data.get("duration", "0.0s")),
        steps=step_results,
        error=data.get("error"),
    )

    # Generate HTML
    generator = ReportGenerator(results_dir)
    html_path = generator.generate_html(result)

    console.print(f"[green]Generated:[/green] {html_path}")


def _parse_duration(duration_str: str) -> float:
    """Parse duration string to float.

    Args:
        duration_str: Duration string like "1.2s" or "0.5s"

    Returns:
        Duration in seconds as float
    """
    if isinstance(duration_str, (int, float)):
        return float(duration_str)
    return float(duration_str.rstrip("s"))


def _generate_junit(result: TestResult, path: Path) -> None:
    """Generate JUnit XML report.

    Args:
        result: Test execution result
        path: Output path for JUnit XML
    """
    from xml.etree.ElementTree import Element, SubElement, tostring

    testsuite = Element(
        "testsuite",
        {
            "name": result.name,
            "tests": str(len(result.steps)),
            "failures": str(sum(1 for s in result.steps if s.status == "failed")),
            "time": str(result.duration),
        },
    )

    for step in result.steps:
        testcase = SubElement(
            testsuite,
            "testcase",
            {
                "name": f"Step {step.step_number}: {step.action}",
                "time": str(step.duration),
            },
        )

        if step.status == "failed":
            failure = SubElement(testcase, "failure", {"message": step.error or "Failed"})
            failure.text = step.error or ""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(tostring(testsuite))


if __name__ == "__main__":
    app()
