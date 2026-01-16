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
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip AI verifications"),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video recording"),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
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

    # Load config
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
) -> None:
    """Start recording user interactions."""
    console.print(f"[blue]Starting recording:[/blue] {name}")

    # TODO: Implement recording
    # from mutcli.core.recorder import Recorder
    # recorder = Recorder(name=name, device=device)
    # recorder.start()

    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def stop() -> None:
    """Stop recording and generate YAML test."""
    console.print("[blue]Stopping recording...[/blue]")

    # TODO: Implement stop recording
    # from mutcli.core.recorder import Recorder
    # recorder = Recorder.load_state()
    # recorder.stop()
    # recorder.open_approval_ui()

    console.print("[yellow]Not yet implemented[/yellow]")


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
    if not results_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {results_dir}")
        raise typer.Exit(1)

    json_file = results_dir / "report.json"
    if not json_file.exists():
        console.print(f"[red]Error:[/red] report.json not found in {results_dir}")
        raise typer.Exit(1)

    console.print(f"[blue]Generating report from:[/blue] {json_file}")

    # TODO: Implement report generation
    # from mutcli.core.report_generator import ReportGenerator
    # generator = ReportGenerator()
    # html_path = generator.generate(json_file)
    # console.print(f"[green]Generated:[/green] {html_path}")

    console.print("[yellow]Not yet implemented[/yellow]")


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
