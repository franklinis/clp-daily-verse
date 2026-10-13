# Daily Verse carousel

Every morning this repository prepares the day's Bible verse in **Tamil, English and German** for Christ the Living Petra Church and saves it as **drafts in Buffer**:

- a three-slide **carousel** (1080×1350) for the Facebook page and Instagram feed, and
- a 15–25 second vertical **video** (1080×1920) for an Instagram Reel, a Facebook Reel and a YouTube Short. Each language holds long enough to read, zooms slowly, and cross-fades into the next, over soft background music.

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

## Music

By default each video gets an original instrumental composed in code (`daily_verse/music.py`): soft chords and sparse piano-like notes in a key and progression chosen per date. The church owns it outright, so YouTube's and Meta's copyright matching can never claim or mute a post, which does happen with "royalty-free" library tracks.

To use specific tracks instead, add audio files (mp3, m4a or wav) to `assets/music/`; the videos rotate through them by date, looping short tracks. Only add music the church is licensed to use on Facebook, Instagram and YouTube, and if a licence requires credit, add it to the captions in `church.json`.

## How it works

1. `.github/workflows/daily.yml` runs every day at 05:15 (CET).
2. It renders slides and the video for the next days that DailyVerses.net has published (it publishes about two days ahead).
3. Everything is pushed to the [`media` branch](../../tree/media), which only keeps the last 14 days, so Buffer can download it.
4. For every day not yet in Buffer, it creates the drafts: a carousel per feed channel and a Reel/Short per video channel, with the publish time preset to 07:00 and alt text on every slide.

Re-running is safe: each day's `DD.json` on the `media` branch records the drafts already created.

## Captions and church details

Each platform gets its own text, in Tamil, English and German:

- **Feed carousel** (Instagram, Facebook): the verse in all three languages, the service invitation, address and website, credits and hashtags.
- **Reels**: the same without the verse text, which is in the video.
- **YouTube Short**: a Tamil-first title, and a description with all three verses, the full weekly schedule and links.

Service times, address, links, invitation wording and hashtags live in [`church.json`](church.json). Edit that file (GitHub's web editor is fine) to change them; for example, add a German service to `schedule` and update `invitation` when German services start. Every entry needs `ta`, `en` and `de`.

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

Buffer's free plan allows 10 scheduled posts **per channel at a time**; a slot frees up as soon as a post publishes, so there is no monthly limit. Facebook and Instagram each get two posts a day (carousel and Reel) and YouTube one, so drafts can be approved up to five days ahead.

## Run locally

Requires Python 3.11+ and Google Chrome.

```bash
pip install -r requirements.txt
python3 -m daily_verse render --start 2026-10-15 --days 1
```

Slides and the video are written to `images/`. Use `--force` to re-render a day after changing the design in `daily_verse/template.html`. Tests: `pip install pytest && pytest`.

## Licensing

The code is MIT licensed. The church logo and name belong to Christ the Living Petra Church e.V. The King James Version and Lutherbibel 1912 are in the public domain. Tamil texts are used under tamil-bible.com's terms: single verses, unaltered, never sold.
