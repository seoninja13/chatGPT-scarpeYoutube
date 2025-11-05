# YouTube Channel URL Scraper

This repository contains a small command-line script that scrapes every video
URL published on a YouTube channel. The implementation relies on Python and
Beautiful Soup to analyse the HTML served by YouTube and to extract the
bootstrap JSON payload embedded in the page. When the third-party
``beautifulsoup4`` package is not available (for example, in restricted
environments), the script falls back to a tiny bundled parser that exposes the
subset of the Beautiful Soup API required by the scraper.

## Features

- Navigates the channel's `/videos` tab to collect metadata for each upload.
- Follows continuation tokens to fetch every page of results exposed by
  YouTube's internal API.
- Stores the collected data as JSON, including video titles, canonical URLs,
  published timestamps, and view counts when available.
- Built solely on Python's standard library, so no third-party installation is
  required in restricted environments.

## Usage

```bash
python scrape_youtube_channel.py https://www.youtube.com/@abbasravji --output videos.json
```

The command above saves the scraped information to `videos.json`. Omit the
`--output` option to print the JSON to standard output. Use `--limit` to restrict
the number of results for quick smoke tests while developing.

## Notes

- Install ``beautifulsoup4`` if you want to use the official library. When the
  dependency cannot be installed the script will automatically use the bundled
  fallback parser implemented on top of the standard library's ``html.parser``.
- The script communicates with YouTube. Network access must be available for the
  scraping process to succeed.
