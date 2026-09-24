# QHealth

<div align="center">

<img src="assets/qhealth.svg" alt="QHealth Icon" width="100">

**A lightweight screen time and activity tracker for Linux.**

[![Linux](https://img.shields.io/badge/Linux-supported-2ea44f?style=for-the-badge\&logo=linux\&logoColor=white)](https://www.linux.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-native-41cd52?style=for-the-badge\&logo=qt\&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![SQLite](https://img.shields.io/badge/SQLite-local-003b57?style=for-the-badge\&logo=sqlite\&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**100% Offline · ~13 MB RAM daemon · ~0% idle CPU · Native PyQt6**

</div>

---

> **Note:** QHealth was built with the help of AI tools, including OpenCode and Antigravity.

## Features

### Screen Time Analytics

* Screen time radial gauge with category breakdowns
* Hourly activity timeline
* 7-day, 30-day, and monthly statistics
* Day, Week, Month, Year, and All Time filters
* Categories such as Development, Browsing, Gaming, Communication, Media, and Design

### Keyboard & Mouse Tracking

* Full physical keyboard heatmap based on keypress frequency
* Mouse tracking for left, right, middle, back, and forward buttons
* 70-day GitHub-style activity matrix for typing and clicking

### Application Explorer

* Application usage leaderboard with native KDE icons
* Detailed statistics for individual applications
* 14-day usage trends
* Recent window titles and tasks

### Calendar

* Activity levels from 0 to 4 for each day
* Active days are highlighted based on screen time
* Hover over days for detailed statistics

### Performance

* Native PyQt6 QtWidgets
* No Chromium or WebEngine
* Background daemon uses around 13 MB RAM
* Around 0% CPU while idle
* Local SQLite database
* No cloud services or network connection required

---

## How It Works

QHealth uses two parts:

```text
┌────────────────────────────────────────────────────────┐
│              QHealth Background Daemon                 │
│                                                        │
│  • Runs continuously through systemd                   │
│  • Reads Linux input events through evdev              │
│  • Tracks keyboard and mouse activity                  │
│  • Detects idle periods                                │
│  • Tracks the focused application                      │
│  • Stores data in local SQLite                         │
└───────────────────────────┬────────────────────────────┘
                            │
                            │ SQLite + IPC
                            ▼
┌────────────────────────────────────────────────────────┐
│                  QHealth GUI Client                    │
│                                                        │
│  • Native PyQt6 QtWidgets                              │
│  • Opens when you run `qhealth`                       │
│  • Exits completely when closed                        │
└────────────────────────────────────────────────────────┘
```

Screen time is only counted while you are actively using your computer. After **60 seconds without input**, tracking pauses.

QHealth also tracks the currently focused window, so minimized and background applications do not continue accumulating time.

---

## Installation

### Requirements

* Linux
* Python 3.10+
* PyQt6
* systemd for automatic background tracking

### Arch Linux / CachyOS

```bash
sudo pacman -S python python-pyqt6
```

### Ubuntu / Debian

```bash
sudo apt install python3 python3-pyqt6
```

### Fedora

```bash
sudo dnf install python3 python3-pyqt6
```

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Qssaf/qhealth.git
cd qhealth
```

### 2. Start QHealth

```bash
python3 main.py
```

This starts the GUI. You can close it whenever you want without stopping background tracking if the daemon is running separately.

---

## Enable Background Tracking

To track your activity 24/7, create a systemd user service.

```bash
mkdir -p ~/.config/systemd/user/
```

Create:

```text
~/.config/systemd/user/qhealth.service
```

with:

```ini
[Unit]
Description=QHealth Activity and Screen Time Tracking Daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/qhealth/main.py --daemon
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Replace `/path/to/qhealth` with the path where you cloned QHealth.

Then enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now qhealth
```

Check whether it is running:

```bash
systemctl --user status qhealth
```

Once enabled, the daemon will start automatically with your user session.

---

## Data & Privacy

QHealth stores its data locally in:

```text
~/.local/share/qhealth/
```

There is no account or cloud service involved.

* No telemetry
* No analytics
* No external database
* No required internet connection
* All activity data stays on your machine

---

## Running Tests

QHealth includes a unit test suite:

```bash
python3 test_suite.py -v
```

---

## License

MIT License. Feel free to use, modify, and distribute.

<div align="center">

**See where your time actually goes.**

</div>


