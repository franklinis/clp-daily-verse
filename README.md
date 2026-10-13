# Daily Verse carousel

Every morning this repository prepares the day's Bible verse in **Tamil, English and German** for Christ the Living Petra Church and saves it as **drafts in Buffer**:

- a three-slide **carousel** (1080×1350) for the Facebook page and Instagram feed, and
- a 15–25 second vertical **video** (1080×1920) for an Instagram Reel, a Facebook Reel and a YouTube Short. Each language holds long enough to read, zooms slowly, and cross-fades into the next; the audio track is silent, so there is no music licensing to worry about.

Someone from the church reviews each draft in Buffer and approves it; nothing is published automatically.

| Slide | Text | Source |
|---|---|---|
| தமிழ் | பரிசுத்த வேதாகமம் | [tamil-bible.com](https://www.tamil-bible.com) |
| English | King James Version (public domain) | [DailyVerses.net](https://dailyverses.net) |
| Deutsch | Lutherbibel 1912 (gemeinfrei) | [DailyVerses.net](https://dailyverses.net/de) |

DailyVerses.net chooses the verse. The English and German texts come from its pages for that date, and the Tamil text of the same passage comes from tamil-bible.com. Every slide credits its translation, and each post's caption credits both sites.

## Design

Each slide has a generated misty-mountain background, like the artwork on christ-livingpetra.de, and no two days look the same:

- **39 palettes**: 30 for weekdays (blues, purples, warm earth and gold tones, teal, neutrals and starry nights), 4 church greens that rotate on Sundays, and 5 for feast days: Christmas (24–26 Dec, with a star), New Year, Good Friday, Easter and Pentecost (dates calculated every year).
- Weekday palettes are shuffled each year and never repeat on consecutive days.
- Every day also varies the sky gradient and its angle, the sun or moon position and size, light rays, fog bands, and the mountain style (rolling, layered or alpine) and number of ridges.
- Re-rendering a date always gives the same picture, and a test checks that every palette keeps white text readable (WCAG 3:1 for large text).

Palettes live in `daily_verse/background.py`; the slide layout is `daily_verse/template.html`.

## How it works

1. `.github/workflows/daily.yml` runs every day at 05:15 (CET).
2. It renders slides and the video for the next days that DailyVerses.net has published (it publishes about two days ahead).
3. Everything is pushed to the [`media` branch](../../tree/media), which only keeps the last 14 days, so Buffer can download it.
4. For every day not yet in Buffer, it creates the drafts: a carousel per feed channel and a Reel/Short per video channel, with the publish time preset to 07:00 and alt text on every slide.

Re-running is safe: each day's `DD.json` on the `media` branch records the drafts already created.

## Reviewing drafts

Open Buffer → **Drafts**. Check the slides and caption, then choose **Schedule** (keeps the 07:00 time) or edit the time first. Delete a draft to skip a day.

## Setup

1. In Buffer, go to **Settings → API** and create an API key.
2. In this repository, go to **Settings → Secrets and variables → Actions**:
   - **Secret** `BUFFER_API_KEY`: the key from step 1.
   - **Variable** `BUFFER_CHANNELS`: where the carousel goes, as comma-separated `channelId:service` pairs, for example `FACEBOOK_CHANNEL_ID:facebook,INSTAGRAM_CHANNEL_ID:instagram` (channel ids are in the URL when you open a channel in Buffer).
   - **Variable** `BUFFER_VIDEO_CHANNELS`: where the video goes, for example `FACEBOOK_CHANNEL_ID:facebook,INSTAGRAM_CHANNEL_ID:instagram,YOUTUBE_CHANNEL_ID:youtube`.
   - Optional **variable** `POST_TIME`: preset publish time, default `07:00` (Europe/Berlin).
3. Run the workflow once from **Actions → Daily verse drafts → Run workflow**.

Without the API key the workflow still renders and publishes everything, but creates no drafts.

Buffer's free plan allows 10 scheduled posts at a time across the organization. With the carousel on two channels and the video on three, each day has five drafts, so approve one day at a time rather than a whole week in advance.

## Run locally

Requires Python 3.11+ and Google Chrome.

```bash
pip install -r requirements.txt
python3 -m daily_verse render --start 2026-10-15 --days 1
```

Slides and the video are written to `images/`. Use `--force` to re-render a day after changing the design in `daily_verse/template.html`. Tests: `pip install pytest && pytest`.

## Licensing

The code is MIT licensed. The church logo and name belong to Christ the Living Petra Church e.V. The King James Version and Lutherbibel 1912 are in the public domain. Tamil texts are used under tamil-bible.com's terms: single verses, unaltered, never sold.
