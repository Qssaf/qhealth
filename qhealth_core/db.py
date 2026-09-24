import os
import re
import urllib.parse
import sqlite3
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from contextlib import contextmanager
from .app_resolver import app_resolver

DB_DIR = Path.home() / ".local" / "share" / "qhealth"
DB_PATH = DB_DIR / "qhealth.db"

EXCLUDED_APP_IDS_SQL = "('desktop', 'desktop / idle', 'idle', 'plasmashell', 'org.kde.plasmashell', 'plasma', 'krunner', '')"

DEFAULT_CATEGORIES = {
    "Development": [
        "code", "vscodium", "cursor", "zed", "alacritty", "kitty", "konsole",
        "wezterm", "nvim", "neovim", "emacs", "idea", "pycharm", "webstorm",
        "clion", "sublime_text", "ai.opencode.desktop", "opencode", "kate"
    ],
    "Gaming": [
        "steam", "lutris", "heroic", "minecraft", "cs2", "csgo", "dota2",
        "wine", "gamescope", "retroarch", "dolphin-emu", "osu", "steamwebhelper"
    ],
    "Browsing": [
        "firefox", "google-chrome", "chromium", "brave-browser", "brave",
        "zen", "zen-browser", "librewolf", "thorium-browser", "opera", "vivaldi"
    ],
    "Communication": [
        "discord", "vesktop", "telegram-desktop", "telegram", "slack",
        "element", "signal-desktop", "signal", "zapzap", "whatsapp-for-linux", "thunderbird"
    ],
    "Media & Design": [
        "spotify", "vlc", "mpv", "blender", "inkscape", "gimp", "figma-linux",
        "obs", "com.obsproject.Studio", "davinci-resolve", "kdenlive", "krita"
    ],
    "Productivity": [
        "obsidian", "notion-app", "notion", "libreoffice", "kwrite",
        "korganizer", "okular", "calibre", "xournalpp", "linear", "linear-native"
    ],
    "System": [
        "systemsettings", "org.kde.systemsettings", "dolphin", "org.kde.dolphin",
        "kcalc", "ark", "htop", "btop", "krunner", "plasma", "qhealth"
    ]
}

RE_COUNT_BADGES = re.compile(r"^[\(\[\{]\d+\+?[\)\]\}]\s*")
RE_LEAD_CHARS = re.compile(r"^[•\*\s\-_]+")
RE_GH_REPO = re.compile(r"^([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)(?::\s*(.*))?$")
RE_DOMAIN = re.compile(r"\b([a-zA-Z0-9-]+\.(?:com|org|net|io|dev|app|ai|me|cc|gg|tv|so|co|edu|gov|xyz|info))\b", re.IGNORECASE)

@contextmanager
def get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -16000;")
    conn.execute("PRAGMA mmap_size = 67108864;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    try:
        yield conn
    finally:
        conn.close()

def get_category_for_app(app_id: str, app_name: str) -> str:
    app_lower = (app_id or "").lower()
    name_lower = (app_name or "").lower()

    try:
        user_rules = get_custom_app_rules()
        if app_lower in user_rules:
            return user_rules[app_lower]["category"]
        if name_lower in user_rules:
            return user_rules[name_lower]["category"]
    except Exception:
        pass
    
    for category, keywords in DEFAULT_CATEGORIES.items():
        for kw in keywords:
            if kw in app_lower or kw in name_lower:
                return category
    return "Other"

_db_initialized = False

ROLLUP_SCHEMA_VERSION = 1

def _rollup_add_sql(sign: str, row: str) -> str:
    """SQL that adds (sign '+') or subtracts (sign '-') trigger row `row` (NEW/OLD) into daily_app_totals."""
    # NOT EXISTS instead of INSERT OR IGNORE: an outer statement's conflict policy
    # (e.g. INSERT OR REPLACE) would override OR IGNORE inside the trigger body.
    return f"""
        INSERT INTO daily_app_totals (date_str, app_id, category)
        SELECT {row}.date_str, {row}.app_id, {row}.category
        WHERE NOT EXISTS (
            SELECT 1 FROM daily_app_totals
            WHERE date_str = {row}.date_str AND app_id = {row}.app_id AND category = {row}.category
        );
        UPDATE daily_app_totals SET
            duration_seconds = duration_seconds {sign} {row}.duration_seconds,
            keystrokes = keystrokes {sign} {row}.keystrokes,
            clicks = clicks {sign} {row}.clicks,
            scrolls = scrolls {sign} {row}.scrolls
        WHERE date_str = {row}.date_str AND app_id = {row}.app_id AND category = {row}.category;
    """

_ROLLUP_PRUNE_OLD_SQL = """
        DELETE FROM daily_app_totals
        WHERE date_str = OLD.date_str AND app_id = OLD.app_id AND category = OLD.category
          AND duration_seconds = 0 AND keystrokes = 0 AND clicks = 0 AND scrolls = 0;
"""

def _init_daily_rollup(conn: sqlite3.Connection):
    """
    Per-day totals of activity_log, kept exact by triggers so week/month/year views scan
    a few thousand rows instead of every hourly/per-title row. Triggers (not Python code)
    keep it in sync, so it stays correct even while an older daemon build is writing.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-check under the write lock so a concurrently starting daemon/GUI can't backfill twice
        if conn.execute("PRAGMA user_version").fetchone()[0] < ROLLUP_SCHEMA_VERSION:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_app_totals (
                date_str TEXT NOT NULL,
                app_id TEXT NOT NULL,
                category TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                keystrokes INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                scrolls INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (date_str, app_id, category)
            ) WITHOUT ROWID
            """)
            conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_rollup_insert AFTER INSERT ON activity_log BEGIN
                {_rollup_add_sql('+', 'NEW')}
            END
            """)
            conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_rollup_update
            AFTER UPDATE OF date_str, app_id, category, duration_seconds, keystrokes, clicks, scrolls ON activity_log
            BEGIN
                {_rollup_add_sql('-', 'OLD')}
                {_rollup_add_sql('+', 'NEW')}
                {_ROLLUP_PRUNE_OLD_SQL}
            END
            """)
            conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_rollup_delete AFTER DELETE ON activity_log BEGIN
                {_rollup_add_sql('-', 'OLD')}
                {_ROLLUP_PRUNE_OLD_SQL}
            END
            """)
            conn.execute("DELETE FROM daily_app_totals")
            conn.execute("""
            INSERT INTO daily_app_totals (date_str, app_id, category, duration_seconds, keystrokes, clicks, scrolls)
            SELECT date_str, app_id, category,
                   SUM(duration_seconds), SUM(keystrokes), SUM(clicks), SUM(scrolls)
            FROM activity_log
            GROUP BY date_str, app_id, category
            HAVING SUM(duration_seconds) != 0 OR SUM(keystrokes) != 0 OR SUM(clicks) != 0 OR SUM(scrolls) != 0
            """)
            conn.execute(f"PRAGMA user_version = {ROLLUP_SCHEMA_VERSION}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def init_db(force: bool = False):
    global _db_initialized
    if _db_initialized and not force:
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA wal_autocheckpoint = 1000;")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            date_str TEXT NOT NULL,
            hour_int INTEGER NOT NULL,
            app_id TEXT NOT NULL,
            app_name TEXT NOT NULL,
            window_title TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            keystrokes INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            scrolls INTEGER NOT NULL DEFAULT 0,
            UNIQUE(date_str, hour_int, app_id, window_title)
        )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(date_str)")
        # Unused by any query (app_id is the prefix of idx_act_app_date_dur; nothing filters
        # on category); they only add write cost on every 5s flush.
        cursor.execute("DROP INDEX IF EXISTS idx_activity_app")
        cursor.execute("DROP INDEX IF EXISTS idx_activity_category")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_app_date_dur ON activity_log(app_id, date_str, duration_seconds)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_date_dur ON activity_log(date_str, duration_seconds)")

        _init_daily_rollup(conn)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_app_rules (
            app_id TEXT PRIMARY KEY,
            display_name TEXT,
            category TEXT NOT NULL,
            custom_color TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS key_heatmap_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_str TEXT NOT NULL,
            key_code INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(date_str, key_code)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_heat_date ON key_heatmap_v2(date_str)")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mouse_heatmap_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_str TEXT NOT NULL,
            button_name TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(date_str, button_name)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mouse_heat_date ON mouse_heatmap_v2(date_str)")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_budgets (
            app_id TEXT PRIMARY KEY,
            daily_limit_minutes INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            block_on_exceed INTEGER NOT NULL DEFAULT 1
        )
        """)

        # Migration: ensure block_on_exceed column exists for pre-existing tables
        try:
            cursor.execute("ALTER TABLE app_budgets ADD COLUMN block_on_exceed INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        _db_initialized = True

def set_app_budget(app_id: str, daily_limit_minutes: int, enabled: bool = True, block_on_exceed: bool = True):
    init_db()
    cleaned_id = app_id.lower().strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO app_budgets (app_id, daily_limit_minutes, enabled, block_on_exceed)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(app_id) DO UPDATE SET
            daily_limit_minutes = excluded.daily_limit_minutes,
            enabled = excluded.enabled,
            block_on_exceed = excluded.block_on_exceed
        """, (cleaned_id, daily_limit_minutes, 1 if enabled else 0, 1 if block_on_exceed else 0))
        conn.commit()

def get_app_budget(app_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    cleaned_id = app_id.lower().strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT app_id, daily_limit_minutes, enabled, block_on_exceed FROM app_budgets WHERE app_id = ?", (cleaned_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_app_budgets() -> Dict[str, Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT app_id, daily_limit_minutes, enabled, block_on_exceed FROM app_budgets")
        return {row["app_id"]: dict(row) for row in cursor.fetchall()}

def get_exceeded_app_budgets(date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Returns apps that reached or exceeded their daily budget for date_str (defaults to today)."""
    init_db()
    if not date_str:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            LOWER(b.app_id) as app_id,
            b.daily_limit_minutes,
            b.block_on_exceed,
            COALESCE(SUM(a.duration_seconds), 0) as used_seconds
        FROM app_budgets b
        LEFT JOIN activity_log a ON LOWER(a.app_id) = LOWER(b.app_id) AND a.date_str = ?
        WHERE b.enabled = 1 AND b.daily_limit_minutes > 0
        GROUP BY b.app_id
        HAVING used_seconds >= (b.daily_limit_minutes * 60)
        """, (date_str,))
        exceeded = {}
        for row in cursor.fetchall():
            a_id = row["app_id"]
            limit_mins = row["daily_limit_minutes"]
            used_secs = row["used_seconds"]
            exceeded[a_id] = {
                "app_id": a_id,
                "daily_limit_minutes": limit_mins,
                "block_on_exceed": bool(row["block_on_exceed"]),
                "used_seconds": used_secs,
                "used_minutes": round(used_secs / 60.0, 1)
            }
        return exceeded

def get_activity_streak_stats() -> Dict[str, Any]:
    init_db()
    today = datetime.date.today()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT DISTINCT date_str
        FROM daily_app_totals
        WHERE LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL} AND duration_seconds > 0
        ORDER BY date_str DESC
        """)
        active_dates = {row["date_str"] for row in cursor.fetchall()}

        cursor.execute(f"""
        SELECT 
            COALESCE(SUM(duration_seconds), 0) as total_dur,
            COALESCE(SUM(keystrokes), 0) as total_keys
        FROM daily_app_totals
        WHERE LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL}
        """)
        totals = cursor.fetchone()
        lifetime_dur = totals["total_dur"]
        lifetime_keys = totals["total_keys"]

    # Calculate current streak (counting backwards from today or yesterday)
    current_streak = 0
    check_date = today
    # If today has no activity yet, check starting from yesterday
    if today.strftime("%Y-%m-%d") not in active_dates:
        check_date = today - datetime.timedelta(days=1)

    while check_date.strftime("%Y-%m-%d") in active_dates:
        current_streak += 1
        check_date -= datetime.timedelta(days=1)

    # Longest streak calculation
    sorted_dates = sorted([datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in active_dates])
    longest_streak = 0
    temp_streak = 0
    prev_date = None
    for d in sorted_dates:
        if prev_date is None or d == prev_date + datetime.timedelta(days=1):
            temp_streak += 1
        else:
            temp_streak = 1
        longest_streak = max(longest_streak, temp_streak)
        prev_date = d

    longest_streak = max(longest_streak, current_streak)

    # Lifetime Milestones
    total_hours = lifetime_dur / 3600.0
    milestones = [
        {"id": "first_day", "title": "First Steps", "desc": "Tracked first activity", "unlocked": len(active_dates) >= 1},
        {"id": "streak_3", "title": "Consistency Master", "desc": "3-day streak", "unlocked": longest_streak >= 3},
        {"id": "streak_7", "title": "Unstoppable", "desc": "7-day streak", "unlocked": longest_streak >= 7},
        {"id": "keys_10k", "title": "Keyboard Warrior", "desc": "10k physical keystrokes", "unlocked": lifetime_keys >= 10000},
        {"id": "keys_50k", "title": "Speed Demon", "desc": "50k physical keystrokes", "unlocked": lifetime_keys >= 50000},
        {"id": "hours_10", "title": "Deep Focus", "desc": "10h active time", "unlocked": total_hours >= 10.0},
        {"id": "hours_50", "title": "Centurion", "desc": "50h active time", "unlocked": total_hours >= 50.0},
    ]

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_active_days": len(active_dates),
        "milestones": milestones
    }

def get_setting(key: str, default: str = "") -> str:
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_setting(key: str, value: str):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = ?
        """, (key, value, value))
        conn.commit()

def set_custom_app_rule(app_id: str, category: str, display_name: Optional[str] = None):
    init_db()
    cleaned_id = app_id.lower().strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO custom_app_rules (app_id, display_name, category)
        VALUES (?, ?, ?)
        ON CONFLICT(app_id) DO UPDATE SET 
            category = excluded.category,
            display_name = COALESCE(excluded.display_name, custom_app_rules.display_name)
        """, (cleaned_id, display_name, category))

        # Also update historical records for this app
        cursor.execute("""
        UPDATE activity_log SET category = ? WHERE LOWER(app_id) = ? OR LOWER(app_name) = ?
        """, (category, cleaned_id, cleaned_id))

        conn.commit()
    app_resolver.clear_cache()

def get_custom_app_rules() -> Dict[str, Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT app_id, display_name, category FROM custom_app_rules")
        return {row["app_id"]: dict(row) for row in cursor.fetchall()}

def toggle_pause_setting() -> bool:
    current = get_setting("paused", "false").lower() == "true"
    new_state = not current
    set_setting("paused", "true" if new_state else "false")
    return new_state

def is_paused_setting() -> bool:
    return get_setting("paused", "false").lower() == "true"

def record_input_heatmap_chunk(key_counts: Dict[int, int], mouse_counts: Dict[str, int]):
    if not key_counts and not mouse_counts:
        return

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        for k_code, k_count in key_counts.items():
            cursor.execute("""
            INSERT INTO key_heatmap_v2 (date_str, key_code, count) VALUES (?, ?, ?)
            ON CONFLICT(date_str, key_code) DO UPDATE SET count = count + ?
            """, (date_str, k_code, k_count, k_count))

        for m_btn, m_count in mouse_counts.items():
            cursor.execute("""
            INSERT INTO mouse_heatmap_v2 (date_str, button_name, count) VALUES (?, ?, ?)
            ON CONFLICT(date_str, button_name) DO UPDATE SET count = count + ?
            """, (date_str, m_btn, m_count, m_count))

        conn.commit()

def get_keyboard_heatmap_data(range_type: str = "day", target_date: Optional[str] = None) -> Dict[int, int]:
    init_db()
    today = datetime.date.today()
    if not target_date:
        target_date = today.strftime("%Y-%m-%d")

    try:
        anchor_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        anchor_date = today

    with get_db() as conn:
        cursor = conn.cursor()
        if range_type == "day":
            date_condition = "date_str = ?"
            params = [target_date]
        elif range_type == "week":
            start_date = (anchor_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "month":
            start_date = (anchor_date - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "year":
            start_date = (anchor_date - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "all_time":
            date_condition = "1=1"
            params = []
        else:
            date_condition = "date_str = ?"
            params = [target_date]

        cursor.execute(f"""
        SELECT key_code, SUM(count) as total_count
        FROM key_heatmap_v2
        WHERE {date_condition}
        GROUP BY key_code
        """, params)
        return {row["key_code"]: row["total_count"] for row in cursor.fetchall()}

def get_mouse_heatmap_data(range_type: str = "day", target_date: Optional[str] = None) -> Dict[str, int]:
    init_db()
    today = datetime.date.today()
    if not target_date:
        target_date = today.strftime("%Y-%m-%d")

    try:
        anchor_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        anchor_date = today

    with get_db() as conn:
        cursor = conn.cursor()
        if range_type == "day":
            date_condition = "date_str = ?"
            params = [target_date]
        elif range_type == "week":
            start_date = (anchor_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "month":
            start_date = (anchor_date - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "year":
            start_date = (anchor_date - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "all_time":
            date_condition = "1=1"
            params = []
        else:
            date_condition = "date_str = ?"
            params = [target_date]

        cursor.execute(f"""
        SELECT button_name, SUM(count) as total_count
        FROM mouse_heatmap_v2
        WHERE {date_condition}
        GROUP BY button_name
        """, params)
        return {row["button_name"]: row["total_count"] for row in cursor.fetchall()}

def record_activity_chunk(
    app_id: str,
    app_name: str,
    window_title: str,
    duration_seconds: int,
    keystrokes: int,
    clicks: int,
    scrolls: int,
    category: Optional[str] = None
):
    if duration_seconds <= 0 and keystrokes <= 0 and clicks <= 0 and scrolls <= 0:
        return

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    hour_int = now.hour
    if not category:
        category = get_category_for_app(app_id, app_name)

    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO activity_log (
            date_str, hour_int, app_id, app_name, window_title,
            category, duration_seconds, keystrokes, clicks, scrolls
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date_str, hour_int, app_id, window_title) DO UPDATE SET
            duration_seconds = duration_seconds + excluded.duration_seconds,
            keystrokes = keystrokes + excluded.keystrokes,
            clicks = clicks + excluded.clicks,
            scrolls = scrolls + excluded.scrolls,
            app_name = excluded.app_name,
            category = excluded.category,
            timestamp = CURRENT_TIMESTAMP
        """, (
            date_str, hour_int, app_id, app_name, window_title,
            category, duration_seconds, keystrokes, clicks, scrolls
        ))
        conn.commit()

def get_stats_by_range(range_type: str = "day", target_date: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    today = datetime.date.today()
    if not target_date:
        target_date = today.strftime("%Y-%m-%d")

    try:
        anchor_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        anchor_date = today

    with get_db() as conn:
        cursor = conn.cursor()

        if range_type == "day":
            date_condition = "date_str = ?"
            params = [target_date]
        elif range_type == "week":
            start_date = (anchor_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "month":
            start_date = (anchor_date - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "year":
            start_date = (anchor_date - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "all_time":
            date_condition = "1=1"
            params = []
        else:
            date_condition = "date_str = ?"
            params = [target_date]

        # Single pass over the range (hourly rows for a day, per-day rollups otherwise);
        # totals, app/category breakdowns and the timeline are all folded from it.
        if range_type == "day":
            source, bucket = "activity_log", "hour_int"
        elif range_type in ("week", "month"):
            source, bucket = "daily_app_totals", "date_str"
        else:
            source, bucket = "daily_app_totals", "SUBSTR(date_str, 1, 7)"

        cursor.execute(f"""
        SELECT
            {bucket} AS bucket,
            app_id,
            category,
            SUM(duration_seconds) AS duration,
            SUM(keystrokes) AS keystrokes,
            SUM(clicks) AS clicks,
            SUM(scrolls) AS scrolls
        FROM {source}
        WHERE {date_condition} AND LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL}
        GROUP BY bucket, app_id, category
        """, params)
        rows = cursor.fetchall()

        metric_keys = ("duration", "keystrokes", "clicks", "scrolls")
        totals = dict.fromkeys(metric_keys, 0)
        app_map: Dict[str, Dict[str, Any]] = {}
        cat_map: Dict[str, Dict[str, Any]] = {}
        bucket_map: Dict[Any, Dict[str, int]] = {}
        for r in rows:
            app = app_map.setdefault(r["app_id"], {"app_id": r["app_id"], "app_name": "", "category": r["category"], **dict.fromkeys(metric_keys, 0)})
            cat = cat_map.setdefault(r["category"], {"category": r["category"], "duration": 0, "keystrokes": 0, "clicks": 0})
            slot = bucket_map.setdefault(r["bucket"], {"duration": 0, "keystrokes": 0, "clicks": 0})
            for k in metric_keys:
                totals[k] += r[k]
                app[k] += r[k]
                if k != "scrolls":
                    cat[k] += r[k]
                    slot[k] += r[k]

        total_duration = totals["duration"]
        apps = sorted(app_map.values(), key=lambda a: a["duration"], reverse=True)
        budgets = get_all_app_budgets()

        for app in apps:
            a_id = app.get("app_id", "").lower()
            info = app_resolver.resolve(a_id, app.get("app_name", ""))
            app["app_name"] = info["display_name"]
            app["category"] = info["category"]
            app["icon"] = info["icon"]
            app["percentage"] = round((app["duration"] / total_duration * 100), 1) if total_duration > 0 else 0.0

            b_info = budgets.get(a_id)
            if b_info and b_info.get("enabled", 1) and b_info.get("daily_limit_minutes", 0) > 0:
                limit_mins = b_info["daily_limit_minutes"]
                range_days = 1
                if range_type == "week":
                    range_days = 7
                elif range_type == "month":
                    range_days = 30
                elif range_type == "year":
                    range_days = 365

                if range_type == "all_time":
                    app["budget_minutes"] = limit_mins
                    app["budget_percentage"] = None
                    app["block_on_exceed"] = bool(b_info.get("block_on_exceed", 1))
                else:
                    total_limit_secs = limit_mins * 60 * range_days
                    app["budget_minutes"] = limit_mins * range_days if range_days > 1 else limit_mins
                    app["daily_limit_minutes"] = limit_mins
                    app["budget_percentage"] = min(100.0, round((app["duration"] / float(total_limit_secs)) * 100, 1))
                    app["block_on_exceed"] = bool(b_info.get("block_on_exceed", 1))
            else:
                app["budget_minutes"] = None
                app["budget_percentage"] = None
                app["block_on_exceed"] = False

        # Category Breakdown
        categories = sorted(cat_map.values(), key=lambda c: c["duration"], reverse=True)
        for cat in categories:
            cat["percentage"] = round((cat["duration"] / total_duration * 100), 1) if total_duration > 0 else 0.0

        # Hourly or Daily Trend Distribution
        empty_slot = {"duration": 0, "keystrokes": 0, "clicks": 0}
        if range_type == "day":
            timeline = []
            for h in range(24):
                entry = {"hour_int": h, **bucket_map.get(h, empty_slot)}
                entry["duration"] = min(3600, int(entry["duration"]))
                timeline.append(entry)
        elif range_type in ("week", "month"):
            num_days = 7 if range_type == "week" else 30
            timeline = []
            for i in range(num_days - 1, -1, -1):
                d_obj = anchor_date - datetime.timedelta(days=i)
                d = d_obj.strftime("%Y-%m-%d")
                entry = bucket_map.get(d, empty_slot)
                timeline.append({
                    "date": d,
                    "label": d_obj.strftime("%a") if range_type == "week" else d[-5:],
                    "duration": entry["duration"],
                    "keystrokes": entry["keystrokes"],
                    "clicks": entry["clicks"]
                })
        else:
            # 12-Month slots for Year and All-Time
            timeline = []
            cur_year = anchor_date.year
            cur_month = anchor_date.month
            for i in range(11, -1, -1):
                m_offset = cur_month - i
                y = cur_year
                while m_offset <= 0:
                    m_offset += 12
                    y -= 1
                m_str = f"{y:04d}-{m_offset:02d}"
                d_sample = datetime.date(y, m_offset, 1)
                entry = bucket_map.get(m_str, empty_slot)
                timeline.append({
                    "month_str": m_str,
                    "label": d_sample.strftime("%b"),
                    "duration": entry["duration"],
                    "keystrokes": entry["keystrokes"],
                    "clicks": entry["clicks"]
                })

        # Calculate Focus & Productivity Score (0-100%)
        productive_cats = {"Development", "Productivity", "Media & Design"}
        neutral_cats = {"System", "Other"}
        prod_secs = sum(c["duration"] for c in categories if c["category"] in productive_cats)
        neut_secs = sum(c["duration"] for c in categories if c["category"] in neutral_cats)
        
        if total_duration > 0:
            focus_score = int(round(((prod_secs + (neut_secs * 0.5)) / float(total_duration)) * 100))
        else:
            focus_score = 100

        if focus_score >= 75:
            focus_rating = "Deep Work"
        elif focus_score >= 50:
            focus_rating = "Balanced"
        else:
            focus_rating = "Leisure"

    return {
        "range_type": range_type,
        "target_date": target_date,
        "total_duration": total_duration,
        "total_keystrokes": totals["keystrokes"],
        "total_clicks": totals["clicks"],
        "total_scrolls": totals["scrolls"],
        "focus_score": focus_score,
        "focus_rating": focus_rating,
        "apps": apps,
        "categories": categories,
        "timeline": timeline
    }

def get_activity_heatmap_data(days: int = 70) -> List[Dict[str, Any]]:
    init_db()
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=days - 1)).strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT 
            date_str,
            SUM(duration_seconds) as duration,
            SUM(keystrokes) as keystrokes,
            SUM(clicks) as clicks
        FROM daily_app_totals
        WHERE date_str >= ? AND LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL}
        GROUP BY date_str
        ORDER BY date_str ASC
        """, (start_date,))
        rows = {r["date_str"]: dict(r) for r in cursor.fetchall()}

    max_interactions = 1
    for r in rows.values():
        total_act = r["keystrokes"] + r["clicks"]
        if total_act > max_interactions:
            max_interactions = total_act

    heatmap = []
    for i in range(days - 1, -1, -1):
        d_obj = today - datetime.timedelta(days=i)
        d_str = d_obj.strftime("%Y-%m-%d")
        item = rows.get(d_str, {"duration": 0, "keystrokes": 0, "clicks": 0})
        
        interactions = item["keystrokes"] + item["clicks"]
        if interactions == 0 and item["duration"] == 0:
            level = 0
        elif interactions < max_interactions * 0.25:
            level = 1
        elif interactions < max_interactions * 0.50:
            level = 2
        elif interactions < max_interactions * 0.75:
            level = 3
        else:
            level = 4

        heatmap.append({
            "date": d_str,
            "day_name": d_obj.strftime("%a"),
            "weekday": d_obj.weekday(),
            "duration": item["duration"],
            "keystrokes": item["keystrokes"],
            "clicks": item["clicks"],
            "interactions": interactions,
            "level": level
        })

    return heatmap

KNOWN_DOMAINS_MAP = {
    "youtube": ("youtube.com", "▶️"),
    "youtu.be": ("youtube.com", "▶️"),
    "github": ("github.com", "🐙"),
    "reddit": ("reddit.com", "🤖"),
    "chess.com": ("chess.com", "♟️"),
    "chess": ("chess.com", "♟️"),
    "twitter": ("x.com", "🐦"),
    "x.com": ("x.com", "🐦"),
    "instagram": ("instagram.com", "📷"),
    "chatgpt": ("chatgpt.com", "🧠"),
    "openai": ("openai.com", "🧠"),
    "wikipedia": ("wikipedia.org", "📚"),
    "twitch": ("twitch.tv", "🟣"),
    "stackoverflow": ("stackoverflow.com", "💻"),
    "stackexchange": ("stackexchange.com", "💻"),
    "hugging face": ("huggingface.co", "🤗"),
    "huggingface": ("huggingface.co", "🤗"),
    "monkeytype": ("monkeytype.com", "⌨️"),
    "livebench": ("livebench.ai", "📊"),
    "brave search": ("search.brave.com", "🦁"),
    "google search": ("google.com", "🔍"),
    "google": ("google.com", "🔍"),
    "duckduckgo": ("duckduckgo.com", "🦆"),
    "whatsapp": ("web.whatsapp.com", "💬"),
    "notion": ("notion.so", "📝"),
    "figma": ("figma.com", "🎨"),
    "spotify": ("open.spotify.com", "🎵"),
    "gitlab": ("gitlab.com", "🦊"),
    "archwiki": ("wiki.archlinux.org", "🐧"),
    "arch wiki": ("wiki.archlinux.org", "🐧"),
    "kernel.org": ("kernel.org", "🐧"),
    "opencode": ("opencode.ai", "⚡"),
    "discord": ("discord.com", "💬"),
}

def parse_window_title_info(app_id: str, raw_title: str) -> Tuple[str, str, str, str]:
    if not raw_title:
        return ("", "", "Other", "📄")

    title = raw_title.strip()
    a_lower = (app_id or "").lower()

    title = RE_COUNT_BADGES.sub("", title)
    title = RE_LEAD_CHARS.sub("", title)

    if "discord" in a_lower or "vesktop" in a_lower:
        parts = [p.strip() for p in title.split("|")]
        if len(parts) >= 3:
            channel = parts[1].strip("•* ")
            server = parts[2].strip("•* ")
            return (channel, f"discord.com · {server}", server, "💬")
        elif len(parts) == 2:
            p0 = parts[0].strip("•* ")
            p1 = parts[1].strip("•* ")
            target_name = p1 if p0.lower() in ("discord", "vesktop") else p0
            group_name = p0 if p0.lower() not in ("discord", "vesktop") else p1
            if "direct message" in p1.lower() or "dms" in p1.lower():
                return (target_name, "discord.com · DMs", "Direct Messages", "💬")
            else:
                return (target_name, f"discord.com · {group_name}", group_name, "💬")
        elif title.startswith("Discord"):
            sub = title[7:].strip(" -|•*")
            return (sub if sub else "Discord", "discord.com", "Discord", "💬")
        return (title, "discord.com", "Discord", "💬")

    elif any(b in a_lower for b in ["brave", "firefox", "chrome", "chromium", "zen", "opera", "vivaldi", "edge", "librewolf", "thorium"]):
        for suffix in [
            " - Brave", " — Brave", " - Mozilla Firefox", " — Mozilla Firefox",
            " - Google Chrome", " — Google Chrome", " - Chromium", " — Chromium",
            " - Zen Browser", " — Zen Browser", " - Opera", " — Opera",
            " - Vivaldi", " — Vivaldi", " - Microsoft Edge", " — Microsoft Edge",
            " - LibreWolf", " — LibreWolf"
        ]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()

        gh_match = RE_GH_REPO.match(title)
        if gh_match and not any(ext in gh_match.group(1) for ext in [".com", ".org", ".net", ".io"]):
            repo = gh_match.group(1)
            desc = gh_match.group(2)
            page_title = f"{repo}: {desc}" if desc else repo
            return (page_title, f"github.com/{repo}", "github.com", "🐙")

        t_low = title.lower()
        for k_key, (k_domain, k_icon) in KNOWN_DOMAINS_MAP.items():
            if k_key in t_low:
                clean_t = title
                for sep in [" - ", " — ", " | ", " • ", " · "]:
                    parts = clean_t.split(sep)
                    filtered = [p.strip() for p in parts if p.strip() and k_key not in p.strip().lower()]
                    if filtered:
                        clean_t = sep.join(filtered).strip()
                return (clean_t if clean_t else title, k_domain, k_domain, k_icon)

        domain_match = RE_DOMAIN.search(title)
        if domain_match:
            dom = domain_match.group(1).lower()
            clean_t = title.replace(domain_match.group(1), "").strip(" -|—•·")
            return (clean_t if clean_t else title, dom, dom, "🌐")

        for sep in [" | ", " — ", " - "]:
            if sep in title:
                parts = [p.strip() for p in title.split(sep) if p.strip()]
                if len(parts) >= 2:
                    site_name = parts[0]
                    page_name = sep.join(parts[1:])
                    return (page_name, site_name, site_name, "🌐")

        return (title, "web", "Other Websites & Tabs", "🌐")

    elif any(e in a_lower for e in ["code", "opencode", "kate", "zed", "sublime", "idea", "pycharm"]):
        for suffix in [" - Visual Studio Code", " — Visual Studio Code", " - VSCodium", " — VSCodium", " — OpenCode", " - OpenCode", " — Kate", " - Zed"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        return (title, "editor", "Project Workspace", "💻")

    elif any(g in a_lower for g in ["steam", "game", "minecraft", "heroic", "lutris", "wine", "csgo", "cs2", "dota2", "rocket league"]):
        return (title if title else raw_title, "gaming", "Games & Sessions", "🎮")

    return (title if title else raw_title, "app", "Tasks & Windows", "📄")

def infer_web_url(app_id: str, raw_title: str, clean_title: str, sub_link: str, group_name: str) -> str:
    a_lower = (app_id or "").lower()
    is_browser = any(b in a_lower for b in ["brave", "firefox", "chrome", "chromium", "zen", "opera", "vivaldi", "edge", "librewolf", "thorium"])
    if not is_browser:
        return ""

    t_low = (raw_title or "").lower()
    c_low = (clean_title or "").lower()

    gh_match = re.search(r"\b([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\b", raw_title)
    if ("github" in t_low or group_name == "github.com" or "github" in sub_link) and gh_match:
        repo = gh_match.group(1).rstrip(".")
        return f"https://github.com/{repo}"
    elif group_name == "github.com":
        return "https://github.com"

    if group_name == "youtube.com" or "youtube" in t_low:
        if clean_title and clean_title != "YouTube":
            q = urllib.parse.quote_plus(clean_title)
            return f"https://youtube.com/results?search_query={q}"
        return "https://youtube.com"

    if group_name == "chess.com" or "chess.com" in t_low:
        if "puzzle" in c_low:
            return "https://chess.com/puzzles"
        elif "analysis" in c_low or "pgn" in c_low:
            return "https://chess.com/analysis"
        elif "computer" in c_low:
            return "https://chess.com/play/computer"
        elif "profile" in c_low:
            u_match = re.search(r"^([a-zA-Z0-9_\-]+)", clean_title)
            if u_match:
                return f"https://chess.com/member/{u_match.group(1)}"
            return "https://chess.com/members"
        elif "online" in c_low or "play" in c_low:
            return "https://chess.com/play/online"
        return "https://chess.com"

    if group_name == "reddit.com" or "reddit" in t_low:
        r_match = re.search(r"r/([a-zA-Z0-9_]+)", raw_title)
        if r_match:
            return f"https://reddit.com/r/{r_match.group(1)}"
        return "https://reddit.com"

    if group_name == "instagram.com" or "instagram" in t_low:
        if "message" in c_low or "direct" in c_low:
            return "https://instagram.com/direct/inbox/"
        return "https://instagram.com"

    if "hugging face" in t_low or group_name == "huggingface.co":
        hf_match = re.search(r"\b([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\b", raw_title)
        if hf_match:
            return f"https://huggingface.co/{hf_match.group(1)}"
        return "https://huggingface.co"

    if group_name == "search.brave.com" or "brave search" in t_low:
        q = urllib.parse.quote_plus(clean_title)
        return f"https://search.brave.com/search?q={q}"
    if group_name == "google.com" or "google search" in t_low:
        q = urllib.parse.quote_plus(clean_title)
        return f"https://google.com/search?q={q}"

    if "whatsapp" in t_low or group_name == "web.whatsapp.com":
        return "https://web.whatsapp.com"

    if "." in group_name and not group_name.startswith("Other") and " " not in group_name and "·" not in group_name:
        return f"https://{group_name}"

    if "." in sub_link and not sub_link.startswith("web") and " " not in sub_link and "·" not in sub_link:
        return f"https://{sub_link}"

    return ""

def vacuum_and_cleanup_db():
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM activity_log WHERE duration_seconds <= 0 AND keystrokes <= 0 AND clicks <= 0 AND scrolls <= 0")
        conn.commit()
        try:
            cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")
            cursor.execute("PRAGMA optimize;")
        except Exception:
            pass

def clean_window_title(app_id: str, raw_title: str) -> str:
    res = parse_window_title_info(app_id, raw_title)
    return res[0]

def get_app_detail_stats(app_id: str, range_type: str = "day", target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns specific drilldown metrics, range-adjusted timeline, and detailed per-page/website/channel breakdown.
    """
    init_db()
    today = datetime.date.today()
    if not target_date:
        target_date = today.strftime("%Y-%m-%d")

    try:
        anchor_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        anchor_date = today

    with get_db() as conn:
        cursor = conn.cursor()

        if range_type == "day":
            date_condition = "date_str = ?"
            params = [target_date]
        elif range_type == "week":
            start_date = (anchor_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "month":
            start_date = (anchor_date - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "year":
            start_date = (anchor_date - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "all_time":
            date_condition = "1=1"
            params = []
        else:
            date_condition = "date_str = ?"
            params = [target_date]

        # 1. Summary stats for this app in the selected range
        summary_query = f"""
        SELECT 
            app_id,
            app_name,
            category,
            COALESCE(SUM(duration_seconds), 0) as total_duration,
            COALESCE(SUM(keystrokes), 0) as total_keystrokes,
            COALESCE(SUM(clicks), 0) as total_clicks,
            COALESCE(SUM(scrolls), 0) as total_scrolls,
            COUNT(DISTINCT date_str) as active_days
        FROM activity_log
        WHERE (app_id = ? OR app_name = ?) AND {date_condition}
        """
        cursor.execute(summary_query, [app_id, app_id] + params)
        row = cursor.fetchone()
        summary = dict(row) if row and row["app_id"] else {
            "app_id": app_id,
            "app_name": app_id,
            "category": "Other",
            "total_duration": 0,
            "total_keystrokes": 0,
            "total_clicks": 0,
            "total_scrolls": 0,
            "active_days": 0
        }

        # 2. Timeline history based on range_type
        if range_type == "day":
            cursor.execute("""
            SELECT 
                hour_int,
                SUM(duration_seconds) as duration,
                SUM(keystrokes) as keystrokes,
                SUM(clicks) as clicks
            FROM activity_log
            WHERE (app_id = ? OR app_name = ?) AND date_str = ?
            GROUP BY hour_int
            ORDER BY hour_int ASC
            """, (app_id, app_id, target_date))
            hourly_map = {r["hour_int"]: dict(r) for r in cursor.fetchall()}
            timeline = []
            for h in range(24):
                entry = dict(hourly_map.get(h, {"hour_int": h, "duration": 0, "keystrokes": 0, "clicks": 0}))
                entry["duration"] = min(3600, int(entry.get("duration", 0)))
                timeline.append(entry)
        elif range_type in ("week", "month"):
            num_days = 7 if range_type == "week" else 30
            cursor.execute(f"""
            SELECT 
                date_str,
                SUM(duration_seconds) as duration,
                SUM(keystrokes) as keystrokes,
                SUM(clicks) as clicks
            FROM activity_log
            WHERE (app_id = ? OR app_name = ?) AND {date_condition}
            GROUP BY date_str
            ORDER BY date_str ASC
            """, [app_id, app_id] + params)
            day_map = {r["date_str"]: dict(r) for r in cursor.fetchall()}
            timeline = []
            for i in range(num_days - 1, -1, -1):
                d_obj = anchor_date - datetime.timedelta(days=i)
                d = d_obj.strftime("%Y-%m-%d")
                entry = day_map.get(d, {"duration": 0, "keystrokes": 0, "clicks": 0})
                timeline.append({
                    "date": d,
                    "label": d_obj.strftime("%a") if range_type == "week" else d[-5:],
                    "duration": entry["duration"],
                    "keystrokes": entry["keystrokes"],
                    "clicks": entry["clicks"]
                })
        else:
            cursor.execute(f"""
            SELECT 
                SUBSTR(date_str, 1, 7) as month_str,
                SUM(duration_seconds) as duration,
                SUM(keystrokes) as keystrokes,
                SUM(clicks) as clicks
            FROM activity_log
            WHERE (app_id = ? OR app_name = ?) AND {date_condition}
            GROUP BY month_str
            ORDER BY month_str ASC
            """, [app_id, app_id] + params)
            month_map = {r["month_str"]: dict(r) for r in cursor.fetchall()}
            timeline = []
            cur_year = anchor_date.year
            cur_month = anchor_date.month
            for i in range(11, -1, -1):
                m_offset = cur_month - i
                y = cur_year
                while m_offset <= 0:
                    m_offset += 12
                    y -= 1
                m_str = f"{y:04d}-{m_offset:02d}"
                d_sample = datetime.date(y, m_offset, 1)
                entry = month_map.get(m_str, {"duration": 0, "keystrokes": 0, "clicks": 0})
                timeline.append({
                    "month_str": m_str,
                    "label": d_sample.strftime("%b"),
                    "duration": entry["duration"],
                    "keystrokes": entry["keystrokes"],
                    "clicks": entry["clicks"]
                })

        # 3. Per-page / website / channel breakdown
        cursor.execute(f"""
        SELECT 
            window_title,
            SUM(duration_seconds) as duration,
            SUM(keystrokes) as keystrokes,
            SUM(clicks) as clicks
        FROM activity_log
        WHERE (app_id = ? OR app_name = ?) AND {date_condition} 
          AND window_title IS NOT NULL AND window_title != ''
        GROUP BY window_title
        ORDER BY duration DESC
        LIMIT 60
        """, [app_id, app_id] + params)
        page_rows = cursor.fetchall()
        
        domain_groups = {}
        tot_app_dur = summary["total_duration"]
        for r in page_rows:
            raw_t = r["window_title"]
            clean_t, sub_link, grp_name, icon = parse_window_title_info(app_id, raw_t)
            if not clean_t:
                continue
            if grp_name not in domain_groups:
                domain_groups[grp_name] = {
                    "group_name": grp_name,
                    "clean_title": grp_name,
                    "icon": icon,
                    "sub_link": sub_link,
                    "duration": 0,
                    "keystrokes": 0,
                    "clicks": 0,
                    "pages": {}
                }
            g = domain_groups[grp_name]
            g["duration"] += r["duration"]
            g["keystrokes"] += r["keystrokes"]
            g["clicks"] += r["clicks"]

            if clean_t not in g["pages"]:
                url = infer_web_url(app_id, raw_t, clean_t, sub_link, grp_name)
                g["pages"][clean_t] = {
                    "clean_title": clean_t,
                    "raw_title": raw_t,
                    "sub_link": sub_link,
                    "url": url,
                    "duration": 0,
                    "keystrokes": 0,
                    "clicks": 0
                }
            g["pages"][clean_t]["duration"] += r["duration"]
            g["pages"][clean_t]["keystrokes"] += r["keystrokes"]
            g["pages"][clean_t]["clicks"] += r["clicks"]

        sorted_groups = sorted(domain_groups.values(), key=lambda g: g["duration"], reverse=True)
        pages_breakdown = []
        for g in sorted_groups:
            g_dur = g["duration"]
            g["percentage"] = round((g_dur / tot_app_dur * 100), 1) if tot_app_dur > 0 else 0.0

            sorted_sub_pages = sorted(g["pages"].values(), key=lambda p: p["duration"], reverse=True)
            for p in sorted_sub_pages:
                p["percentage"] = round((p["duration"] / g_dur * 100), 1) if g_dur > 0 else 0.0
                p["app_percentage"] = round((p["duration"] / tot_app_dur * 100), 1) if tot_app_dur > 0 else 0.0
            g["pages"] = sorted_sub_pages
            g["page_count"] = len(sorted_sub_pages)
            pages_breakdown.append(g)

        recent_titles = [g["group_name"] for g in pages_breakdown]

    info = app_resolver.resolve(summary.get("app_id", app_id), summary.get("app_name", ""))
    summary["display_name"] = info["display_name"]
    summary["icon"] = info["icon"]
    summary["category"] = info["category"]
    summary["timeline"] = timeline
    summary["daily_history"] = timeline
    summary["recent_titles"] = recent_titles
    summary["pages_breakdown"] = pages_breakdown
    summary["range_type"] = range_type
    summary["budget"] = get_app_budget(app_id)

    return summary

def get_month_activity_map(year: int, month: int) -> Dict[str, Dict[str, Any]]:
    init_db()
    prefix = f"{year:04d}-{month:02d}%"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT 
            date_str,
            SUM(duration_seconds) as duration,
            SUM(keystrokes) as keystrokes,
            SUM(clicks) as clicks
        FROM daily_app_totals
        WHERE date_str LIKE ? AND LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL}
        GROUP BY date_str
        """, (prefix,))
        rows = {r["date_str"]: dict(r) for r in cursor.fetchall()}

    max_dur = max([r["duration"] for r in rows.values()] + [1])
    result = {}
    for d_str, item in rows.items():
        dur = item["duration"]
        if dur == 0:
            level = 0
        elif dur < max_dur * 0.25:
            level = 1
        elif dur < max_dur * 0.50:
            level = 2
        elif dur < max_dur * 0.75:
            level = 3
        else:
            level = 4

        result[d_str] = {
            "duration": dur,
            "keystrokes": item["keystrokes"],
            "clicks": item["clicks"],
            "level": level
        }
    return result

def export_data_to_csv(file_path: str, range_type: str = "all_time", target_date: Optional[str] = None):
    """Exports activity history to CSV for spreadsheets."""
    import csv
    init_db()
    today = datetime.date.today()
    if not target_date:
        target_date = today.strftime("%Y-%m-%d")

    try:
        anchor_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        anchor_date = today

    with get_db() as conn:
        cursor = conn.cursor()
        if range_type == "day":
            date_condition = "date_str = ?"
            params = [target_date]
        elif range_type == "week":
            start_date = (anchor_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "month":
            start_date = (anchor_date - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        elif range_type == "year":
            start_date = (anchor_date - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
            date_condition = "date_str >= ? AND date_str <= ?"
            params = [start_date, target_date]
        else:
            date_condition = "1=1"
            params = []

        cursor.execute(f"""
        SELECT 
            date_str,
            hour_int,
            app_name,
            app_id,
            category,
            window_title,
            duration_seconds,
            keystrokes,
            clicks,
            scrolls
        FROM activity_log
        WHERE {date_condition} AND LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL}
        ORDER BY date_str DESC, hour_int DESC
        """, params)
        rows = cursor.fetchall()

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Hour", "Application", "App ID", "Category", "Window Title", "Duration (Seconds)", "Duration (Formatted)", "Keystrokes", "Clicks", "Scrolls"])
        for r in rows:
            dur = r["duration_seconds"]
            mins = dur // 60
            secs = dur % 60
            dur_fmt = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            writer.writerow([
                r["date_str"],
                f"{r['hour_int']:02d}:00",
                r["app_name"],
                r["app_id"],
                r["category"],
                r["window_title"] or "",
                dur,
                dur_fmt,
                r["keystrokes"],
                r["clicks"],
                r["scrolls"]
            ])

def export_data_to_json(file_path: str):
    """Exports full database backup as structured JSON."""
    import json
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM activity_log WHERE LOWER(app_id) NOT IN {EXCLUDED_APP_IDS_SQL} ORDER BY id ASC")
        logs = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT key_code, SUM(count) as count FROM key_heatmap_v2 GROUP BY key_code")
        keys = {r["key_code"]: r["count"] for r in cursor.fetchall()}

        cursor.execute("SELECT button_name, SUM(count) as count FROM mouse_heatmap_v2 GROUP BY button_name")
        mouse = {r["button_name"]: r["count"] for r in cursor.fetchall()}

        cursor.execute("SELECT * FROM custom_app_rules")
        rules = [dict(r) for r in cursor.fetchall()]

    backup = {
        "version": "2.2",
        "exported_at": datetime.datetime.now().isoformat(),
        "total_records": len(logs),
        "activity_logs": logs,
        "key_heatmap": keys,
        "mouse_heatmap": mouse,
        "custom_rules": rules
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2)

def get_stats_for_date(date_str: Optional[str] = None) -> Dict[str, Any]:
    res = get_stats_by_range("day", date_str)
    res["hourly"] = res.get("timeline", [])
    res["date"] = res.get("target_date")
    return res

def get_week_stats() -> List[Dict[str, Any]]:
    res = get_stats_by_range("week")
    return res.get("timeline", [])
