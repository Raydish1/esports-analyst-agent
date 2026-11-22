"""The hosted server's data, as one file to upload (deploy/README.md):

    py -3.14 deploy/bundle.py      writes data/deploy/bundle.tgz

It holds the live build (data/db/current.json and the build it names), the legends' mains and the event logos' list
(data/curated), and the logos as 256-pixel WebP thumbs, made here for any logo without one. data/ is never committed
(DATA.md), and neither is this bundle; the server unpacks it into its volume (deploy/start.sh).
"""

import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "deploy" / "bundle.tgz"


def thumbs():
    """A 256-pixel WebP of every fetched logo that has none yet, as the app makes them (main.event_logo)."""
    from PIL import Image
    folder = DATA / "raw" / "event_images"
    (folder / "thumbs").mkdir(exist_ok=True)
    made = 0
    for source in folder.iterdir():
        thumb = folder / "thumbs" / (source.stem + ".webp")
        if source.is_file() and not thumb.exists():
            with Image.open(source) as im:
                im = im.convert("RGBA")
                im.thumbnail((256, 256))
                im.save(thumb, "WEBP", quality=88)
            made += 1
    return made


def main():
    pointer = json.loads((DATA / "db" / "current.json").read_text(encoding="utf-8"))
    build = DATA / "db" / pointer["file"]
    made = thumbs()
    files = [DATA / "db" / "current.json", build, DATA / "curated" / "player_legends.csv",
             DATA / "curated" / "event_images.csv", *sorted((DATA / "raw" / "event_images" / "thumbs").glob("*.webp"))]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(OUT, "w:gz") as tar:
        for f in files:
            tar.add(f, arcname=f.relative_to(DATA).as_posix())
    print(f"{OUT.relative_to(ROOT)}: build {pointer['build']}, {len(files)} files ({made} new thumbs),"
          f" {OUT.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    sys.exit(main())
