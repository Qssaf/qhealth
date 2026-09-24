import os
import sys
import unittest
import unittest.mock
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

# Never touch the real ~/.local/share/qhealth database: every test (including ones that
# only build an ActivityTracker or resolve apps) uses a throwaway DB by default.
_TEST_DB_DIR = tempfile.TemporaryDirectory()
db.DB_DIR = Path(_TEST_DB_DIR.name)
db.DB_PATH = db.DB_DIR / "qhealth.db"

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
        db.export_data_to_csv(str(csv_path), "day")
        db.export_data_to_json(str(json_path))

        self.assertTrue(csv_path.exists())
        self.assertTrue(json_path.exists())
        self.assertGreater(csv_path.stat().st_size, 50)
        self.assertGreater(json_path.stat().st_size, 50)

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

    def test_generic_desktop_suffix_does_not_hijack(self):
        app_resolver._apps_cache["io.elementary.terminal"] = {
            "display_name": "Elementary Terminal", "icon": "utilities-terminal",
            "category": "Development", "desktop_id": "io.elementary.terminal"
        }
        app_resolver.clear_cache()
        try:
            res = app_resolver.resolve("xfce4-terminal")
            self.assertEqual(res["app_id"], "xfce4-terminal")
        finally:
            del app_resolver._apps_cache["io.elementary.terminal"]
            app_resolver.clear_cache()

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

        # Critical desktop and editor components must be immune
        self.assertTrue(is_immune("qhealth"))
        self.assertTrue(is_immune("opencode"))
        self.assertTrue(is_immune("ai.opencode.desktop"))
        self.assertTrue(is_immune("plasmashell"))
        self.assertTrue(is_immune("kwin_wayland"))
        self.assertTrue(is_immune("systemsettings"))
        self.assertTrue(is_immune("desktop"))
        self.assertTrue(is_immune("idle"))
        self.assertTrue(is_immune("konsole"))

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

    @unittest.mock.patch("qhealth_core.blocker.subprocess.run")
    def test_notification_throttling(self, mock_run):
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
        self.assertEqual(mock_run.call_count, 1)

    def test_process_matching_is_not_substring_based(self):
        from qhealth_core.blocker import _process_matches
        # Exact comm / argv[0] basename
        self.assertTrue(_process_matches("discord", ["discord"], "discord", "/opt/discord/discord"))
        # Helper binaries living inside the app's own directory
        self.assertTrue(_process_matches("discord", ["discord"], "chrome_crashpad", "/opt/discord/chrome_crashpad_handler"))
        # Truncated comm prefix for long tokens (steam -> steamwebhelper)
        self.assertTrue(_process_matches("steam", ["steam"], "steamwebhelper", "/home/u/.steam/ubuntu12_64/steamwebhelper"))
        # Short ids must not match unrelated paths by substring
        self.assertFalse(_process_matches("vi", [], "libvirtd", "/usr/lib/libvirt/libvirtd"))
        self.assertFalse(_process_matches("code", ["code"], "python3", "/usr/bin/python3"))
        self.assertFalse(_process_matches("zed", [], "gzip", "/usr/bin/gzip"))

class TestDaemonBudgetEnforcement(unittest.TestCase):
    def _make_daemon(self, raw_app="", app_id="desktop", pid=0):
        from qhealth_core.daemon import QHealthDaemon
        from qhealth_core.tracker import ActivityTracker
        d = QHealthDaemon.__new__(QHealthDaemon)
        d.notified_budget_alerts = set()
        d.tracker = ActivityTracker.__new__(ActivityTracker)
        d.tracker.window_lock = __import__("threading").Lock()
        d.tracker.current_raw_app = raw_app
        d.tracker.current_title = "title"
        d.tracker.current_class = raw_app
        d.tracker.current_pid = pid
        d.tracker.resolved_app_info = {"app_id": app_id}
        return d

    def _run(self, d, mock_close):
        budgets = {"steam": {"app_id": "steam", "daily_limit_minutes": 1, "enabled": 1, "block_on_exceed": 1}}
        exceeded = {"steam": {"app_id": "steam", "daily_limit_minutes": 1, "block_on_exceed": True}}
        stats = {"apps": [{"app_id": "steam", "app_name": "Steam", "duration": 120}]}
        with unittest.mock.patch("qhealth_core.daemon.get_all_app_budgets", return_value=budgets), \
             unittest.mock.patch("qhealth_core.daemon.send_block_notification"), \
             unittest.mock.patch.object(d, "_send_notification"):
            d._check_budget_limits(stats, exceeded)

    @unittest.mock.patch("qhealth_core.daemon.force_close_app")
    def test_unfocused_exceeded_app_killed_once_and_idle_state_untouched(self, mock_close):
        # Nothing focused (empty raw app) must not be treated as a match for every app
        d = self._make_daemon(raw_app="", app_id="desktop")
        self._run(d, mock_close)
        mock_close.assert_called_once_with("steam", "Steam", None)
        self.assertEqual(d.tracker.current_title, "title")
        # Later loops must not rescan /proc while the app stays unfocused
        self._run(d, mock_close)
        self.assertEqual(mock_close.call_count, 1)

    @unittest.mock.patch("qhealth_core.daemon.force_close_app")
    def test_focused_exceeded_app_killed_with_pid(self, mock_close):
        d = self._make_daemon(raw_app="steam", app_id="steam", pid=4242)
        self._run(d, mock_close)
        self._run(d, mock_close)  # already focused-and-killed state was reset
        mock_close.assert_called_once_with("steam", "Steam", 4242)
        self.assertEqual(d.tracker.current_raw_app, "")
        self.assertEqual(d.tracker.current_pid, 0)
        self.assertEqual(d.tracker.resolved_app_info.get("app_id"), "desktop")

    @unittest.mock.patch("qhealth_core.daemon.force_close_app")
    def test_unrelated_focused_app_not_matched(self, mock_close):
        d = self._make_daemon(raw_app="org.kde.konsole", app_id="org.kde.konsole", pid=777)
        self._run(d, mock_close)
        mock_close.assert_called_once_with("steam", "Steam", None)
        self.assertEqual(d.tracker.current_pid, 777)

class TestKWinScriptRecovery(unittest.TestCase):
    def _run(self, returncode, stdout):
        from qhealth_core.tracker import ActivityTracker
        tracker = ActivityTracker.__new__(ActivityTracker)
        result = unittest.mock.Mock(returncode=returncode, stdout=stdout)
        with unittest.mock.patch("qhealth_core.tracker.subprocess.run", return_value=result), \
             unittest.mock.patch.object(ActivityTracker, "_inject_kwin_script") as inject:
            tracker._ensure_kwin_script()
        return inject.called

    def test_reinjects_only_when_kwin_reports_not_loaded(self):
        self.assertTrue(self._run(0, "b false\n"))    # KWin restarted, script gone
        self.assertFalse(self._run(0, "b true\n"))    # still loaded
        self.assertFalse(self._run(1, ""))            # no KWin on the bus (other WM)

class TestDailyRollup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig = (db.DB_DIR, db.DB_PATH)
        db.DB_DIR = Path(self.temp_dir.name)
        db.DB_PATH = db.DB_DIR / "rollup.db"
        db.init_db(force=True)

    def tearDown(self):
        db.DB_DIR, db.DB_PATH = self.orig
        self.temp_dir.cleanup()

    def _assert_rollup_exact(self):
        with db.get_db() as conn:
            expected = sorted(tuple(r) for r in conn.execute(
                "SELECT date_str, app_id, category, SUM(duration_seconds), SUM(keystrokes), SUM(clicks), SUM(scrolls) "
                "FROM activity_log GROUP BY 1, 2, 3"))
            actual = sorted(tuple(r) for r in conn.execute(
                "SELECT date_str, app_id, category, duration_seconds, keystrokes, clicks, scrolls FROM daily_app_totals"))
        self.assertEqual(actual, expected)

    def test_rollup_tracks_every_write_path(self):
        for i in range(6):  # first insert, then upsert-update of the same row
            db.record_activity_chunk("code", "VS Code", f"file{i % 2}.py", 5, 2, 1, 0, "Development")
        db.record_activity_chunk("reader", "Reader", "doc", 0, 0, 0, 3, "Other")
        self._assert_rollup_exact()

        with db.get_db() as conn:
            conn.execute("UPDATE activity_log SET date_str = '2020-01-01' WHERE window_title = 'file1.py'")
            conn.commit()
        self._assert_rollup_exact()

        db.set_custom_app_rule("code", "Productivity")  # rewrites category on history
        self._assert_rollup_exact()

        with db.get_db() as conn:
            conn.execute("DELETE FROM activity_log WHERE app_id = 'reader'")
            conn.commit()
        self._assert_rollup_exact()

        stats = db.get_stats_by_range("year")
        self.assertEqual(stats["total_duration"], 15)
        self.assertEqual(stats["categories"][0]["category"], "Productivity")

    def test_backfill_existing_history_once(self):
        db.record_activity_chunk("steam", "Steam", "game", 120, 0, 5, 0, "Gaming")
        with db.get_db() as conn:
            # Simulate a database created before the rollup existed
            conn.execute("DROP TRIGGER trg_rollup_insert")
            conn.execute("DELETE FROM daily_app_totals")
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
        db.init_db(force=True)
        db.init_db(force=True)  # a second start must not add the history again
        self._assert_rollup_exact()
        self.assertEqual(db.get_stats_by_range("week")["total_duration"], 120)

class TestDaemonDetection(unittest.TestCase):
    def test_stale_pid_file_with_recycled_pid(self):
        from qhealth_core import desktop_app
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "daemon.pid"
            # Our own PID is alive but is not a "main.py --daemon" process
            pid_file.write_text(str(os.getpid()))
            with unittest.mock.patch.object(desktop_app, "PID_FILE", pid_file):
                self.assertFalse(desktop_app.is_daemon_running())
            pid_file.write_text("garbage")
            with unittest.mock.patch.object(desktop_app, "PID_FILE", pid_file):
                self.assertFalse(desktop_app.is_daemon_running())
            with unittest.mock.patch.object(desktop_app, "PID_FILE", Path(tmp) / "missing.pid"):
                self.assertFalse(desktop_app.is_daemon_running())

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

if __name__ == "__main__":
    unittest.main()
