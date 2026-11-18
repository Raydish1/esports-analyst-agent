"""Render a broadcast card with Playwright and compare it with its reference screenshot.

    py -3.14 app/dev/compare_card.py --player 79853 --mode 1v1 --reference PATH --out DIR

Needs the server running with --preview, Playwright for Python (py -3.14 -m pip install playwright) and Google Chrome
or Microsoft Edge installed (--browser chrome or msedge): Playwright drives the installed browser, so no browser
download is needed.

Writes to DIR: render.png (the card at 1920x1080), reference.png (the reference scaled to 1920 wide, top-aligned on a
1920x1080 canvas), side_by_side.png, overlay.png (the two at 50%) and diff.png (their difference, brighter where they
differ). The reference screenshots stay out of git, and so do these files: DIR should be outside the repo.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageOps
from playwright.sync_api import sync_playwright

W, H = 1920, 1080


def render(url, path, browser):
    with sync_playwright() as p:
        b = p.chromium.launch(channel=browser)
        page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(url)
        page.wait_for_selector("body[data-ready=true]", timeout=30000)
        page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()


def reference(path, crop=None):
    """The reference scaled to 1920 wide, top-aligned on a black 1920x1080 canvas."""
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    im = im.resize((W, round(im.height * W / im.width)), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(im.crop((0, 0, W, min(H, im.height))), (0, 0))
    return canvas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    parser.add_argument("--player", type=int, required=True)
    parser.add_argument("--opponent", type=int, help="render the head-to-head of --player against this player")
    parser.add_argument("--sets", action="store_true", help="render the set list of --player against --opponent")
    parser.add_argument("--legend", help="development: draw this legend for --player (a manifest slug)")
    parser.add_argument("--opponent-legend", help="development: draw this legend for --opponent")
    parser.add_argument("--mode", default="")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--crop", type=int, nargs=4, help="a box of the reference to use: left top right bottom")
    parser.add_argument("--out", required=True)
    parser.add_argument("--browser", default="chrome")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    url = (f"{args.server}/preview.html?player={args.player}" + (f"&opponent={args.opponent}" if args.opponent else "")
           + (f"&mode={args.mode}" if args.mode else "") + ("&sets=1" if args.sets else "")
           + (f"&legend={args.legend}" if args.legend else "") + (f"&opponent_legend={args.opponent_legend}" if args.opponent_legend else ""))
    render(url, out / "render.png", args.browser)
    mine = Image.open(out / "render.png").convert("RGB")
    ref = reference(args.reference, args.crop)
    ref.save(out / "reference.png")
    side = Image.new("RGB", (W * 2 + 20, H), (255, 255, 255))
    side.paste(ref, (0, 0))
    side.paste(mine, (W + 20, 0))
    side.resize((side.width // 2, side.height // 2), Image.LANCZOS).save(out / "side_by_side.png")
    Image.blend(ref, mine, 0.5).save(out / "overlay.png")
    diff = ImageOps.autocontrast(ImageOps.grayscale(ImageChops.difference(ref, mine)))
    diff.save(out / "diff.png")
    print(f"Wrote {out}: render, reference, side_by_side, overlay, diff")


if __name__ == "__main__":
    main()
