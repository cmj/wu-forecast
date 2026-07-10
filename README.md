# wu-forecast

Grab a 10-day forecast chart screenshot from [wunderground.com](https://www.wunderground.com) for any city, caption it with the location and timestamp, save it locally, and optionally upload it anonymously to imgur.

| Full chart (Los Angeles) | `--short --dark` (Seattle) |
|---|---|
| ![Los Angeles forecast](https://i.imgur.com/BDYREaq.png) | ![Seattle forecast, short + dark](https://i.imgur.com/DV0GIdD.png) |

## Features

- Looks up any city (and optional state) via a public geocoding endpoint - no API key setup needed
- Screenshots just the forecast chart itself (headless Firefox via Playwright), not the whole page
- Captions the image with the resolved location and timestamp
- `--dark` - dark mode via the real [DarkReader](https://github.com/darkreader/darkreader) engine
- `--short` - just the temperature and humidity/pressure/cloud panels, skipping precip accumulation and wind speed
- `--upload` - anonymous imgur upload, prints the link and a delete link
- Saves a `.txt` info file alongside each image with the resolved address, source URL, and (if uploaded) imgur link/delete hash

## Requirements

- Python 3.9+
- [Playwright](https://playwright.dev/python/) with the Firefox browser

```bash
pip install playwright requests Pillow
playwright install firefox
```

## Usage

```bash
./wu-forecast.py Seattle WA
./wu-forecast.py "New York" NY --upload
./wu-forecast.py Seattle WA --dark --short --view
./wu-forecast.py "Los Angeles" CA -o ~/weather --upload -q
```

On Windows, run it as `python wu-forecast.py Seattle WA` instead.

## Options

| Flag | Description |
|---|---|
| `city` | City name (and optional state), e.g. `Seattle WA` |
| `-o, --output-dir` | Directory to save the PNG + info file (default: `~/weather-forecasts`) |
| `-u, --upload` | Upload the image anonymously to imgur |
| `--imgur-client-id` | Imgur Client ID (or set `IMGUR_CLIENT_ID`); defaults to a public anonymous-upload client ID |
| `--dark` | Dark mode via DarkReader |
| `--short` | Only the temperature and humidity/pressure/cloud panels |
| `--padding` | Horizontal padding in pixels (default 5, `0` to disable) |
| `--no-caption` | Don't overlay the location/timestamp caption on the image |
| `--wait` | Seconds to wait for the page/chart to render (default 2.5) |
| `--no-headless` | Run Firefox with a visible window (useful for debugging) |
| `--view` | Open the saved image after saving |
| `-q, --quiet` | Only print the final result line |

## Notes

- Anonymous imgur uploads only need a Client ID, not a secret API key - register your own for free at [api.imgur.com](https://api.imgur.com/oauth2/addclient) if you'd rather not use the built-in public one.
- Each run writes both `{city}_{timestamp}.png` and `{city}_{timestamp}.txt` to the output directory.
