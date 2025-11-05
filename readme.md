# YouTube Channel URL Scraper

This repository contains a small command-line script that scrapes every video
URL published on a YouTube channel. The implementation relies on Python and a
minimal Beautiful Soup-compatible parser to analyse the HTML served by YouTube
and to extract the bootstrap JSON payload embedded in the page.

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

- The repository bundles a lightweight drop-in replacement for the parts of
  Beautiful Soup required by the scraper. It mirrors the `find` and `find_all`
  methods and is implemented on top of the standard library's `html.parser`.
- The script communicates with YouTube. Network access must be available for the
  scraping process to succeed.
