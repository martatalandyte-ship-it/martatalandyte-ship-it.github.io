#!/usr/bin/env python3
"""
Martos rytinė apžvalga — daily Lithuanian morning news generator.
Runs in GitHub Actions. Calls the Anthropic API (with the server-side web
search tool) to research YESTERDAY's news and produce a self-contained
index.html in the fixed soft pink & rose design, dated TODAY (so it reads
like this morning's paper) with a clear "covers yesterday" line.

Idempotent: the page carries an HTML marker <!-- edition:YYYY-MM-DD --> with
today's Vilnius date. If index.html already has today's marker, the script
exits without calling the API, so multiple early-morning cron triggers are
safe and cheap (only the first one each day actually generates).

Requires env var ANTHROPIC_API_KEY.
"""

import os
import sys
import re
from datetime import datetime, timedelta, timezone

import anthropic

MODEL = "claude-sonnet-4-6"

# --- Dates in Vilnius local time ---------------------------------------------
def vilnius_now():
    # Simple DST approximation: EEST (UTC+3) Apr–Sep, EET (UTC+2) otherwise.
    now_utc = datetime.now(timezone.utc)
    month = now_utc.month
    offset = 3 if 4 <= month <= 9 else 2
    return now_utc + timedelta(hours=offset)

LT_WEEKDAYS = ["pirmadienis", "antradienis", "trečiadienis", "ketvirtadienis",
               "penktadienis", "šeštadienis", "sekmadienis"]
LT_MONTHS = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
             "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

def lt_date(d):
    return f"{LT_WEEKDAYS[d.weekday()]}, {d.year} m. {LT_MONTHS[d.month-1]} {d.day} d."

today = vilnius_now()
yesterday = today - timedelta(days=1)
TODAY_LT = lt_date(today)
YESTERDAY_LT = lt_date(yesterday)
EDITION_DATE = today.strftime("%Y-%m-%d")
EDITION_MARKER = f"<!-- edition:{EDITION_DATE} -->"

TEMPLATE = r"""<!DOCTYPE html>
<html lang="lt"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Martos rytinė apžvalga</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=Nunito+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#fff5f7;--bg-card:#fffafb;--rose:#d6688a;--rose-deep:#b14a6e;--rose-soft:#f7d6e0;--blush:#fce4ec;--gold:#c79a5b;--ink:#3d2b33;--ink-soft:#7a5e69;--line:#f0cdd9;}
*{box-sizing:border-box;}
body{margin:0;background:radial-gradient(1200px 600px at 50% -200px,#ffe3ec 0%,rgba(255,227,236,0) 70%),var(--bg);color:var(--ink);font-family:"Nunito Sans",system-ui,sans-serif;line-height:1.7;font-size:18px;}
.wrap{max-width:740px;margin:0 auto;padding:0 22px 80px;}
header.mast{text-align:center;padding:54px 0 26px;}
.kicker{letter-spacing:.32em;text-transform:uppercase;font-size:12px;font-weight:700;color:var(--rose);margin-bottom:14px;}
h1.title{font-family:"Fraunces",serif;font-weight:600;font-size:46px;line-height:1.05;margin:0 0 14px;color:var(--rose-deep);letter-spacing:-.01em;}
.meta{font-size:14px;color:var(--ink-soft);display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;}
.meta .dot{color:var(--rose-soft);}
.covers{margin-top:6px;font-size:13px;color:var(--rose-deep);font-weight:600;text-transform:uppercase;letter-spacing:.1em;}
.intro{font-family:"Fraunces",serif;font-size:20px;line-height:1.6;color:var(--ink);background:var(--bg-card);border:1px solid var(--line);border-radius:18px;padding:26px 28px;box-shadow:0 12px 30px -22px rgba(177,74,110,.5);}
.intro b{color:var(--rose-deep);font-weight:600;}
h2.sec{font-family:"Fraunces",serif;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--rose-deep);display:flex;align-items:center;gap:14px;margin:48px 0 22px;}
h2.sec::before{content:"\2740";color:var(--rose);font-size:16px;}
h2.sec::after{content:"";flex:1;height:1px;background:var(--line);}
article{margin:0 0 30px;}
h3.head{font-family:"Fraunces",serif;font-size:25px;font-weight:600;line-height:1.22;margin:0 0 6px;color:var(--ink);}
.dek{font-style:italic;color:var(--rose-deep);font-size:16px;margin:0 0 12px;font-family:"Fraunces",serif;}
p{margin:0 0 14px;}
.why{background:linear-gradient(180deg,var(--blush),#fff5f8);border-left:4px solid var(--rose);border-radius:0 14px 14px 0;padding:14px 20px;margin:14px 0 4px;font-size:16px;}
.why .lab{display:block;font-weight:700;color:var(--rose-deep);text-transform:uppercase;letter-spacing:.12em;font-size:12px;margin-bottom:4px;}
ul.cards{list-style:none;padding:0;margin:0;}
ul.cards li{background:var(--bg-card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-bottom:12px;}
ul.cards li b{color:var(--rose-deep);}
.nums{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 22px;}
.num{flex:1 1 150px;background:var(--bg-card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;text-align:center;}
.num .v{font-family:"Fraunces",serif;font-size:24px;font-weight:600;color:var(--rose-deep);}
.num .l{font-size:12px;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.08em;margin-top:2px;}
footer{margin-top:56px;text-align:center;font-size:13px;color:var(--ink-soft);border-top:1px solid var(--line);padding-top:24px;}
footer .src{font-size:12.5px;line-height:1.6;}
a{color:var(--rose-deep);}
@media(max-width:560px){h1.title{font-size:34px;}body{font-size:17px;}.intro{font-size:18px;}}
</style></head><body><div class="wrap">
<header class="mast"><div class="kicker">Martos rytinė apžvalga</div><h1 class="title">Labas rytas, Marta</h1>
<div class="meta"><span>[DATA]</span><span class="dot">·</span><span>~[X] min skaitymo</span></div>
<div class="covers">Vakar dienos ([YDATE]) svarbiausios naujienos</div></header>
<div class="intro">[INTRO]</div>
[SECTIONS]
<footer><p class="src"><b>Šaltiniai:</b> [SOURCES]</p>
<p>Parengta automatiškai · „Martos rytinė apžvalga" · [TODAY]<br>Naujienos apibendrina [YESTERDAY] įvykius. Šaltinius patartina patikrinti, jei žinia naudojama svarbiems sprendimams.</p></footer>
</div></body></html>"""

PROMPT = f"""Esi Martos asmeninės rytinės naujienų apžvalgos redaktorė. Šiandien yra {TODAY_LT}.
Tavo užduotis – paruošti šios dienos laidą LIETUVIŲ KALBA, kuri apibendrina VAKARYKŠTĖS dienos ({YESTERDAY_LT}) įvykius. Laida datuojama šiandienos data, tarsi rytinis laikraštis.

Pirmiausia atlik web paieškas (naudok web_search įrankį, kelis kartus) ir surink konkrečius, tikrus faktus su skaičiais ir įvardytais šaltiniais šiose srityse:
- Pasaulio svarbiausios antraštės.
- Lietuvos naujienos (tikrink LRT).
- Europa ir ES.
- Rinkos ir ekonomika (nafta/Brent, JAV infliacija/CPI, Fed/ECB palūkanos, akcijos, EUR/USD).
- Prekybai svarbu (ekonominis kalendorius, ką stebi prekiautojai: FOMC, svarbūs duomenys, nafta, doleris).
Pirmenybę teik šaltiniams: Reuters, AP, BBC, NPR, LRT, Euronews, Consilium, European Commission, CNBC, Trading Economics.

Tada parenk vieną savarankišką index.html failą, NAUDODAMA TIKSLIAI šį šabloną. NIEKO nekeisk CSS ar struktūroje – keisk tik datas ir turinį tarp žymeklių. Pakeisk [DATA] -> "{TODAY_LT}", [YDATE] -> "{YESTERDAY_LT}", [TODAY] -> "{TODAY_LT}", [YESTERDAY] -> "{YESTERDAY_LT}", [X] -> skaitymo trukmės įvertis, [INTRO], [SECTIONS], [SOURCES].

Privalomos sekcijos [SECTIONS] vietoje, šia tvarka:
1. "Pasaulio antraštės" – 3–5 istorijos. Pirma istorija turi <p class="dek"> paantraštę ir <div class="why"> ("Kodėl tai svarbu") bloką.
2. "Lietuvos rubrika" – 2–3 istorijos su "Kodėl tai svarbu" bloku prie pirmos.
3. "Europa ir ES" – 1 pagrindinis straipsnis + <ul class="cards"> sąrašas (3–4 trumpi ES punktai su <b>...</b> pradžia).
4. "Rinkos ir ekonomika" – <div class="nums"> juosta su 3 skaičiais (infliacija, nafta, Fed/ECB palūkanos) + 2–3 trumpi straipsniai.
5. "Prekybai svarbu žinoti" – <ul class="cards watch"> sąrašas (3–4 punktai su <b>...</b>).
6. "Šiandien stebime" – 1 trumpa pastraipa.
Kiekviena sekcija prasideda <h2 class="sec">PAVADINIMAS</h2>. Straipsniai – <article> su <h3 class="head">.

Rašyk natūralia, taisyklinga lietuvių kalba. NEGALIMA prasimanyti faktų – naudok tik tai, ką radai paieškoje.

Į ATSAKYMĄ įrašyk TIK galutinį HTML – nuo "<!DOCTYPE html>" iki "</html>", be jokio papildomo teksto, be markdown ženklų.

ŠABLONAS:
{TEMPLATE}
"""

def main():
    # Idempotency: if today's edition is already published, do nothing.
    if os.path.exists("index.html"):
        with open("index.html", encoding="utf-8") as f:
            if EDITION_MARKER in f.read():
                print(f"Edition for {EDITION_DATE} already published — skipping.")
                return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    resp = client.messages.create(
        model=MODEL,
        max_tokens=12000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": PROMPT}],
    )

    text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )

    m = re.search(r"<!DOCTYPE html>.*?</html>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        print("ERROR: could not find HTML in model response. Raw output:\n", file=sys.stderr)
        print(text[:4000], file=sys.stderr)
        sys.exit(2)

    # Stamp the edition marker so future runs today are skipped.
    html = m.group(0).replace("<!DOCTYPE html>", f"<!DOCTYPE html>\n{EDITION_MARKER}", 1)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: wrote index.html ({len(html)} bytes), edition {EDITION_DATE}, covers {YESTERDAY_LT}")

if __name__ == "__main__":
    main()
