# QHealth — Project Guidelines & Architecture

## Overview
QHealth is a native, offline screen time and hardware activity tracker for Linux (CachyOS / Arch Linux with KDE Plasma 6, Wayland and X11) and Windows 10/11.

- **UI Aesthetic ("Quiet Instrument")**: Calm graphite surfaces (`#0D0F12` canvas → `#16191E` cards → `#1C2026` rows; elevation = lighter step, no shadows/glow) with a single jade accent (`#3CC7AD`, "Tide" palette), sidebar navigation, and zero Electron/Chromium bloat.
- **Design tokens**: `qhealth_gui/theme.py` is the single source for colours, type, spacing and helpers (`label(role)`, `set_prop`, `heat`, `fade_in`); `qhealth_gui/styles.py` builds the QSS from it and `apply_theme()` forces Fusion so Breeze/Kvantum can't alter rendering. Don't hardcode hex in widgets — use tokens and QSS roles (`role="h2"`, `class="Card"`, `tone="warn"`).
- **Data colour rules**: each metric keeps one colour everywhere (time = jade `#1FA58C`, keys = blue, clicks = orange, scrolls = neutral); apps use the fixed `CATEGORICAL` order coloured by screen-time rank (never by current sort); heatmaps are single-hue ramps via `theme.heat()`; status colours (good/warn/bad) are never data series.
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

### Windows (same code base, different backends)
- Platform switch is `qhealth_core.paths.IS_WINDOWS`; data lives in `%LOCALAPPDATA%\QHealth` (`paths.DATA_DIR`).
- `qhealth_core/win32.py` (ctypes only, no extra deps): **Raw Input** on a hidden message-only window for keys/clicks/scrolls (never low-level hooks — those add system-wide input lag when Python is busy), foreground-window polling (1 s), Toolhelp process snapshots, `WM_CLOSE` → `TerminateProcess` for blocking, the `HKCU\...\Run` autostart value.
- Scan codes go through `qhealth_core/keymap.py` so the keyboard heatmap keeps evdev numbering on both platforms.
- No service: the **tray app runs the daemon loop in-process** (`QHealthDaemon.start_embedded()`), started at sign-in with `QHealth.exe --minimized`. Notifications go through `qhealth_core/notify.py` (notify-send on Linux, tray toasts on Windows).
- Apps are identified by exe name (`code`, `chrome`); names/icons come from the exe's version resource and are remembered in `learned_apps.json` (Windows has no `.desktop` catalogue).
- Build: `packaging/windows/` (icon generator, PyInstaller spec, Inno Setup script); `.github/workflows/build.yml` tests both OSes and builds the installer. Windows-only tests are in `TestWindowsBackend` and run on the CI Windows runner.

### 2. Database Layer (`qhealth_core/db.py`)
- Stored at `~/.local/share/qhealth/qhealth.db` (Windows: `%LOCALAPPDATA%\QHealth\qhealth.db`). The directory is owner-only (0700) because it holds window-title history; keep any new state files inside it.
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

### Packaging
- Version lives in `qhealth_core/__init__.py` (`__version__`); bump it together with `packaging/arch/PKGBUILD` (`pkgver`), `packaging/linux/qhealth.metainfo.xml` (`<release>`) and the plasmoid `metadata.json`.
- Entry point: `qhealth = qhealth_core.cli:main` (`main.py` is only the from-source shim). UI SVGs ship as package data in `qhealth_gui/assets/ui/`.
- `install.sh` (any distro, per-user or `PREFIX=`) and `packaging/arch/PKGBUILD` both install the files in `packaging/linux/` (desktop entry, metainfo, systemd user unit) plus `assets/qhealth.svg` and the plasmoid.

### Database
- See "Database Layer" above. `db.data_version()` (DB/WAL file stat) lets GUI pollers skip a refresh when nothing was committed; `db.close_connection()` exists only for tests (Windows can't delete an open DB file).
- An interim Oct-2026 build created `daily_app_stats` at `user_version` 1; `_migrate` drops it and reruns the real v1/v2 steps.