import threading
import logging
import os
import io
import requests

from PIL import Image, ImageDraw, ImageFont

from config import (
    MOCK, DISPLAY_WIDTH, DISPLAY_HEIGHT,
    DISPLAY_SPI_PORT, DISPLAY_SPI_CS, DISPLAY_DC,
    DISPLAY_BACKLIGHT, DISPLAY_ROTATION, DISPLAY_SPI_SPEED_MHZ,
    THUMBNAIL_CACHE_DIR, BASE_DIR,
)

logger = logging.getLogger(__name__)

_st7789 = None
if not MOCK:
    try:
        import st7789
        _st7789 = st7789
    except ImportError:
        logger.warning("st7789 not available, falling back to mock display")


def _get_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


class Display:
    def __init__(self):
        self._lock = threading.Lock()
        self._disp = None
        self._thumb_cache = {}

        if _st7789 and not MOCK:
            self._disp = _st7789.ST7789(
                port=DISPLAY_SPI_PORT,
                cs=DISPLAY_SPI_CS,
                dc=DISPLAY_DC,
                backlight=DISPLAY_BACKLIGHT,
                rotation=DISPLAY_ROTATION,
                spi_speed_hz=DISPLAY_SPI_SPEED_MHZ * 1_000_000,
                width=DISPLAY_WIDTH,
                height=DISPLAY_HEIGHT,
            )
            self._disp.begin()

        self._font_title = _get_font(16)
        self._font_small = _get_font(12)

    def render_player(self, state):
        try:
            self._render_player_inner(state)
        except Exception as e:
            logger.error("Display render error: %s", e, exc_info=True)

    def _render_player_inner(self, state):
        img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        track = state.get("track")
        logger.info("render_player: track=%s, playing=%s", track.get('title') if track else None, state.get('playing'))
        if not track:
            draw.text((DISPLAY_WIDTH // 2 - 50, DISPLAY_HEIGHT // 2 - 10),
                       "No Track", fill=(128, 128, 128), font=self._font_title)
            self._show(img)
            return

        # Thumbnail (top ~170px)
        thumb_url = track.get("thumbnail_url", "")
        thumb_img = self._load_thumbnail(thumb_url)
        if thumb_img:
            tw, th = thumb_img.size
            ratio = max(DISPLAY_WIDTH / tw, 170 / th)
            thumb_img = thumb_img.resize((int(tw * ratio), int(th * ratio)), Image.LANCZOS)
            tw, th = thumb_img.size
            left = (tw - DISPLAY_WIDTH) // 2
            top = (th - 170) // 2
            thumb_img = thumb_img.crop((left, top, left + DISPLAY_WIDTH, top + 170))
            img.paste(thumb_img, (0, 0))

        # Title bar (y=170~210)
        title = track.get("title", "Unknown")
        title_text = self._truncate_text(title, self._font_title, DISPLAY_WIDTH - 10)
        draw.rectangle([(0, 170), (DISPLAY_WIDTH, 210)], fill=(20, 20, 20))
        draw.text((5, 174), title_text, fill=(255, 255, 255), font=self._font_title)

        vol = state.get("volume", 0)
        vol_text = f"Vol:{vol}"
        draw.text((DISPLAY_WIDTH - 55, 195), vol_text, fill=(150, 150, 150), font=self._font_small)

        # Progress bar (y=218)
        pos = state.get("position", 0)
        dur = state.get("duration", 0)
        progress = pos / dur if dur > 0 else 0

        bar_y = 218
        bar_h = 6
        draw.rectangle([(10, bar_y), (DISPLAY_WIDTH - 10, bar_y + bar_h)], fill=(60, 60, 60))
        bar_w = int((DISPLAY_WIDTH - 20) * progress)
        if bar_w > 0:
            draw.rectangle([(10, bar_y), (10 + bar_w, bar_y + bar_h)], fill=(0, 200, 100))

        pos_str = self._format_time(pos)
        dur_str = self._format_time(dur)
        draw.text((10, bar_y + bar_h + 2), pos_str, fill=(180, 180, 180), font=self._font_small)
        draw.text((DISPLAY_WIDTH - 50, bar_y + bar_h + 2), dur_str, fill=(180, 180, 180), font=self._font_small)

        if state.get("paused"):
            draw.text((DISPLAY_WIDTH // 2 - 5, bar_y + bar_h + 1), "||", fill=(255, 200, 0), font=self._font_small)
        elif state.get("playing"):
            draw.text((DISPLAY_WIDTH // 2 - 5, bar_y + bar_h + 1), ">", fill=(0, 200, 100), font=self._font_small)

        self._show(img)

    def render_screensaver_frame(self, frame):
        if frame.mode != "RGB":
            frame = frame.convert("RGB")
        frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.LANCZOS)
        self._show(frame)

    def clear(self):
        img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
        self._show(img)

    def _show(self, img):
        with self._lock:
            if self._disp:
                self._disp.display(img)
            else:
                img.save(os.path.join(BASE_DIR, "display_preview.png"))

    def _load_thumbnail(self, url):
        if not url:
            return None
        if url in self._thumb_cache:
            return self._thumb_cache[url].copy()
        try:
            safe_name = url.split("/")[-1].split("?")[0][:50] + ".jpg"
            cache_path = os.path.join(THUMBNAIL_CACHE_DIR, safe_name)
            if os.path.exists(cache_path):
                thumb = Image.open(cache_path)
                self._thumb_cache[url] = thumb
                return thumb.copy()

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            thumb = Image.open(io.BytesIO(resp.content))
            thumb.save(cache_path, "JPEG")
            self._thumb_cache[url] = thumb

            if len(self._thumb_cache) > 50:
                oldest = next(iter(self._thumb_cache))
                del self._thumb_cache[oldest]

            return thumb.copy()
        except Exception as e:
            logger.debug("Thumbnail load error: %s", e)
            return None

    def _truncate_text(self, text, font, max_width):
        if not text:
            return ""
        bbox = font.getbbox(text)
        if bbox[2] <= max_width:
            return text
        while len(text) > 0:
            text = text[:-1]
            bbox = font.getbbox(text + "…")
            if bbox[2] <= max_width:
                return text + "…"
        return ""

    @staticmethod
    def _format_time(seconds):
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
