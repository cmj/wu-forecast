#!/usr/bin/env python3
"""
wu-forecast.py - 10-day forecast chart screenshot from wunderground.com,
captioned, saved locally, with optional anonymous imgur upload.

Usage:
    ./wu-forecast.py Seattle WA
    ./wu-forecast.py "New York" NY --upload
    ./wu-forecast.py Seattle WA -o ~/weather --upload -q --dark --short

Requires: playwright, requests, Pillow (run `playwright install firefox` once).
"""

import argparse
import base64
import os
import re
import shutil
import subprocess
import sys
import platform
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

WEATHER_SEARCH_URL = "https://api.weather.com/v3/location/search"
WEATHER_API_KEY = "e1f10a1e78da46f5b10a1e78da96f525"
IMGUR_UPLOAD_URL = "https://api.imgur.com/3/image"


def log(msg, quiet=False):
    if not quiet:
        print(msg, file=sys.stderr)


def geocode_city(query, quiet=False):
    params = {
        "apiKey": WEATHER_API_KEY,
        "language": "en-US",
        "query": query,
        "locationType": "city",
        "format": "json",
    }
    log(f"[*] Geocoding '{query}'...", quiet)
    resp = requests.get(WEATHER_SEARCH_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    loc = data.get("location")
    if not loc or not loc.get("city"):
        raise ValueError(f"No location results found for '{query}'")

    country_code = loc["countryCode"][0]
    city = loc["city"][0]
    admin_code = (loc.get("adminDistrictCode") or [None])[0]
    address = loc["address"][0]

    city_slug = city.replace(" ", "-")
    url_ext = f"{country_code}/{admin_code}/{city_slug}" if admin_code else f"{country_code}/{city_slug}"
    return url_ext.lower(), address


def screenshot_forecast(url, out_path, headless=True, window_size="1000,600", wait_seconds=2.5, dark=False, short=False, quiet=False):
    w, h = (int(x) for x in window_size.split(","))
    color_scheme = "dark" if dark else "light"

    log(f"[*] Loading {url}", quiet)
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=headless)
        context = browser.new_context(viewport={"width": w, "height": h}, color_scheme=color_scheme)
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(int(wait_seconds * 1000))

            page.evaluate(
                """
                () => {
                    const l = document.getElementsByClassName("weather-chart-options")[0];
                    if (l) { l.parentNode.removeChild(l); }
                }
                """
            )

            if short:
                page.evaluate(
                    """
                    () => {
                        const canvas = document.querySelector('div.charts-canvas');
                        if (canvas) {
                            Array.from(canvas.children).slice(2).forEach(el => {
                                el.style.display = 'none';
                            });
                        }
                    }
                    """
                )

            if dark:
                page.add_script_tag(url="https://cdn.jsdelivr.net/npm/darkreader@4.9.67/darkreader.min.js")
                page.evaluate(
                    """
                    () => {
                        DarkReader.enable({ brightness: 100, contrast: 100, sepia: 0 });
                    }
                    """
                )
                page.wait_for_timeout(300)
                page.evaluate(
                    """
                    () => {
                        document.querySelectorAll('rect.bc-bar.bar-on').forEach(el => {
                            el.setAttribute('fill', '#2f3234');
                            el.style.setProperty('fill', '#2f3234', 'important');
                        });
                    }
                    """
                )
                page.wait_for_timeout(100)

            el = page.locator(".forecast-chart")
            el.wait_for(state="visible", timeout=15000)
            el.screenshot(path=str(out_path))
            log(f"[*] Saved raw screenshot to {out_path}", quiet)
        finally:
            context.close()
            browser.close()


def _find_font(size):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def pad_image(path, padding=5):
    if padding <= 0:
        return
    img = Image.open(path).convert("RGB")
    bg = img.getpixel((0, 0))

    padded = Image.new("RGB", (img.width + padding * 2, img.height), bg)
    padded.paste(img, (padding, 0))
    padded.save(path)


def caption_image(path, caption_text, dark=False, font_size=14):
    img = Image.open(path).convert("RGB")
    bg = img.getpixel((0, 0))

    draw = ImageDraw.Draw(img)
    font = _find_font(font_size)
    fill = "white" if dark else "black"

    bbox = draw.textbbox((0, 0), caption_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    v_pad = 10
    strip_h = text_h + v_pad * 2

    canvas = Image.new("RGB", (img.width, img.height + strip_h), bg)
    canvas.paste(img, (0, 0))

    draw = ImageDraw.Draw(canvas)
    x = (canvas.width - text_w) // 2
    y = img.height + v_pad - bbox[1]
    draw.text((x, y), caption_text, font=font, fill=fill)

    canvas.save(path)


def upload_to_imgur(path, client_id, quiet=False):
    log("[*] Uploading to imgur...", quiet)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read())

    resp = requests.post(
        IMGUR_UPLOAD_URL,
        headers={"Authorization": f"Client-ID {client_id}"},
        data={"image": b64, "type": "base64"},
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or not data.get("success"):
        raise RuntimeError(f"imgur upload failed: {data}")

    return data["data"]["link"], data["data"]["deletehash"]


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)


def update_latest(png_path, latest_path, quiet=False):
    """Point latest_path at png_path: symlink on POSIX, copy on Windows
    (or wherever symlinks aren't permitted)."""
    png_path = Path(png_path)
    latest_path = Path(latest_path)

    if latest_path.exists() or latest_path.is_symlink():
        try:
            latest_path.unlink()
        except OSError as e:
            log(f"[!] Could not remove existing {latest_path} ({e}); skipping latest update.", quiet)
            return

    if platform.system() == "Windows":
        shutil.copyfile(png_path, latest_path)
        log(f"[*] Copied to {latest_path}", quiet)
    else:
        try:
            os.symlink(png_path.name, latest_path)
            log(f"[*] Linked {latest_path} -> {png_path.name}", quiet)
        except OSError as e:
            log(f"[!] Symlink failed ({e}); falling back to copy.", quiet)
            shutil.copyfile(png_path, latest_path)
            log(f"[*] Copied to {latest_path}", quiet)


def open_file(path, quiet=False):
    system = platform.system()
    try:
        if system == "Linux":
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Windows":
            os.startfile(str(path))
        else:
            log(f"[!] Don't know how to open files on '{system}'; open manually: {path}", quiet)
            return
        log(f"[*] Opened {path}", quiet)
    except (FileNotFoundError, OSError) as e:
        log(f"[!] Could not open {path} automatically ({e}); open manually.", quiet)


def main():
    ap = argparse.ArgumentParser(description="10-day forecast chart from wunderground.com, with optional imgur upload.")
    ap.add_argument("city", nargs="+", help="City name (and optional state), e.g. Seattle WA")
    ap.add_argument("-o", "--output-dir", default=str(Path.home() / "weather-forecasts"),
                     help="Directory to save the PNG + info file (default: ~/weather-forecasts)")
    ap.add_argument("-u", "--upload", action="store_true", help="Upload the image anonymously to imgur")
    ap.add_argument("--imgur-client-id", default=os.environ.get("IMGUR_CLIENT_ID", "17385cf5260cef9"),
                     help="Imgur Client ID (or set IMGUR_CLIENT_ID env var)")
    ap.add_argument("--no-headless", action="store_true", help="Run Firefox with a visible window")
    ap.add_argument("--dark", action="store_true", help="Render in dark mode via DarkReader; caption switches to white text")
    ap.add_argument("--short", action="store_true", help="Only include the temperature and humidity/pressure/cloud panels")
    ap.add_argument("--wait", type=float, default=2.5, help="Seconds to wait for the page/chart to render (default 2.5)")
    ap.add_argument("--padding", type=int, default=5, help="Horizontal padding in pixels (default 5, 0 to disable)")
    ap.add_argument("--no-caption", action="store_true", help="Don't overlay the location/timestamp caption on the image")
    ap.add_argument("--latest", action="store_true",
                     help="Also point a stable filename (default latest.png) at this run's image - "
                          "symlink on Linux/macOS, copy on Windows. Handy for desktop widgets/media frames.")
    ap.add_argument("--latest-name", default="latest.png",
                     help="Filename to use for --latest (default: latest.png)")
    ap.add_argument("-q", "--quiet", action="store_true", help="Only print the final result line")
    ap.add_argument("--view", action="store_true", help="Open the saved image after saving")
    args = ap.parse_args()

    query = " ".join(args.city)

    url_ext, address = geocode_city(query, quiet=args.quiet)
    wg_url = f"https://www.wunderground.com/forecast/{url_ext}"

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp_now = datetime.now()
    ts_for_filename = timestamp_now.strftime("%Y%m%d_%H%M%S")
    day_flag = "%#d" if platform.system() == "Windows" else "%-d"
    ts_for_caption = timestamp_now.strftime(f"%a %b {day_flag} %I:%M:%S %p %Z %Y").strip()

    base_name = f"{slugify(query)}_{ts_for_filename}"
    png_path = out_dir / f"{base_name}.png"
    info_path = out_dir / f"{base_name}.txt"

    screenshot_forecast(
        wg_url,
        png_path,
        headless=not args.no_headless,
        wait_seconds=args.wait,
        dark=args.dark,
        short=args.short,
        quiet=args.quiet,
    )

    pad_image(png_path, padding=args.padding)
    if not args.no_caption:
        caption = f"{address} - {ts_for_caption}".strip(" -")
        caption_image(png_path, caption, dark=args.dark)

    latest_path = None
    if args.latest:
        latest_path = out_dir / args.latest_name
        update_latest(png_path, latest_path, quiet=args.quiet)

    lines = [
        f"City query: {query}",
        f"Resolved address: {address}",
        f"Forecast URL: {wg_url}",
        f"Timestamp: {timestamp_now.isoformat()}",
        f"Image file: {png_path}",
    ]
    if latest_path is not None:
        lines.append(f"Latest file: {latest_path}")

    imgur_link = None
    delete_hash = None
    if args.upload:
        imgur_link, delete_hash = upload_to_imgur(png_path, args.imgur_client_id, quiet=args.quiet)
        lines.append(f"Imgur link: {imgur_link}")
        lines.append(f"Imgur delete hash: {delete_hash}")
        lines.append(f"Imgur delete link: https://imgur.com/delete/{delete_hash}")

    info_path.write_text("\n".join(lines) + "\n")

    if args.upload:
        print(f"10-day forecast - {address} {imgur_link} (delete: https://imgur.com/delete/{delete_hash})")
    else:
        print(f"10-day forecast - {address} saved to {png_path}")

    if not args.quiet:
        print(f"[*] Info file: {info_path}", file=sys.stderr)

    if args.view:
        open_file(png_path, quiet=args.quiet)


if __name__ == "__main__":
    main()
