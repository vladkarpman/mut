"""CLI commands for mutcli."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
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
    video: bool = typer.Option(
        True, "--video/--no-video", "-v", help="Record video during test"
    ),
    ai_analysis: bool = typer.Option(
        True, "--ai/--no-ai", "-a", help="AI analysis of all steps (enabled by default)"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed step-by-step output"),
) -> None:
    """Execute a YAML test file."""
    from mutcli.core.config import ConfigLoader, setup_logging
    from mutcli.core.console_reporter import ConsoleReporter
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

    # Determine device and get device info
    devices_list = DeviceController.list_devices()
    if not config.device:
        if not devices_list:
            console.print("[red]Error:[/red] No devices found. Run 'mut devices' to check.")
            raise typer.Exit(2)
        config.device = devices_list[0]["id"]

    device_info = next((d for d in devices_list if d["id"] == config.device), None)
    device_display = f"{device_info['name']} ({config.device})" if device_info else config.device

    # Parse test file
    try:
        test = TestParser.parse(test_file)
    except ParseError as e:
        console.print(f"[red]Parse error:[/red] {e}")
        raise typer.Exit(2)

    # Calculate step counts
    setup_count = len(test.setup)
    main_count = len(test.steps)
    teardown_count = len(test.teardown)
    total_steps = setup_count + main_count + teardown_count

    # Show test summary panel
    test_name = test_dir.name
    app_name = test.config.app or "unknown"
    step_summary = f"{total_steps} steps"
    if setup_count or teardown_count:
        parts = []
        if setup_count:
            parts.append(f"setup: {setup_count}")
        parts.append(f"main: {main_count}")
        if teardown_count:
            parts.append(f"teardown: {teardown_count}")
        step_summary = f"{total_steps} ({', '.join(parts)})"

    panel_content = f"[dim]Test:[/dim]   {test_name}\n"
    panel_content += f"[dim]App:[/dim]    {app_name}\n"
    panel_content += f"[dim]Steps:[/dim]  {step_summary}"
    console.print(Panel(panel_content, border_style="blue", padding=(0, 1)))
    console.print()

    console.print(f"[dim]Device: {device_display}[/dim]")

    # Generate report
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Determine output directory
    if output:
        report_dir = output
    else:
        # Default: tests/{name}/reports/{timestamp}/
        report_dir = test_file.parent / "reports" / timestamp

    # Setup ScrcpyService if video recording requested
    scrcpy = None
    if video:
        from mutcli.core.scrcpy_service import ScrcpyService

        console.print("[dim]Connecting for video recording...[/dim]")
        scrcpy = ScrcpyService(config.device)
        if not scrcpy.connect():
            console.print("[yellow]Warning:[/yellow] Could not connect scrcpy, video disabled")
            scrcpy = None

    # Execute test with live output
    console.print()

    # Create live reporter for step-by-step output
    reporter = ConsoleReporter(test_name, total_steps, console=console)

    try:
        executor = TestExecutor(
            device_id=config.device,
            config=config,
            scrcpy=scrcpy,
            output_dir=report_dir,
            reporter=reporter,
        )

        reporter.start()
        result = executor.execute_test(test, record_video=video and scrcpy is not None)
        reporter.finish(result.status, result.duration)

        # AI analysis of all steps (if requested)
        if ai_analysis and result.steps:
            from mutcli.core.ai_analyzer import AIAnalyzer
            from mutcli.core.step_verifier import StepVerifier

            console.print()
            analyzer = AIAnalyzer()
            verifier = StepVerifier(analyzer)

            # Build step dicts for analysis
            step_dicts = [
                {
                    "action": s.action,
                    "target": s.target,
                    "description": s.description,
                    "status": s.status,
                    "error": s.error,
                    "screenshot_before": s.screenshot_before,
                    "screenshot_after": s.screenshot_after,
                    "details": s.details,
                }
                for s in result.steps
            ]

            # Run parallel analysis with progress bar
            with Progress(
                TextColumn("[blue]AI analysis...[/blue]"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
            ) as progress:
                task = progress.add_task("", total=len(step_dicts))

                def on_progress(completed: int, total: int) -> None:
                    progress.update(task, completed=completed)

                analyses = asyncio.run(
                    verifier.analyze_all_steps_parallel(
                        step_dicts,
                        on_progress=on_progress,
                        app_package=test.config.app,
                        test_name=test_name,
                    )
                )

            # Populate AI fields in StepResult
            for step, analysis in zip(result.steps, analyses):
                step.ai_verified = analysis.verified
                step.ai_outcome = analysis.outcome_description
                step.ai_suggestion = analysis.suggestion

    finally:
        # Disconnect scrcpy if it was connected
        if scrcpy:
            scrcpy.disconnect()

    # Check for source video from recording session
    source_video = test_file.parent / "video.mp4"
    generator = ReportGenerator(
        report_dir,
        source_video_path=source_video if source_video.exists() else None,
    )
    generator.generate_json(result)
    html_path = generator.generate_html(result)

    # Show report path (result status already shown by reporter)
    console.print()
    console.print(f"[dim]Report: {html_path}[/dim]")

    # Generate JUnit if requested
    if junit:
        _generate_junit(result, junit)
        console.print(f"[dim]JUnit: {junit}[/dim]")

    # Exit code
    if result.status == "passed":
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


def _print_step_results(steps: list, total: int) -> None:
    """Print all step results in verbose mode.

    Args:
        steps: List of StepResult objects
        total: Total number of steps
    """
    for step in steps:
        status_icon = "[green]✓[/green]" if step.status == "passed" else "[red]✗[/red]"
        step_info = f"[{step.step_number}/{total}] {status_icon} {step.action}"
        if step.target:
            step_info += f" '{step.target}'"
        step_info += f" [dim]({step.duration:.2f}s)[/dim]"
        console.print(step_info)
        if step.status == "failed" and step.error:
            console.print(f"    [red]Error:[/red] {step.error}")


def _print_failed_step(step, total: int) -> None:
    """Print details of a failed step.

    Args:
        step: The failed StepResult
        total: Total number of steps
    """
    console.print()
    console.print(f"[red]✗ Failed at step {step.step_number}/{total}[/red]")
    action_info = f"  Action: {step.action}"
    if step.target:
        action_info += f" '{step.target}'"
    console.print(action_info)
    if step.error:
        console.print(f"  Error: {step.error}")


@app.command()
def record(
    name: str = typer.Argument(..., help="Test name"),
    app: str = typer.Option(
        ..., "--app", "-a", help="App package name (required for UI element capture)"
    ),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
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

    # Determine device and get device info for display
    device_id = device
    devices_list = DeviceController.list_devices()
    if not device_id:
        if not devices_list:
            console.print("[red]Error:[/red] No devices found. Run 'mut devices' to check.")
            raise typer.Exit(2)
        device_id = devices_list[0]["id"]

    device_info = next((d for d in devices_list if d["id"] == device_id), None)
    device_display = f"{device_info['name']} ({device_id})" if device_info else device_id

    # Suppress noisy myscrcpy library logs
    logging.getLogger("myscrcpy").setLevel(logging.WARNING)

    # Create and start recorder
    recorder = Recorder(name=name, device_id=device_id, app_package=app)

    # Setup verbose logging after recorder is created (so we have the output directory)
    if config and config.verbose:
        log_file = setup_logging(verbose=True, log_dir=recorder.output_dir)
        if log_file:
            console.print(f"[dim]Verbose logging → {log_file}[/dim]")
    result = recorder.start()

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('error', 'Failed to start recording')}")
        raise typer.Exit(2)

    # Display info panel
    content = f"[dim]Device:[/dim]  {device_display}\n"
    content += f"[dim]App:[/dim]     {app}\n"
    content += f"[dim]Output:[/dim]  {result['output_dir']}"
    panel = Panel(
        content,
        title=f"[bold]Recording: {name}[/bold]",
        border_style="blue",
    )
    console.print(panel)

    # Status and prompt
    console.print()
    console.print("🎬 [green]Recording...[/green] interact with your device")
    console.print()
    console.print("┌─────────────────────────┐")
    console.print("│  Press Ctrl+C to stop   │")
    console.print("└─────────────────────────┘")

    # Wait for Ctrl+C
    try:
        import select
        while True:
            select.select([sys.stdin], [], [], 0.5)
    except (KeyboardInterrupt, EOFError):
        console.print()

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
def analyze(
    test_name_or_path: str = typer.Argument(..., help="Test name or path to analyze"),
) -> None:
    """Analyze recording and generate YAML test.

    Processes an existing recording by extracting frames, running AI analysis,
    and opening the approval UI to generate a YAML test file.

    Examples:
        mut analyze calculator-test    # Looks in tests/calculator-test/
        mut analyze ./my-tests/foo     # Uses path directly
    """
    # Check if it's a path or a test name
    path = Path(test_name_or_path)

    if path.exists():
        # Direct path provided
        test_dir = path
        test_name = path.name
    else:
        # Try as test name under tests/
        test_dir = Path("tests") / test_name_or_path
        test_name = test_name_or_path

        if not test_dir.exists():
            console.print(f"[red]Error:[/red] Test not found: {test_name_or_path}")
            console.print(f"  Tried: {path}")
            console.print(f"  Tried: {test_dir}")
            console.print("\nRecord a test first with: mut record <name>")
            raise typer.Exit(2)

    # Check for touch_events.json - first in test_dir, then in recording/
    touch_events_path = test_dir / "touch_events.json"
    recording_dir = test_dir  # Default: flat structure

    if not touch_events_path.exists():
        # Try recording subdirectory (old structure)
        recording_subdir = test_dir / "recording"
        if recording_subdir.exists() and (recording_subdir / "touch_events.json").exists():
            recording_dir = recording_subdir
        else:
            console.print(f"[red]Error:[/red] No recording found in {test_dir}")
            console.print("Missing touch_events.json - recording may not have completed.")
            raise typer.Exit(2)

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

    # Load screen dimensions from screen_size.json (created by recorder)
    screen_size_path = test_dir / "screen_size.json"
    if screen_size_path.exists():
        try:
            with open(screen_size_path) as f:
                screen_size = json.load(f)
                screen_width = screen_size.get("width", 1080)
                screen_height = screen_size.get("height", 2400)
            console.print(f"  Loaded screen size: {screen_width}x{screen_height}")
        except Exception as e:
            console.print(f"  [dim]Could not load screen size: {e}[/dim]")
            screen_width = 1080
            screen_height = 2400
    else:
        # Fallback to defaults
        screen_width = 1080
        screen_height = 2400

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

    # UI hierarchy dumps disabled - they caused timing issues where element data
    # from wrong screen state was provided to AI, leading to incorrect analysis.
    # AI vision analysis of screenshots is more reliable.

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
            # Convert to dicts for preview server (disabled by default, user opts in)
            verifications_raw = [
                {"description": v.description, "after_step": v.after_step_index, "enabled": False}
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

    # Build a lookup from step index to analyzed step
    analyzed_lookup = {a.index: a for a in analyzed_steps}

    # Add collapsed steps
    for step in collapsed_steps:
        step_num = step.index
        step_str = f"{step_num:03d}"

        # Find matching analyzed step if available
        analyzed = analyzed_lookup.get(step_num - 1)  # analyzed_steps use 0-based index
        element_text = analyzed.element_text if analyzed else None
        if analyzed:
            action_desc = analyzed.action_description
        else:
            action_desc = _build_default_action_description(step.action, element_text)
        before_desc = analyzed.before_description if analyzed else ""
        after_desc = analyzed.after_description if analyzed else ""
        suggested_verification = analyzed.suggested_verification if analyzed else None
        scroll_to_target = analyzed.scroll_to_target if analyzed else None

        # Get coordinates based on action type
        if step.coordinates:
            coords = (step.coordinates["x"], step.coordinates["y"])
        elif step.start:
            coords = (step.start["x"], step.start["y"])
        else:
            coords = (0, 0)

        # Get end coordinates for swipes
        end_coords: tuple[int, int] | None = None
        if step.action == "swipe" and step.end:
            end_coords = (step.end["x"], step.end["y"])

        # Screenshots use step_NNN_before.png, step_NNN_touch.png, step_NNN_after.png
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        touch_path = screenshots_dir / f"step_{step_str}_touch.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        # Build frames dict
        frames: dict[str, str | None] = {}
        if before_path.exists():
            frames["before"] = f"screenshots/step_{step_str}_before.png"
        if touch_path.exists():
            frames["action"] = f"screenshots/step_{step_str}_touch.png"
        if after_path.exists():
            frames["after"] = f"screenshots/step_{step_str}_after.png"

        preview_steps.append(PreviewStep(
            index=step_num,
            action=step.action,
            element_text=element_text,
            coordinates=coords,
            screenshot_path=str(before_path) if before_path.exists() else None,
            enabled=True,
            action_description=action_desc,
            before_description=before_desc,
            after_description=after_desc,
            direction=step.direction,
            timestamp=step.timestamp,
            frames=frames,
            suggested_verification=suggested_verification,
            scroll_to_target=scroll_to_target,
            end_coordinates=end_coords,
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

    # Add steps from analysis data
    for step_data in analysis_data.steps:
        step_num = step_data.get("index", 0)
        step_str = f"{step_num:03d}"

        coords = step_data.get("coordinates", (0, 0))
        if isinstance(coords, dict):
            coords = (coords.get("x", 0), coords.get("y", 0))
        elif isinstance(coords, list):
            coords = tuple(coords) if len(coords) >= 2 else (0, 0)

        # Get end coordinates for swipes (from analysis.json end_coordinates field)
        end_coords: tuple[int, int] | None = None
        if step_data.get("action") == "swipe":
            end_data = step_data.get("end_coordinates")
            if isinstance(end_data, dict):
                end_coords = (end_data.get("x", 0), end_data.get("y", 0))
            elif isinstance(end_data, list) and len(end_data) >= 2:
                end_coords = tuple(end_data)

        # Screenshots use step_NNN_before.png, step_NNN_touch.png, step_NNN_after.png
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        touch_path = screenshots_dir / f"step_{step_str}_touch.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        # Build frames dict
        frames: dict[str, str | None] = {}
        if before_path.exists():
            frames["before"] = f"screenshots/step_{step_str}_before.png"
        if touch_path.exists():
            frames["action"] = f"screenshots/step_{step_str}_touch.png"
        if after_path.exists():
            frames["after"] = f"screenshots/step_{step_str}_after.png"

        # Get action_description from data or build default
        action_desc = step_data.get("action_description") or _build_default_action_description(
            step_data.get("action", "tap"), step_data.get("element_text")
        )

        preview_steps.append(PreviewStep(
            index=step_num,
            action=step_data.get("action", "tap"),
            element_text=step_data.get("element_text"),
            coordinates=coords,
            screenshot_path=str(before_path) if before_path.exists() else None,
            enabled=step_data.get("enabled", True),
            action_description=action_desc,
            before_description=step_data.get("before_description", ""),
            after_description=step_data.get("after_description", ""),
            direction=step_data.get("direction"),
            timestamp=step_data.get("timestamp", 0.0),
            frames=frames,
            suggested_verification=step_data.get("suggested_verification"),
            scroll_to_target=step_data.get("scroll_to_target"),
            end_coordinates=end_coords,
        ))

    return preview_steps


def _build_default_action_description(action: str, element_text: str | None) -> str:
    """Build a default action description based on action type and element.

    Args:
        action: The action type (tap, swipe, long_press, type)
        element_text: The element text if available

    Returns:
        Human-readable action description like "User taps on 5"
    """
    if action == "tap":
        if element_text:
            return f"User taps on {element_text}"
        return "User taps on element"
    elif action == "swipe":
        return "User swipes"
    elif action == "long_press":
        if element_text:
            return f"User long-presses on {element_text}"
        return "User long-presses on element"
    elif action == "type":
        return "User types in text field"
    else:
        return f"User performs {action}"


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

        # Build default action description if not from AI
        default_action_desc = _build_default_action_description(
            step.action, analyzed.element_text if analyzed else None
        )

        step_dict = {
            "index": step.index,
            "action": step.action,
            "timestamp": step.timestamp,
            "coordinates": coords,
            "direction": step.direction,
            "element_text": analyzed.element_text if analyzed else None,
            "action_description": analyzed.action_description if analyzed else default_action_desc,
            "before_description": analyzed.before_description if analyzed else "",
            "after_description": analyzed.after_description if analyzed else "",
            "suggested_verification": analyzed.suggested_verification if analyzed else None,
            "scroll_to_target": analyzed.scroll_to_target if analyzed else None,
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
    console.print("[dim]Waiting for approval... (Ctrl+C to cancel)[/dim]")

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

    generator = YAMLGenerator(
        name=test_name,
        app_package=app_package,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    generator.add_launch_app()

    # Build verification map: step_index -> verification description (only enabled ones)
    verification_map: dict[int, str] = {}
    for v in result.verifications:
        if v.get("enabled", True) and v.get("description"):
            after_step = v.get("after_step")
            if after_step is not None:
                verification_map[after_step] = v["description"]

    # Get enabled steps from approval result (skip app_launched which is index 0)
    enabled_steps = [
        s for s in result.steps
        if s.get("enabled", True) and s.get("action") != "app_launched"
    ]

    for step_data in enabled_steps:
        action = step_data.get("action", "tap")
        element = step_data.get("element_text")
        coords = step_data.get("coordinates", {})
        step_index = step_data.get("index")
        description = step_data.get("action_description")

        # Get verification for this step if approved
        verification = verification_map.get(step_index) if step_index is not None else None

        # Convert coords to tuple format
        coords_tuple = None
        if isinstance(coords, dict) and "x" in coords and "y" in coords:
            coords_tuple = (coords["x"], coords["y"])
        elif isinstance(coords, (list, tuple)) and len(coords) >= 2:
            coords_tuple = (coords[0], coords[1])

        if action == "tap":
            generator.add_rich_tap(
                element=element,
                coords=coords_tuple,
                description=description,
                verification=verification,
            )
        elif action == "type":
            # Type action - text field was already tapped in a separate step
            text = step_data.get("text", "")
            submit = step_data.get("submit", False)
            if text:
                generator.add_type(text, submit=submit)
        elif action == "swipe":
            direction = step_data.get("direction", "up")
            # Calculate distance from start/end coordinates
            distance_str = None
            end_coords = step_data.get("end_coordinates", {})
            if isinstance(end_coords, dict) and coords_tuple:
                start_x, start_y = coords_tuple
                end_x = end_coords.get("x", start_x)
                end_y = end_coords.get("y", start_y)
                if direction in ("up", "down") and screen_height:
                    distance_pct = abs(end_y - start_y) / screen_height * 100
                    distance_str = f"{round(distance_pct)}%"
                elif direction in ("left", "right") and screen_width:
                    distance_pct = abs(end_x - start_x) / screen_width * 100
                    distance_str = f"{round(distance_pct)}%"
            generator.add_swipe(direction, distance=distance_str, description=description)
        elif action == "long_press":
            # Long press is not directly supported in YAML format
            # For now, generate a tap with the element/coordinates
            # TODO: Add proper long_press support to YAML format
            generator.add_rich_tap(
                element=element,
                coords=coords_tuple,
                description=description,
                verification=verification,
            )

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


@app.command()
def preview(
    test_name_or_path: str = typer.Argument(..., help="Test name or path to preview"),
) -> None:
    """Open approval UI for an existing recording.

    Opens the approval UI to view and edit test steps from a previous recording.
    Uses the existing analysis.json file and always renders with the latest
    approval UI template (ensuring bug fixes and improvements are applied).

    Examples:
        mut preview calculator-test    # Looks in tests/calculator-test/
        mut preview ./my-tests/foo     # Uses path directly
    """
    from mutcli.core.analysis_io import load_analysis
    from mutcli.core.preview_server import PreviewServer

    # Resolve test directory
    test_dir = Path(test_name_or_path)
    if not test_dir.exists():
        test_dir = Path("tests") / test_name_or_path

    if not test_dir.exists():
        console.print(f"[red]Error:[/red] Test not found: {test_name_or_path}")
        console.print(f"  Tried: {Path(test_name_or_path)} and tests/{test_name_or_path}")
        raise typer.Exit(1)

    # Load analysis.json
    analysis_path = test_dir / "analysis.json"
    if not analysis_path.exists():
        console.print(f"[red]Error:[/red] No analysis.json found in {test_dir}")
        console.print("  Run 'mut analyze' first to create the analysis")
        raise typer.Exit(1)

    analysis = load_analysis(test_dir)
    if analysis is None:
        console.print("[red]Error:[/red] Failed to load analysis.json")
        raise typer.Exit(1)

    test_name = test_dir.name
    app_package = analysis.app_package
    screen_width = analysis.screen_width
    screen_height = analysis.screen_height

    # Build preview steps from analysis
    preview_steps = _build_preview_steps_from_analysis(analysis, test_dir)

    # Calculate video duration
    steps_data = analysis.steps
    if steps_data:
        max_ts = max(s.get("timestamp", 0) for s in steps_data)
        mins = int((max_ts + 2) // 60)
        secs = int((max_ts + 2) % 60)
        video_duration = f"{mins}:{secs:02d}"
    else:
        video_duration = "0:00"

    # Build verifications from preview steps (disabled by default, user opts in)
    verifications = [
        {"description": ps.suggested_verification, "after_step": ps.index, "enabled": False}
        for ps in preview_steps
        if ps.suggested_verification
    ]

    console.print(f"[blue]Opening approval UI for:[/blue] {test_name}")
    console.print(f"  Steps: {len(preview_steps)}")
    console.print(f"  Verifications: {len(verifications)} suggested")
    console.print(f"  Screen: {screen_width}x{screen_height}")
    console.print()
    console.print("[dim]Review and edit steps, then click 'Generate YAML'[/dim]")
    console.print("[dim]Waiting for approval... (Ctrl+C to cancel)[/dim]")

    from mutcli.core.yaml_generator import YAMLGenerator

    server = PreviewServer(
        steps=preview_steps,
        verifications=verifications,
        test_name=test_name,
        app_package=app_package,
        recording_dir=test_dir,
        screen_width=screen_width,
        screen_height=screen_height,
        video_duration=video_duration,
    )

    result = server.start_and_wait()

    if result is None or not result.approved:
        console.print("[yellow]Cancelled[/yellow] - no YAML generated")
        return

    # Generate YAML from approved steps with rich details
    console.print()
    console.print("[blue]Generating YAML from approved steps...[/blue]")

    generator = YAMLGenerator(
        name=test_name,
        app_package=app_package,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    generator.add_launch_app()

    # Create lookup from preview_steps for rich data (by index)
    preview_lookup = {ps.index: ps for ps in preview_steps}

    # Filter to enabled steps, excluding app_launched
    # Use actual step index from data, not enumeration position
    enabled_indices = []
    for step in result.steps:
        if step.get("enabled", True) and step.get("action") != "app_launched":
            step_index = step.get("index")
            if step_index is not None:
                enabled_indices.append(step_index)

    # Build verification map from approval result (only enabled ones)
    verification_map: dict[int, str] = {}
    for v in result.verifications:
        if v.get("enabled", False) and v.get("description"):
            after_step = v.get("after_step")
            if after_step is not None:
                verification_map[after_step] = v["description"]

    for idx in enabled_indices:
        preview_step = preview_lookup.get(idx)
        if not preview_step:
            continue

        action = preview_step.action
        element = preview_step.element_text
        coords = preview_step.coordinates
        description = preview_step.action_description
        # Only include verification if user enabled it in approval UI
        verification = verification_map.get(idx)

        if action == "tap":
            generator.add_rich_tap(
                element=element,
                coords=coords,
                description=description,
                verification=verification,
            )
        elif action == "type":
            text = preview_step.text or ""
            generator.add_type(text=text)
            if verification:
                generator.add_verify_screen(verification)
        elif action == "swipe":
            direction = preview_step.direction or "up"
            # Calculate distance from start/end coordinates
            distance_str = None
            if coords and preview_step.end_coordinates:
                start_x, start_y = coords
                end_x, end_y = preview_step.end_coordinates
                if direction in ("up", "down") and screen_height:
                    distance_pct = abs(end_y - start_y) / screen_height * 100
                    distance_str = f"{round(distance_pct)}%"
                elif direction in ("left", "right") and screen_width:
                    distance_pct = abs(end_x - start_x) / screen_width * 100
                    distance_str = f"{round(distance_pct)}%"
            generator.add_swipe(direction=direction, distance=distance_str, description=description)
            if verification:
                generator.add_verify_screen(verification)
        elif action == "long_press":
            generator.add_rich_tap(
                element=element,
                coords=coords,
                description=description,
                verification=verification,
            )

    generator.add_terminate_app()

    yaml_path = test_dir / "test.yaml"
    generator.save(yaml_path)

    console.print(f"[green]Generated:[/green] {yaml_path}")
    console.print()
    console.print(f"[dim]Run with: mut run {yaml_path}[/dim]")


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
