import os
import glob
import re
import configparser
from typing import Dict, Any

DESKTOP_DIRS = [
    os.path.expanduser("~/.local/share/applications"),
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
]

CATEGORY_MAPPING = {
    "Development": ["Development", "IDE", "TextEditor", "Programming", "TerminalEmulator"],
    "Gaming": ["Game", "Emulator"],
    "Browsing": ["WebBrowser"],
    "Communication": ["Chat", "InstantMessaging", "Email", "Telephony", "IRCClient"],
    "Media & Design": ["AudioVideo", "Audio", "Video", "Graphics", "Photography", "RasterGraphics", "VectorGraphics", "Recorder"],
    "Productivity": ["Office", "Spreadsheet", "WordProcessor", "Presentation", "Finance", "Calendar"],
    "System": ["System", "Utility", "Settings", "FileManager", "Monitor"]
}

# Special overrides for specific apps
EXPLICIT_OVERRIDES = {
    "ai.opencode.desktop": {"display_name": "OpenCode", "icon": "ai.opencode.desktop", "category": "Development"},
    "ai.opencode": {"display_name": "OpenCode", "icon": "ai.opencode.desktop", "category": "Development"},
    "opencode": {"display_name": "OpenCode", "icon": "ai.opencode.desktop", "category": "Development"},
    "qhealth": {"display_name": "QHealth", "icon": "qhealth", "category": "System"},
    "vesktop": {"display_name": "Vesktop", "icon": "vesktop", "category": "Communication"},
    "code": {"display_name": "Visual Studio Code", "icon": "vscode", "category": "Development"},
    "code-oss": {"display_name": "Code OSS", "icon": "code-oss", "category": "Development"},
}

IDLE_APPS = {
    "desktop", "desktop / idle", "idle",
    "plasmashell", "org.kde.plasmashell", "plasma",
    "krunner", "org.kde.krunner", "kscreenlocker_greet",
    "org.kde.kscreenlocker_greet", "lockscreen"
}

class AppInfoResolver:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppInfoResolver, cls).__new__(cls)
            cls._instance._apps_cache = {}
            cls._instance._resolved_cache = {}
            cls._instance._scan_desktop_files()
        return cls._instance

    def clear_cache(self):
        self._resolved_cache.clear()

    def _scan_desktop_files(self):
        self._apps_cache.clear()
        self._resolved_cache.clear()
        for d in DESKTOP_DIRS:
            if not os.path.exists(d):
                continue
            for fpath in glob.glob(os.path.join(d, "**", "*.desktop"), recursive=True):
                fname = os.path.basename(fpath)
                base_id = fname[:-8].lower() if fname.endswith(".desktop") else fname.lower()
                try:
                    config = configparser.ConfigParser(interpolation=None)
                    config.read(fpath, encoding="utf-8")
                    if "Desktop Entry" in config:
                        entry = config["Desktop Entry"]
                        if entry.get("Type") == "Application" and not entry.getboolean("NoDisplay", fallback=False):
                            name = entry.get("Name", "").strip()
                            icon = entry.get("Icon", "").strip()
                            cats_raw = entry.get("Categories", "")
                            
                            category = self._detect_category(cats_raw, base_id, name)
                            
                            info = {
                                "display_name": name if name else base_id.title(),
                                "icon": icon if icon else base_id,
                                "category": category,
                                "desktop_id": base_id
                            }
                            
                            self._apps_cache[base_id] = info
                except Exception:
                    pass

    def _detect_category(self, cats_raw: str, app_id: str, app_name: str) -> str:
        cats_set = {c.strip() for c in cats_raw.split(";") if c.strip()}
        for cat_name, keywords in CATEGORY_MAPPING.items():
            for kw in keywords:
                if kw in cats_set:
                    return cat_name
        
        target = f"{app_id} {app_name}".lower()
        if any(k in target for k in ["code", "cursor", "zed", "nvim", "konsole", "terminal", "idea", "pycharm", "opencode", "alacritty", "kitty"]):
            return "Development"
        if any(k in target for k in ["steam", "game", "minecraft", "heroic", "lutris", "csgo", "cs2", "wine"]):
            return "Gaming"
        if any(k in target for k in ["firefox", "chrome", "chromium", "brave", "zen", "browser"]):
            return "Browsing"
        if any(k in target for k in ["discord", "vesktop", "telegram", "slack", "element", "signal"]):
            return "Communication"
        if any(k in target for k in ["spotify", "vlc", "mpv", "blender", "gimp", "inkscape", "obs", "davinci"]):
            return "Media & Design"
        if any(k in target for k in ["obsidian", "notion", "office", "writer", "calc"]):
            return "Productivity"
        if any(k in target for k in ["settings", "dolphin", "system", "htop", "btop", "ark", "qhealth"]):
            return "System"
        return "Other"

    def resolve(self, raw_app_id: str, raw_title: str = "", raw_class: str = "") -> Dict[str, Any]:
        cache_key = (raw_app_id, raw_class)
        if cache_key in self._resolved_cache:
            return self._resolved_cache[cache_key]

        cleaned_id = raw_app_id.lower().strip() if raw_app_id else ""
        if cleaned_id.endswith(".desktop"):
            cleaned_id = cleaned_id[:-8]
        cleaned_cls = raw_class.lower().strip() if raw_class else ""

        if not cleaned_id or cleaned_id in IDLE_APPS or (cleaned_cls and cleaned_cls in IDLE_APPS):
            res = {
                "app_id": "desktop",
                "display_name": "Desktop / Idle",
                "icon": "user-desktop",
                "category": "System",
                "is_active_window": False
            }
            self._resolved_cache[cache_key] = res
            return res

        try:
            from .db import get_custom_app_rules
            user_rules = get_custom_app_rules()
            if cleaned_id in user_rules or (cleaned_cls and cleaned_cls in user_rules):
                matched_rule = user_rules.get(cleaned_id) or user_rules.get(cleaned_cls)
                base_info = self._apps_cache.get(cleaned_id) or self._apps_cache.get(cleaned_cls) or {}
                icon = base_info.get("icon", cleaned_id)
                display_name = matched_rule.get("display_name") or base_info.get("display_name", cleaned_id.replace("-", " ").title())
                res = {
                    "app_id": cleaned_id,
                    "display_name": display_name,
                    "icon": icon,
                    "category": matched_rule["category"],
                    "is_active_window": True
                }
                self._resolved_cache[cache_key] = res
                return res
        except Exception:
            pass

        if cleaned_id in EXPLICIT_OVERRIDES:
            ov = EXPLICIT_OVERRIDES[cleaned_id]
            res = {"app_id": cleaned_id, "display_name": ov["display_name"], "icon": ov["icon"], "category": ov["category"], "is_active_window": True}
            self._resolved_cache[cache_key] = res
            return res
        if cleaned_cls in EXPLICIT_OVERRIDES:
            ov = EXPLICIT_OVERRIDES[cleaned_cls]
            res = {"app_id": cleaned_cls, "display_name": ov["display_name"], "icon": ov["icon"], "category": ov["category"], "is_active_window": True}
            self._resolved_cache[cache_key] = res
            return res

        if cleaned_id in self._apps_cache:
            info = self._apps_cache[cleaned_id]
            res = {"app_id": cleaned_id, "display_name": info["display_name"], "icon": info["icon"], "category": info["category"], "is_active_window": True}
            self._resolved_cache[cache_key] = res
            return res

        if cleaned_cls and cleaned_cls in self._apps_cache:
            info = self._apps_cache[cleaned_cls]
            res = {"app_id": cleaned_cls, "display_name": info["display_name"], "icon": info["icon"], "category": info["category"], "is_active_window": True}
            self._resolved_cache[cache_key] = res
            return res

        cleaned_parts = [p for p in re.split(r"[\.\-_/\s]+", f"{cleaned_id} {cleaned_cls}") if p]
        for key, info in self._apps_cache.items():
            key_last = key.split(".")[-1]
            # Generic last segments (e.g. io.elementary.terminal) would hijack unrelated apps
            if key_last and key_last not in {"desktop", "client", "app", "linux", "browser", "terminal", "editor", "player", "viewer"}:
                if key_last in cleaned_parts or key.endswith(f".{cleaned_id}") or (cleaned_cls and key.endswith(f".{cleaned_cls}")):
                    res = {
                        "app_id": key,
                        "display_name": info["display_name"],
                        "icon": info["icon"],
                        "category": info["category"],
                        "is_active_window": True
                    }
                    self._resolved_cache[cache_key] = res
                    return res

        pretty_name = cleaned_id.replace("-", " ").replace("_", " ").title()
        category = self._detect_category("", cleaned_id, pretty_name)
        res = {
            "app_id": cleaned_id,
            "display_name": pretty_name,
            "icon": cleaned_id,
            "category": category,
            "is_active_window": True
        }
        self._resolved_cache[cache_key] = res
        return res

app_resolver = AppInfoResolver()
