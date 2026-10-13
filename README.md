# Daily Verse carousel

Every morning this repository prepares a three-slide carousel of the day's Bible verse in **Tamil, English and German** for Christ the Living Petra Church, and saves it as a **draft in Buffer** for the Facebook page and Instagram. Someone from the church reviews each draft in Buffer and approves it; nothing is published automatically.

| Slide | Text | Source |
|---|---|---|
| தமிழ் | பரிசுத்த வேதாகமம் | [tamil-bible.com](https://www.tamil-bible.com) |
| English | King James Version (public domain) | [DailyVerses.net](https://dailyverses.net) |
| Deutsch | Lutherbibel 1912 (gemeinfrei) | [DailyVerses.net](https://dailyverses.net/de) |

DailyVerses.net chooses the verse. The English and German texts come from its pages for that date, and the Tamil text of the same passage comes from tamil-bible.com. Every slide credits its translation, and each post's caption credits both sites.

## Design

Each slide has a generated misty-mountain background, like the artwork on christ-livingpetra.de. The ridgelines are different every day, and the colours follow the day of the week: dawn blue (Mon), earth (Tue), teal (Wed), dusk (Thu), gold (Fri), slate (Sat) and the church's green (Sun). Palettes live in `daily_verse/background.py`; the layout is `daily_verse/template.html`.

## How it works

1. `.github/workflows/daily.yml` runs every day at 05:15 (CET).
2. It renders slides for the next three days that DailyVerses.net has published (it publishes about two days ahead).
3. The slides are pushed to the [`media` branch](../../tree/media), which only keeps the last 30 days, so Buffer, Facebook and Instagram can download them.
4. For every day not yet in Buffer, it creates one draft per channel, with all three slides as a carousel, the publish time preset to 07:00, and alt text for each slide.

Re-running is safe: each day's `DD.json` on the `media` branch records the drafts already created.

## Reviewing drafts

Open Buffer → **Drafts**. Check the slides and caption, then choose **Schedule** (keeps the 07:00 time) or edit the time first. Delete a draft to skip a day.

## Setup

1. In Buffer, go to **Settings → API** and create an API key.
2. In this repository, go to **Settings → Secrets and variables → Actions**:
   - **Secret** `BUFFER_API_KEY`: the key from step 1.
   - **Variable** `BUFFER_CHANNELS`: comma-separated `channelId:service` pairs, for example `FACEBOOK_CHANNEL_ID:facebook,INSTAGRAM_CHANNEL_ID:instagram` (channel ids are in the URL when you open a channel in Buffer).
   - Optional **variable** `POST_TIME`: preset publish time, default `07:00` (Europe/Berlin).
3. Run the workflow once from **Actions → Daily verse drafts → Run workflow**.

Without `BUFFER_CHANNELS` the workflow still renders and publishes the slides, but creates no drafts.

Buffer's free plan allows 10 scheduled posts at a time across the organization. Preparing three days for two channels stays within that.

## Run locally

Requires Python 3.11+ and Google Chrome.

```bash
python3 -m daily_verse render --start 2026-10-15 --days 1
```

Slides are written to `images/`. Use `--force` to re-render a day after changing the design in `daily_verse/template.html`. Tests: `pip install pytest && pytest`.

## Licensing

The code is MIT licensed. The church logo and name belong to Christ the Living Petra Church e.V. The King James Version and Lutherbibel 1912 are in the public domain. Tamil texts are used under tamil-bible.com's terms: single verses, unaltered, never sold.
