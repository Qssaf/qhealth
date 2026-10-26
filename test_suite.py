import os
import sys
import unittest
import datetime
import tempfile
import sqlite3
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from qhealth_core.app_resolver import app_resolver
from qhealth_core import db
from qhealth_gui.utils import format_duration, format_number, get_category_color, get_app_icon_pixmap

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Create Qt Application for headless widget testing
app = QApplication.instance() or QApplication(sys.argv)

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_db_dir = db.DB_DIR
        self.orig_db_path = db.DB_PATH

        db.DB_DIR = Path(self.temp_dir.name)
        db.DB_PATH = db.DB_DIR / "test_qhealth.db"
        db.init_db(force=True)

    def tearDown(self):
        db.DB_DIR = self.orig_db_dir
        db.DB_PATH = self.orig_db_path
        db.close_connection()  # Windows can't delete a database file that is still open
        self.temp_dir.cleanup()

    def test_init_db(self):
        self.assertTrue(db.DB_PATH.exists())
        conn = sqlite3.connect(db.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("activity_log", tables)
        self.assertIn("key_heatmap_v2", tables)
        self.assertIn("mouse_heatmap_v2", tables)
        self.assertIn("app_settings", tables)
        conn.close()

    def test_record_and_get_stats_by_range(self):
        # Empty DB check (no division by zero)
        empty_stats = db.get_stats_by_range("day")
        self.assertEqual(empty_stats["total_duration"], 0)
        self.assertEqual(empty_stats["apps"], [])
        self.assertEqual(empty_stats["categories"], [])

        # Record activity chunks with special characters in title and app
        db.record_activity_chunk(
            app_id="ai.opencode.desktop",
            app_name="OpenCode",
            window_title="qhealth - main.py [modified] (test's quote)",
            duration_seconds=120,
            keystrokes=450,
            clicks=80,
            scrolls=15
        )
        db.record_activity_chunk(
            app_id="firefox",
            app_name="Firefox",
            window_title="YouTube - Music Stream",
            duration_seconds=300,
            keystrokes=30,
            clicks=40,
            scrolls=20
        )

        # Test Day stats
        day_stats = db.get_stats_by_range("day")
        self.assertEqual(day_stats["total_duration"], 420)
        self.assertEqual(day_stats["total_keystrokes"], 480)
        self.assertEqual(day_stats["total_clicks"], 120)
        self.assertEqual(day_stats["total_scrolls"], 35)
        self.assertEqual(len(day_stats["apps"]), 2)
        
        # Verify app resolution in DB query
        top_app = day_stats["apps"][0] # Firefox (300s)
        self.assertEqual(top_app["app_name"], "Firefox")
        self.assertEqual(top_app["category"], "Browsing")
        self.assertGreater(top_app["percentage"], 70.0)

        # Test Week, Month, Year, All-Time stats
        for r_type in ["week", "month", "year", "all_time"]:
            stats = db.get_stats_by_range(r_type)
            self.assertEqual(stats["total_duration"], 420)
            self.assertEqual(len(stats["apps"]), 2)
            self.assertTrue(len(stats["timeline"]) > 0)

    def test_daily_rollup_matches_raw_log(self):
        q = """SELECT date_str, app_id, category, SUM(duration_seconds), SUM(keystrokes), SUM(clicks), SUM(scrolls)
               FROM {} GROUP BY 1, 2, 3
               HAVING SUM(duration_seconds) + SUM(keystrokes) + SUM(clicks) + SUM(scrolls) > 0 ORDER BY 1, 2, 3"""

        def assert_in_sync():
            with db.get_db() as conn:
                raw = [tuple(r) for r in conn.execute(q.format("activity_log"))]
                rolled = [tuple(r) for r in conn.execute(q.format("daily_app_stats"))]
            self.assertEqual(raw, rolled)
            return raw

        db.record_activity_chunk("code", "VS Code", "a.py", 60, 10, 2, 1, category="Development")
        db.record_activity_chunk("code", "VS Code", "a.py", 30, 5, 1, 0, category="Development")  # upsert path
        db.record_activity_chunk("code", "VS Code", "b.py", 20, 0, 0, 3, category="Development")
        db.record_activity_chunk("spotify", "Spotify", "song", 40, 0, 4, 0, category="Media & Design")
        self.assertEqual(len(assert_in_sync()), 2)

        db.set_custom_app_rule("code", "Productivity")  # re-categorises history via UPDATE
        self.assertEqual(assert_in_sync()[0][2], "Productivity")

        with db.get_db() as conn:
            conn.execute("DELETE FROM activity_log WHERE window_title = 'b.py'")
            conn.commit()
        assert_in_sync()

        # Pre-rollup databases are backfilled once on startup
        with db.get_db() as conn:
            conn.execute("DROP TABLE daily_app_stats")
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
        db.init_db(force=True)
        assert_in_sync()
        self.assertEqual(db.get_stats_by_range("day")["total_duration"], 130)

    def test_heatmap_data(self):
        db.record_activity_chunk("code", "VS Code", "main.py", 100, 500, 100, 10)
        heatmap = db.get_activity_heatmap_data(days=70)
        self.assertEqual(len(heatmap), 70)
        today_item = heatmap[-1]
        self.assertGreaterEqual(today_item["keystrokes"], 500)
        self.assertGreaterEqual(today_item["clicks"], 100)
        self.assertTrue(0 <= today_item["level"] <= 4)

    def test_app_detail_stats(self):
        db.record_activity_chunk("vesktop", "Vesktop", "(1) Discord | #general | OpenCode", 240, 600, 150, 10)
        # Test day range
        detail_day = db.get_app_detail_stats("vesktop", "day")
        self.assertEqual(detail_day["display_name"], "Vesktop")
        self.assertEqual(detail_day["total_duration"], 240)
        self.assertEqual(detail_day["total_keystrokes"], 600)
        self.assertEqual(detail_day["total_clicks"], 150)
        self.assertTrue(len(detail_day["pages_breakdown"]) >= 1)
        self.assertEqual(detail_day["pages_breakdown"][0]["group_name"], "OpenCode")
        self.assertEqual(detail_day["pages_breakdown"][0]["pages"][0]["clean_title"], "#general")
        self.assertEqual(len(detail_day["timeline"]), 24) # 24 hours

        clean_yt, yt_link, yt_grp, yt_ico = db.parse_window_title_info("brave-browser", "YouTube - Lofi Hip Hop Stream - Brave")
        self.assertEqual(clean_yt, "Lofi Hip Hop Stream")
        self.assertEqual(yt_link, "youtube.com")
        self.assertEqual(yt_grp, "youtube.com")
        self.assertEqual(yt_ico, "▶️")

        clean_gh, gh_link, gh_grp, gh_ico = db.parse_window_title_info("firefox", "GitHub - Qssaf/qhealth: Digital Wellbeing — Mozilla Firefox")
        self.assertEqual(clean_gh, "Qssaf/qhealth: Digital Wellbeing")
        self.assertEqual(gh_link, "github.com")
        self.assertEqual(gh_grp, "github.com")
        self.assertEqual(gh_ico, "🐙")

        clean_chess, chess_link, chess_grp, chess_ico = db.parse_window_title_info("brave-browser", "Play Chess Online - Chess.com - Brave")
        self.assertEqual(clean_chess, "Play Chess Online")
        self.assertEqual(chess_link, "chess.com")
        self.assertEqual(chess_grp, "chess.com")
        self.assertEqual(chess_ico, "♟️")

        url_gh = db.infer_web_url("firefox", "GitHub - Qssaf/qhealth: Digital Wellbeing — Mozilla Firefox", "Qssaf/qhealth", "github.com", "github.com")
        self.assertEqual(url_gh, "https://github.com/Qssaf/qhealth")

        url_chess = db.infer_web_url("brave-browser", "Play Chess Online - Chess.com - Brave", "Play Chess Online", "chess.com", "chess.com")
        self.assertEqual(url_chess, "https://chess.com/play/online")

        db.vacuum_and_cleanup_db()

        # Test week range
        detail_week = db.get_app_detail_stats("vesktop", "week")
        self.assertEqual(len(detail_week["timeline"]), 7)

    def test_parse_window_title_annotations_and_dms(self):
        annotations = db.parse_window_title_info.__annotations__
        self.assertIn("return", annotations)

        dm_title, dm_link, dm_grp, dm_ico = db.parse_window_title_info("vesktop", "• Discord | @Special Snail ;)")
        self.assertEqual(dm_title, "@Special Snail ;)")
        self.assertEqual(dm_grp, "@Special Snail ;)")

        dm2_title, dm2_link, dm2_grp, dm2_ico = db.parse_window_title_info("vesktop", "• Discord | Direct Messages")
        self.assertEqual(dm2_title, "Direct Messages")

    def test_historical_anchor_date_timeline(self):
        past_date = "2026-08-15"
        db.record_activity_chunk("firefox", "Firefox", "Historical Tab", 600, 100, 20, 5)
        with db.get_db() as conn:
            conn.cursor().execute("UPDATE activity_log SET date_str = ? WHERE window_title = 'Historical Tab'", (past_date,))
            conn.commit()

        stats_week = db.get_stats_by_range("week", target_date=past_date)
        timeline_dates = [entry["date"] for entry in stats_week["timeline"]]
        self.assertIn(past_date, timeline_dates)
        past_entry = next(entry for entry in stats_week["timeline"] if entry["date"] == past_date)
        self.assertEqual(past_entry["duration"], 600)

        detail_week = db.get_app_detail_stats("firefox", "week", target_date=past_date)
        detail_dates = [entry["date"] for entry in detail_week["timeline"]]
        self.assertIn(past_date, detail_dates)

    def test_scroll_only_chunk_recorded_and_preserved(self):
        db.record_activity_chunk("reader", "PDF Reader", "Document.pdf", 0, 0, 0, 75)
        with db.get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT scrolls FROM activity_log WHERE app_id = 'reader'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 75)

        db.vacuum_and_cleanup_db()

        with db.get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT scrolls FROM activity_log WHERE app_id = 'reader'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 75)

    def test_key_and_mouse_heatmap(self):
        db.record_input_heatmap_chunk(
            {57: 100, 17: 50, 30: 40},
            {"left": 200, "right": 30, "middle": 10}
        )
        keys_day = db.get_keyboard_heatmap_data("day")
        mouse_day = db.get_mouse_heatmap_data("day")
        self.assertEqual(keys_day[57], 100)
        self.assertEqual(keys_day[17], 50)
        self.assertEqual(mouse_day["left"], 200)
        self.assertEqual(mouse_day["right"], 30)

        # Test week range
        keys_week = db.get_keyboard_heatmap_data("week")
        self.assertEqual(keys_week[57], 100)

    def test_month_activity_map(self):
        today = datetime.date.today()
        d_str = today.strftime("%Y-%m-%d")
        db.record_activity_chunk("code", "VS Code", "main.py", 720, 1500, 300, 40)
        month_map = db.get_month_activity_map(today.year, today.month)
        self.assertIn(d_str, month_map)
        self.assertEqual(month_map[d_str]["duration"], 720)
        self.assertEqual(month_map[d_str]["keystrokes"], 1500)
        self.assertEqual(month_map[d_str]["clicks"], 300)
        self.assertEqual(month_map[d_str]["level"], 4)

    def test_custom_rule_and_export(self):
        # 1. Custom app rule
        db.record_activity_chunk("custom_tool", "Custom Tool", "Editing code", 300, 100, 20, 5)
        db.set_custom_app_rule("custom_tool", "Productivity")
        rules = db.get_custom_app_rules()
        self.assertIn("custom_tool", rules)
        self.assertEqual(rules["custom_tool"]["category"], "Productivity")

        # 2. App budget & limit
        db.set_app_budget("custom_tool", 60, enabled=True)
        b_info = db.get_app_budget("custom_tool")
        self.assertIsNotNone(b_info)
        self.assertEqual(b_info["daily_limit_minutes"], 60)

        # 3. Streaks & milestones
        streak_stats = db.get_activity_streak_stats()
        self.assertIn("current_streak", streak_stats)
        self.assertIn("longest_streak", streak_stats)
        self.assertGreaterEqual(len(streak_stats["milestones"]), 5)

        # 4. CSV & JSON export
        csv_path = db.DB_DIR / "export_test.csv"
        json_path = db.DB_DIR / "export_test.json"
        
        # Insert a row with potential CSV injection formula
        db.record_activity_chunk(
            app_id="malicious_calc",
            app_name="=cmd|'/C calc'!A0",
            window_title="@SUM(1+1)",
            duration_seconds=60,
            keystrokes=10,
            clicks=2,
            scrolls=1
        )
        db.export_data_to_csv(str(csv_path), "day")
        db.export_data_to_json(str(json_path))

        self.assertTrue(csv_path.exists())
        self.assertTrue(json_path.exists())
        self.assertGreater(csv_path.stat().st_size, 50)
        self.assertGreater(json_path.stat().st_size, 50)

        # Verify CSV formula injection sanitization (prepended single quote)
        csv_content = csv_path.read_text(encoding="utf-8")
        self.assertIn("'=cmd|'/C calc'!A0", csv_content)
        self.assertIn("'@SUM(1+1)", csv_content)

    def test_settings_ipc(self):
        self.assertFalse(db.is_paused_setting())
        new_state = db.toggle_pause_setting()
        self.assertTrue(new_state)
        self.assertTrue(db.is_paused_setting())
        db.toggle_pause_setting()
        self.assertFalse(db.is_paused_setting())

    def test_budget_and_exceeded_blocking(self):
        # 1. Set budget with block_on_exceed enabled
        db.set_app_budget("steam", 30, enabled=True, block_on_exceed=True)
        b_info = db.get_app_budget("steam")
        self.assertIsNotNone(b_info)
        self.assertEqual(b_info["daily_limit_minutes"], 30)
        self.assertEqual(b_info["block_on_exceed"], 1)

        # 2. Record 20 minutes (under 30m limit)
        today = datetime.date.today().strftime("%Y-%m-%d")
        db.record_activity_chunk(
            app_id="steam",
            app_name="Steam",
            window_title="Steam Library",
            duration_seconds=1200, # 20 mins
            keystrokes=50,
            clicks=10,
            scrolls=5
        )
        exceeded = db.get_exceeded_app_budgets(today)
        self.assertNotIn("steam", exceeded)

        # 3. Record another 15 minutes (total 35m -> exceeds 30m limit)
        db.record_activity_chunk(
            app_id="steam",
            app_name="Steam",
            window_title="Counter-Strike 2",
            duration_seconds=900, # 15 mins
            keystrokes=200,
            clicks=80,
            scrolls=10
        )
        exceeded = db.get_exceeded_app_budgets(today)
        self.assertIn("steam", exceeded)
        self.assertEqual(exceeded["steam"]["daily_limit_minutes"], 30)
        self.assertTrue(exceeded["steam"]["block_on_exceed"])
        self.assertGreaterEqual(exceeded["steam"]["used_minutes"], 35.0)

        # 4. Check get_stats_by_range includes block_on_exceed
        stats = db.get_stats_by_range("day", target_date=today)
        steam_app = next((a for a in stats["apps"] if a["app_id"] == "steam"), None)
        self.assertIsNotNone(steam_app)
        self.assertEqual(steam_app["budget_percentage"], 100.0)
        self.assertTrue(steam_app["block_on_exceed"])

        # 5. Disable blocking toggle
        db.set_app_budget("steam", 30, enabled=True, block_on_exceed=False)
        exceeded = db.get_exceeded_app_budgets(today)
        self.assertIn("steam", exceeded)
        self.assertFalse(exceeded["steam"]["block_on_exceed"])

        # 6. Disable budget completely
        db.set_app_budget("steam", 0, enabled=False)
        exceeded = db.get_exceeded_app_budgets(today)
        self.assertNotIn("steam", exceeded)

class TestAppResolver(unittest.TestCase):
    def test_explicit_overrides(self):
        res = app_resolver.resolve("ai.opencode.desktop")
        self.assertEqual(res["display_name"], "OpenCode")
        self.assertEqual(res["icon"], "ai.opencode.desktop")
        self.assertEqual(res["category"], "Development")
        self.assertTrue(res["is_active_window"])

        res_code = app_resolver.resolve("code")
        self.assertEqual(res_code["display_name"], "Visual Studio Code")

    def test_desktop_and_idle_detection(self):
        res_idle = app_resolver.resolve("Desktop / Idle")
        self.assertFalse(res_idle["is_active_window"])

        res_empty = app_resolver.resolve("")
        self.assertFalse(res_empty["is_active_window"])

    def test_token_isolation(self):
        # Ensure 'code' does not match 'opencode'
        res_open = app_resolver.resolve("opencode")
        self.assertEqual(res_open["display_name"], "OpenCode")

    def test_reverse_dns_and_suffix_resolution(self):
        app_resolver._apps_cache["org.pulseaudio.pavucontrol"] = {
            "display_name": "Volume Control",
            "icon": "org.pulseaudio.pavucontrol",
            "category": "Media & Design",
            "desktop_id": "org.pulseaudio.pavucontrol"
        }
        app_resolver.clear_cache()
        res = app_resolver.resolve("pavucontrol")
        self.assertEqual(res["display_name"], "Volume Control")
        self.assertEqual(res["category"], "Media & Design")

    def test_category_color_distinctness(self):
        dev_c = get_category_color("Development")
        browse_c = get_category_color("Browsing")
        game_c = get_category_color("Gaming")
        self.assertNotEqual(dev_c.name(), browse_c.name())
        self.assertNotEqual(dev_c.name(), game_c.name())

class TestGUIWidgets(unittest.TestCase):
    def setUp(self):
        from qhealth_gui.main_window import QHealthMainWindow
        from qhealth_gui.widgets.radial_chart import RadialChartWidget
        from qhealth_gui.widgets.hourly_timeline import HourlyTimelineWidget
        from qhealth_gui.widgets.app_leaderboard import AppLeaderboardWidget
        from qhealth_gui.widgets.app_detail_view import AppDetailView
        from qhealth_gui.widgets.heatmap_grid import HeatmapGridWidget
        from qhealth_gui.widgets.keyboard_heatmap import KeyboardHeatmapWidget
        from qhealth_gui.widgets.mouse_heatmap import MouseHeatmapWidget
        from qhealth_gui.widgets.live_pulse import LivePulseWidget
        from qhealth_gui.widgets.stat_cards import StatCardsWidget
        from qhealth_gui.widgets.glowing_calendar import GlowingCalendarPopup, GlowingDatePickerBtn

        self.RadialChartWidget = RadialChartWidget
        self.HourlyTimelineWidget = HourlyTimelineWidget
        self.AppLeaderboardWidget = AppLeaderboardWidget
        self.AppDetailView = AppDetailView
        self.HeatmapGridWidget = HeatmapGridWidget
        self.KeyboardHeatmapWidget = KeyboardHeatmapWidget
        self.MouseHeatmapWidget = MouseHeatmapWidget
        self.LivePulseWidget = LivePulseWidget
        self.StatCardsWidget = StatCardsWidget
        self.GlowingCalendarPopup = GlowingCalendarPopup
        self.GlowingDatePickerBtn = GlowingDatePickerBtn
        self.QHealthMainWindow = QHealthMainWindow

    def test_widget_rendering_edge_cases(self):
        # 1. Radial chart with 0 seconds and with apps
        radial = self.RadialChartWidget()
        radial.update_data(0, [])
        radial.update_data(3600, [{"app_name": "OpenCode", "duration": 3600, "percentage": 100.0}], "week")

        # 2. Timeline widget across all ranges
        timeline = self.HourlyTimelineWidget()
        timeline.update_data([{"hour_int": h, "duration": h * 100, "keystrokes": 10, "clicks": 5} for h in range(24)], "day")
        timeline.update_data([{"date": "2026-08-30", "label": "Sun", "duration": 500, "keystrokes": 50, "clicks": 20}], "week")
        timeline.update_data([], "month")

        # 3. Leaderboard with search, sort, and selection
        selected_app = None
        def on_click(app_dict):
            nonlocal selected_app
            selected_app = app_dict

        board = self.AppLeaderboardWidget(on_app_click=on_click)
        board.update_apps([
            {"app_id": "ai.opencode.desktop", "app_name": "OpenCode", "category": "Development", "duration": 1200, "keystrokes": 300, "clicks": 50, "percentage": 80.0},
            {"app_id": "vesktop", "app_name": "Vesktop", "category": "Communication", "duration": 300, "keystrokes": 50, "clicks": 20, "percentage": 20.0}
        ])
        board._set_sort("keystrokes")
        board._on_search_changed("open")

        # 4. App detail view
        detail = self.AppDetailView(on_back=lambda: None)
        detail.set_app_data({
            "app_id": "ai.opencode.desktop",
            "display_name": "OpenCode",
            "category": "Development",
            "icon": "ai.opencode.desktop",
            "total_duration": 1200,
            "total_keystrokes": 300,
            "total_clicks": 50,
            "active_days": 3,
            "daily_history": [{"date": "2026-08-30", "day_name": "Sun", "duration": 1200, "keystrokes": 300, "clicks": 50}],
            "recent_titles": ["main.py", "db.py"]
        })

        # 5. Keyboard & Mouse heatmaps
        kb = self.KeyboardHeatmapWidget()
        kb.update_data({57: 500, 17: 200, 30: 150})
        
        mouse = self.MouseHeatmapWidget()
        mouse.update_data({"left": 800, "right": 100, "middle": 40, "side1": 20})

        # 6. Glowing Calendar Popup & Picker Button
        picker = self.GlowingDatePickerBtn("2026-08-30")
        self.assertIn("Aug 30", picker.text())
        popup = self.GlowingCalendarPopup("2026-08-30")
        popup._prev_month()
        popup._next_month()
        popup._go_today()

        # 7. Main window comprehensive test
        win = self.QHealthMainWindow()
        for page_idx in [0, 1, 2]:
            win._switch_main_page(page_idx)
        for r in ["day", "week", "month", "year", "all_time"]:
            win._set_range(r)
        
        win._on_app_selected({"app_id": "vesktop", "app_name": "Vesktop"})
        win._on_back_to_apps_list()
        win.close()

class TestBlocker(unittest.TestCase):
    def test_immunity_checks(self):
        from qhealth_core.blocker import is_immune, is_process_running

        # Critical desktop, screenshot, and editor components must be immune
        self.assertTrue(is_immune("qhealth"))
        self.assertTrue(is_immune("opencode"))
        self.assertTrue(is_immune("ai.opencode.desktop"))
        self.assertTrue(is_immune("plasmashell"))
        self.assertTrue(is_immune("kwin_wayland"))
        self.assertTrue(is_immune("systemsettings"))
        self.assertTrue(is_immune("spectacle"))
        self.assertTrue(is_immune("desktop"))
        self.assertTrue(is_immune("idle"))
        self.assertTrue(is_immune("konsole"))
        self.assertTrue(is_immune("alacritty"))
        self.assertTrue(is_immune("kitty"))
        self.assertTrue(is_immune("polkit-kde-authentication-agent-1"))

        # Low PIDs and self PID must be immune
        self.assertTrue(is_immune("", "", pid=1))
        self.assertTrue(is_immune("", "", pid=os.getpid()))

        # Non-immune user apps
        self.assertFalse(is_immune("steam"))
        self.assertFalse(is_immune("brave-browser"))
        self.assertFalse(is_immune("vesktop"))
        self.assertFalse(is_immune("spotify"))

    def test_process_tree_safety(self):
        from qhealth_core.blocker import get_process_tree
        # Never traverse PID 1 or self
        self.assertEqual(get_process_tree(1), [])
        self.assertEqual(get_process_tree(os.getpid()), [])

    def test_notification_throttling(self):
        from qhealth_core.blocker import send_block_notification, _last_notification_time
        _last_notification_time.clear()
        t0 = datetime.datetime.now().timestamp()
        send_block_notification("TestApp", 30, "test_app", is_reopen=True)
        self.assertIn("test_app", _last_notification_time)
        recorded_t = _last_notification_time["test_app"]
        self.assertGreaterEqual(recorded_t, t0 - 1)

        # Second call immediately should be throttled (timestamp unchanged)
        send_block_notification("TestApp", 30, "test_app", is_reopen=True)
        self.assertEqual(_last_notification_time["test_app"], recorded_t)

class TestActivityTrackerBlocking(unittest.TestCase):
    def test_tracker_blocking_cache_and_matching(self):
        from qhealth_core.tracker import ActivityTracker
        tracker = ActivityTracker()

        # Initially unblocked
        self.assertIsNone(tracker.is_app_blocked("steam"))

        # Update blocked apps
        tracker.update_blocked_apps({
            "steam": {"daily_limit_minutes": 60, "block_on_exceed": True},
            "brave-browser": {"daily_limit_minutes": 120, "block_on_exceed": True},
            "unblocked_app": {"daily_limit_minutes": 30, "block_on_exceed": False},
        })

        # Check direct match
        res_steam = tracker.is_app_blocked("steam")
        self.assertIsNotNone(res_steam)
        self.assertEqual(res_steam["daily_limit_minutes"], 60)

        # Check reverse-DNS / suffix match
        res_brave = tracker.is_app_blocked("brave", raw_cls="brave-browser")
        self.assertIsNotNone(res_brave)

        # Check app with block_on_exceed=False is not in blocked set
        self.assertIsNone(tracker.is_app_blocked("unblocked_app"))

        # Check unmonitored app
        self.assertIsNone(tracker.is_app_blocked("vesktop"))


class TestFocusSession(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_db_dir = db.DB_DIR
        self.orig_db_path = db.DB_PATH

        db.DB_DIR = Path(self.temp_dir.name)
        db.DB_PATH = db.DB_DIR / "test_qhealth_focus.db"
        db.init_db(force=True)

    def tearDown(self):
        db.DB_DIR = self.orig_db_dir
        db.DB_PATH = self.orig_db_path
        db.close_connection()  # Windows can't delete a database file that is still open
        self.temp_dir.cleanup()

    def test_focus_session_lifecycle(self):
        # 1. Initially inactive
        sess = db.get_focus_session()
        self.assertFalse(sess["active"])
        self.assertFalse(db.is_focus_active())

        # 2. Start Focus Session for 60 minutes with 2 allowed apps
        started = db.start_focus_session(60, ["code", "alacritty"])
        self.assertTrue(started["active"])
        self.assertEqual(started["duration_minutes"], 60)
        self.assertIn("code", started["allowed_apps"])
        self.assertIn("alacritty", started["allowed_apps"])
        self.assertTrue(db.is_focus_active())

        # 3. Query back active session
        curr = db.get_focus_session()
        self.assertTrue(curr["active"])
        self.assertGreater(curr["remaining_seconds"], 3500)
        self.assertIn("code", curr["allowed_apps"])

        # 4. Stop session early
        db.stop_focus_session()
        self.assertFalse(db.is_focus_active())
        stopped = db.get_focus_session()
        self.assertFalse(stopped["active"])
        self.assertEqual(stopped["remaining_seconds"], 0)

    def test_focus_session_expiration(self):
        import time
        import json
        # Simulate expired session in DB
        expired_data = {
            "active": True,
            "start_time": time.time() - 3700,
            "end_time": time.time() - 100,
            "duration_minutes": 60,
            "allowed_apps": ["code"]
        }
        db.set_setting("focus_session", json.dumps(expired_data))

        # Query should auto-deactivate
        sess = db.get_focus_session()
        self.assertFalse(sess["active"])
        self.assertEqual(sess["remaining_seconds"], 0)

    def test_tracker_focus_enforcement(self):
        import time
        from qhealth_core.tracker import ActivityTracker
        tracker = ActivityTracker()

        # Inactive focus: all apps allowed
        self.assertTrue(tracker.is_app_allowed_in_focus("steam"))
        self.assertTrue(tracker.is_app_allowed_in_focus("vesktop"))

        # Activate Focus Session for 1 hour with only 'code' and 'konsole'
        tracker.update_focus_session({
            "active": True,
            "end_time": time.time() + 3600,
            "duration_minutes": 60,
            "allowed_apps": ["code", "konsole"]
        })
        self.assertTrue(tracker.is_focus_session_active())

        # Allowed app is permitted
        self.assertTrue(tracker.is_app_allowed_in_focus("code"))
        self.assertTrue(tracker.is_app_allowed_in_focus("code.desktop"))
        self.assertTrue(tracker.is_app_allowed_in_focus("konsole"))

        # Immune apps are always permitted even if not in allowlist
        self.assertTrue(tracker.is_app_allowed_in_focus("qhealth"))
        self.assertTrue(tracker.is_app_allowed_in_focus("plasmashell"))
        self.assertTrue(tracker.is_app_allowed_in_focus("kwin_wayland"))
        self.assertTrue(tracker.is_app_allowed_in_focus("opencode"))

        # Cross-suffix & hyphen matching (e.g. allowed: brave-browser -> window raw: brave)
        tracker.update_focus_session({
            "active": True,
            "end_time": time.time() + 3600,
            "duration_minutes": 60,
            "allowed_apps": ["brave-browser"]
        })
        self.assertTrue(tracker.is_app_allowed_in_focus("brave"))
        self.assertTrue(tracker.is_app_allowed_in_focus("brave-browser"))

        # Non-allowed apps are strictly blocked
        self.assertFalse(tracker.is_app_allowed_in_focus("steam"))
        self.assertFalse(tracker.is_app_allowed_in_focus("vesktop"))
        self.assertFalse(tracker.is_app_allowed_in_focus("spotify"))
        self.assertFalse(tracker.is_app_allowed_in_focus("minecraft"))

    def test_focus_dialog_widget(self):
        from qhealth_gui.widgets.focus_dialog import FocusModeDialog
        # Test dialog instantiation when inactive
        dlg = FocusModeDialog(current_active_app="Visual Studio Code", current_active_id="code")
        self.assertEqual(dlg.spin_custom.value(), 60) # Default 1 Focus Hour
        dlg._on_preset_clicked(25)
        self.assertEqual(dlg.spin_custom.value(), 25)
        dlg._on_preset_clicked(60)
        self.assertEqual(dlg.spin_custom.value(), 60)
        dlg._filter_app_items("code")
        dlg.close()

        # Test app list population from DB without TypeError
        db.record_activity_chunk("spotify", "Spotify", "Song", 60, 5, 2, 1)
        dlg_pop = FocusModeDialog()
        dlg_pop._populate_app_list()
        app_ids = [item.app_id for item in dlg_pop.app_items]
        self.assertIn("spotify", app_ids)
        dlg_pop.close()

        # Test dialog instantiation when active
        db.start_focus_session(60, ["code"])
        dlg_active = FocusModeDialog()
        self.assertTrue(hasattr(dlg_active, "clock_lbl"))
        dlg_active._refresh_status()
        dlg_active.close()
        db.stop_focus_session()



class TestPlatformLayer(unittest.TestCase):
    def test_scan_codes_map_to_evdev(self):
        from qhealth_core.keymap import scancode_to_evdev
        self.assertEqual(scancode_to_evdev(0x10, False), 16)    # Q
        self.assertEqual(scancode_to_evdev(0x39, False), 57)    # Space
        self.assertEqual(scancode_to_evdev(0x48, True), 103)    # Up arrow
        self.assertEqual(scancode_to_evdev(0x1D, True), 97)     # Right Ctrl
        self.assertEqual(scancode_to_evdev(0x5B, True), 125)    # Windows key -> Super
        self.assertIsNone(scancode_to_evdev(0x2A, True))        # fake shift around E0 keys is not a keystroke
        self.assertIsNone(scancode_to_evdev(0xFF, False))       # keyboard overrun

    def test_data_dir_per_platform(self):
        from qhealth_core import paths
        if sys.platform == "win32":
            self.assertEqual(paths.DATA_DIR.name, "QHealth")
            self.assertIn("AppData", str(paths.DATA_DIR))
        else:
            self.assertEqual(paths.DATA_DIR, Path.home() / ".local" / "share" / "qhealth")

    def test_notifications_use_registered_handler(self):
        from qhealth_core import notify
        seen = []
        notify.set_handler(lambda title, msg, critical: seen.append((title, critical)))
        try:
            notify.send("QHealth", "hello", critical=True)
        finally:
            notify.set_handler(None)
        self.assertEqual(seen, [("QHealth", True)])

    def test_learned_apps_resolve_with_their_own_name(self):
        from qhealth_core import app_resolver as resolver_module
        original_file = resolver_module.LEARNED_APPS_FILE
        with tempfile.TemporaryDirectory() as tmp:
            resolver_module.LEARNED_APPS_FILE = Path(tmp) / "learned_apps.json"  # never touch the real data dir
            try:
                app_resolver.register_app("unittestapp", "Unit Test App", "C:\\Apps\\unittestapp.exe")
                res = app_resolver.resolve("unittestapp")
                self.assertEqual(res["display_name"], "Unit Test App")
                self.assertTrue(app_resolver.is_known("UnitTestApp"))
                self.assertEqual(resolver_module.LEARNED_APPS_FILE.exists(), sys.platform == "win32")
            finally:
                resolver_module.LEARNED_APPS_FILE = original_file
                app_resolver._apps_cache.pop("unittestapp", None)
                app_resolver._learned.pop("unittestapp", None)


@unittest.skipUnless(sys.platform == "win32", "Windows backend")
class TestWindowsBackend(unittest.TestCase):
    def test_process_and_window_queries(self):
        from qhealth_core import win32
        pids = {p for p, _, _ in win32.processes()}
        self.assertIn(os.getpid(), pids)
        self.assertIn(win32.process_name(os.getpid()), ("python", "pythonw"))
        self.assertTrue(win32.process_alive(os.getpid()))
        self.assertTrue(win32.file_description(sys.executable))
        fg = win32.foreground_window()
        self.assertTrue(fg is None or isinstance(fg[0], int))
        self.assertIsInstance(win32.gui_processes(), list)

    def test_raw_input_listener_runs_and_stops(self):
        import threading, time
        from qhealth_core.win32 import RawInputListener
        listener = RawInputListener(lambda code, repeat: None, lambda button: None, lambda: None)
        thread = threading.Thread(target=listener.run, daemon=True)
        thread.start()
        time.sleep(0.5)
        self.assertTrue(thread.is_alive(), "raw input registration failed (message loop exited)")
        listener.stop()
        thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_force_close_app_ends_process(self):
        import subprocess
        from qhealth_core.blocker import find_pids_for_app, force_close_app, is_immune
        proc = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL)
        try:
            self.assertFalse(is_immune("ping", "ping", proc.pid))
            self.assertIn(proc.pid, find_pids_for_app("ping"))
            self.assertGreaterEqual(force_close_app("ping", "ping", proc.pid), 1)
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_shell_processes_are_immune(self):
        from qhealth_core.blocker import is_immune, find_pids_for_app
        self.assertTrue(is_immune("explorer"))
        self.assertEqual(find_pids_for_app("explorer"), [])

    def test_autostart_round_trip(self):
        from qhealth_core import win32
        before = win32.autostart_enabled()
        try:
            win32.set_autostart(True)
            self.assertTrue(win32.autostart_enabled())
            self.assertIn("--minimized", win32.autostart_command())
            win32.set_autostart(False)
            self.assertFalse(win32.autostart_enabled())
        finally:
            win32.set_autostart(before)


if __name__ == "__main__":
    unittest.main()
