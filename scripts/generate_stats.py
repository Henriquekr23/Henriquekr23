"""
Gera streak.svg, langs.svg e year.svg a partir da API do GitHub (GraphQL + REST),
no mesmo estilo visual do ascii-portrait.svg (fundo escuro, verde matrix, monoespaçada).

Roda dentro do GitHub Actions (usa GITHUB_TOKEN / GH_TOKEN do ambiente).
Nada é carregado de servidor de terceiros: os SVGs são desenhados aqui e
commitados de volta no repositório pelo workflow.
"""

import os
import sys
import json
import datetime
import urllib.request

USERNAME = os.environ.get("STATS_USERNAME", "Henriquekr23")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUT_DIR = os.environ.get("OUT_DIR", "assets")

GREEN = "#39ff88"
WHITE = "#eafff2"
DIM = "#123420"
BG_TOP = "#03050a"
BG_BOTTOM = "#010204"

RAMP = [":", "+", "#", "@"]  # quiet -> loud, same ramp used in ascii-portrait.svg


def gh_request(url, body=None):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats-script",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_contributions(username):
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """
    payload = {"query": query, "variables": {"login": username}}
    res = gh_request("https://api.github.com/graphql", payload)
    cal = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    return cal["totalContributions"], days


def fetch_languages(username):
    repos = []
    page = 1
    while True:
        batch = gh_request(
            f"https://api.github.com/users/{username}/repos?per_page=100&page={page}&type=owner"
        )
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    totals = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        langs = gh_request(repo["languages_url"])
        for lang, byte_count in langs.items():
            totals[lang] = totals.get(lang, 0) + byte_count
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:6]


def compute_streaks(days):
    # days is chronological [(date, count), ...]
    longest = current = 0
    running = 0
    today_str = datetime.date.today().isoformat()
    for date, count in days:
        if count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    # current streak = consecutive non-zero days ending at the most recent day
    for date, count in reversed(days):
        if date > today_str:
            continue
        if count > 0:
            current += 1
        else:
            break
    return current, longest


def svg_shell(width, height, body, extra_defs=""):
    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG_TOP}"/>
      <stop offset="100%" stop-color="{BG_BOTTOM}"/>
    </linearGradient>
    {extra_defs}
  </defs>
  <rect width="{width}" height="{height}" rx="10" fill="url(#bg)"/>
  {body}
  <rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="10" fill="none" stroke="{DIM}" stroke-width="1"/>
</svg>'''


def render_streak(total, current, longest, path):
    W, H = 380, 140
    cols = [
        ("TOTAL", total, 60),
        ("CURRENT STREAK", current, 200),
        ("LONGEST STREAK", longest, 320),
    ]
    parts = []
    for label, value, cx in cols:
        parts.append(f'''
    <text x="{cx}" y="66" text-anchor="middle" font-family="Consolas, monospace" font-size="34" font-weight="700" fill="{WHITE}" opacity="0">
      {value}
      <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="0.15s" fill="freeze"/>
    </text>
    <text x="{cx}" y="90" text-anchor="middle" font-family="Consolas, monospace" font-size="10.5" letter-spacing="1" fill="{GREEN}">{label}</text>''')
    body = f'''
  <text x="20" y="26" font-family="Consolas, monospace" font-size="12" fill="{GREEN}" opacity="0.85">&gt; contributions --last-year</text>
  <line x1="130" y1="40" x2="130" y2="105" stroke="{DIM}"/>
  <line x1="260" y1="40" x2="260" y2="105" stroke="{DIM}"/>
  {"".join(parts)}
  <line x1="20" y1="115" x2="{W-20}" y2="115" stroke="{DIM}"/>
  <text x="20" y="130" font-family="Consolas, monospace" font-size="10" fill="{DIM}">generated · github actions</text>'''
    svg = svg_shell(W, H, body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def render_langs(ranked, path):
    W, H = 380, 40 + len(ranked) * 30 + 20
    max_bytes = ranked[0][1] if ranked else 1
    bars = []
    y = 46
    for i, (lang, count) in enumerate(ranked):
        pct = count / max_bytes
        bar_w = round(200 * pct, 1)
        delay = round(0.1 + i * 0.08, 2)
        bars.append(f'''
    <text x="20" y="{y}" font-family="Consolas, monospace" font-size="12" fill="{WHITE}">{lang}</text>
    <rect x="130" y="{y-11}" width="200" height="12" fill="{DIM}" rx="2"/>
    <rect x="130" y="{y-11}" width="0" height="12" fill="{GREEN}" rx="2">
      <animate attributeName="width" from="0" to="{bar_w}" dur="0.8s" begin="{delay}s" fill="freeze"/>
    </rect>''')
        y += 30
    body = f'''
  <text x="20" y="26" font-family="Consolas, monospace" font-size="12" fill="{GREEN}" opacity="0.85">&gt; top languages --by-bytes</text>
  {"".join(bars)}'''
    svg = svg_shell(W, H, body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def render_year(days, path):
    # 53 weeks x 7 days grid, ramp chars ':' '+' '#' '@' quiet -> loud
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    counts = [c for _, c in days if c > 0]
    q = sorted(counts)
    def bucket(c):
        if c == 0:
            return None
        if not q:
            return 0
        idx = min(3, int((sum(1 for x in q if x <= c) / len(q)) * 4))
        return idx

    cell = 11
    W = 24 + len(weeks) * cell
    H = 24 + 7 * cell + 20
    cells = []
    day_i = 0
    for wi, week in enumerate(weeks):
        for di, (date, count) in enumerate(week):
            level = bucket(count)
            x = 20 + wi * cell
            y = 24 + di * cell
            delay = round(0.002 * day_i, 3)
            if level is None:
                fill, op = DIM, 0.5
                ch = "."
            else:
                fill = WHITE if level == 3 else GREEN
                op = [0.35, 0.55, 0.8, 1.0][level]
                ch = RAMP[level]
            cells.append(
                f'<text x="{x}" y="{y}" font-family="Consolas, monospace" font-size="10" '
                f'fill="{fill}" fill-opacity="0"><animate attributeName="fill-opacity" from="0" to="{op}" '
                f'dur="0.01s" begin="{delay}s" fill="freeze"/>{ch}</text>'
            )
            day_i += 1
    body = f'''
  <text x="20" y="16" font-family="Consolas, monospace" font-size="12" fill="{GREEN}" opacity="0.85">&gt; year --one-char-per-day</text>
  {"".join(cells)}'''
    svg = svg_shell(W, H, body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not TOKEN:
        print("GITHUB_TOKEN não definido — abortando (rode isso dentro do Actions).", file=sys.stderr)
        sys.exit(1)

    total, days = fetch_contributions(USERNAME)
    current, longest = compute_streaks(days)
    render_streak(total, current, longest, os.path.join(OUT_DIR, "streak.svg"))
    render_year(days, os.path.join(OUT_DIR, "year.svg"))

    ranked = fetch_languages(USERNAME)
    render_langs(ranked, os.path.join(OUT_DIR, "langs.svg"))

    print(f"OK — total={total} current_streak={current} longest_streak={longest} langs={ranked}")


if __name__ == "__main__":
    main()
