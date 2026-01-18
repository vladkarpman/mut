# Recording Start Message Improvement

## Problem

The current recording start message has several issues:
1. Noisy myscrcpy library logs appear between user messages
2. Instructions are unclear (mentions Enter when only Ctrl+C works)
3. Plain text formatting lacks visual hierarchy
4. Missing useful context (output directory)

## Design

### Message Flow

```
╭─ Recording: calculator-simple-9 ─────────────────────────╮
│ Device:  SM S911B (RFCW318P7NV)                          │
│ App:     com.google.android.calculator                   │
│ Output:  tests/calculator-simple-9/                      │
╰──────────────────────────────────────────────────────────╯

🎬 Recording... interact with your device

┌─────────────────────────┐
│  Press Ctrl+C to stop   │
└─────────────────────────┘
```

### Implementation

#### 1. Suppress Library Noise

Set myscrcpy logger to WARNING before creating recorder:

```python
import logging
logging.getLogger("myscrcpy").setLevel(logging.WARNING)
```

#### 2. Info Panel

Use Rich Panel with device name, app, and output directory:

```python
from rich.panel import Panel

# Get device name for display
devices_list = DeviceController.list_devices()
device_info = next((d for d in devices_list if d["id"] == device_id), None)
device_display = f"{device_info['name']} ({device_id})" if device_info else device_id

# Build panel content
content = f"[dim]Device:[/dim]  {device_display}\n"
content += f"[dim]App:[/dim]     {app}\n"
content += f"[dim]Output:[/dim]  {result['output_dir']}"

panel = Panel(
    content,
    title=f"[bold]Recording: {name}[/bold]",
    border_style="blue",
)
console.print(panel)
```

#### 3. Status and Prompt

```python
console.print()
console.print("🎬 [green]Recording...[/green] interact with your device")
console.print()
console.print("┌─────────────────────────┐")
console.print("│  Press Ctrl+C to stop   │")
console.print("└─────────────────────────┘")
```

#### 4. Remove Enter-based Input

Remove the `select.select()` loop that waits for Enter. Keep only KeyboardInterrupt handling.

### Files to Modify

- `mutcli/cli.py`: Lines ~200-240 (record command)
