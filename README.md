# QHealth

<div align="center">

<img src="assets/qhealth.svg" alt="QHealth Icon" width="100">

**A lightweight screen time and activity tracker for Linux.**

[![Linux](https://img.shields.io/badge/Linux-supported-2ea44f?style=for-the-badge\&logo=linux\&logoColor=white)](https://www.linux.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-native-41cd52?style=for-the-badge\&logo=qt\&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**100% Offline · ~13 MB RAM daemon · ~0% idle CPU · Native PyQt6**

</div>

---

> **Note:** QHealth was built with the help of AI tools, including OpenCode and Antigravity.

## Features

* **Screen Time Analytics**

  * Radial screen time gauge
  * Hourly, daily, weekly, monthly, and yearly charts
  * Development, Browsing, Gaming, Communication, Media, and more
  * Day, Week, Month, Year, and All Time filters

* **Keyboard & Mouse Heatmaps**

  * Full keyboard heatmap based on keypress frequency
  * Mouse button tracking for LMB, RMB, middle, and side buttons
  * 70-day GitHub-style activity matrix

* **Application Explorer**

  * Application usage leaderboard with native KDE icons
  * Detailed application statistics
  * 14-day usage trends
  * Recent window titles

* **Activity Calendar**

  * Daily activity levels from 0 to 4
  * Hover for daily statistics

* **Low Resource Usage**

  * Native PyQt6 QtWidgets
  * No Chromium or WebEngine
  * Background daemon uses around 13 MB RAM
  * Around 0% CPU while idle
  * Fully local SQLite storage

## How It Works

QHealth uses a small background daemon to collect activity data while the GUI stays closed.

```text
┌──────────────────────────────────────────────┐
│        QHealth Background Daemon             │
│                                              │
│  evdev → Input Tracking → Activity → SQLite │
│                                              │
│              ~13 MB RAM / ~0% CPU           │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│              QHealth GUI                    │
│          Native PyQt6 / QtWidgets            │
└──────────────────────────────────────────────┘
```

Screen time only counts while you are actively using your computer. Tracking pauses after 60 seconds without input, and background or minimized applications are not counted.

## Installation

### Requirements

* Linux
* Python 3.10+
* PyQt6

**Arch / CachyOS**

```bash
sudo pacman -S python python-pyqt6
```

**Ubuntu / Debian**

```bash
sudo apt install python3 python3-pyqt6
```

**Fedora**

```bash
sudo dnf install python3 python3-pyqt6
```

### Run

```bash
git clone https://github.com/Qssaf/qhealth.git
cd qhealth
python3 main.py
```

For 24/7 tracking, QHealth can also be run as a systemd user service.

## Testing

```bash
python3 test_suite.py -v
```

## Privacy

QHealth is completely local.

* No accounts
* No cloud services
* No telemetry
* No required internet connection

Data is stored in:

```text
~/.local/share/qhealth/
```

## License

MIT License. Feel free to use, modify, and distribute.

<div align="center">

**See where your time actually goes.**

</div>

