"""Fetch the legends' art for the stat cards from the Brawlhalla wiki (brawlhalla.wiki.gg), through its MediaWiki API.

    py -3.14 app/dev/fetch_legend_art.py list               the legends, their idle-pose and head files: nothing saved
    py -3.14 app/dev/fetch_legend_art.py fetch --out DIR    download the originals into DIR (a new, empty folder)
    py -3.14 app/dev/fetch_legend_art.py convert --raw DIR  convert DIR's PNGs to transparent WebP in app/static/art/legends/
                                                            and write the manifest

For each legend: the idle pose is the first image on its page (the infobox's "Idle Pose" tab), and the head is its
classic skin icon on the Legends page (SkinIcon_<Legend>_Classic.png). The site's robots.txt allows access; requests
are spaced a second apart, with a plain user agent. The art is Blue Mammoth Games'; the WebP files stay out of git until
their redistribution is confirmed (DATA.md).
"""

import argparse
import html as entities
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://brawlhalla.wiki.gg/api.php"
SITE = "https://brawlhalla.wiki.gg"
AGENT = "esports-analyst-agent/0.1 (local demo; one request a second)"
ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "app" / "static" / "art" / "legends"
PAUSE = 1.0


def get(url):
    time.sleep(PAUSE)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def api(**params):
    return json.loads(get(API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})))


def slug(name):
    """A legend's file name: lowercase ASCII letters and digits ('Bödvar' -> 'bodvar', 'Lin Fei' -> 'linfei')."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", plain.lower())


def legends():
    """[(name, head file)] from the Legends page: each link to a legend page wrapped around its classic skin icon."""
    html = api(action="parse", page="Legends", prop="text")["parse"]["text"]
    found = {}
    for m in re.finditer(r'<a href="/wiki/[^"#]+" title="([^"]+)"[^>]*>\s*<img[^>]*alt="(SkinIcon[^"]*\.png)"', html):
        icon = entities.unescape(m.group(2)).replace(" ", "_")
        # a legend without its own icon yet shows the generic SkinIcon_Classic.png: no head, rather than the placeholder
        found.setdefault(entities.unescape(m.group(1)), None if icon == "SkinIcon_Classic.png" else icon)
    return sorted(found.items())


def idle_file(name):
    """The image in the infobox's "Idle Pose" tab, the first on a legend's page; None when the page has no idle pose
    yet (a new legend's first image can be something else, such as a stats chart)."""
    html = api(action="parse", page=name, prop="text")["parse"]["text"]
    pose = html.find('infobox-swapper pose"')
    tab = html[pose:html.find("</tr>", pose)] if pose >= 0 else ""  # the tab's own row: an empty tab has no file
    m = re.search(r'href="/wiki/File:([^"]+)"', tab)
    return entities.unescape(urllib.parse.unquote(m.group(1))) if m else None


def originals(files, **scale):
    """{file: (url, width, height, mime)}, 50 files at a time. With scale (iiurlheight or iiurlwidth), the url is the
    wiki's copy scaled to fit: the cards never draw a legend taller than the 1080 px frame."""
    out = {}
    files = list(files)
    for i in range(0, len(files), 50):
        q = api(action="query", titles="|".join("File:" + f for f in files[i:i + 50]), prop="imageinfo",
                iiprop="url|size|mime", **scale)
        for page in q["query"]["pages"]:
            info = (page.get("imageinfo") or [None])[0]
            if info:
                out[page["title"].split(":", 1)[1].replace(" ", "_")] = (
                    info.get("thumburl") or info["url"], info.get("thumbwidth") or info["width"],
                    info.get("thumbheight") or info["height"], info["mime"])
    return out


def plan():
    rows = []
    for name, head in legends():
        rows.append({"name": name, "slug": slug(name), "idle": (idle_file(name) or "").replace(" ", "_") or None,
                     "head": head})
    idle = originals([r["idle"] for r in rows if r["idle"]], iiurlheight=1080)
    heads = originals([r["head"] for r in rows if r["head"]], iiurlwidth=256)
    for r in rows:
        r["idle_info"], r["head_info"] = idle.get(r["idle"]), heads.get(r["head"])
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["list", "fetch", "convert"])
    parser.add_argument("--out", help="fetch: a new, empty folder for the downloads (outside the repo)")
    parser.add_argument("--raw", help="convert: the folder fetch downloaded into")
    args = parser.parse_args(argv)
    if args.command == "convert":
        return convert(Path(args.raw))
    rows = plan()
    if args.command == "list":
        for r in rows:
            i, h = r["idle_info"], r["head_info"]
            print(f"{r['slug']:14s} {r['name']:22s} idle {r['idle']} {i[1:3] if i else 'MISSING'} | head {h[1:3] if h else 'MISSING'}")
        total = sum(x[1] * x[2] for r in rows for x in (r["idle_info"], r["head_info"]) if x)
        print(f"{len(rows)} legends; {sum(1 for r in rows if r['idle_info'])} idle poses, "
              f"{sum(1 for r in rows if r['head_info'])} heads; {total / 1e6:.1f} megapixels in all")
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        sys.exit(f"{out} isn't empty: give fetch a new folder.")
    (out / "idle").mkdir()
    (out / "heads").mkdir()
    for r in rows:
        for kind, info in (("idle", r["idle_info"]), ("heads", r["head_info"])):
            if not info or info[3] != "image/png":
                print(f"skipped {r['name']} {kind}: {info and info[3]}")
                continue
            (out / kind / f"{r['slug']}.png").write_bytes(get(info[0]))
    (out / "plan.json").write_text(json.dumps([{k: v for k, v in r.items()} for r in rows], indent=1, ensure_ascii=False),
                                   encoding="utf-8")
    print(f"Downloaded into {out}")


def convert(raw):
    """Each downloaded PNG as a transparent WebP (lossless for heads, quality 92 for poses), and the manifest."""
    from PIL import Image

    rows = json.loads((raw / "plan.json").read_text(encoding="utf-8"))
    (ART / "heads").mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))
    legends_out = {}
    for r in rows:
        entry = {"name": r["name"], "source": f"{SITE}/wiki/{urllib.parse.quote(r['name'].replace(' ', '_'))}"}
        for kind, key, options in (("idle", "file", {"quality": 92}), ("heads", "head", {"lossless": True})):
            src = raw / kind / f"{r['slug']}.png"
            if not src.exists():
                continue
            with Image.open(src) as im:
                im = im.convert("RGBA")
                box = im.getbbox()  # trim the transparent margin, so offsets and scales start from the figure
                if box:
                    im = im.crop(box)
                name = f"{r['slug']}.webp" if kind == "idle" else f"heads/{r['slug']}.webp"
                im.save(ART / name, "WEBP", **options)
            entry[key] = name
        if "file" in entry or "head" in entry:
            legends_out[r["slug"]] = entry
    manifest["legends"] = legends_out
    (ART / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(legends_out)} legends written to {ART}")


if __name__ == "__main__":
    main()
