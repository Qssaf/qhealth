# QHealth — Digital Wellbeing & Activity Tracker for Linux

<div align="center">

![QHealth Icon](assets/qhealth.svg)

**A high-performance, dark glassmorphic screen time and activity tracker crafted for Linux (KDE Plasma & Wayland / X11).**

*100% Offline • Ultra-Lightweight (~13 MB RAM Daemon) • 0% Idle CPU • Native PyQt6*

</div>

---

> 🤖 **Note:** This application was architected and built collaboratively with **AI (OpenCode / Antigravity)**.

---

## ✨ Features

- **📊 Comprehensive Screen Time Analytics:**
  - **Screen Time Radial Gauge:** Multi-segment glowing ring showing active hours and category share (*Development, Browsing, Gaming, Communication, Media & Design, etc.*).
  - **Dynamic Activity Timeline:** Interactive bar chart displaying 24-hour hourly distribution, 7-day breakdowns, 30-day trends, and monthly distribution with hover stats.
  - **Global Time Range Filter:** Seamlessly switch between **`[ Day ]`**, **`[ Week ]`**, **`[ Month ]`**, **`[ Year ]`**, and **`[ All Time ]`**.

- **⌨️ Physical Hardware Heatmaps:**
  - **Physical Keyboard Heatmap:** Full visual keyboard layout (*Spacebar, Enter, Shift, WASD, Number row, Modifiers*) that glows from dark slate to bright neon emerald/cyan based on real-time keypress frequency.
  - **Physical Mouse Heatmap:** Visual ergonomic mouse illustration tracking **Left Click (LMB)**, **Right Click (RMB)**, **Middle Click (Wheel)**, and **Side Buttons (Back/Forward)**.
  - **70-Day GitHub-Style Activity Matrix:** Intensity matrix of daily typing and clicking volume over the past 10 weeks.

- **📱 Application Explorer & Interactive Drilldown:**
  - Ranked leaderboard with official native KDE icons and duration badges.
  - **Interactive Drilldown View:** Click on any application to view dedicated metrics, 14-day usage trend charts, and recent window titles/tasks.

- **📅 Glowing Calendar Date Selector:**
  - Dark glassmorphic calendar popup where **active days glow** based on screen time intensity (Level 0 to Level 4 neon glow) with hover stats.

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

## 🚀 Installation & Setup

### Prerequisites
- Linux OS (Arch Linux, CachyOS, Fedora, Ubuntu, Debian, etc.)
- Python 3.10+
- `python-pyqt6`

On Arch Linux / CachyOS:
```bash
sudo pacman -S python python-pyqt6
```

On Ubuntu / Debian:
```bash
sudo apt install python3 python3-pyqt6
```

On Fedora:
```bash
sudo dnf install python3 python3-pyqt6
```

---

### Running QHealth

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Qssaf/qhealth.git
   cd qhealth
   ```

2. **Launch the GUI:**
   ```bash
   python3 main.py
   ```

3. **Enable 24/7 Background Tracking (Systemd User Service):**
   ```bash
   mkdir -p ~/.config/systemd/user/
   cat << 'EOF' > ~/.config/systemd/user/qhealth.service
   [Unit]
   Description=QHealth 24/7 Activity and Screen Time Tracking Daemon
   After=graphical-session.target

   [Service]
   Type=simple
   ExecStart=/usr/bin/python3 /path/to/qhealth/main.py --daemon
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=default.target
   EOF

   systemctl --user daemon-reload
   systemctl --user enable --now qhealth
   ```

---

## 🧪 Running Tests

A comprehensive unit test suite is included:

```bash
python3 test_suite.py -v
```

---

## 📄 License

MIT License. Feel free to use, modify, and distribute.
