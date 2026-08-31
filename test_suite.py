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
        self.assertEqual(len(detail_week["timeline"]), 7) # 7 days

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

if __name__ == "__main__":
    unittest.main()
