"""Moosey Rates: a static review site, built in Python, served by GitHub Pages.

    python main.py           fetch any missing art, build docs/, preview on localhost
    python main.py build     fetch + build, no server
    python main.py deploy    build, commit, push (GitHub Pages serves docs/ on main)

To add or change a review, edit the data below and run it again.
"""

import html
import math
import random
import io
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
IMG = OUT / "img"
ART = OUT / "art"

# ---------------------------------------------------------------------------
# The ledger. Art specs say where the cover comes from:
#   itunes:<search>   album artwork (Apple serves it up to 1000px)
#   wiki:<Page_Title> lead image of an English Wikipedia article
#   steam:<appid>     Steam's 600x900 library capsule, the sharpest game art going
#   tvmaze:<show>#<n> poster for season n (or the show, without #n)
#   mw:<api>|<title>  lead image from any MediaWiki, i.e. the fandom wikis
# ---------------------------------------------------------------------------


def item(title, by, year, score, review, art):
    return dict(title=title, by=by, year=year, score=score, review=review, art=art)


CATEGORIES = [
    dict(
        key="music", num="I", name="Music", unit="record", aspect="1 / 1",
        deck="Ten records I'd drag out of a burning house, in the order I'd grab them.",
        mentions_label="Honourable mentions",
        items=[
            item("In Rainbows", "Radiohead", "2007", 9.7,
                 "Released as pay-what-you-want, which was frankly an insult: it's worth a kidney. "
                 "'Reckoner' alone should be prescribed to anyone who thinks they've felt things.",
                 "itunes:In Rainbows Radiohead"),
            item("Takk…", "Sigur Rós", "2005", 9.4,
                 "Icelandic for 'thanks', and the only word on it I understood. Didn't matter. "
                 "'Hoppípolla' is what a glacier sounds like when it's happy.",
                 "itunes:Takk Sigur Ros"),
            item("…Like Clockwork", "Queens of the Stone Age", "2013", 9.1,
                 "Josh Homme nearly died on an operating table and came back with this, which seems a fair trade. "
                 "Wounded, swaggering, and far sexier than desert rock has any right to be.",
                 "wiki:...Like_Clockwork"),
            item("CRAWLER", "IDLES", "2021", 9.0,
                 "IDLES stop shouting long enough to say something devastating, then go back to shouting. "
                 "A car crash of an album, literally and as a compliment.",
                 "wiki:Crawler_(album)"),
            item("Mordechai", "Khruangbin", "2020", 9.0,
                 "Bass lines so smooth they need a lifeguard. "
                 "The audio equivalent of a linen shirt on a warm evening. 'Pelota' is compulsory.",
                 "itunes:Mordechai Khruangbin"),
            item("This Could Be Texas", "English Teacher", "2024", 8.8,
                 "Leeds art-rock that won the Mercury and deserved it. "
                 "Wry, wonky and cleverer than you, but it buys the next round so you let it off.",
                 "itunes:This Could Be Texas English Teacher"),
            item("Visions of Light", "Ishmael Ensemble", "2021", 8.6,
                 "Bristol jazz that's been left out in the rain and come back stranger. "
                 "Saxophone drifting through fog. Put it on at 1am and let it do the rest.",
                 "itunes:Visions of Light Ishmael Ensemble"),
            item("Eternally Even", "Jim James", "2016", 8.5,
                 "My Morning Jacket's frontman goes full cosmic soul and quietly leaves orbit. "
                 "Lush, political, unhurried. Best heard horizontal.",
                 "wiki:Eternally_Even"),
            item("Led Zeppelin III", "Led Zeppelin", "1970", 8.4,
                 "They retreated to a Welsh cottage with no electricity and came back plugged in anyway. "
                 "'Immigrant Song' is half Viking war cry, half air-raid siren. All hair.",
                 "itunes:Led Zeppelin III"),
            item("HEAL", "Strand of Oaks", "2014", 8.2,
                 "A man exorcising every demon he owns through a fuzz pedal. "
                 "Raw, slightly unhinged, and with choruses you'll hum in the shower against your will.",
                 "itunes:HEAL Strand of Oaks"),
        ],
        mentions=[
            ("Songs for the Deaf", "A road trip through hell with Dave Grohl on drums. Mind the radio."),
            ("Axis: Bold as Love", "Hendrix making a guitar do things guitars aren't licensed to do."),
            ("So Long Forever", "Palace. Heartbreak with excellent reverb."),
            ("What Kinda Music", "Tom Misch and Yussef Dayes. Two lads, one groove, infinite head nods."),
            ("Maggot Brain", "Ten minutes of Eddie Hazel's guitar weeping. You will too."),
        ],
    ),
    dict(
        key="film", num="II", name="Film", unit="film", aspect="2 / 3",
        deck="Ten films worth the popcorn, the overpriced seat and the bloke on his phone in row F.",
        mentions_label="Reputable mentions",
        items=[
            item("mother!", "Darren Aronofsky", "2017", 9.6,
                 "The most divisive film of the decade, and I'm on the correct side of the divide. "
                 "A biblical fever dream in one house. People walked out. Their loss.",
                 "wiki:Mother!"),
            item("Three Billboards Outside Ebbing, Missouri", "Martin McDonagh", "2017", 9.1,
                 "Frances McDormand with a grudge and a lot of plywood. "
                 "Furious, filthy and very funny, right up until it very much isn't.",
                 "wiki:Three_Billboards_Outside_Ebbing,_Missouri"),
            item("Tenet", "Christopher Nolan", "2020", 9.0,
                 "Understood about forty per cent of it, enjoyed all of it. "
                 "The film's own advice applies: don't try to understand it. Feel it.",
                 "wiki:Tenet_(film)"),
            item("The Matrix", "The Wachowskis", "1999", 8.9,
                 "Every action film since has been paying rent to this one. "
                 "Leather coats, bullet time, and the red pill before the internet ruined it.",
                 "wiki:The_Matrix"),
            item("Interstellar", "Christopher Nolan", "2014", 8.8,
                 "A dad, a wormhole and a bookshelf, scored on an organ the size of a cathedral. "
                 "The docking scene did things to my blood pressure that my GP should know about.",
                 "wiki:Interstellar_(film)"),
            item("Blade Runner 2049", "Denis Villeneuve", "2017", 8.7,
                 "Every frame is a painting. Roger Deakins should be legally required to light everything. "
                 "Slow as a glacier and twice as beautiful.",
                 "wiki:Blade_Runner_2049"),
            item("Prisoners", "Denis Villeneuve", "2013", 8.6,
                 "Two and a half hours of rain, dread and Jake Gyllenhaal blinking. "
                 "Hugh Jackman has never been angrier and I have never been more stressed.",
                 "wiki:Prisoners_(2013_film)"),
            item("Drive", "Nicolas Winding Refn", "2011", 8.3,
                 "Gosling says about nine words, wears a scorpion jacket, plays Kavinsky. Then the lift scene. "
                 "Cooler than you and fully aware of it.",
                 "wiki:Drive_(2011_film)"),
            item("The Dark Knight", "Christopher Nolan", "2008", 8.2,
                 "Ledger's Joker is the only agent of chaos whose logic is airtight. "
                 "Not really a superhero film. A crime epic that happens to own a cape.",
                 "wiki:The_Dark_Knight"),
            item("Parasite", "Bong Joon-ho", "2019", 8.1,
                 "Starts as a cheeky comedy, ends somewhere in the basement of your soul. "
                 "You will never look at a peach the same way again.",
                 "wiki:Parasite_(2019_film)"),
        ],
        mentions=[
            ("No Country for Old Men", "Bardem's haircut is the scariest thing in it, and it has a cattle gun."),
            ("Fargo", "Yah, a masterpiece, you betcha."),
            ("Oppenheimer", "Three hours of men in hats talking, and somehow a thriller."),
            ("Saving Private Ryan", "The first twenty minutes deserve their own medal."),
            ("The Place Beyond the Pines", "Gosling on a motorbike, and a generation paying for it."),
            ("The Hateful Eight", "Eight liars, one cabin, a great deal of stew."),
            ("Gangs of New York", "Day-Lewis in a butcher's apron, eating the film whole."),
            ("Forrest Gump", "Life is like a box of chocolates. This one's the good one."),
            ("The Two Towers", "Helm's Deep. That's the review."),
            ("The Shawshank Redemption", "Hope is a good thing. So is this."),
        ],
    ),
    dict(
        key="series", num="III", name="Series", unit="series", aspect="2 / 3",
        deck="Ten reasons I have never once gone to bed at a sensible hour.",
        mentions_label="Noble mentions",
        items=[
            item("True Detective", "Season One", "2014", 9.5,
                 "McConaughey philosophising in a car for eight hours, and I'd happily have watched eighty. "
                 "Time is a flat circle. So is my rewatch habit.",
                 "tvmaze:True Detective#1"),
            item("Breaking Bad", "Vince Gilligan", "2008", 9.4,
                 "A chemistry teacher becomes the worst man in New Mexico and you cheer him on. "
                 "Says more about you than him, frankly.",
                 "tvmaze:Breaking Bad"),
            item("Chernobyl", "Craig Mazin", "2019", 9.3,
                 "Five episodes of quiet, radioactive dread. "
                 "Not great, not terrible. Actually, it's flawless.",
                 "tvmaze:Chernobyl"),
            item("Fargo", "Season One", "2014", 9.0,
                 "Billy Bob Thornton as a wolf in a parka. Minnesota nice, Minnesota murderous. "
                 "The Coens' world, somehow improved.",
                 "tvmaze:Fargo#1"),
            item("Vikings", "Michael Hirst", "2013", 8.8,
                 "Ragnar with a smirk and an axe, sailing west because why not. "
                 "Seasons one to four are a proper saga. We don't talk about after.",
                 "tvmaze:Vikings"),
            item("Band of Brothers", "HBO", "2001", 8.7,
                 "Easy Company, from Normandy to the Eagle's Nest, and a lump in your throat the whole way. "
                 "The real veterans' interviews finish you off.",
                 "tvmaze:Band of Brothers"),
            item("Succession", "Jesse Armstrong", "2018", 8.6,
                 "Horrible people, superb insults, four seasons of a family failing upwards. "
                 "Kendall deserved better. Actually, no, he didn't.",
                 "tvmaze:Succession"),
            item("Severance", "Dan Erickson", "2022", 8.5,
                 "Office work, but you split your brain in half to survive it. Relatable. "
                 "Also the most stylish corporate horror on telly.",
                 "tvmaze:Severance"),
            item("The Office", "American edition", "2005", 8.2,
                 "Yes, the British one came first. Yes, I've picked the American one. "
                 "Michael Scott is a tragic genius and I won't be taking questions.",
                 "tvmaze:#526"),
            item("Game of Thrones", "HBO", "2011", 8.1,
                 "Seasons one to four are some of the best telly ever made. Season eight happened. "
                 "The average lands here, bruised but proud.",
                 "tvmaze:Game of Thrones"),
        ],
        mentions=[
            ("Peaky Blinders", "By order of the Peaky Blinders, this gets a mention."),
            ("Parks and Recreation", "Ron Swanson is a lifestyle. Breakfast food forever."),
            ("The Last Dance", "Jordan took everything personally, and that's the whole documentary."),
        ],
    ),
    dict(
        key="games", num="IV", name="Games", unit="game", aspect="2 / 3",
        deck="Ten games that cost me sleep, friendships, and roughly a year of my life. No regrets.",
        mentions_label="Special mentions",
        items=[
            item("Baldur's Gate 3", "Larian Studios", "2023", 9.8,
                 "Seduce a vampire, interrogate a squirrel, beat a boss by shoving him off a ledge. "
                 "Two hundred hours in and still finding things. The peak.",
                 "steam:1086940"),
            item("Mass Effect 3", "BioWare", "2012", 9.2,
                 "Yes, the ending. I know. But the hundred hours before it are the finest farewell tour in gaming. "
                 "Tuchanka still gets me. Shepard out.",
                 "wiki:Mass_Effect_3"),
            item("God of War", "Santa Monica Studio", "2018", 8.8,
                 "Kratos becomes a dad, which turns out to be scarier than any god. "
                 "One unbroken shot, an axe that comes when called. BOY.",
                 "steam:1593500"),
            item("Horizon Zero Dawn", "Guerrilla Games", "2017", 8.8,
                 "Robot dinosaurs versus a bow and arrow: the premise of a ten-year-old, the story of a philosopher. "
                 "Aloy deserves a statue.",
                 "steam:1151640"),
            item("Metal Gear Solid 4", "Kojima Productions", "2008", 8.6,
                 "Old Snake, nanomachines, and cutscenes long enough to do your tax return during. "
                 "A glorious, unhinged farewell. Kojima-san, you madman.",
                 "wiki:Metal_Gear_Solid_4:_Guns_of_the_Patriots"),
            item("Elden Ring", "FromSoftware", "2022", 8.6,
                 "You will die. A lot. Then you'll spot a castle on the horizon and ride straight at it anyway. "
                 "Try finger, but hole.",
                 "steam:1245620"),
            item("Heavy Rain", "Quantic Dream", "2010", 8.5,
                 "Press X to Jason. Ignore the memes: a properly tense noir that made "
                 "button prompts feel like life or death.",
                 "steam:960910"),
            item("Detroit: Become Human", "Quantic Dream", "2018", 8.5,
                 "Androids, choices, and a flowchart that silently judges you after every chapter. "
                 "Never felt so guilty about a branching path.",
                 "steam:1222140"),
            item("Modern Warfare 2", "Infinity Ward", "2009", 8.2,
                 "The golden age of lobbies, killstreaks and twelve-year-olds questioning my parentage. "
                 "Ghost wore the balaclava best.",
                 "steam:10180"),
            item("Bloodborne", "FromSoftware", "2015", 8.3,
                 "Gothic Victorian horror where the cure is worse than the disease and the bosses worse than both. "
                 "Still waiting on that 60fps patch. Still.",
                 "wiki:Bloodborne"),
        ],
        mentions=[
            ("Destiny, co-op", "The loot's mediocre. Raiding with mates is sacred."),
            ("Skyrim", "You've played it. I've played it. My fridge has played it."),
            ("Dark Souls III", "Praise the sun, then die to the Nameless King."),
            ("Bad Company 2", "Buildings that fall down when you shoot them. Revolutionary."),
            ("LittleBigPlanet", "Sackboy. Need I say more."),
            ("Metal Gear Solid V", "Unfinished, and still the best stealth sandbox ever made."),
            ("Modern Warfare (2019)", "The lighting alone deserves an award."),
            ("Ghost of Tsushima", "Follow the wind. Every standoff is pure Kurosawa."),
            ("Red Dead Redemption 2", "Arthur Morgan deserved better. So did my horse."),
        ],
    ),
]

# The guest chapter. No scores: the cat does not deal in numbers, only in approval.
CATEGORIES.append(dict(
    key="books", num="V", name="Books", aspect="2 / 3", guest=True,
    deck="Ten books, reviewed by the Long-Haired Black Cat, who sat on every one of them "
         "while they were being read. Moosey was not consulted.",
    mentions_label="Worthy mentions",
    items=[
        item("The Secret History", "Donna Tartt", "1992", None,
             "Rich students, Greek verbs, and a murder in the snow. Everyone is terrible and beautifully dressed. "
             "Read it in one night on the warm bit of the radiator.",
             "wiki:The_Secret_History"),
        item("The Book Thief", "Markus Zusak", "2005", None,
             "Narrated by Death, who is kinder than you'd think and nearly as patient as a cat. "
             "I wept into my own fur. Do not tell the dog.",
             "wiki:The_Book_Thief"),
        item("Nineteen Eighty-Four", "George Orwell", "1949", None,
             "Big Brother is watching you. I have always been watching you. "
             "The difference is that I'm adorable about it.",
             "wiki:Nineteen_Eighty-Four"),
        item("To Kill a Mockingbird", "Harper Lee", "1960", None,
             "Scout is the finest human kitten in literature, and Atticus would give up the good chair for a cat. "
             "Quietly, devastatingly decent.",
             "wiki:To_Kill_a_Mockingbird"),
        item("The Hobbit", "J. R. R. Tolkien", "1937", None,
             "A small creature who adores second breakfast and hates leaving the house. Relatable. "
             "The dragon asleep on a pile of treasure is also, frankly, me.",
             "wiki:The_Hobbit"),
        item("The Handmaid's Tale", "Margaret Atwood", "1985", None,
             "Every sentence has its claws out. Afterwards I sat very still on the windowsill for an hour, "
             "which, admittedly, I do anyway.",
             "wiki:The_Handmaid's_Tale"),
        item("The Picture of Dorian Gray", "Oscar Wilde", "1890", None,
             "A beautiful creature who never ages and never faces consequences. I fail to see the tragedy. "
             "Wicked, witty, and gorgeous on every page.",
             "wiki:The_Picture_of_Dorian_Gray"),
        item("The Bell Jar", "Sylvia Plath", "1963", None,
             "Sharp, lonely and luminous, like a cold moon through a window. "
             "Not a cosy read. The true ones rarely are.",
             "wiki:The_Bell_Jar"),
        item("Piranesi", "Susanna Clarke", "2020", None,
             "An endless house of statues and tides, kept by a gentle soul who talks to birds. "
             "This is what I dream about when my paws twitch.",
             "wiki:Piranesi_(novel)"),
        item("The Color Purple", "Alice Walker", "1982", None,
             "Letters to God, sisterhood, and a slow, hard-won joy. "
             "Celie deserves every good thing, and a sunny spot to lie in.",
             "wiki:The_Color_Purple"),
    ],
    mentions=[
        ("Of Mice and Men", "Short, sad, and there's a rabbit situation. I had feelings."),
        ("The Fellowship of the Ring", "Nine walkers. Not one cat. Points deducted."),
        ("The Song of Achilles", "Achilles is basically a cat: gorgeous, sulky, fast. Patroclus is a saint."),
        ("The Subtle Knife", "A knife that cuts windows between worlds. I'd use it on the fridge."),
    ],
))

MEMORIAL = item(
    "Ragnar Volarus", "Obsidian, of the Valkyrie Spires", "", None,
    "Raised to be a weapon, chose to be a poet. The gentlest giant in fiction "
    "and the best friend a Reaper ever had.",
    "mw:https://redrising.fandom.com/api.php|Ragnar Volarus",
)

# Picked by hand across categories, so they're references into the lists above.
TOP_FIVE = [
    ("games", "Baldur's Gate 3"),
    ("music", "In Rainbows"),
    ("film", "mother!"),
    ("series", "True Detective"),
    ("games", "Mass Effect 3"),
]

NUGGETS = [
    item("Vikings, Seasons I–IV", "the Ragnar years", "", None,
         "The good seasons. Before the saga got soggy.", "tvmaze:Vikings"),
    item("…Like Clockwork", "Queens of the Stone Age", "", None,
         "Already in the ten. Mentioned twice because it earned it.",
         "wiki:...Like_Clockwork"),
    item("Maggot Brain", "Funkadelic", "", None,
         "Ten minutes of Eddie Hazel's guitar weeping. You will too.", "wiki:Maggot_Brain"),
    item("Morning Star", "Pierce Brown, a book", "", None,
         "Red Rising's third act and the best payoff in modern sci-fi. Ragnar. That's all.",
         "wiki:Morning_Star_(Brown_novel)"),
]

# ---------------------------------------------------------------------------
# Art fetching
# ---------------------------------------------------------------------------

# Wikimedia wants a descriptive agent with a contact; Fandom's Cloudflare bounces anything
# that doesn't look like a browser. Hence two personalities.
UA_POLITE = "MooseyRates/1.0 (https://github.com/mooseyDev/moosey-rates)"
UA_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"


def get(url, tries=4):
    ua = UA_BROWSER if "fandom" in url or "wikia" in url else UA_POLITE
    for n in range(tries):
        try:
            headers = {"User-Agent": ua}
            if "nocookie" in url:  # Fandom's image CDN refuses requests that don't come "from" a wiki
                headers["Referer"] = "https://www.fandom.com/"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as err:
            if err.code != 429 or n == tries - 1:
                raise
            time.sleep(2 ** n * 3)  # rate limited: back off rather than hammer


def get_json(url):
    return json.loads(get(url))


def art_source(spec):
    kind, _, q = spec.partition(":")
    if kind == "itunes":
        qs = urllib.parse.urlencode({"term": q, "entity": "album", "limit": 1, "country": "gb"})
        hit = get_json(f"https://itunes.apple.com/search?{qs}")["results"][0]
        # Apple's artwork URLs encode the size in the path; asking for more just works.
        return hit["artworkUrl100"].replace("100x100bb", "1000x1000bb")
    if kind == "steam":
        appid, _, kind = q.partition("#")
        return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{kind or 'library_600x900_2x'}.jpg"
    if kind == "wiki":
        d = get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}")
        return d["originalimage"]["source"]
    if kind == "tvmaze":
        name, _, season = q.partition("#")
        if not name:  # "#526" means TVmaze show id 526, for when a name is ambiguous
            return get_json(f"https://api.tvmaze.com/shows/{season}")["image"]["original"]
        qs = urllib.parse.urlencode({"q": name, "embed": "seasons"})
        show = get_json(f"https://api.tvmaze.com/singlesearch/shows?{qs}")
        if season:
            for s in show["_embedded"]["seasons"]:
                if s["number"] == int(season) and s.get("image"):
                    return s["image"]["original"]
        return show["image"]["original"]
    if kind == "mw":
        api, _, title = q.partition("|")
        qs = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "pageimages",
                                     "piprop": "original", "format": "json", "redirects": 1})
        pages = get_json(f"{api}?{qs}")["query"]["pages"]
        return next(iter(pages.values()))["original"]["source"]
    raise ValueError(spec)


def slug(text):
    keep = "".join(c.lower() if c.isalnum() else "-" for c in text)
    return "-".join(filter(None, keep.split("-")))


def save_jpeg(img, path, max_side):
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    img.save(path, "JPEG", quality=84, progressive=True, optimize=True)


def all_items():
    for c in CATEGORIES:
        yield from c["items"]
    yield MEMORIAL
    yield from NUGGETS


def fetch_art():
    IMG.mkdir(parents=True, exist_ok=True)
    seen = set()
    for it in all_items():
        it["img"] = f"img/{slug(it['art'])}.jpg"
        path = OUT / it["img"]
        if it["img"] in seen or path.exists():
            seen.add(it["img"])
            continue
        seen.add(it["img"])
        try:
            spec, _, box = it["art"].partition("@")  # "@x0,y0,x1,y1" crops before shrinking
            im = Image.open(io.BytesIO(get(art_source(spec))))
            if box:
                im = im.crop(tuple(int(n) for n in box.split(",")))
            save_jpeg(im, path, 900)
            print(f"  fetched  {it['title']}")
        except Exception as e:  # one missing cover shouldn't sink the build
            print(f"  MISSING  {it['title']}  ({it['art']}): {e}")
    for f in IMG.glob("*.jpg"):  # art for entries that have since been cut
        if f"img/{f.name}" not in seen:
            f.unlink()
            print(f"  removed  {f.name}")

    # Plates: the two paintings, shrunk from ~600 KB PNGs to something a phone can stomach.
    ART.mkdir(parents=True, exist_ok=True)
    plates = {
        "moose-ship.jpg": ("Portrate Moose on the Red Sea Best.png", 1792),  # native size; it was upscaled and soft
        "wizard-swirl.jpg": ("moose and a wizard and an object.png", 1800),
    }
    for name, (src, size) in plates.items():
        if not (ART / name).exists() and (ROOT / src).exists():
            save_jpeg(Image.open(ROOT / src), ART / name, size)


def dims(rel):
    path = OUT / rel
    if not path.exists():
        return 600, 900
    with Image.open(path) as im:
        return im.size


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

e = html.escape


def fmt(score):
    return f"{score:.1f}"


PAW = ('<svg class="paw" viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="16.2" rx="5.2" ry="4.4"/>'
       '<ellipse cx="5.2" cy="10.4" rx="2.2" ry="2.8"/><ellipse cx="9.5" cy="6.2" rx="2.2" ry="2.9"/>'
       '<ellipse cx="14.5" cy="6.2" rx="2.2" ry="2.9"/><ellipse cx="18.8" cy="10.4" rx="2.2" ry="2.8"/></svg>')


def card(it, rank, aspect, label=None, big=False, guest=False):
    w, h = dims(it["img"])
    meta = " · ".join(x for x in (it["by"], it["year"]) if x)
    if guest:
        stamp = f"{PAW}<small>Approved</small>"
        sig = "L.H.B.C."
        score_html = f'<span class="score paw-score" title="Purr-approved">{PAW}</span>'
    else:
        stamp = f"<b>{fmt(it['score'])}</b><small>Moosey rates</small>"
        sig = "M."
        score_html = (f'<span class="score tick{" gold" if it["score"] >= 9.5 else ""}" style="--t:{round(it["score"] * 10)}" '
                      f'aria-label="{fmt(it["score"])}"><span class="static">{fmt(it["score"])}</span></span>')
    tag = f'<span class="tag">{e(label)}</span>' if label else ""
    return f"""
      <article class="card{' big' if big else ''}" tabindex="0" style="--i:{rank}">
        <div class="art" style="aspect-ratio:{aspect}">
          <img src="{it['img']}" alt="{e(it['title'])}" width="{w}" height="{h}" loading="lazy" decoding="async">
          <span class="rank">{rank}</span>
          <div class="slip"><span class="stamp">{stamp}</span><p>{e(it['review'])}</p><span class="sig">{sig}</span></div>
        </div>
        <div class="cap">
          <div>{tag}<h3>{e(it['title'])}</h3><p>{e(meta)}</p></div>
          {score_html}
        </div>
      </article>"""


def mentions(label, items):
    spans = "".join(
        f'<span class="hm" tabindex="0">{e(t)}<span class="tip">{e(q)}</span></span>' for t, q in items
    )
    return f'<div class="mentions"><h4>{e(label)}</h4><p>{spans}</p></div>'


def chapter(c, cards):
    guest = c.get("guest")
    html_ = f"""
  <section class="chapter{' guest' if guest else ''}" id="{c['key']}">
    <header class="sec-head" data-num="{c['num']}">
      {cat_svg() if guest else ''}
      {'<div class="gaze" aria-hidden="true">' + '<i></i>' * (GAZE_COLS * GAZE_ROWS) + '</div>' if guest else ''}
      <p class="eyebrow">Chapter {c['num']}{' · A guest column' if guest else ''}</p>
      <h2>{c['name']}</h2>
      <p class="sec-deck">{e(c['deck'])}</p>
      {'<p class="byline">Reviews by the Long-Haired Black Cat</p>' if guest else ''}
    </header>
    <div class="grid">{cards}
    </div>
    {mentions(c['mentions_label'], c['mentions']) if c.get('mentions') else ''}
  </section>"""
    # the guest column gets its own night sky, so it needs a full-width wrapper
    return f'<div class="guest-wrap"><div class="stars"></div>{html_}</div>' if guest else html_


# Eye tracking without JavaScript: an invisible grid of hover cells over the cat's header.
# Whichever cell the cursor is in, :has() points the pupils at it. Same trick for the book cards.
GAZE_COLS, GAZE_ROWS = 12, 6


def gaze_css():
    def look(dx, dy):
        dist = math.hypot(dx, dy) or 1
        reach = min(1, dist / 220)  # near the face the pupils barely move, like real eyes
        return f"{4 * reach * dx / dist:.2f}px,{2.6 * reach * dy / dist:.2f}px"

    # rough desktop geometry of the header zone, in CSS px, measured from the eyes
    zone_w, zone_h, eye_y = 1440, 660, 185
    rules = []
    for k in range(GAZE_COLS * GAZE_ROWS):
        r, c = divmod(k, GAZE_COLS)
        dx = (c + 0.5) / GAZE_COLS * zone_w - zone_w / 2
        dy = (r + 0.5) / GAZE_ROWS * zone_h - eye_y
        rules.append(f".guest-wrap:has(.gaze i:nth-child({k + 1}):hover) .pupils{{animation:none;transform:translate({look(dx, dy)})}}")
    cards = []
    for i in range(10):
        r, c = divmod(i, 5)
        dx = (c + 0.5) / 5 * 1260 - 630
        dy = 640 + r * 440
        cards.append(f".guest-wrap:has(.grid .card:nth-child({i + 1}):hover) .pupils{{animation:none;transform:translate({look(dx, dy)})}}")
    return ("\n".join(rules) + "\n@media (min-width:1101px){\n" + "\n".join(cards) + "\n}\n"
            + ".guest-wrap:has(.mentions:hover) .pupils{animation:none;transform:translate(0px,2.6px)}\n")


def fluff(cx, cy, rx, ry, n, amp, seed, side_boost=0.0, bottom_boost=0.0):
    """A closed blob whose edge is a ring of fur tufts; boosts swell the ruff at the cheeks or base."""
    rnd = random.Random(seed)  # seeded so the cat doesn't get a new haircut every build
    pts = []
    for i in range(2 * n):
        t = 2 * math.pi * i / (2 * n) - math.pi / 2
        a = amp + side_boost * abs(math.cos(t)) ** 2 + bottom_boost * max(0, math.sin(t)) ** 2
        k = 1 + a * (0.75 + 0.5 * rnd.random()) if i % 2 == 0 else 1 - a * 0.25
        tw = t + (rnd.random() - 0.5) * 0.08
        pts.append((cx + rx * k * math.cos(tw), cy + ry * k * math.sin(tw)))
    d = f"M{pts[1][0]:.1f},{pts[1][1]:.1f}"
    for j in range(1, n + 1):
        tip, nxt = pts[(2 * j) % (2 * n)], pts[(2 * j + 1) % (2 * n)]
        d += f" Q{tip[0]:.1f},{tip[1]:.1f} {nxt[0]:.1f},{nxt[1]:.1f}"
    return d + "Z"


def sparkle(x, y, r, delay):
    d = f"M{x},{y-r} Q{x},{y} {x+r},{y} Q{x},{y} {x},{y+r} Q{x},{y} {x-r},{y} Q{x},{y} {x},{y-r}Z"
    return f'<path class="spark" style="animation-delay:{delay}s" d="{d}"/>'


def cat_svg():
    fur = "#17131f"
    body = fluff(100, 168, 46, 44, 26, 0.09, 3, bottom_boost=0.05)
    chest = fluff(100, 140, 30, 26, 14, 0.12, 9)
    head = fluff(100, 96, 40, 35, 30, 0.07, 5, side_boost=0.16, bottom_boost=0.08)
    # the tail is a string of overlapping puffs along a curve, which reads as one fluffy brush
    puffs = [
        f'<circle cx="{140 + 30 * math.sin(u * 2.4) - 4 * u:.1f}" cy="{196 - 70 * u + 10 * u * u:.1f}" '
        f'r="{13 - 5 * u + (2.2 if i % 2 else 0):.1f}"/>'
        for i, u in ((i, i / 15) for i in range(16))
    ]
    # three jointed segments; each one lags the last, so a wave travels from base to tip
    def along(u):
        return 140 + 30 * math.sin(u * 2.4) - 4 * u, 196 - 70 * u + 10 * u * u
    base, mid, end = "".join(puffs[:6]), "".join(puffs[6:11]), "".join(puffs[11:])
    (mx, my), (tx, ty) = along(5.5 / 15), along(10.5 / 15)
    tip = fluff(166.5, 128, 10, 10, 9, 0.22, 11)
    return f"""<svg class="cat" viewBox="0 0 200 230" role="img" aria-label="A long-haired black cat with golden eyes, sitting under a crescent moon">
        <defs>
          <radialGradient id="halo"><stop offset="0" stop-color="#8f7cf0" stop-opacity=".42"/><stop offset="1" stop-color="#8f7cf0" stop-opacity="0"/></radialGradient>
          <radialGradient id="iris" cx="45%" cy="40%" r="60%"><stop offset="0" stop-color="#ffe08a"/><stop offset=".65" stop-color="#f2a93b"/><stop offset="1" stop-color="#b8661e"/></radialGradient>
          <clipPath id="irises"><ellipse cx="84" cy="97" rx="10" ry="11"/><ellipse cx="116" cy="97" rx="10" ry="11"/></clipPath>
          <filter id="rim" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="0" stdDeviation="1.6" flood-color="#c9bcff" flood-opacity=".55"/></filter>
        </defs>
        <circle cx="100" cy="120" r="95" fill="url(#halo)"/>
        <path class="moon" d="M160,22 a18,18 0 1,0 18,26 a14,14 0 1,1 -18,-26Z"/>
        {sparkle(30, 46, 6, 0)}{sparkle(176, 92, 4.5, 1.3)}{sparkle(22, 150, 4, 2.1)}{sparkle(60, 20, 3.5, .7)}
        <g filter="url(#rim)" fill="{fur}">
          <g class="tail">{base}<g class="tail-mid" style="transform-origin:{mx:.1f}px {my:.1f}px">{mid}<g class="tail-tip" style="transform-origin:{tx:.1f}px {ty:.1f}px"><g class="tail-flick" style="transform-origin:{tx:.1f}px {ty:.1f}px">{end}<path d="{tip}"/></g></g></g></g>
          <path d="{body}"/><path d="{chest}"/>
          <ellipse cx="84" cy="206" rx="13" ry="9"/><ellipse cx="116" cy="206" rx="13" ry="9"/>
          <path d="M60,86 L68,48 Q72,41 78,46 L98,66Z"/><path d="M140,86 L132,48 Q128,41 122,46 L102,66Z"/>
          <path d="M71,47 l-2.5,-8 M73.5,45.5 l.5,-8 M129,47 l2.5,-8 M126.5,45.5 l-.5,-8" stroke="{fur}" stroke-width="1.8" stroke-linecap="round"/>
          <path d="{head}"/>
        </g>
        <path d="M71,54 L75,76 L90,68Z M129,54 L125,76 L110,68Z" fill="#3b2e55"/>
        <g fill="none" stroke="rgba(201,188,255,.5)" stroke-width=".8" stroke-linecap="round">
          <path d="M78,207 v-5 M84,208 v-6 M90,207 v-5 M110,207 v-5 M116,208 v-6 M122,207 v-5"/>
          <path d="M92,150 q8,6 16,0 M88,160 q12,8 24,0 M94,171 q6,4 12,0" opacity=".55"/>
        </g>
        <g class="eyes">
          <ellipse cx="84" cy="97" rx="10" ry="11" fill="url(#iris)"/><ellipse cx="116" cy="97" rx="10" ry="11" fill="url(#iris)"/>
          <g clip-path="url(#irises)"><g class="pupils"><ellipse cx="85" cy="98" rx="3" ry="8.5" fill="#0b0910"/><ellipse cx="117" cy="98" rx="3" ry="8.5" fill="#0b0910"/></g></g>
          <circle cx="80.5" cy="92.5" r="2.6" fill="#fff"/><circle cx="112.5" cy="92.5" r="2.6" fill="#fff"/>
          <circle cx="88" cy="103" r="1.1" fill="#fff" opacity=".8"/><circle cx="120" cy="103" r="1.1" fill="#fff" opacity=".8"/>
        </g>
        <path d="M96,110 h8 l-4,4.5Z" fill="#c58fa8"/>
        <path d="M100,114.5 v2.5 q-3,3.5 -6,1 M100,117 q3,3.5 6,1" fill="none" stroke="#4a3f63" stroke-width="1.1" stroke-linecap="round"/>
        <path d="M86,113 q-16,-3 -30,-1 M86,116 q-15,1 -28,5 M114,113 q16,-3 30,-1 M114,116 q15,1 28,5" fill="none" stroke="rgba(220,216,238,.45)" stroke-width=".7" stroke-linecap="round"/>
        <path d="M93,127 q7,5 14,0" fill="none" stroke="#c9a54a" stroke-width="1.2"/>
        <path d="M100,129 a5,5 0 1,0 4,7 a4,4 0 1,1 -4,-7Z" fill="#e8c35a"/>
      </svg>"""


def embers(n=11):
    rnd = random.Random(7)  # seeded: the same embers every build
    return "".join(
        f'<i style="--x:{rnd.uniform(14, 86):.0f}%;--sz:{rnd.uniform(2, 4.2):.1f}px;--dx:{rnd.uniform(-26, 26):.0f}px;'
        f'--rise:{rnd.uniform(150, 250):.0f}px;--d:{rnd.uniform(4.5, 8.5):.1f}s;--dl:{-rnd.uniform(0, 8):.1f}s"></i>'
        for _ in range(n)
    )


def memorial(m):
    return f"""
<section class="memoriam" id="memoriam">
  <div class="shrine">
    <figure class="arch"><img src="{m['img']}" alt="Ragnar Volarus" loading="lazy"></figure>
    <div class="embers" aria-hidden="true">{embers()}</div>
  </div>
  <div class="memoriam-text">
    <p class="eyebrow">In memoriam</p>
    <h2>{e(m['title'])}</h2>
    <p class="of">{e(m['by'])} · Red Rising</p>
    <p class="epitaph">{e(m['review'])}</p>
    <p class="valkyrie">May the Valkyrie carry him home.</p>
  </div>
</section>"""


def build():
    fetch_art()
    by_key = {c["key"]: c for c in CATEGORIES}
    lookup = {(c["key"], it["title"]): it for c in CATEGORIES for it in c["items"]}

    five = "".join(
        card(lookup[k], i, "1 / 1", label=by_key[k[0]]["name"], big=(i == 1))
        for i, k in enumerate(TOP_FIVE, 1)
    )
    chapters = "".join(
        chapter(c, "".join(card(it, i, c["aspect"], guest=c.get("guest")) for i, it in enumerate(c["items"], 1)))
        for c in CATEGORIES
    )
    nuggets = "".join(
        f"""<li tabindex="0"><img src="{n['img']}" alt="" loading="lazy">
          <div><b>{e(n['title'])}</b><i>{e(n['by'])}</i></div><span class="tip">{e(n['review'])}</span></li>"""
        for n in NUGGETS
    )
    contents = [("five", "The Five", "Frontis.", False)] + [
        (c["key"], c["name"], c["num"], c.get("guest", False)) for c in CATEGORIES]
    toc = "".join(
        f'<li{" class=guest-row" if g else ""}><a href="#{k}"><span>{n}'
        f'{"<em class=guest-tag>special guest</em>" if g else ""}</span>'
        f'<span class="leader"></span><span class="pg">{p}</span></a></li>'
        for k, n, p, g in contents
    )
    nav = "".join(f'<a href="#{k}">{n}</a>' for k, n, _, _ in contents)

    page = TEMPLATE.format(css=CSS + gaze_css(), five=five, chapters=chapters, memorial=memorial(MEMORIAL), nuggets=nuggets, toc=toc, nav=nav)
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / ".nojekyll").touch()  # stop Pages running Jekyll over a site that doesn't need it
    print(f"Built {OUT / 'index.html'}")


TEMPLATE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Moosey Rates</title>
<meta name="description" content="Records, films, series and games, ranked and reviewed by Moosey. Scores out of ten, opinions out of line.">
<meta property="og:title" content="Moosey Rates">
<meta property="og:description" content="Scores out of ten. Opinions out of line.">
<meta property="og:image" content="art/moose-ship.jpg">
<meta name="theme-color" content="#110c09">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🫎</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400..700;1,400..700&family=IM+Fell+English:ital@0;1&family=IM+Fell+English+SC&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>

<nav class="bar">
  <a class="mono" href="#top">M<i>r</i></a>
  <div class="links">{nav}</div>
</nav>

<header class="hero" id="top">
  <div class="hero-art" aria-hidden="true">
    <img class="haze" src="art/moose-ship.jpg" alt="">
    <img class="sharp" src="art/moose-ship.jpg" alt="">
  </div>
  <div class="hero-text">
    <p class="kicker"><span>Vol. I</span><span>Autumn MMXXVI</span><span>Price: your time</span></p>
    <h1><span class="w1">Moosey</span><em class="w2" data-text="Rates">Rates</em></h1>
    <p class="deck">A ledger of the records, films, series and games that earned their keep, plus a guest column from the cat.
      Scores out of ten. <em>Opinions out of line.</em></p>
    <div class="contents">
      <h2>Contents</h2>
      <ol>{toc}</ol>
    </div>
  </div>
  <figure class="plate">
    <div class="frame"><img src="art/moose-ship.jpg" alt="An engraved moose standing on the deck of a pirate galleon on a red sea" width="1024" height="1792"></div>
    <figcaption><span>Pl. I.</span> The critic, en route to an opinion.</figcaption>
  </figure>
</header>

<section class="five" id="five">
  <header class="sec-head" data-num="5">
    <p class="eyebrow">Frontispiece</p>
    <h2>The Five</h2>
    <p class="sec-deck">Of all time, across every medium. Signed, sealed, and not up for appeal.</p>
  </header>
  <div class="five-grid">{five}
  </div>
  <aside class="nuggets">
    <h4>Moosey's special nuggets</h4>
    <p>Not ranked, not forgotten. Kept in the top drawer.</p>
    <ul>{nuggets}</ul>
  </aside>
</section>

<section class="interlude" aria-hidden="true">
  <div class="interlude-art"></div>
  <blockquote>
    <p>Every score here was argued over, slept on, and then argued over again.</p>
    <cite>Pl. II. A moose, a wizard, and the long road to a 9.8.</cite>
  </blockquote>
</section>

<main>{chapters}
</main>
{memorial}

<footer class="colophon">
  <div class="colophon-art"></div>
  <div class="colophon-text">
    <p class="fin">Fin.</p>
    <p>Hover, or tap, any entry for the verdict. Scores are final. Complaints may be submitted in writing to the sea.</p>
    <p class="small">Set in IM Fell &amp; EB Garamond. Built by hand in Python. No algorithms were consulted.</p>
    <p class="norsk">Takk for besøket. Ha det bra.</p>
  </div>
</footer>

</body>
</html>
"""

CSS = r"""
:root{
  --ink:#110c09; --ink-2:#1a130f; --ink-3:#251b15;
  --paper:#ecdfc6; --paper-2:#d9c9a8; --paper-dim:#b4a487; --muted:#8a7b66;
  --blood:#b8321f; --blood-2:#8e2416; --amber:#e08a32; --amber-2:#f2b25c;
  --cobalt:#3557b7; --sea:#c24a2c;
  --line:rgba(236,223,198,.14);
  --ease:cubic-bezier(.2,.7,.2,1);
  --thud:cubic-bezier(.25,1.6,.45,1);
  color-scheme:dark;
}
*{box-sizing:border-box;margin:0;padding:0}
/* clip, not hidden: hidden tooltips at the screen edge otherwise widen the page on phones */
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%;overflow-x:clip}
body{
  background:
    radial-gradient(1200px 700px at 85% -5%, rgba(224,138,50,.13), transparent 60%),
    radial-gradient(900px 600px at -10% 40%, rgba(184,50,31,.10), transparent 60%),
    radial-gradient(900px 700px at 110% 85%, rgba(53,87,183,.08), transparent 60%),
    var(--ink);
  color:var(--paper);
  font:400 1.075rem/1.6 "EB Garamond", Georgia, serif;
  font-feature-settings:"onum","liga","dlig";
  overflow-x:clip;
}
/* Grain: printed matter is never perfectly flat */
body::after{
  content:"";position:fixed;inset:-50%;pointer-events:none;z-index:100;opacity:.10;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1.1 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
}
::selection{background:var(--blood);color:var(--paper)}
a{color:inherit;text-decoration:none}
img{display:block;max-width:100%}
:focus-visible{outline:1px solid var(--amber);outline-offset:4px}

/* ---------- top bar ---------- */
.bar{
  position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;justify-content:space-between;
  padding:.7rem clamp(1rem,4vw,3rem);
  background:linear-gradient(to bottom, rgba(17,12,9,.85), rgba(17,12,9,.55));
  backdrop-filter:blur(10px) saturate(1.2);-webkit-backdrop-filter:blur(10px) saturate(1.2);
  border-bottom:1px solid var(--line);
  animation:drop 1s .9s var(--ease) both;
}
.mono{font:1.5rem/1 "IM Fell English",serif;letter-spacing:-.02em;color:var(--paper)}
.mono i{color:var(--amber)}
.links{display:flex;gap:clamp(.8rem,2.2vw,2rem);font:.82rem/1 "IM Fell English SC",serif;letter-spacing:.14em}
.links a{color:var(--paper-dim);position:relative;transition:color .35s var(--ease)}
.links a::after{content:"";position:absolute;left:0;right:0;bottom:-6px;height:1px;background:var(--amber);
  transform:scaleX(0);transform-origin:left;transition:transform .45s var(--ease)}
.links a:hover{color:var(--paper)}
.links a:hover::after{transform:scaleX(1)}

/* ---------- hero ---------- */
.hero{
  min-height:100svh;display:grid;grid-template-columns:1.15fr .85fr;gap:clamp(2rem,5vw,5rem);
  align-items:center;padding:7rem clamp(1rem,6vw,6rem) 4rem;max-width:1440px;margin:0 auto;
}
.hero-art{display:none}  /* the dissolving cover is a phone-only layout; desktop keeps the framed plate */
.plate{justify-self:center;width:min(100%,430px);animation:rise 1.4s .3s var(--ease) both}
.frame{position:relative;padding:12px;border:1px solid rgba(236,223,198,.28);background:rgba(236,223,198,.03);
  box-shadow:0 40px 90px -30px rgba(0,0,0,.9),0 0 120px -30px rgba(194,74,44,.45)}
.frame::before{content:"";position:absolute;inset:5px;border:1px solid rgba(236,223,198,.12);pointer-events:none}
.frame img{width:100%;height:auto;aspect-ratio:1024/1792;object-fit:cover;max-height:72svh;
  animation:develop 3.2s .4s var(--ease) both}
.plate figcaption{margin-top:.9rem;text-align:center;font-style:italic;color:var(--muted);font-size:.95rem}
.plate figcaption span{font-style:normal;font-family:"IM Fell English SC",serif;letter-spacing:.12em;color:var(--paper-dim);margin-right:.3rem}
.kicker{display:flex;flex-wrap:wrap;gap:.6rem 1.4rem;font:.8rem/1 "IM Fell English SC",serif;letter-spacing:.2em;color:var(--muted);
  padding-bottom:1.1rem;border-bottom:1px solid var(--line);margin-bottom:1.6rem;animation:rise 1s .1s var(--ease) both}
.kicker span+span::before{content:"✦";margin-right:1.4rem;color:var(--blood);font-size:.6rem;vertical-align:.15em}
h1{font-family:"IM Fell English",serif;font-weight:400;line-height:.82;letter-spacing:-.035em;font-size:clamp(4.4rem,12.5vw,11rem)}
h1 .w1{display:block;animation:rise 1.2s .2s var(--ease) both}
h1 .w2{display:block;position:relative;isolation:isolate;padding-left:.55em;color:var(--amber);
  text-shadow:0 0 .35em rgba(224,138,50,.35),0 0 1.2em rgba(184,50,31,.25);
  animation:rise 1.2s .38s var(--ease) both,burn 3.7s 1.6s infinite}
/* the flame: a blurred copy of the word behind itself, licking upwards on irregular beats */
h1 .w2::before{content:attr(data-text);position:absolute;inset:0;padding-left:.55em;z-index:-1;
  color:#ff8a2a;filter:blur(.14em);opacity:.5;transform-origin:50% 90%;animation:lick 2.3s 1.6s infinite}
@keyframes lick{
  0%,100%{opacity:.5;transform:none}
  11%{opacity:.8;transform:translateY(-.035em) scaleY(1.06)}
  17%{opacity:.36;transform:translateY(.005em) scaleY(.98)}
  29%{opacity:.72;transform:translateY(-.025em) scaleY(1.05) skewX(-1.2deg)}
  38%{opacity:.44;transform:scaleY(1.01)}
  52%{opacity:.85;transform:translateY(-.045em) scaleY(1.08) skewX(1deg)}
  58%{opacity:.4;transform:none}
  71%{opacity:.68;transform:translateY(-.02em) scaleY(1.04) skewX(-.6deg)}
  84%{opacity:.34;transform:scaleY(.99)}
  93%{opacity:.74;transform:translateY(-.03em) scaleY(1.05)}
}
@keyframes burn{0%,100%{filter:brightness(1)}13%{filter:brightness(1.1)}19%{filter:brightness(.93)}
  47%{filter:brightness(1.13)}53%{filter:brightness(.91)}78%{filter:brightness(1.07)}}
.deck{max-width:32rem;margin-top:2rem;font-size:clamp(1.1rem,1.6vw,1.3rem);color:var(--paper-2);animation:rise 1s .6s var(--ease) both}
.deck em{color:var(--paper)}
.contents{margin-top:2.6rem;max-width:26rem;animation:rise 1s .8s var(--ease) both}
.contents h2{font:.78rem/1 "IM Fell English SC",serif;letter-spacing:.24em;color:var(--blood);margin-bottom:.9rem}
.contents ol{list-style:none}
.contents a{display:flex;align-items:baseline;gap:.6rem;padding:.28rem 0;font-style:italic;color:var(--paper-2);transition:color .3s,padding .4s var(--ease)}
.contents .leader{flex:1;border-bottom:1px dotted rgba(236,223,198,.28);transform:translateY(-.3em)}
.contents .pg{font:.85rem "IM Fell English SC",serif;font-style:normal;color:var(--muted);letter-spacing:.1em}
.contents a:hover{color:var(--amber-2);padding-left:.5rem}
.contents a:hover .pg{color:var(--amber)}

.guest-row a{color:#cfc5f5}
.guest-tag{margin-left:.6rem;font:.68rem/1 "IM Fell English SC",serif;font-style:normal;letter-spacing:.16em;
  color:#b3a4ff;text-shadow:0 0 12px rgba(143,124,240,.55);vertical-align:.15em}
.guest-tag::before{content:"✦ ";font-size:.8em}
.contents .guest-row a:hover{color:#ddd4ff}
.contents .guest-row a:hover .pg{color:#b3a4ff}

/* ---------- section heads ---------- */
section{position:relative;max-width:1360px;margin:0 auto;padding:clamp(4rem,9vw,8rem) clamp(1rem,4vw,3rem)}
.sec-head{position:relative;text-align:center;margin-bottom:clamp(2.5rem,5vw,4rem)}
.sec-head::before{content:attr(data-num);position:absolute;left:50%;top:50%;transform:translate(-50%,-56%);
  font:italic clamp(9rem,22vw,18rem)/1 "IM Fell English",serif;color:transparent;
  -webkit-text-stroke:1px rgba(236,223,198,.07);pointer-events:none;z-index:-1}
.eyebrow{font:.78rem/1 "IM Fell English SC",serif;letter-spacing:.28em;color:var(--blood);margin-bottom:.8rem}
.eyebrow::before,.eyebrow::after{content:"";display:inline-block;width:2.4rem;height:1px;background:currentColor;opacity:.6;vertical-align:.3em;margin:0 .9rem}
.sec-head h2{font:400 clamp(3rem,7vw,5.4rem)/.95 "IM Fell English",serif;letter-spacing:-.02em}
.sec-deck{margin:1rem auto 0;max-width:34rem;font-style:italic;color:var(--paper-dim);font-size:1.15rem}

/* ---------- cards ---------- */
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:clamp(1rem,2vw,1.8rem) clamp(.9rem,1.6vw,1.4rem)}
.card{position:relative;outline:none;cursor:default;transition:transform .6s var(--ease)}
.art{position:relative;overflow:hidden;background:var(--ink-3);
  box-shadow:0 18px 40px -22px rgba(0,0,0,.9);transition:box-shadow .6s var(--ease)}
.art::after{content:"";position:absolute;inset:0;border:1px solid rgba(236,223,198,.12);pointer-events:none;transition:border-color .6s}
.art img{width:100%;height:100%;object-fit:cover;
  filter:sepia(.55) saturate(.75) contrast(1.06) brightness(.82);
  transform:scale(1.001);transition:filter .9s var(--ease),transform 1.2s var(--ease)}
.art::before{content:"";position:absolute;inset:0;z-index:1;pointer-events:none;
  background:radial-gradient(circle at 0 0,rgba(10,7,5,.75),transparent 34%);transition:opacity .5s}
.card:hover .art::before,.card:focus-within .art::before{opacity:0}
.slip{z-index:2}
.rank{z-index:2;position:absolute;left:.55rem;top:.2rem;font:italic 2.6rem/1 "IM Fell English",serif;color:var(--paper);
  text-shadow:0 2px 14px rgba(0,0,0,.85);transition:opacity .4s,transform .6s var(--ease)}

/* the review: a parchment slip that slides up out of the frame */
.slip{position:absolute;left:.5rem;right:.5rem;bottom:.5rem;padding:.9rem .9rem .65rem;
  background:linear-gradient(170deg,#f1e6cf,#e3d3b2 70%,#d6c29c);color:#2a1d14;
  font:italic .9rem/1.42 "EB Garamond",serif;
  box-shadow:0 10px 30px rgba(0,0,0,.5);
  transform:translateY(calc(100% + 1rem)) rotate(.6deg);opacity:0;
  transition:transform .65s var(--ease),opacity .35s}
/* torn top edge, kept off the slip itself so the stamp isn't clipped with it */
.slip::before{content:"";position:absolute;left:0;right:0;top:-6px;height:7px;background:#f1e6cf;
  clip-path:polygon(0 6px,7% 1px,15% 5px,24% 0,33% 4px,45% 1px,56% 5px,66% 0,77% 4px,88% 1px,100% 5px,100% 100%,0 100%)}
.slip .sig{display:block;text-align:right;margin-top:.3rem;font:1rem/1 "IM Fell English",serif;font-style:italic;color:var(--blood-2)}

/* the score: a rubber stamp that lands with a thud */
.stamp{float:right;margin:-.2rem -.25rem .3rem .55rem;width:3.9rem;height:3.9rem;border-radius:50%;
  display:grid;place-content:center;text-align:center;color:#c23a24;font-style:normal;
  border:2px solid currentColor;box-shadow:inset 0 0 0 3px #eadbbd,inset 0 0 0 4px currentColor;
  mix-blend-mode:multiply;
  transform:rotate(-16deg) scale(1.9);opacity:0;transition:transform .45s var(--thud),opacity .2s}
.stamp b{font:1.4rem/1 "IM Fell English",serif}
.stamp small{font:.52rem/1 "IM Fell English SC",serif;letter-spacing:.14em;margin-top:.12rem}

.cap{display:flex;justify-content:space-between;align-items:flex-start;gap:.8rem;padding:.85rem .1rem 0}
.cap h3{font:600 1.08rem/1.18 "EB Garamond",serif;letter-spacing:.005em;transition:color .4s}
.cap p{font:.74rem/1.3 "IM Fell English SC",serif;letter-spacing:.11em;color:var(--muted);margin-top:.3rem}
.tag{display:inline-block;font:.68rem/1 "IM Fell English SC",serif;letter-spacing:.2em;color:var(--blood);margin-bottom:.35rem}
.score{font:italic 1.55rem/1 "IM Fell English",serif;color:var(--amber);flex:none;padding-top:.05rem}
.score.gold{color:var(--amber-2);text-shadow:0 0 18px rgba(224,138,50,.55)}

.card:hover,.card:focus-within{transform:translateY(-6px)}
.card:hover .art,.card:focus-within .art{box-shadow:0 30px 60px -24px rgba(0,0,0,.95),0 0 50px -12px rgba(224,138,50,.38)}
.card:hover .art::after,.card:focus-within .art::after{border-color:rgba(224,138,50,.45)}
.card:hover img,.card:focus-within img{filter:none;transform:scale(1.05)}
.card:hover .slip,.card:focus-within .slip{transform:none;opacity:1}
.card:hover .stamp,.card:focus-within .stamp{transform:rotate(-12deg) scale(1);opacity:.9;transition-delay:.3s}
.card:hover .rank,.card:focus-within .rank{opacity:0;transform:translateY(-6px)}
.card:hover h3,.card:focus-within h3{color:var(--amber-2)}

/* ---------- The Five ---------- */
.five-grid{max-width:1080px;margin:0 auto;display:grid;grid-template-columns:1.35fr 1fr 1fr;grid-template-rows:auto auto;gap:clamp(1.2rem,2.4vw,2.2rem)}
.five-grid .big{grid-row:span 2;display:flex;flex-direction:column}
.five-grid .big .art{flex:1;aspect-ratio:auto!important;min-height:0}
.five-grid .big .rank{font-size:5rem;left:1rem;top:.4rem}
.five-grid .big .slip{font-size:1.1rem;padding:1.5rem 1.3rem .9rem;left:1rem;right:1rem;bottom:1rem}
.five-grid .big .stamp{width:5.2rem;height:5.2rem}
.five-grid .big .stamp b{font-size:1.9rem}
.five-grid .big h3{font-size:1.6rem}
.five-grid .big .score{font-size:2.4rem}

.nuggets{margin:clamp(3rem,6vw,5rem) auto 0;max-width:62rem;padding:1.8rem clamp(1rem,3vw,2.4rem) 2rem;
  border-top:1px solid var(--line);border-bottom:1px solid var(--line);text-align:center;position:relative}
.nuggets::before{content:"❦";position:absolute;top:-.8em;left:50%;transform:translateX(-50%);padding:0 1rem;background:var(--ink);color:var(--blood);font-size:1.2rem}
.nuggets h4{font:400 1.7rem/1.1 "IM Fell English",serif;font-style:italic}
.nuggets>p{color:var(--muted);font-style:italic;margin:.3rem 0 1.5rem}
.nuggets ul{list-style:none;display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;text-align:left}
.nuggets li{position:relative;display:flex;gap:.8rem;align-items:center;padding:.5rem;border:1px solid transparent;
  transition:border-color .4s,background .4s;outline:none}
.nuggets li img{width:3.4rem;height:3.4rem;object-fit:cover;flex:none;filter:sepia(.6) brightness(.85);transition:filter .6s}
.nuggets li b{display:block;font-weight:600;font-size:.98rem;line-height:1.2}
.nuggets li i{font-size:.85rem;color:var(--muted)}
.nuggets li:hover,.nuggets li:focus-within{border-color:var(--line);background:rgba(236,223,198,.03)}
.nuggets li:hover img,.nuggets li:focus-within img{filter:none}

/* tooltips for mentions and nuggets */
.tip{position:absolute;left:50%;bottom:calc(100% + .7rem);width:max-content;max-width:min(17rem,80vw);z-index:5;
  padding:.65rem .85rem;background:linear-gradient(170deg,#f1e6cf,#ddcba8);color:#2a1d14;
  font:italic .92rem/1.4 "EB Garamond",serif;text-align:left;white-space:normal;
  box-shadow:0 14px 34px rgba(0,0,0,.55);pointer-events:none;
  opacity:0;transform:translate(-50%,8px) rotate(-.6deg);transition:opacity .3s,transform .45s var(--ease)}
.tip::after{content:"";position:absolute;top:100%;left:50%;margin-left:-6px;border:6px solid transparent;border-top-color:#ddcba8}
:hover>.tip,:focus>.tip{opacity:1;transform:translate(-50%,0) rotate(-.6deg)}

.mentions{margin-top:clamp(2.6rem,5vw,3.6rem);text-align:center;padding-top:1.6rem;border-top:1px solid var(--line)}
.mentions h4{font:.78rem/1 "IM Fell English SC",serif;letter-spacing:.24em;color:var(--blood);margin-bottom:1rem}
.mentions p{max-width:56rem;margin:0 auto;line-height:2.1}
.hm{position:relative;white-space:nowrap;font-style:italic;font-size:1.1rem;color:var(--paper-2);cursor:default;outline:none;
  border-bottom:1px dotted transparent;transition:color .3s,border-color .3s}
.hm+.hm::before{content:"❧";font-style:normal;color:var(--muted);margin:0 .75rem;font-size:.85em;display:inline-block}
.hm:hover,.hm:focus{color:var(--amber-2);border-bottom-color:rgba(224,138,50,.5)}

/* ---------- interlude & colophon: the oil painting ---------- */
.interlude{max-width:none;padding:0;height:clamp(26rem,72vh,44rem);display:grid;place-items:center;overflow:hidden;
  margin:clamp(2rem,4vw,4rem) 0}
.interlude-art,.colophon-art{position:absolute;inset:-10% 0;background:url("art/wizard-swirl.jpg") 62% 70%/cover;
  filter:saturate(.95) brightness(.7)}
.interlude-art{animation:drift 30s ease-in-out infinite alternate}
.interlude::after{content:"";position:absolute;inset:0;
  background:linear-gradient(to bottom,var(--ink) 0%,transparent 22%,transparent 86%,var(--ink) 100%),
             radial-gradient(ellipse at 50% 42%,rgba(17,12,9,.5),transparent 60%)}
.interlude blockquote{position:relative;z-index:1;max-width:44rem;text-align:center;padding:0 1.5rem;margin-bottom:8%}
.interlude p{font:italic clamp(1.7rem,3.8vw,3rem)/1.18 "IM Fell English",serif;color:#fff6e4;text-shadow:0 4px 30px rgba(0,0,0,.8)}
.interlude cite{display:block;margin-top:1.2rem;font:.82rem/1.4 "IM Fell English SC",serif;letter-spacing:.16em;font-style:normal;color:var(--paper-2);text-shadow:0 2px 12px #000}

.colophon{position:relative;overflow:hidden;padding:clamp(8rem,16vw,12rem) 1.5rem clamp(4rem,8vw,6rem);text-align:center}
.colophon-art{inset:0;background-position:62% 80%;filter:saturate(.9) brightness(.62)}
.colophon::before{content:"";position:absolute;inset:0;z-index:1;
  background:linear-gradient(to bottom,var(--ink),rgba(17,12,9,.2) 38%,rgba(17,12,9,.45) 75%,rgba(17,12,9,.8)),
             radial-gradient(ellipse at 50% 55%,rgba(17,12,9,.65),transparent 55%)}
main>section:last-child{padding-bottom:clamp(2rem,4vw,3rem)}
.colophon-text{position:relative;z-index:2;max-width:36rem;margin:0 auto;color:var(--paper-2)}
.fin{font:italic clamp(4rem,10vw,7rem)/1 "IM Fell English",serif;color:var(--amber);
  text-shadow:0 0 .4em rgba(224,138,50,.4);margin-bottom:1.2rem}
.colophon .small{margin-top:1rem;font:.75rem/1.6 "IM Fell English SC",serif;letter-spacing:.16em;color:var(--paper-dim)}
.colophon .norsk{margin-top:1.4rem;font-style:italic;color:var(--amber-2)}

/* ---------- the guest column: same paper, different night ---------- */
/* eased stops over ~22rem so the night creeps in rather than starting at a line */
.guest-wrap{position:relative;overflow:hidden;margin-top:clamp(2rem,5vw,4rem);
  background:radial-gradient(900px 560px at 50% 22rem,rgba(143,124,240,.15),transparent 70%),
    linear-gradient(to bottom,var(--ink) 0,#110c0b 4rem,#110d11 9rem,#110e18 14rem,#110f1d 19rem,#110f1f 23rem,
      #110f1f calc(100% - 23rem),#110f1d calc(100% - 19rem),#110e18 calc(100% - 14rem),#110d11 calc(100% - 9rem),#110c0b calc(100% - 4rem),var(--ink) 100%)}
.guest-wrap>.chapter{padding-top:clamp(5rem,9vw,7rem);padding-bottom:clamp(6rem,12vw,9rem)}
.stars,.stars::after{position:absolute;inset:0;pointer-events:none;
  background-image:radial-gradient(1px 1px at 12% 18%,#e9e2ff,transparent),radial-gradient(1px 1px at 78% 9%,#e9e2ff,transparent),
    radial-gradient(1.5px 1.5px at 33% 42%,#cfc5ff,transparent),radial-gradient(1px 1px at 91% 35%,#e9e2ff,transparent),
    radial-gradient(1px 1px at 55% 71%,#e9e2ff,transparent),radial-gradient(1.5px 1.5px at 6% 83%,#cfc5ff,transparent),
    radial-gradient(1px 1px at 67% 91%,#e9e2ff,transparent),radial-gradient(1px 1px at 24% 64%,#e9e2ff,transparent);
  background-size:520px 520px;opacity:.55;animation:twinkle-field 7s ease-in-out infinite alternate;
  -webkit-mask:linear-gradient(to bottom,transparent,#000 22rem,#000 calc(100% - 22rem),transparent);
  mask:linear-gradient(to bottom,transparent,#000 22rem,#000 calc(100% - 22rem),transparent)}
.stars::after{content:"";background-size:330px 330px;background-position:140px 90px;animation-delay:-3.5s;opacity:.4}
@keyframes twinkle-field{from{opacity:.2}to{opacity:.65}}
.guest .sec-head::before{display:none}  /* the cat is the chapter mark here */
.guest .eyebrow,.guest .mentions h4{color:#a99bf0}
.guest .sec-head h2{color:#efe9ff;text-shadow:0 0 .6em rgba(143,124,240,.35)}
.guest .sec-deck{color:#b9b0d6}
.byline{margin-top:.9rem;font:.78rem/1 "IM Fell English SC",serif;letter-spacing:.22em;color:#c9bcff}
.cat{display:block;width:min(220px,55vw);height:auto;margin:-1rem auto .6rem;overflow:visible}
.cat .moon{fill:#f3e9c6;filter:drop-shadow(0 0 8px rgba(243,233,198,.55))}
.cat .spark{fill:#ece6ff;transform-box:fill-box;transform-origin:center;animation:sparkle 3.2s ease-in-out infinite}
.cat .eyes{transform-box:fill-box;transform-origin:center;animation:blink 7s infinite}
.cat .tail,.cat .tail-mid,.cat .tail-tip,.cat .tail-flick{transform-box:view-box}
.cat .tail{transform-origin:140px 198px;animation:wave-a 4.8s ease-in-out infinite}
.cat .tail-mid{animation:wave-b 4.8s -4.1s ease-in-out infinite}
.cat .tail-tip{animation:wave-c 4.8s -3.4s ease-in-out infinite}
.cat .tail-flick{animation:flick 9s 2s ease-in-out infinite}
@keyframes wave-a{0%,100%{transform:rotate(-6deg)}50%{transform:rotate(7deg)}}
@keyframes wave-b{0%,100%{transform:rotate(-11deg)}50%{transform:rotate(11deg)}}
@keyframes wave-c{0%,100%{transform:rotate(-15deg)}50%{transform:rotate(16deg)}}
.cat .pupils{transition:transform .35s cubic-bezier(.3,.7,.3,1);animation:glance 13s ease-in-out infinite}
.gaze{position:absolute;z-index:3;top:-6rem;bottom:0;left:calc(50% - 50vw);width:100vw;
  display:grid;grid-template-columns:repeat(12,1fr);grid-template-rows:repeat(6,1fr)}
@keyframes flick{0%,55%,100%{transform:rotate(0)}61%{transform:rotate(16deg)}67%{transform:rotate(-7deg)}73%{transform:rotate(9deg)}82%{transform:rotate(0)}}
/* left alone, the cat glances about the room */
@keyframes glance{0%,26%,100%{transform:none}31%,44%{transform:translate(-3.5px,.6px)}50%,62%{transform:translate(3.2px,-1.2px)}68%,80%{transform:translate(.4px,2.2px)}86%{transform:none}}
@keyframes sparkle{0%,100%{opacity:.2;transform:scale(.55)}50%{opacity:1;transform:scale(1.1)}}
@keyframes blink{0%,93%,100%{transform:scaleY(1)}95.5%{transform:scaleY(.06)}}
@keyframes swish{from{transform:rotate(-5deg)}to{transform:rotate(6deg)}}
.guest .art::before{background:radial-gradient(circle at 0 0,rgba(12,9,26,.8),transparent 36%),linear-gradient(rgba(70,50,160,.22),rgba(70,50,160,.22))}
.guest .art img{filter:grayscale(.6) brightness(.8) contrast(1.05)}
.guest .rank{color:#ece6ff}
.guest .slip{background:linear-gradient(170deg,#28224a,#1c1834);color:#e8e2fb;box-shadow:0 10px 30px rgba(0,0,0,.6),inset 0 0 0 1px rgba(201,188,255,.14)}
.guest .slip::before{background:#28224a}
.guest .slip .sig{font:.72rem/1 "IM Fell English SC",serif;letter-spacing:.16em;color:#c9bcff;margin-top:.5rem}
.guest .stamp{color:#c9bcff;mix-blend-mode:normal;box-shadow:inset 0 0 0 3px #241e42,inset 0 0 0 4px currentColor}
.guest .stamp .paw{width:1.45rem;height:1.45rem;fill:currentColor;margin:0 auto .1rem}
.guest .stamp small{font-size:.44rem}
.paw-score .paw{width:1.25rem;height:1.25rem;fill:#8f7cf0;filter:drop-shadow(0 0 6px rgba(143,124,240,.6))}
.guest .card:hover .art,.guest .card:focus-within .art{box-shadow:0 30px 60px -24px rgba(0,0,0,.95),0 0 50px -10px rgba(143,124,240,.55)}
.guest .card:hover .art::after,.guest .card:focus-within .art::after{border-color:rgba(201,188,255,.5)}
.guest .card:hover h3,.guest .card:focus-within h3{color:#d9cfff}
.guest .mentions{border-top-color:rgba(201,188,255,.14)}
.guest .hm:hover,.guest .hm:focus{color:#d9cfff;border-bottom-color:rgba(201,188,255,.5)}
.guest .tip{background:linear-gradient(170deg,#28224a,#1c1834);color:#e8e2fb;box-shadow:0 14px 34px rgba(0,0,0,.6),inset 0 0 0 1px rgba(201,188,255,.14)}
.guest .tip::after{border-top-color:#1c1834}

/* ---------- in memoriam ---------- */
.memoriam{max-width:820px;display:grid;grid-template-columns:auto 1fr;gap:clamp(1.6rem,4vw,3rem);align-items:center;
  padding-top:clamp(4rem,8vw,6rem);padding-bottom:clamp(3rem,6vw,4rem)}
.memoriam::before{content:"";position:absolute;top:0;left:50%;width:min(60%,22rem);height:1px;transform:translateX(-50%);
  background:linear-gradient(90deg,transparent,rgba(236,223,198,.3),transparent)}
.shrine{position:relative}
.embers{position:absolute;inset:0;pointer-events:none}
.embers i{position:absolute;bottom:6%;left:var(--x);width:var(--sz);height:var(--sz);border-radius:50%;
  background:#ffc070;box-shadow:0 0 6px 2px rgba(255,140,50,.75),0 0 16px 5px rgba(224,90,30,.3);
  opacity:0;animation:ember var(--d) var(--dl) linear infinite}
@keyframes ember{
  0%{opacity:0;transform:translate(0,0) scale(1)}
  12%{opacity:.95}
  45%{transform:translate(var(--dx),calc(var(--rise) * -.45)) scale(.85)}
  75%{opacity:.55}
  100%{opacity:0;transform:translate(calc(var(--dx) * -.5),calc(var(--rise) * -1)) scale(.35)}}
.arch{width:clamp(130px,18vw,180px);aspect-ratio:3/4;border-radius:999px 999px 6px 6px;overflow:hidden;padding:6px;
  border:1px solid rgba(236,223,198,.25);animation:candle 4s ease-in-out infinite alternate}
.arch img{width:100%;height:100%;object-fit:cover;object-position:top;border-radius:999px 999px 3px 3px;
  filter:grayscale(1) contrast(1.1) brightness(.85);transition:filter 1.2s var(--ease)}
.memoriam:hover .arch img{filter:sepia(.5) brightness(.95)}
@keyframes candle{0%{box-shadow:0 0 40px -12px rgba(224,138,50,.35)}45%{box-shadow:0 0 55px -10px rgba(224,138,50,.5)}
  55%{box-shadow:0 0 38px -12px rgba(224,138,50,.3)}100%{box-shadow:0 0 60px -8px rgba(224,138,50,.48)}}
.memoriam .eyebrow::before,.memoriam .eyebrow::after{display:none}
.memoriam .eyebrow{margin-bottom:.5rem}
.memoriam h2{font:400 clamp(2.2rem,5vw,3.4rem)/1 "IM Fell English",serif}
.memoriam .of{font:.76rem/1.4 "IM Fell English SC",serif;letter-spacing:.16em;color:var(--muted);margin-top:.5rem}
.memoriam .epitaph{margin-top:1rem;font-style:italic;font-size:1.15rem;color:var(--paper-2);max-width:30rem}
.memoriam .valkyrie{margin-top:.9rem;font:italic 1.05rem "IM Fell English",serif;color:var(--amber)}

/* ---------- ticking scores ----------
   Registered integer properties can be animated, and counters can print them. The score is stored
   as tenths (97), split into 9 and 7 by integer rounding, and scrubbed by the card's scroll position. */
@property --s{syntax:'<integer>';inherits:false;initial-value:0}
@property --si{syntax:'<integer>';inherits:false;initial-value:0}
@property --sd{syntax:'<integer>';inherits:false;initial-value:0}
@supports (animation-timeline: view()){
  .card{view-timeline-name:--card}
  .tick .static{display:none}
  .tick{--s:var(--t);--si:calc((var(--s) - 5) / 10);--sd:calc(var(--s) - var(--si) * 10);
    counter-reset:si var(--si) sd var(--sd);
    animation:tick linear both;animation-timeline:--card;animation-range:entry 35% entry 100%}
  .tick::after{content:counter(si) "." counter(sd)}
  @keyframes tick{from{--s:0}to{--s:var(--t)}}
}

/* ---------- motion ---------- */
@keyframes rise{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:none}}
@keyframes drop{from{opacity:0;transform:translateY(-100%)}to{opacity:1;transform:none}}
/* the plate "develops" like a print in the tray */
@keyframes develop{from{filter:sepia(1) contrast(.6) brightness(1.5) blur(6px);opacity:.2}to{filter:none;opacity:1}}
@keyframes settle{from{transform:scale(1.06)}to{transform:none}}
@keyframes fade{from{opacity:0}}
@keyframes breathe{from{transform:none}to{transform:scale(1.05) translateY(-1%)}}
@keyframes drift{from{transform:scale(1.05) translate3d(-1.5%,0,0)}to{transform:scale(1.14) translate3d(1.5%,-3%,0)}}
@keyframes appear{from{opacity:0;transform:translateY(46px) scale(.97)}to{opacity:1;transform:none}}

@supports (animation-timeline: view()){
  .grid .card,.five-grid .card,.sec-head,.mentions,.nuggets,.memoriam{
    animation:appear linear both;animation-timeline:view();animation-range:entry 0% entry 55%}
  .interlude-art{animation:none;transform:scale(1.15)}
  .interlude-art{animation:pan linear both;animation-timeline:view()}
  @keyframes pan{from{transform:scale(1.12) translateY(-4%)}to{transform:scale(1.12) translateY(4%)}}
}

/* ---------- smaller screens ---------- */
@media (max-width:1100px){
  .grid{grid-template-columns:repeat(4,1fr)}
  .nuggets ul{grid-template-columns:repeat(2,1fr)}
}
@media (max-width:860px){
  /* phones: the painting becomes a cover that dissolves downwards into the title */
  .plate{display:none}
  .hero{display:block;position:relative;overflow:clip;max-width:none;padding:56svh 1.25rem 3rem}
  .hero-text{position:relative;z-index:1}
  .hero-art{display:block;position:absolute;top:0;left:0;right:0;height:82svh;
    animation:settle 9s var(--ease) both,breathe 22s 9s ease-in-out infinite alternate}
  .hero-art img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 46%}
  .hero-art .haze{filter:blur(26px) saturate(1.15) brightness(.75);opacity:.75;transform:scale(1.1);
    -webkit-mask:linear-gradient(to bottom,transparent 30%,#000 55%,#000 70%,transparent);
    mask:linear-gradient(to bottom,transparent 30%,#000 55%,#000 70%,transparent);animation:fade 2.4s .2s ease both}
  .hero-art .sharp{-webkit-mask:linear-gradient(to bottom,#000 32%,rgba(0,0,0,.4) 52%,transparent 68%);
    mask:linear-gradient(to bottom,#000 32%,rgba(0,0,0,.4) 52%,transparent 68%);animation:develop 3.2s .4s var(--ease) both}
  .hero-art::after{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(17,12,9,.55),transparent 22%)}
  .hero h1{text-shadow:0 4px 30px rgba(17,12,9,.9)}
  .kicker{text-shadow:0 1px 12px rgba(17,12,9,.95);border-bottom-color:rgba(236,223,198,.22)}
  .kicker span:nth-child(3){display:none}
  .memoriam{grid-template-columns:1fr;justify-items:center;text-align:center}
  .grid{grid-template-columns:repeat(3,1fr)}
  .five-grid{grid-template-columns:1fr 1fr}
  .five-grid .big{grid-column:span 2;grid-row:auto}
  .five-grid .big .art{min-height:0;aspect-ratio:4/5!important}
  .links{display:none}
}
@media (max-width:560px){
  .grid{grid-template-columns:repeat(2,1fr)}
  .nuggets ul{grid-template-columns:1fr}
  .slip{font-size:.82rem;padding:.9rem .7rem .55rem}
  .stamp{width:3.3rem;height:3.3rem}
  .stamp b{font-size:1.15rem}
  .rank{font-size:2rem}
  .hm+.hm::before{margin:0 .45rem}
  .guest .eyebrow::before,.guest .eyebrow::after{display:none}
}
@media (hover:none){ .card{cursor:pointer} }
/* Reduce Motion is for vestibular triggers: big slides, zooms, parallax. Those stop.
   Small, contained life (flicker, blink, tail, embers, ticking) is left running. */
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .grid .card,.five-grid .card,.sec-head,.mentions,.nuggets,.memoriam,
  .interlude-art,.hero-art,.plate,.kicker,h1 .w1,.deck,.contents,.bar{animation:none!important}
  h1 .w2{animation:burn 3.7s infinite!important}
}
"""

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def serve(port=8000):
    handler = partial(SimpleHTTPRequestHandler, directory=str(OUT))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"Preview at {url}  (Ctrl+C to stop)")
        webbrowser.open(url)
        httpd.serve_forever()


def deploy():
    build()
    for cmd in (["git", "add", "-A"],
                ["git", "commit", "-m", "Update Moosey Rates"],
                ["git", "push"]):
        subprocess.run(cmd, cwd=ROOT)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "build":
        build()
    elif cmd == "deploy":
        deploy()
    else:
        build()
        serve()
