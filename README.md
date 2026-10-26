# QHealth — Digital Wellbeing & Activity Tracker for Linux

<div align="center">

![QHealth Icon](assets/qhealth.svg)

**A high-performance, calm dark-mode screen time and activity tracker for Linux (KDE Plasma, Wayland / X11) and Windows 10 / 11.**

*100% Offline • Ultra-Lightweight (~13 MB RAM Daemon) • 0% Idle CPU • Native PyQt6*

</div>

---

> 🤖 **Note:** This application was architected and built collaboratively with **AI (OpenCode / Antigravity)**.

---

## ✨ Features

- **📊 Comprehensive Screen Time Analytics:**
  - **Screen Time Radial Gauge:** Multi-segment ring showing active hours and category share (*Development, Browsing, Gaming, Communication, Media & Design, etc.*).
  - **Dynamic Activity Timeline:** Interactive bar chart displaying 24-hour hourly distribution, 7-day breakdowns, 30-day trends, and monthly distribution with hover stats.
  - **Global Time Range Filter:** Seamlessly switch between **`[ Day ]`**, **`[ Week ]`**, **`[ Month ]`**, **`[ Year ]`**, and **`[ All Time ]`**.

- **⌨️ Physical Hardware Heatmaps:**
  - **Physical Keyboard Heatmap:** Full visual keyboard layout (*Spacebar, Enter, Shift, WASD, Number row, Modifiers*) shaded from the card surface to full blue based on keypress frequency.
  - **Physical Mouse Heatmap:** Visual ergonomic mouse illustration tracking **Left Click (LMB)**, **Right Click (RMB)**, **Middle Click (Wheel)**, and **Side Buttons (Back/Forward)**.
  - **70-Day GitHub-Style Activity Matrix:** Intensity matrix of daily typing and clicking volume over the past 10 weeks.

- **📱 Application Explorer & Interactive Drilldown:**
  - Ranked leaderboard with official native KDE icons and duration badges.
  - **Interactive Drilldown View:** Click on any application to view dedicated metrics, 14-day usage trend charts, and recent window titles/tasks.

- **📅 Glowing Calendar Date Selector:**
  - Calendar popup where **active days are shaded** by screen time intensity (Level 0 to Level 4) with hover stats, plus ‹ › stepping by day / week / month / year.

- **⚡ High Performance & Low Resource Footprint:**
  - **100% Pure Native PyQt6:** Zero Chromium or WebEngine bloat.
  - **Daemon + Client Architecture:** Headless background tracking daemon uses **~13 MB RAM** and **0.0% idle CPU**.
  - **Strict Active vs. Idle Detection:** Screen time only accumulates when physical input occurs; automatically pauses when away (>60s).
  - **Strict Foreground Window Isolation:** Minimized and background apps never gain time.

---

## 🏛 Architecture

```
┌────────────────────────────────────────────────────────┐
│         QHealth Background Daemon (13 MB RAM)          │
│   • 24/7 background service via systemd                │
│   • Async Linux /dev/input event reader (evdev)        │
│   • KDE Plasma KWin Wayland window focus integration   │
│   • Local SQLite database (~/.local/share/qhealth/)    │
└───────────────────────────▲────────────────────────────┘
                            │ SQLite DB & State IPC
┌───────────────────────────┴────────────────────────────┐
│                  QHealth GUI Client                    │
│   • Native PyQt6 QtWidgets (GPU hardware accelerated)  │
│   • Opens on demand when you run `qhealth`             │
│   • When closed (X or Esc), exits cleanly (0 MB RAM)   │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation

On Linux QHealth needs **Python 3.10+**, **PyQt6** (with SVG support) and a **KDE Plasma** session (Wayland or X11).
To count keystrokes and clicks it reads `/dev/input`, so your account must be in the `input` group:

```bash
sudo usermod -aG input "$USER"   # then log out and back in
```

Without it nothing is recorded, and QHealth says **No input access** (dashboard, panel widget and a notification).

> Being in `input` lets any program you run read raw keyboard/mouse events — that is how QHealth works,
> and it keeps everything in a local SQLite database (`~/.local/share/qhealth/`). Nothing is sent anywhere.

### Windows 10 / 11

Download `QHealth-<version>-Setup.exe` from the [Releases](https://github.com/Qssaf/qhealth/releases) page
(every `v*` tag publishes one; the latest `main` build is also attached to the
[CI run](https://github.com/Qssaf/qhealth/actions) as the `qhealth-windows` artifact) and run it.
No admin rights are needed. The installer adds a Start-menu entry and, unless you untick it,
starts QHealth in the tray when you sign in — tracking runs inside the tray app, so keep it running
(toggle it later from the tray menu: **Start with Windows**). Your history lives in `%LOCALAPPDATA%\QHealth`.

Build it yourself from a checkout (Python 3.10+):

```powershell
pip install PyQt6 pyinstaller
python packaging\windows\make_icon.py
pyinstaller packaging\windows\qhealth.spec --noconfirm   # -> dist\QHealth\QHealth.exe
iscc /DAppVersion=3.0.0 packaging\windows\qhealth.iss       # optional installer (Inno Setup 6)
```

Or just run it from source: `pip install PyQt6` then `python main.py`.

### Arch Linux / CachyOS (native package)

```bash
cd packaging/arch
makepkg -si                                  # builds from the v$pkgver release tag
systemctl --user enable --now qhealth.service
```

The package installs the `qhealth` command, app-menu entry, icon, AppStream metadata, the systemd user
service and the Plasma panel widget ("QHealth Status").

### Any distro (per-user install, no root)

Install PyQt6 from your distro first:

| Distro | Command |
|---|---|
| Arch / CachyOS | `sudo pacman -S python-pyqt6 qt6-svg libnotify` |
| Fedora | `sudo dnf install python3-pyqt6 libnotify` |
| Debian / Ubuntu | `sudo apt install python3-pyqt6 python3-pyqt6.qtsvg libnotify-bin` |

Then, from the repository:

```bash
./install.sh --enable      # installs into ~/.local and starts 24/7 tracking
./install.sh --uninstall   # removes the app (your history is kept)
```

For a system-wide copy use `sudo PREFIX=/usr/local ./install.sh`. Re-running the installer upgrades in place
and restarts the tracking service if it was running.

### Run from source (development)

```bash
python3 main.py            # dashboard
python3 main.py --daemon   # tracking daemon in the foreground
```

Python packaging (`pyproject.toml`) is included too: `pipx install .` gives you the `qhealth` command
(without the desktop entry and service files).

### Good to know

- After updating, restart tracking so the daemon runs the new code: `systemctl --user restart qhealth`.
  Database upgrades happen automatically on the next start, and all history is kept.
- With the service running, the window is only a viewer: closing it (X or Esc) exits completely.
  Without the service (and always on Windows) the app does the tracking itself, so closing keeps it in the
  tray — it tells you so; use **Quit** in the tray menu to stop.
- The Plasma panel widget is installed by the package and `install.sh`. From a source checkout:
  `kpackagetool6 --type Plasma/Applet --install plasma_plasmoid/org.kde.plasma.qhealth`
  (`--upgrade` after pulling), then **Add Widgets… → QHealth Status**. It shows **OFF** when the daemon isn't running.

---

## 🧪 Running Tests

A comprehensive unit test suite is included:

```bash
python3 test_suite.py -v
```

---

## 📄 License

MIT License. Feel free to use, modify, and distribute.
