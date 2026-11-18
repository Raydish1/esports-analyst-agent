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
