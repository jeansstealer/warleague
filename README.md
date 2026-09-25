# War League Report

Round-by-round reports for the **Warhammer 40,000: Tacticus** War League: who won
and lost, promotions and demotions, top-50 entrants and drop-outs, rank movers
and the full top 50.

Live site: <https://jeansstealer.github.io/warleague/>

Unofficial fan site, not affiliated with or endorsed by Snowprint Studios.

## Where the data comes from

The in-game **War League leaderboard (top 50)**, captured when someone opens
that screen with the [GW Tracker](https://github.com/maxbergsten/GuildWar)
running. Nothing here contacts the game: the site only knows what was shown
in-game at the time of a capture. Only the top 50 is visible, so every
statement on the site is about the top 50. A guild that drops out of it is
"left the top 50", not "lost".

## How it updates

1. Someone opens the War League leaderboard in Tacticus with the tracker running.
   The tracker's Apps Script keeps that latest top 50 and serves it at
   `…/exec?feed=league`.
2. Every 30 minutes (and on **Actions → Update War League → Run workflow**) the
   workflow fetches it. `scripts/ingest.py` stores it in `data/snapshots/` if
   it's new, and rebuilds `data/league.json`. New snapshots are committed.
3. The workflow publishes `site/` plus `league.json` to GitHub Pages.

Open the leaderboard **once after each round's war ends** for a report per
round. If a round is missed, the next report says which rounds it covers.

## Rounds

`data/calendar.json` holds the season calendar: season 27's war 1 began
2026-09-19 09:32:44 UTC; wars are 60 hours apart (24 h preparation + 36 h war,
none before war 1); 6 wars per season; a new season every 28 days. A capture
belongs to the last round whose war phase had ended when it was taken. If
Snowprint changes the schedule, edit this file and run the workflow.

## Setup

1. Repository secret `LEAGUE_FEED_URL` = the tracker's web app URL followed by
   `?feed=league`.
2. **Settings → Pages → Source: GitHub Actions**.
3. Run the workflow once.

## Development

```
python -m unittest discover -s scripts       # tests
python scripts/ingest.py feed.json           # ingest a saved feed
```

The site is plain HTML/CSS/JS in `site/` and reads only `league.json`.
