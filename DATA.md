# Data use

The project's data comes from three sources:
- the official Brawlhalla Esports Stats API (https://www.docs.brawltools.com/v2/pages/);
- start.gg;
- Challengermode.

Each source has given the project's author permission to use its data publicly, as of 2026-11-17. That covers showing
the data, and answers and tables computed from it, in a public deployment of the demo app (`app/`).

The permission covers using the data, not redistributing it in this repository. API responses and the built
databases (`data/`) stay out of git.

The Esports Earnings snapshot (`curation/esports_earnings_snapshot.csv`, 2026-10-04) fills gaps in career earnings. It
isn't one of the three sources above, so this permission doesn't cover it: showing its figures publicly is a
separate decision.

## Broadcast graphics

The stat cards copy the broadcast graphics of the official Brawlhalla streams. The streams' lead producer gave the
reference screenshots (`docs/graphics-reference/`) as examples to copy, and suggested building them with HTML, CSS and
images (2026-11-18).
- The screenshots stay out of git (`.gitignore`).
- Until the producer sends the source fonts, colors, backgrounds and edge assets, the cards use colors sampled from the
  screenshots, free fonts that match, and edges traced into SVG. The producer's assets replace them when they arrive.
- The broadcast's fonts (the producer, 2026-11-18): Proxima Nova Condensed Black for the heavy text, and Author
  Medium for the small text. Author Medium loads from Fontshare, where it's free. Proxima Nova is a commercial font
  (Mark Simonson Studio) whose license doesn't cover web embedding; the user chose to publish its three used cuts in
  `app/static/fonts/` anyway (2026-11-19), after being told so.
- The character art (the legends' idle poses and heads in `app/static/art/legends/`, from the Brawlhalla wiki, and the
  hero's official artwork in `app/static/art/hero/`) is cleared for redistribution (2026-11-19), so it's committed.
- The cards' backgrounds (`app/static/art/backgrounds/`, five Brawlhalla stage paintings) were supplied by the user for
  the cards (2026-11-22), and are committed with the other art; a card picks one at random.
