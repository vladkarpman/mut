"""CLI commands for mutcli."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from dotenv import load_dotenv
from rich.console import Console
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
    from datetime import datetime

    from mutcli.core.config import ConfigLoader
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
    from mutcli.core.device_controller import DeviceController
    from mutcli.core.recorder import Recorder

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
        input()
    except KeyboardInterrupt:
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
    console.print(f"  Output: {stop_result.get('output_dir')}")
    console.print()
    console.print("[dim]Run 'mut stop' to generate YAML test file.[/dim]")


@app.command()
def stop(
    test_dir: Path | None = typer.Argument(
        None, help="Test directory (optional, uses most recent)"
    ),
) -> None:
    """Process recording and generate YAML test."""
    import json

    from mutcli.core.ai_analyzer import AIAnalyzer
    from mutcli.core.config import ConfigLoader
    from mutcli.core.frame_extractor import FrameExtractor
    from mutcli.core.step_analyzer import StepAnalyzer
    from mutcli.core.typing_detector import TypingDetector
    from mutcli.core.verification_suggester import VerificationSuggester
    from mutcli.core.yaml_generator import YAMLGenerator

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

    console.print("[blue]Processing recording...[/blue]")

    # Load touch events
    touch_events_path = recording_dir / "touch_events.json"
    if not touch_events_path.exists():
        console.print(f"[red]Error:[/red] touch_events.json not found in {recording_dir}")
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

    # Get screen dimensions for typing detection
    screen_height = touch_events[0].get("screen_height", 2400) if touch_events else 2400

    # 1. Detect typing sequences
    console.print("  [dim]Detecting typing patterns...[/dim]")
    typing_detector = TypingDetector(screen_height)
    typing_sequences = typing_detector.detect(touch_events)

    if typing_sequences:
        console.print(f"    Found {len(typing_sequences)} typing sequence(s)")
        # Ask user for typed text
        for seq in typing_sequences:
            text = typer.prompt(
                f"    What text was typed at step {seq.start_index + 1}?",
                default="",
            )
            seq.text = text if text else None

    # 2. Extract frames from video (if exists)
    video_path = recording_dir / "recording.mp4"
    screenshots_dir = recording_dir / "screenshots"
    if video_path.exists():
        console.print("  [dim]Extracting frames...[/dim]")
        extractor = FrameExtractor(video_path)
        extracted = extractor.extract_for_touches(touch_events, screenshots_dir)
        console.print(f"    Extracted {len(extracted)} frames")
    else:
        console.print("  [dim]No video found, skipping frame extraction[/dim]")

    # Get app package from config
    try:
        config = ConfigLoader.load(require_api_key=False)
        app_package = config.app or "com.example.app"
    except Exception:
        config = None
        app_package = "com.example.app"

    # 3. Analyze steps with AI (if API key available)
    analyzed_steps = []
    verifications = []

    try:
        if config and config.google_api_key:
            console.print("  [dim]Analyzing with AI...[/dim]")
            ai = AIAnalyzer(api_key=config.google_api_key)
            step_analyzer = StepAnalyzer(ai)
            analyzed_steps = step_analyzer.analyze_all(touch_events, screenshots_dir)

            suggester = VerificationSuggester(ai)
            verifications = suggester.suggest(analyzed_steps)

            element_count = sum(1 for s in analyzed_steps if s.element_text)
            console.print(f"    Extracted {element_count} element names")
            console.print(f"    Suggested {len(verifications)} verifications")
        else:
            console.print("  [dim]AI analysis skipped (no API key)[/dim]")
    except Exception as e:
        console.print(f"  [yellow]AI analysis skipped: {e}[/yellow]")

    # Derive test name from directory
    if test_dir is None:
        test_dir = recording_dir.parent
    test_name = test_dir.name

    # 4. Generate YAML
    console.print("  [dim]Generating YAML...[/dim]")
    generator = YAMLGenerator(name=test_name, app_package=app_package)
    generator.add_launch_app()

    if analyzed_steps:
        generator.generate_from_analysis(analyzed_steps, typing_sequences, verifications)
    else:
        # Fallback to coordinates
        for event in touch_events:
            generator.add_tap(event.get("x", 0), event.get("y", 0))

    generator.add_terminate_app()

    # Save YAML
    yaml_path = test_dir / "test.yaml"
    generator.save(yaml_path)

    # Show results
    console.print()
    console.print("[green]Test generated![/green]")
    console.print(f"  Output: {yaml_path}")
    console.print()
    console.print("[dim]Run with: mut run {yaml_path}[/dim]")


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
