"""Live console output for test execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.text import Text


@dataclass
class StepDisplay:
    """Display state for a single step."""

    step_num: int
    action: str
    target: str | None
    status: str  # pending, running, passed, failed, skipped
    error: str | None = None


# Status icons
ICONS = {
    "pending": "🔲",
    "running": "⏳",
    "passed": "✅",
    "failed": "❌",
    "skipped": "⏭️",
}


class ConsoleReporter:
    """Live console output for test execution.

    Provides Maestro-style real-time step status display during test execution.
    Uses Rich's Live display for in-place terminal updates.

    Usage:
        reporter = ConsoleReporter("my-test", total_steps=5)
        reporter.start()
        reporter.step_started(1, "tap", "Email")
        reporter.step_completed(1, "passed")
        reporter.finish("passed", 2.3)
    """

    def __init__(self, test_name: str, total_steps: int, console: Console | None = None):
        """Initialize reporter.

        Args:
            test_name: Name of the test (shown in header)
            total_steps: Total number of steps (for pre-allocation)
            console: Optional Rich console (uses default if not provided)
        """
        self._test_name = test_name
        self._total_steps = total_steps
        self._console = console or Console()
        self._steps: list[StepDisplay] = []
        self._live: Live | None = None
        self._final_status: str | None = None
        self._final_duration: float | None = None

    def start(self) -> None:
        """Start live display."""
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=10,
            transient=True,  # Clear when done, we'll print final state
        )
        self._live.start()

    def step_started(self, step_num: int, action: str, target: str | None) -> None:
        """Called when a step begins executing.

        Args:
            step_num: Step number (1-indexed)
            action: Action type (tap, type, verify_screen, etc.)
            target: Target element or description
        """
        self._steps.append(StepDisplay(
            step_num=step_num,
            action=action,
            target=target,
            status="running",
        ))
        if self._live:
            self._live.update(self._render())

    def step_completed(
        self, step_num: int, status: str, error: str | None = None
    ) -> None:
        """Called when a step finishes.

        Args:
            step_num: Step number (1-indexed)
            status: Final status (passed, failed)
            error: Error message if failed
        """
        # Find and update the step
        for step in self._steps:
            if step.step_num == step_num:
                step.status = status
                step.error = error
                break

        if self._live:
            self._live.update(self._render())

    def mark_remaining_skipped(self, from_step: int) -> None:
        """Mark all remaining steps as skipped.

        Called when a step fails to show what won't be executed.

        Args:
            from_step: Step number to start skipping from (1-indexed)
        """
        # This would require knowing remaining steps ahead of time
        # For now, skipped steps are just not added to the display
        pass

    def finish(self, status: str, duration: float) -> None:
        """Called when test completes.

        Args:
            status: Final test status (passed, failed, error)
            duration: Total test duration in seconds
        """
        self._final_status = status
        self._final_duration = duration

        # Stop live display and print final state
        if self._live:
            self._live.stop()
            self._live = None

        # Print final static output
        self._console.print(self._render())

    def _render(self) -> Text:
        """Build the current display.

        Returns:
            Rich Text object with formatted output
        """
        lines: list[str] = []

        # Header
        header = f"┌─ {self._test_name} "
        header += "─" * max(0, 40 - len(header))
        lines.append(header)

        # Steps
        for step in self._steps:
            icon = ICONS.get(step.status, "🔲")

            # Verification prefix
            if step.action == "verify_screen":
                prefix = "🔍 verify"
            else:
                prefix = step.action

            # Build line
            line = f"│ {icon} {prefix}"
            if step.target:
                # Truncate long targets
                target = step.target
                if len(target) > 30:
                    target = target[:27] + "..."
                line += f' "{target}"'

            # Skipped indicator
            if step.status == "skipped":
                line += "  [dim](skipped)[/dim]"

            lines.append(line)

            # Error message if failed
            if step.error:
                # Truncate long errors
                error = step.error
                if len(error) > 50:
                    error = error[:47] + "..."
                lines.append(f"│    [red]{error}[/red]")

        # Footer (only when finished)
        if self._final_status is not None and self._final_duration is not None:
            if self._final_status == "passed":
                status_text = f"[green]✓ PASSED[/green] ({self._final_duration:.1f}s)"
            else:
                status_text = f"[red]✗ FAILED[/red] ({self._final_duration:.1f}s)"

            footer = f"└─ {status_text} "
            lines.append(footer + "─" * max(0, 40 - len(footer) + 20))  # +20 for markup
        else:
            # Running state - show simple footer
            lines.append("└" + "─" * 39)

        # Join with newlines
        content = "\n".join(lines)
        return Text.from_markup(content)
