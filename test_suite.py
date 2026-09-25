import os
import atexit
import sys
import unittest
import unittest.mock
import datetime
import time
import tempfile
import sqlite3
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from qhealth_core.app_resolver import app_resolver
from qhealth_core import db
from qhealth_gui.utils import get_category_color

# Never touch the real ~/.local/share/qhealth database: every test (including ones that
# only build an ActivityTracker or resolve apps) uses a throwaway DB by default.
_TEST_DB_DIR = tempfile.TemporaryDirectory()
atexit.register(_TEST_DB_DIR.cleanup)
db.DB_DIR = Path(_TEST_DB_DIR.name)
db.DB_PATH = db.DB_DIR / "qhealth.db"

from PyQt6.QtWidgets import QApplication

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

    def test_heatmap_anchors_on_selected_date_and_empty_focus(self):
        db.record_activity_chunk("code", "VS Code", "x", 60, 5, 1, 0, "Development")
        today = datetime.date.today()
        past = (today - datetime.timedelta(days=100)).strftime("%Y-%m-%d")
        heat = db.get_activity_heatmap_data(days=70, target_date=past)
        self.assertEqual(len(heat), 70)
        self.assertEqual(heat[-1]["date"], past)
        self.assertEqual(sum(d["duration"] for d in heat), 0)  # today's activity is outside the window
        self.assertEqual(db.get_activity_heatmap_data(days=70)[-1]["duration"], 60)

        empty = db.get_stats_by_range("day", past)
        self.assertEqual((empty["focus_score"], empty["focus_rating"]), (0, "No Activity"))
        self.assertEqual(db.get_stats_by_range("day")["focus_rating"], "Deep Work")

    def test_all_time_chart_covers_whole_history(self):
        today = datetime.date.today()
        db.record_activity_chunk("code", "VS Code", "now", 60, 1, 1, 0, "Development")
        # Short history: 12 monthly bars, same as the Year view
        short = db.get_stats_by_range("all_time")["timeline"]
        self.assertEqual(len(short), 12)
        self.assertEqual(short[-1]["month_str"], today.strftime("%Y-%m"))

        # History older than 12 months: one bar per year, and the bars add up to the total
        old_day = today.replace(year=today.year - 3, day=1).strftime("%Y-%m-%d")
        db.record_activity_chunk("code", "VS Code", "old", 90, 1, 1, 0, "Development")
        with db.get_db() as conn:
            conn.execute("UPDATE activity_log SET date_str = ? WHERE window_title = 'old'", (old_day,))
            conn.commit()
        for stats in (db.get_stats_by_range("all_time"), db.get_app_detail_stats("code", "all_time")):
            timeline = stats["timeline"]
            self.assertEqual([t["label"] for t in timeline], [str(y) for y in range(today.year - 3, today.year + 1)])
            total = stats["total_duration"]
            self.assertEqual(sum(t["duration"] for t in timeline), total)
            self.assertEqual(total, 150)
        # The Year view keeps its 12 rolling months
        self.assertEqual(len(db.get_stats_by_range("year")["timeline"]), 12)

    def test_app_detail_matches_leaderboard_totals(self):
        db.record_activity_chunk("reader", "Reader", "book", 300, 10, 2, 0, "Productivity")
        # A different app whose recorded display name happens to equal "reader"
        db.record_activity_chunk("org.other.reader", "reader", "other", 900, 50, 9, 0, "Other")
        listed = next(a for a in db.get_stats_by_range("day")["apps"] if a["app_id"] == "reader")
        for rng in ("day", "week", "year", "all_time"):
            detail = db.get_app_detail_stats("reader", rng)
            self.assertEqual(detail["total_duration"], listed["duration"], rng)
            self.assertEqual(detail["total_keystrokes"], 10, rng)
            self.assertEqual([p["group_name"] for p in detail["pages_breakdown"]], ["Tasks & Windows"], rng)
            self.assertEqual(detail["active_days"], 1, rng)
        self.assertEqual(sum(h["duration"] for h in db.get_app_detail_stats("reader", "day")["timeline"]), 300)

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

        # JSON backup also carries budgets and settings
        import json
        db.set_app_budget("steam", 45)
        db.set_break_reminder_minutes(50)
        db.export_data_to_json(str(json_path))
        backup = json.loads(json_path.read_text())
        budgets = {b["app_id"]: b["daily_limit_minutes"] for b in backup["app_budgets"]}
        self.assertEqual(budgets["steam"], 45)
        self.assertEqual(backup["settings"]["break_reminder_minutes"], "50")

    def test_break_reminder_setting(self):
        self.assertEqual(db.get_break_reminder_minutes(), 0)  # off by default
        db.set_break_reminder_minutes(30)
        self.assertEqual(db.get_break_reminder_minutes(), 30)
        db.set_setting("break_reminder_minutes", "garbage")
        self.assertEqual(db.get_break_reminder_minutes(), 0)
        db.set_break_reminder_minutes(-5)
        self.assertEqual(db.get_break_reminder_minutes(), 0)

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

        # 5b. A one-day extension lifts the block until the new limit
        db.extend_app_budget("steam", 15, today)
        self.assertNotIn("steam", db.get_exceeded_app_budgets(today))
        usage = db.get_budget_usage(today)["steam"]
        self.assertEqual((usage["extra_minutes"], usage["effective_limit_minutes"]), (15, 45))
        stats = db.get_stats_by_range("day", target_date=today)
        steam_app = next(a for a in stats["apps"] if a["app_id"] == "steam")
        self.assertLess(steam_app["budget_percentage"], 100.0)
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(db.get_budget_extensions(tomorrow), {})

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

    def test_midnight_rollover_while_viewing_past_date(self):
        win = self.QHealthMainWindow(None)
        win.show()
        today = datetime.date.today()
        d = lambda n: (today - datetime.timedelta(days=n)).strftime("%Y-%m-%d")
        # Opened yesterday, viewing the day before; midnight has since passed
        win._today_str, win.selected_date = d(1), d(2)
        with unittest.mock.patch.object(win, "_poll_db") as poll:
            win._on_db_timer()
            poll.assert_not_called()          # past day range: nothing to refresh
            self.assertEqual(win._today_str, d(0))
            win.current_range = "all_time"    # still includes today
            win._on_db_timer()
            poll.assert_called_once()
        win.current_range = "day"
        win._on_date_changed(d(1))            # picking yesterday must stay on yesterday
        self.assertEqual(win.selected_date, d(1))
        win.close()

    def test_window_close_quits_viewer_but_keeps_tracker(self):
        from qhealth_core.desktop_app import QHealthApp
        win = self.QHealthMainWindow(None)
        win.on_close = unittest.mock.Mock()
        win.show()
        win.close()
        win.on_close.assert_called_once()

        qa = QHealthApp.__new__(QHealthApp)
        qa.tray = unittest.mock.Mock()
        qa._tray_hint_shown = False
        with unittest.mock.patch.object(QHealthApp, "quit") as quit_:
            qa.tracker = None                 # daemon running: viewer only
            qa._on_window_closed()
            quit_.assert_called_once()
            quit_.reset_mock()
            qa.tracker = unittest.mock.Mock() # no daemon: this process tracks
            qa._on_window_closed()
            qa._on_window_closed()
            quit_.assert_not_called()
        qa.tray.showMessage.assert_called_once()  # told once, not on every close

    def test_live_card_explains_missing_input_access(self):
        live = self.LivePulseWidget()
        live.update_metrics({"active_app": "Desktop", "is_idle": True, "input_access_denied": True})
        self.assertEqual(live.badge.text(), "NO INPUT ACCESS")
        self.assertIn("usermod -aG input", live.badge.toolTip())
        live.update_metrics({"active_app": "Desktop", "is_idle": True, "input_access_denied": False})
        self.assertEqual(live.badge.text(), "IDLE / AFK")
        self.assertEqual(live.badge.toolTip(), "")

    def test_past_date_labels_and_blocked_pill(self):
        from PyQt6.QtWidgets import QLabel
        radial = self.RadialChartWidget()
        radial.update_data(60, [], "day", datetime.date.today().strftime("%Y-%m-%d"))
        self.assertEqual(radial.tag_lbl.text(), "Today")
        radial.update_data(60, [], "day", "2026-01-05")
        self.assertEqual(radial.tag_lbl.text(), "Jan 05, 2026")
        radial.update_data(60, [], "week", "2026-01-05")
        self.assertEqual(radial.tag_lbl.text(), "Last 7 Days to Jan 05, 2026")
        radial.update_data(60, [], "year", "")
        self.assertEqual(radial.tag_lbl.text(), "Last 12 Months")  # rolling 365 days, not the calendar year

        timeline = self.HourlyTimelineWidget()
        timeline.update_data([{"hour_int": 0, "duration": 5}], "day", is_today=False)
        self.assertFalse(timeline.painter_widget.is_today)
        timeline.update_data([{"month_str": "2024", "label": "2024", "duration": 60}], "all_time")
        timeline.grab()  # yearly bars paint through the generic branch

        app_row = {"app_id": "steam", "app_name": "Steam", "duration": 7200, "percentage": 100.0,
                   "budget_minutes": 60, "budget_percentage": 100.0, "block_on_exceed": True}
        board = self.AppLeaderboardWidget()
        def texts():
            # Replaced rows are only deleteLater()'d, so read the rows currently in the layout
            lay = board.scroll_layout
            rows = [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget()]
            return " ".join(l.text() for r in rows for l in r.findChildren(QLabel))
        board.update_apps([app_row], can_block=True)
        self.assertIn("BLOCKED", texts())
        board.update_apps([app_row], can_block=False)  # same apps, different context
        self.assertNotIn("BLOCKED", texts())

    def test_past_date_input_page_is_static_but_streak_updates(self):
        win = self.QHealthMainWindow(None)
        win.show()
        win.selected_date = "2020-01-01"
        win._switch_main_page(1)
        win._last_streak_poll = 0.0
        with unittest.mock.patch.object(win, "_poll_db") as poll, \
             unittest.mock.patch("qhealth_gui.main_window.get_activity_streak_stats", return_value={"current_streak": 3}):
            win._on_db_timer()
            poll.assert_not_called()   # the Input page now anchors on the selected (past) date
        self.assertIn("3-Day Streak", win.streak_badge.text())
        win.hide()
        win._last_streak_poll = 0.0
        with unittest.mock.patch("qhealth_gui.main_window.get_activity_streak_stats") as streak:
            win._on_db_timer()         # hidden in the tray: no DB work at all
            streak.assert_not_called()
        win.close()

    def test_budget_extension_button(self):
        today = datetime.date.today().strftime("%Y-%m-%d")
        db.set_app_budget("steam", 30)
        self.addCleanup(db.set_app_budget, "steam", 0, False)
        view = self.AppDetailView(on_back=lambda: None)
        data = {"app_id": "steam", "display_name": "Steam", "total_duration": 1800, "target_date": today,
                "budget": {"daily_limit_minutes": 30, "enabled": 1, "block_on_exceed": 1},
                "budget_extra_minutes": 0, "timeline": [], "pages_breakdown": []}
        view.set_app_data(data, "day")
        self.assertFalse(view.extend_btn.isHidden())
        before = db.get_budget_extensions(today).get("steam", 0)
        view.extend_btn.click()
        self.assertEqual(db.get_budget_extensions(today)["steam"], before + 15)
        self.assertTrue(view.extend_btn.isHidden())  # 30m used of 45m
        self.assertIn("+15m extension", view.budget_status_lbl.text())

        # Past days, other ranges and custom limits
        view.set_app_data(dict(data, target_date="2020-01-01"), "day")
        self.assertTrue(view.extend_btn.isHidden())
        self.assertIn("on 2020-01-01", view.budget_status_lbl.text())
        view.set_app_data(dict(data, budget={"daily_limit_minutes": 45, "enabled": 1, "block_on_exceed": 1}), "week")
        self.assertEqual(view.budget_combo.currentData(), 45)
        view.set_app_data(data, "all_time")
        self.assertIn("Daily limit", view.budget_status_lbl.text())

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
        from qhealth_core.blocker import is_immune

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

    def _spawn(self, ignore_term=False):
        import subprocess
        code = ("import signal, sys, time\n"
                + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_term else "")
                + "print('ready', flush=True)\ntime.sleep(30)\n")
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        self.addCleanup(child.stdout.close)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        self.assertEqual(child.stdout.readline().strip(), "ready")  # handlers installed
        return child

    def test_terminate_pids_term_then_kill(self):
        import signal
        from qhealth_core.blocker import _terminate_pids
        polite, stubborn = self._spawn(), self._spawn(ignore_term=True)
        self.assertEqual(_terminate_pids([polite.pid, stubborn.pid]), 2)
        self.assertEqual(polite.wait(timeout=5), -signal.SIGTERM)
        self.assertEqual(stubborn.wait(timeout=5), -signal.SIGKILL)

    def test_terminate_pids_already_exited_and_fallback(self):
        import signal, subprocess, errno
        from qhealth_core.blocker import _terminate_pids
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait()  # reaped: its PID may be recycled, so it must never be signalled
        with unittest.mock.patch("qhealth_core.blocker.os.kill") as kill:
            self.assertEqual(_terminate_pids([done.pid]), 1)
            kill.assert_not_called()
        # Kernels without pidfd support fall back to plain PIDs
        child = self._spawn(ignore_term=True)
        with unittest.mock.patch("qhealth_core.blocker.os.pidfd_open", side_effect=OSError(errno.ENOSYS, "nosys")):
            self.assertEqual(_terminate_pids([child.pid]), 1)
        self.assertEqual(child.wait(timeout=5), -signal.SIGKILL)

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

class TestBudgetEnforcer(unittest.TestCase):
    def setUp(self):
        from qhealth_core.wellbeing import BudgetEnforcer
        patches = {
            "close": unittest.mock.patch("qhealth_core.wellbeing.force_close_app"),
            "block_note": unittest.mock.patch("qhealth_core.wellbeing.send_block_notification"),
            "note": unittest.mock.patch("qhealth_core.wellbeing.send_notification"),
        }
        self.mocks = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)
        self.enforcer = BudgetEnforcer(self._make_tracker())

    def _make_tracker(self, raw_app="", app_id="desktop", pid=0):
        import threading
        from qhealth_core.tracker import ActivityTracker
        t = ActivityTracker.__new__(ActivityTracker)
        t.window_lock = threading.Lock()
        t._blocked_lock = threading.Lock()
        t.blocked_app_details, t.blocked_app_ids = {}, set()
        t.current_raw_app = raw_app
        t.current_title = "title"
        t.current_class = raw_app
        t.current_pid = pid
        t.resolved_app_info = {"app_id": app_id}
        return t

    @staticmethod
    def _usage(used_seconds, limit=10, extra=0, block=True):
        return {"steam": {
            "app_id": "steam", "daily_limit_minutes": limit, "extra_minutes": extra,
            "effective_limit_minutes": limit + extra, "block_on_exceed": block,
            "used_seconds": used_seconds, "used_minutes": used_seconds / 60.0,
        }}

    def test_unfocused_exceeded_app_killed_once_and_idle_state_untouched(self):
        # Nothing focused (empty raw app) must not be treated as a match for every app
        self.enforcer.check(self._usage(700))
        self.mocks["close"].assert_called_once_with("steam", "Steam", None)
        self.assertEqual(self.enforcer.tracker.current_title, "title")
        self.assertIn("steam", self.enforcer.tracker.blocked_app_ids)
        # Later checks must not rescan /proc while the app stays unfocused
        self.enforcer.check(self._usage(705))
        self.assertEqual(self.mocks["close"].call_count, 1)

    def test_focused_exceeded_app_killed_with_pid(self):
        self.enforcer.tracker = self._make_tracker(raw_app="steam", app_id="steam", pid=4242)
        self.enforcer.check(self._usage(700))
        self.enforcer.check(self._usage(700))  # focus state was reset by the first kill
        self.mocks["close"].assert_called_once_with("steam", "Steam", 4242)
        t = self.enforcer.tracker
        self.assertEqual((t.current_raw_app, t.current_pid), ("", 0))
        self.assertEqual(t.resolved_app_info.get("app_id"), "desktop")

    def test_unrelated_focused_app_not_matched(self):
        self.enforcer.tracker = self._make_tracker(raw_app="org.kde.konsole", app_id="org.kde.konsole", pid=777)
        self.enforcer.check(self._usage(700))
        self.mocks["close"].assert_called_once_with("steam", "Steam", None)
        self.assertEqual(self.enforcer.tracker.current_pid, 777)

    def test_alert_levels_fire_once_in_order(self):
        titles = lambda: [c.args[0] for c in self.mocks["note"].call_args_list]
        self.enforcer.check(self._usage(300))   # 50%: nothing
        self.assertEqual(titles(), [])
        self.enforcer.check(self._usage(500))   # 83%
        self.enforcer.check(self._usage(510))
        self.assertEqual(titles(), ["QHealth — 80% Limit Warning"])
        self.enforcer.check(self._usage(545))   # 55s left
        self.assertEqual(titles()[-1], "QHealth — 1 Minute Left")
        self.enforcer.check(self._usage(600))   # limit reached
        self.mocks["block_note"].assert_called_once()
        self.assertEqual(len(titles()), 2)

    def test_jump_past_all_thresholds_sends_one_alert(self):
        self.enforcer.check(self._usage(900, block=False))
        self.assertEqual([c.args[0] for c in self.mocks["note"].call_args_list], ["QHealth — Daily Budget Exceeded"])
        self.mocks["close"].assert_not_called()  # block_on_exceed off
        self.assertNotIn("steam", self.enforcer.tracker.blocked_app_ids)

    def test_no_80_percent_alert_right_after_extension(self):
        self.enforcer.check(self._usage(3600, limit=60))            # limit reached
        self.mocks["note"].reset_mock()
        self.enforcer.check(self._usage(3605, limit=60, extra=15))  # 80% of the new 75m limit
        self.mocks["note"].assert_not_called()

    def test_extension_unblocks_and_rearms_warnings(self):
        self.enforcer.check(self._usage(600))
        self.assertIn("steam", self.enforcer.tracker.blocked_app_ids)
        exceeded = self.enforcer.check(self._usage(610, extra=15))  # +15 min granted
        self.assertEqual(exceeded, {})
        self.assertNotIn("steam", self.enforcer.tracker.blocked_app_ids)
        self.enforcer.check(self._usage(25 * 60 - 30, extra=15))  # 30s left of the new limit
        self.assertEqual(self.mocks["note"].call_args_list[-1].args[0], "QHealth — 1 Minute Left")
        self.enforcer.check(self._usage(25 * 60, extra=15))
        self.assertEqual(self.mocks["close"].call_count, 2)  # killed again at the new limit

class TestBreakReminder(unittest.TestCase):
    def setUp(self):
        from qhealth_core.wellbeing import BreakReminder
        self.tracker = unittest.mock.Mock(paused=False, last_input_time=0.0)
        self.reminder = BreakReminder(self.tracker)
        patcher = unittest.mock.patch("qhealth_core.wellbeing.send_notification")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def _at(self, now, last_input=None, minutes=50):
        self.tracker.last_input_time = now if last_input is None else last_input
        return self.reminder.check(minutes, now=now)

    def test_reminds_after_continuous_activity_and_repeats(self):
        self.assertFalse(self._at(0))
        self.assertFalse(self._at(49 * 60))
        self.assertTrue(self._at(50 * 60))
        self.assertFalse(self._at(51 * 60))         # restarts the count
        self.assertTrue(self._at(100 * 60))
        self.assertEqual(self.notify.call_count, 2)

    def test_short_pauses_do_not_count_as_break(self):
        self._at(0)
        self._at(20 * 60, last_input=20 * 60 - 120)  # 2 min without input
        self.assertTrue(self._at(50 * 60))

    def test_five_minute_break_resets(self):
        self._at(0)
        self._at(30 * 60, last_input=24 * 60)       # 6 min without input: a real break
        self.assertFalse(self._at(50 * 60))         # activity resumes: count starts over here
        self.assertFalse(self._at(80 * 60))
        self.assertTrue(self._at(100 * 60))

    def test_suspend_counts_as_break(self):
        # CLOCK_MONOTONIC (input times) stops while suspended; CLOCK_BOOTTIME keeps going
        self.reminder.check(50, now=0, boot_now=0)
        self.tracker.last_input_time = 45 * 60
        self.reminder.check(50, now=45 * 60, boot_now=45 * 60)
        self.tracker.last_input_time = 45 * 60 + 10
        # 8 hours asleep: monotonic barely moved, boottime jumped
        self.assertFalse(self.reminder.check(50, now=45 * 60 + 10, boot_now=45 * 60 + 8 * 3600))
        self.tracker.last_input_time = 50 * 60
        self.assertFalse(self.reminder.check(50, now=50 * 60, boot_now=50 * 60 + 8 * 3600))
        self.notify.assert_not_called()

    def test_off_or_paused(self):
        self._at(0, minutes=0)
        self.assertFalse(self._at(999 * 60, minutes=0))
        self._at(0)
        self.tracker.paused = True
        self.assertFalse(self._at(60 * 60))
        self.notify.assert_not_called()

class TestFocusHookBlocking(unittest.TestCase):
    def _focus(self, tracker, app):
        import json as _json
        line = "QHEALTH_FOCUS:" + _json.dumps({"app": app, "title": "t", "cls": app, "pid": 999}) + "\n"

        class FakeProc:
            def __init__(self):
                self.lines = [line]
                self.stdout = self
            def readline(self):
                if self.lines:
                    return self.lines.pop(0)
                tracker.running = False
                return ""
            def terminate(self):
                pass
            def wait(self, timeout=None):
                pass

        tracker.running = True
        with unittest.mock.patch.object(type(tracker), "_inject_kwin_script", return_value=True), \
             unittest.mock.patch("qhealth_core.tracker.subprocess.Popen", return_value=FakeProc()):
            tracker._kwin_loop()

    @unittest.mock.patch("qhealth_core.tracker.send_block_notification")
    @unittest.mock.patch("qhealth_core.tracker.force_close_app")
    def test_fresh_extension_is_honoured_and_limit_reported(self, mock_close, mock_note):
        from qhealth_core.tracker import ActivityTracker
        db.set_app_budget("focusgame", 1)
        self.addCleanup(db.set_app_budget, "focusgame", 0, False)
        db.record_activity_chunk("focusgame", "Focusgame", "t", 120, 0, 0, 0, "Gaming")
        tracker = ActivityTracker()
        tracker.update_blocked_apps(db.get_exceeded_app_budgets())

        # Blocked: killed, and the message uses the effective limit
        self._focus(tracker, "focusgame")
        mock_close.assert_called_once()
        self.assertEqual(mock_note.call_args.args[1], 1)

        # "+15 min" granted less than 5s ago: the stale blocked set must not kill it
        db.extend_app_budget("focusgame", 15)
        tracker.update_blocked_apps({"focusgame": {"daily_limit_minutes": 1, "block_on_exceed": True}})
        self._focus(tracker, "focusgame")
        self.assertEqual(mock_close.call_count, 1)
        self.assertEqual(tracker.current_raw_app, "focusgame")

class TestTerminalsAndLaunchedProcesses(unittest.TestCase):
    def test_terminal_detection(self):
        for app_id in ("org.kde.konsole", "konsole", "kitty", "Alacritty", "com.mitchellh.ghostty",
                       "org.gnome.Console", "org.gnome.Ptyxis", "io.elementary.terminal", "org.kde.yakuake.desktop"):
            self.assertTrue(app_resolver.is_terminal(app_id), app_id)
        for app_id in ("code", "brave-browser", "steam", "org.kde.dolphin", "vesktop", ""):
            self.assertFalse(app_resolver.is_terminal(app_id), app_id)
        # Anything whose .desktop file says Categories=...;TerminalEmulator;
        app_resolver._apps_cache["com.example.fancyterm"] = {"display_name": "Fancy", "icon": "", "category": "Development", "is_terminal": True}
        self.addCleanup(app_resolver._apps_cache.pop, "com.example.fancyterm")
        self.assertTrue(app_resolver.is_terminal("com.example.fancyterm"))

    def test_terminals_are_never_force_closed(self):
        from qhealth_core.blocker import is_immune, force_close_app
        self.assertTrue(is_immune("org.kde.konsole"))  # the real Plasma 6 id; previously killable
        self.assertTrue(is_immune("", "Konsole"))
        with unittest.mock.patch("qhealth_core.blocker.find_pids_for_app") as scan:
            self.assertEqual(force_close_app("org.kde.konsole", "Konsole", 4242), 0)
            scan.assert_not_called()

    def test_terminal_budget_warns_but_never_blocks(self):
        db.set_app_budget("org.kde.konsole", 1, block_on_exceed=True)
        self.addCleanup(db.set_app_budget, "org.kde.konsole", 0, False)
        db.record_activity_chunk("org.kde.konsole", "Konsole", "zsh", 120, 0, 0, 0, "Development")
        exceeded = db.get_exceeded_app_budgets()
        self.assertIn("org.kde.konsole", exceeded)              # still over its limit (reminders)
        self.assertFalse(exceeded["org.kde.konsole"]["block_on_exceed"])
        konsole = next(a for a in db.get_stats_by_range("day")["apps"] if a["app_id"] == "org.kde.konsole")
        self.assertFalse(konsole["block_on_exceed"])            # no BLOCKED pill
        self.assertTrue(db.get_app_detail_stats("org.kde.konsole")["is_terminal"])

    def test_blocking_closes_launched_processes_but_spares_terminals(self):
        import signal, subprocess
        from qhealth_core.blocker import get_process_tree, _terminate_pids
        # app -> plain child (a helper it launched)
        #     -> child renamed "konsole" (a terminal it launched) -> grandchild (runs in that terminal)
        code = (
            "import ctypes, subprocess, sys, time\n"
            "helper = subprocess.Popen(['sleep', '60'])\n"
            "term = subprocess.Popen([sys.executable, '-c', "
            "'import ctypes, subprocess, time; ctypes.CDLL(None).prctl(15, b\"konsole\", 0, 0, 0); "
            "shell = subprocess.Popen([\"sleep\", \"60\"]); print(shell.pid, flush=True); time.sleep(60)'], "
            "stdout=subprocess.PIPE, text=True)\n"
            "shell_pid = term.stdout.readline().strip()\n"
            "print(helper.pid, term.pid, shell_pid, flush=True)\n"
            "time.sleep(60)\n"
        )
        app = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        helper_pid, term_pid, shell_pid = map(int, app.stdout.readline().split())
        def cleanup():
            for pid in (app.pid, helper_pid, term_pid, shell_pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            app.wait(timeout=5)
            app.stdout.close()
        self.addCleanup(cleanup)
        if app.pid <= 100:
            self.skipTest("PIDs <= 100 are always immune")
        with open(f"/proc/{term_pid}/comm") as f:
            self.assertEqual(f.read().strip(), "konsole")

        tree = get_process_tree(app.pid)
        self.assertIn(app.pid, tree)
        self.assertIn(helper_pid, tree)       # things the app launched are closed with it
        self.assertNotIn(term_pid, tree)      # a terminal it launched is not
        self.assertNotIn(shell_pid, tree)     # nor anything running inside that terminal

        _terminate_pids(tree)
        self.assertEqual(app.wait(timeout=5), -signal.SIGTERM)
        time.sleep(0.2)
        for pid in (term_pid, shell_pid):
            with open(f"/proc/{pid}/status") as f:
                state = next(l for l in f if l.startswith("State:")).split()[1]
            self.assertNotIn(state, ("Z", "X"), f"pid {pid} should still be running")

class TestInputAccessWarning(unittest.TestCase):
    def test_detects_permission_denied_devices(self):
        from qhealth_core.tracker import ActivityTracker
        tracker = ActivityTracker()
        paths = ["/dev/input/event0", "/dev/input/event1"]
        fds = {}
        with unittest.mock.patch("qhealth_core.tracker.glob.glob", return_value=paths), \
             unittest.mock.patch("qhealth_core.tracker.os.open", side_effect=PermissionError):
            tracker._refresh_input_devices(fds)
        self.assertTrue(tracker.input_access_denied)
        self.assertTrue(tracker.get_live_metrics()["input_access_denied"])

        # After joining the input group the next rescan clears it
        real_fd = os.open(os.devnull, os.O_RDONLY)
        self.addCleanup(lambda: [os.close(fd) for fd in fds.values()])
        with unittest.mock.patch("qhealth_core.tracker.glob.glob", return_value=paths[:1]), \
             unittest.mock.patch("qhealth_core.tracker.os.open", return_value=real_fd):
            tracker._refresh_input_devices(fds)
        self.assertFalse(tracker.input_access_denied)

        # No devices at all (VM, container) is not a permission problem
        with unittest.mock.patch("qhealth_core.tracker.glob.glob", return_value=[]):
            tracker._refresh_input_devices(fds)
        self.assertFalse(tracker.input_access_denied)

    @unittest.mock.patch("qhealth_core.daemon.send_notification")
    def test_daemon_warns_once(self, notify):
        from qhealth_core.daemon import QHealthDaemon
        d = QHealthDaemon.__new__(QHealthDaemon)
        d._warned_input_access = False
        d.tracker = unittest.mock.Mock(input_access_denied=True)
        with unittest.mock.patch("builtins.print"):
            d._warn_if_no_input_access()
            d._warn_if_no_input_access()
        notify.assert_called_once()
        self.assertIn("usermod -aG input", notify.call_args.args[1])

class TestPrivacyAndInstanceIsolation(unittest.TestCase):
    def test_data_dir_is_owner_only(self):
        import stat
        orig = (db.DB_DIR, db.DB_PATH)
        self.addCleanup(lambda: setattr(db, "DB_DIR", orig[0]) or setattr(db, "DB_PATH", orig[1]))
        with tempfile.TemporaryDirectory() as tmp:
            for existing in (False, True):
                data_dir = Path(tmp) / f"qhealth_{existing}"
                if existing:
                    data_dir.mkdir(mode=0o755)  # created by an older version
                    os.chmod(data_dir, 0o755)
                db.DB_DIR, db.DB_PATH = data_dir, data_dir / "qhealth.db"
                db.init_db(force=True)
                self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700, f"existing={existing}")

    def test_single_instance_socket_is_per_user(self):
        from PyQt6.QtNetwork import QLocalServer, QLocalSocket
        from qhealth_core.desktop_app import _single_instance_socket_name
        with tempfile.TemporaryDirectory() as runtime:
            with unittest.mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}):
                name = _single_instance_socket_name()
            self.assertEqual(name, os.path.join(runtime, "qhealth.sock"))
            # Qt accepts a full path: the socket really lives in the private runtime dir
            server = QLocalServer()
            self.assertTrue(server.listen(name))
            client = QLocalSocket()
            client.connectToServer(name)
            self.assertTrue(client.waitForConnected(1000))
            self.assertTrue(os.path.exists(name))
            client.disconnectFromServer()
            server.close()
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_single_instance_socket_name(), f"qhealth_single_instance_{os.getuid()}")

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
