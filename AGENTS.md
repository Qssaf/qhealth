# QHealth — Project Guidelines & Architecture

## Overview
QHealth is a native, offline screen time and hardware activity tracker crafted specifically for Linux (CachyOS / Arch Linux with KDE Plasma 6 Wayland and X11).

- **UI Aesthetic**: Dark glassmorphic design with cyan (`#00F2FE`) and emerald (`#10B981`) neon glow accents, deep dark backgrounds (`#0B0F17`, `#111827`), high-contrast typography, and zero Electron/Chromium bloat.
- **Resource Target**: ~13 MB RAM daemon, 0% idle CPU, native PyQt6 QtWidgets.

---

## Architecture

### 1. Dual Process Model
- **Daemon (`qhealth_core/daemon.py`, `qhealth_core/tracker.py`)**:
  - Runs headless 24/7 as systemd user service (`qhealth.service`).
  - Asynchronously captures input events via Linux `/dev/input/event*` (`evdev`).
  - Interacts with KWin Wayland via DBus script to monitor focused window/app.
  - Flushes aggregated chunks every 5 seconds into SQLite database.
  - Emits real-time state into `~/.local/share/qhealth/live_state.json`.
- **GUI Client (`qhealth_gui/main_window.py`, `qhealth_core/desktop_app.py`)**:
  - Native PyQt6 application opened on demand (`python3 main.py`).
  - Detects running daemon via `is_daemon_running()`. If daemon is active, client runs in **viewer-only mode** and does NOT instantiate an `ActivityTracker` (preventing double-counting time/keystrokes).
  - Consumes SQLite database directly and polls `live_state.json` for live pulse/speedometers.
  - Closing the window quits in viewer-only mode. Without a daemon the GUI is the tracker, so closing hides it to the tray (with a one-time tray message) instead of stopping tracking.

### 2. Database Layer (`qhealth_core/db.py`)
- Stored at `~/.local/share/qhealth/qhealth.db`. The directory is owner-only (0700) because it holds window-title history; keep any new state files inside it.
- SQLite configuration: WAL mode, `busy_timeout=5000`, `synchronous=NORMAL`, `mmap_size=64MB`, `auto_vacuum=INCREMENTAL`.
- History is kept forever, so storage per row matters. `activity_log` is a `WITHOUT ROWID` table keyed by `(date_str, hour_int, app_id, window_title)`, with no secondary indexes. Don't add indexes without measuring: on this layout every index entry repeats the full key, window title included.
- Schema changes go through `_migrate` as `PRAGMA user_version` steps in one transaction. Keep the upsert used by the previous release working, because a daemon started before an update keeps running old code until restarted.
- `get_db()` returns this thread's kept-open connection. Never close it, and don't keep cursors alive after a function returns. Read functions that the GUI or daemon poll use `@_cached_read`; they must not write, and callers receive copies.
- Inactive / idle threshold: Screen time only increments when physical input occurs; auto-pauses after 60s of inactivity.
- Excluded window IDs: `desktop`, `plasmashell`, `krunner`, `idle`.
- `daily_app_totals` holds per-day (date, app, category) sums of `activity_log`. SQLite triggers keep it exact. Never write it directly; write `activity_log` and let the triggers update it. Week/month/year/all-time stats, streaks and heatmaps read it. Day view and per-title breakdowns read `activity_log`.
- `budget_extensions` stores per-day extra minutes ("+15 min today"). Effective limit = `daily_limit_minutes` + that day's extension.

### 3. Wellbeing Logic (`qhealth_core/wellbeing.py`)
- `BudgetEnforcer` (80% / 1-minute / limit alerts, force-close) and `BreakReminder` run in the daemon. The GUI runs them only when it tracks on its own (no daemon). Keep budget logic here, not in `daemon.py`.
- Blocking closes the app and every process it launched. Terminal emulators are never force-closed or blocked, and the process walk stops at them: `app_resolver.is_terminal` / `TERMINAL_EMULATORS`, and the `TerminalEmulator` desktop category. A budget on a terminal only sends reminders.

---

## Critical Invariants & Rules

1. **Strict Concurrency / No Double-Tracking**:
   - Never initialize hardware `evdev` listeners or background flush threads in the GUI client when `qhealth.service` daemon is running.
2. **Date Anchoring**:
   - Historical date navigation (via `glowing_calendar.py`) passes an `anchor_date`.
   - All timeline and stats queries in `db.py` must anchor on `anchor_date`, never hardcoded `today`.
3. **Hardware Input Boundaries**:
   - Reading `/dev/input` needs the `input` group. Never fail silently: `ActivityTracker.input_access_denied` feeds the live state, and the GUI, plasmoid and daemon all surface it.
   - Clamp keycodes to `ev_code < 0x100` (256) to ignore laptop touchpad taps (`BTN_TOUCH` = 330) and gamepads.
   - Mouse wheel events are tracked as `'scroll'`, not `'click'`, preventing Clicks/Min speedometer spikes.
4. **Website Domain Isolation**:
   - Web domain tracking is strictly isolated to supported browsers (e.g. Brave). Do not parse arbitrary windows or file managers as domains.
   - Show clean root domains (e.g. `github.com`, `youtube.com`) without raw URL spam or click-to-open traps.
5. **Defensive QPainter**:
   - Always clamp arc angles (`span_angle <= 360 * 16`) in `radial_chart.py` and widget dimensions to avoid graphical overdraw crashes.

---

## Common Commands

### Run GUI
```bash
python3 main.py
```

### Run Daemon in Foreground (Debugging)
```bash
python3 main.py --daemon
```

### Manage Daemon Service
```bash
systemctl --user status qhealth
systemctl --user restart qhealth
systemctl --user stop qhealth
```

### Run Test Suite
```bash
python3 test_suite.py -v
```
