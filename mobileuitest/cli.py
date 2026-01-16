"""CLI commands for mobileuitest."""

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from mobileuitest import __version__

# Load .env file from current directory or parent directories
load_dotenv()

app = typer.Typer(
    name="mobileuitest",
    help="Mobile UI Testing CLI - Run YAML-based mobile tests anywhere",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"mobileuitest version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit"
    ),
) -> None:
    """mobileuitest - Mobile UI Testing CLI."""
    pass


@app.command()
def run(
    test_file: Path = typer.Argument(..., help="YAML test file to execute"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output directory"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip AI verifications"),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video recording"),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
) -> None:
    """Execute a YAML test file."""
    if not test_file.exists():
        console.print(f"[red]Error:[/red] Test file not found: {test_file}")
        raise typer.Exit(1)

    console.print(f"[blue]Running test:[/blue] {test_file}")

    # TODO: Implement test execution
    # from mobileuitest.core.test_executor import TestExecutor
    # executor = TestExecutor(device=device, no_ai=no_ai, no_video=no_video)
    # result = executor.run(test_file)

    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def record(
    name: str = typer.Argument(..., help="Test name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
) -> None:
    """Start recording user interactions."""
    console.print(f"[blue]Starting recording:[/blue] {name}")

    # TODO: Implement recording
    # from mobileuitest.core.recorder import Recorder
    # recorder = Recorder(name=name, device=device)
    # recorder.start()

    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def stop() -> None:
    """Stop recording and generate YAML test."""
    console.print("[blue]Stopping recording...[/blue]")

    # TODO: Implement stop recording
    # from mobileuitest.core.recorder import Recorder
    # recorder = Recorder.load_state()
    # recorder.stop()
    # recorder.open_approval_ui()

    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def devices() -> None:
    """List connected devices."""
    from mobileuitest.core.device_controller import DeviceController

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
    # from mobileuitest.core.report_generator import ReportGenerator
    # generator = ReportGenerator()
    # html_path = generator.generate(json_file)
    # console.print(f"[green]Generated:[/green] {html_path}")

    console.print("[yellow]Not yet implemented[/yellow]")


if __name__ == "__main__":
    app()
