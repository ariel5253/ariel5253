"""Genera las tarjetas de cifras del README desde la API GraphQL de GitHub.

Sin dependencias externas: solo la biblioteca estandar, para que corra tal cual
en el runner de Actions con el GITHUB_TOKEN del propio workflow. Las cifras son
las mismas que muestra el perfil ("contributions in the last year"), no una
estimacion de un servicio de terceros.

Uso: GITHUB_TOKEN=... python3 scripts/stats_cards.py <usuario>
"""
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import List, NamedTuple
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"
ASSETS = Path(__file__).resolve().parents[1] / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      startedAt
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      restrictedContributionsCount
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# Paleta del portafolio (ariel5253.github.io). Las tarjetas son transparentes:
# el texto se pinta sobre el fondo de GitHub de cada modo.
THEMES = {
    "light": {"ink": "#121a1c", "muted": "#52605f", "accent": "#0f766e", "line": "#dfe6e6"},
    "dark": {"ink": "#e6eeee", "muted": "#9fb0b0", "accent": "#3fd0bd", "line": "#30363d"},
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
WIDTH, HEIGHT, PAD = 400, 200, 20


class Stats(NamedTuple):
    total: int
    commits: int
    pull_requests: int
    reviews: int
    issues: int
    private: int
    repos_with_commits: int
    current_streak: int
    longest_streak: int
    active_days: int
    weekly: List[int]


def current_streak(counts):
    """Dias seguidos con contribuciones hasta hoy; un hoy en cero no la rompe."""
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    streak = 0
    while i >= 0 and counts[i] > 0:
        streak += 1
        i -= 1
    return streak


def longest_streak(counts):
    best = run = 0
    for count in counts:
        run = run + 1 if count > 0 else 0
        best = max(best, run)
    return best


def fmt(n):
    return f"{n:,}"


def days_label(n):
    return f"{fmt(n)} day" if n == 1 else f"{fmt(n)} days"


def summarize(user):
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    # El calendario arranca en el domingo previo a startedAt: esos dias quedan
    # fuera de la ventana de 12 meses y no cuentan para rachas ni dias activos.
    start = collection["startedAt"][:10]
    days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days if d["date"] >= start]
    return Stats(
        total=calendar["totalContributions"],
        commits=collection["totalCommitContributions"],
        pull_requests=collection["totalPullRequestContributions"],
        reviews=collection["totalPullRequestReviewContributions"],
        issues=collection["totalIssueContributions"],
        private=collection["restrictedContributionsCount"],
        repos_with_commits=collection["totalRepositoriesWithContributedCommits"],
        current_streak=current_streak(counts),
        longest_streak=longest_streak(counts),
        active_days=sum(1 for c in counts if c > 0),
        weekly=[sum(d["contributionCount"] for d in w["contributionDays"]) for w in calendar["weeks"]],
    )


def _card(title, body, t):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" font-family="{FONT}">\n'
        f"  <title>{escape(title)}</title>\n"
        f'  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="10" '
        f'fill="none" stroke="{t["line"]}"/>\n'
        f"{body}"
        f"</svg>\n"
    )


def _header(label, value, caption, t):
    return (
        f'  <text x="{PAD}" y="34" fill="{t["accent"]}" font-size="11" font-weight="600" '
        f'letter-spacing="1.2">{escape(label)}</text>\n'
        f'  <text x="{PAD}" y="76" fill="{t["ink"]}" font-size="32" font-weight="600">{escape(value)}</text>\n'
        f'  <text x="{PAD}" y="98" fill="{t["muted"]}" font-size="13">{escape(caption)}</text>\n'
    )


def _figure(x, y, value, label, t):
    return (
        f'  <text x="{x}" y="{y}" font-size="13"><tspan fill="{t["ink"]}" font-weight="600">'
        f'{escape(value)}</tspan><tspan fill="{t["muted"]}"> {escape(label)}</tspan></text>\n'
    )


def render_activity(stats, theme):
    t = THEMES[theme]
    mid = WIDTH // 2
    body = (
        _header("LAST 12 MONTHS", fmt(stats.total), "contributions", t)
        + _figure(PAD, 128, fmt(stats.commits), "commits", t)
        + _figure(mid, 128, fmt(stats.pull_requests), "pull requests", t)
        + _figure(PAD, 150, fmt(stats.reviews), "code reviews", t)
        + _figure(mid, 150, fmt(stats.issues), "issues", t)
        + f'  <text x="{PAD}" y="182" fill="{t["muted"]}" font-size="12">'
        f"{fmt(stats.private)} in private repositories · "
        f"{fmt(stats.repos_with_commits)} repos with commits</text>\n"
    )
    title = (
        f"{fmt(stats.total)} contributions in the last 12 months: {fmt(stats.commits)} commits, "
        f"{fmt(stats.pull_requests)} pull requests, {fmt(stats.reviews)} code reviews, "
        f"{fmt(stats.issues)} issues"
    )
    return _card(title, body, t)


def render_consistency(stats, theme):
    t = THEMES[theme]
    mid = WIDTH // 2
    top, height = 144, 40
    span = WIDTH - 2 * PAD
    n = max(len(stats.weekly), 1)
    step = span / n
    peak = max(stats.weekly, default=0) or 1
    bars = []
    for i, value in enumerate(stats.weekly):
        h = max(2.0, value / peak * height)
        opacity = "1" if value else "0.3"
        bars.append(
            f'    <rect x="{PAD + i * step:.2f}" y="{top + height - h:.2f}" width="{step * 0.75:.2f}" '
            f'height="{h:.2f}" rx="1" fill="{t["accent"]}" fill-opacity="{opacity}"/>\n'
        )
    body = (
        _header("CONSISTENCY", days_label(stats.current_streak), "current streak", t)
        + _figure(PAD, 128, fmt(stats.longest_streak), "longest in 12 months", t)
        + _figure(mid, 128, fmt(stats.active_days), "active days", t)
        + '  <g id="weeks">\n' + "".join(bars) + "  </g>\n"
    )
    title = (
        f"Current streak: {days_label(stats.current_streak)}; longest in 12 months: "
        f"{days_label(stats.longest_streak)}; {fmt(stats.active_days)} active days"
    )
    return _card(title, body, t)


def fetch(login, token):
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(API, data=payload, headers={
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"{login}-readme-stats",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if data.get("errors") or not (data.get("data") or {}).get("user"):
        raise SystemExit(f"La API de GitHub respondio con error: {data.get('errors')}")
    return data["data"]["user"]


def main(argv):
    if len(argv) != 2:
        raise SystemExit("Uso: stats_cards.py <usuario>")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Falta GITHUB_TOKEN")
    stats = summarize(fetch(argv[1], token))
    # Se renderiza todo antes de escribir: o se actualizan las cuatro, o ninguna.
    cards = {
        f"{name}-{theme}.svg": render(stats, theme)
        for name, render in (("activity", render_activity), ("consistency", render_consistency))
        for theme in THEMES
    }
    ASSETS.mkdir(exist_ok=True)
    for filename, svg in cards.items():
        (ASSETS / filename).write_text(svg, encoding="utf-8", newline="\n")
        print(f"assets/{filename}")


if __name__ == "__main__":
    main(sys.argv)
