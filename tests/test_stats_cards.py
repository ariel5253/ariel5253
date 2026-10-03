import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stats_cards as sc  # noqa: E402

# Fondos de pagina reales de GitHub: las tarjetas son transparentes y el texto
# se pinta directamente sobre ellos.
GITHUB_BG = {"light": "#ffffff", "dark": "#0d1117"}
SVG = "{http://www.w3.org/2000/svg}"


def luminance(hex_color):
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def user_fixture():
    return {
        "contributionsCollection": {
            "startedAt": "2025-10-03T00:00:00Z",
            "totalCommitContributions": 556,
            "totalPullRequestContributions": 45,
            "totalPullRequestReviewContributions": 78,
            "totalIssueContributions": 277,
            "restrictedContributionsCount": 5206,
            "totalRepositoriesWithContributedCommits": 86,
            "contributionCalendar": {
                "totalContributions": 6177,
                "weeks": [
                    {"contributionDays": [
                        {"date": "2025-10-01", "contributionCount": 9},
                        {"date": "2025-10-02", "contributionCount": 9},
                        {"date": "2025-10-03", "contributionCount": 0},
                        {"date": "2025-10-04", "contributionCount": 2},
                    ]},
                    {"contributionDays": [
                        {"date": "2025-10-05", "contributionCount": 3},
                        {"date": "2025-10-06", "contributionCount": 0},
                        {"date": "2025-10-07", "contributionCount": 4},
                    ]},
                ],
            },
        }
    }


class StreakTest(unittest.TestCase):
    def test_current_streak_ignores_today_without_contributions(self):
        self.assertEqual(sc.current_streak([1, 1, 0, 1, 1, 0]), 2)

    def test_current_streak_counts_today_when_it_has_contributions(self):
        self.assertEqual(sc.current_streak([0, 1, 1, 1]), 3)

    def test_current_streak_is_zero_after_two_empty_days(self):
        self.assertEqual(sc.current_streak([1, 1, 0, 0]), 0)

    def test_longest_streak(self):
        self.assertEqual(sc.longest_streak([1, 1, 1, 0, 1, 1, 0]), 3)

    def test_streaks_of_an_empty_calendar(self):
        self.assertEqual(sc.current_streak([]), 0)
        self.assertEqual(sc.longest_streak([]), 0)


class FormatTest(unittest.TestCase):
    def test_thousands_separator(self):
        self.assertEqual(sc.fmt(6177), "6,177")
        self.assertEqual(sc.fmt(45), "45")

    def test_days_label_is_singular_for_one(self):
        self.assertEqual(sc.days_label(1), "1 day")
        self.assertEqual(sc.days_label(40), "40 days")


class SummarizeTest(unittest.TestCase):
    def setUp(self):
        self.stats = sc.summarize(user_fixture())

    def test_totals_come_from_the_collection(self):
        self.assertEqual(self.stats.total, 6177)
        self.assertEqual(self.stats.commits, 556)
        self.assertEqual(self.stats.pull_requests, 45)
        self.assertEqual(self.stats.reviews, 78)
        self.assertEqual(self.stats.issues, 277)
        self.assertEqual(self.stats.private, 5206)
        self.assertEqual(self.stats.repos_with_commits, 86)

    def test_days_before_the_window_do_not_count(self):
        # 2025-10-01 y 2025-10-02 son previos a startedAt (2025-10-03).
        self.assertEqual(self.stats.active_days, 3)
        self.assertEqual(self.stats.longest_streak, 2)
        self.assertEqual(self.stats.current_streak, 1)

    def test_weekly_totals_keep_every_calendar_week(self):
        self.assertEqual(self.stats.weekly, [20, 7])


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.stats = sc.summarize(user_fixture())

    def test_activity_card_is_valid_svg_with_the_figures(self):
        svg = sc.render_activity(self.stats, "light")
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, SVG + "svg")
        text = "".join(root.itertext())
        for figure in ("6,177", "556", "45", "78", "277", "5,206", "86"):
            self.assertIn(figure, text)

    def test_consistency_card_draws_one_bar_per_week(self):
        svg = sc.render_consistency(self.stats, "dark")
        root = ET.fromstring(svg)
        bars = root.findall(f".//{SVG}g[@id='weeks']/{SVG}rect")
        self.assertEqual(len(bars), len(self.stats.weekly))
        self.assertIn("1 day", "".join(root.itertext()))

    def test_consistency_card_survives_a_year_without_contributions(self):
        stats = self.stats._replace(weekly=[0, 0, 0], current_streak=0, longest_streak=0, active_days=0)
        ET.fromstring(sc.render_consistency(stats, "light"))

    def test_cards_have_an_accessible_title(self):
        for render in (sc.render_activity, sc.render_consistency):
            root = ET.fromstring(render(self.stats, "light"))
            self.assertEqual(root.get("role"), "img")
            self.assertTrue(root.find(SVG + "title").text.strip())


class ThemeTest(unittest.TestCase):
    def test_text_colors_pass_wcag_aa_on_github_backgrounds(self):
        self.assertEqual(set(sc.THEMES), {"light", "dark"})
        for name, theme in sc.THEMES.items():
            for role in ("ink", "muted", "accent"):
                ratio = contrast(theme[role], GITHUB_BG[name])
                self.assertGreaterEqual(ratio, 4.5, f"{name}.{role} = {ratio:.2f}:1")


if __name__ == "__main__":
    unittest.main()
