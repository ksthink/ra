import threading
import time
import logging
import os

from PIL import Image

from config import MOCK, SCREENSAVER_GIF_PATH, DISPLAY_WIDTH, DISPLAY_HEIGHT
import playlist_manager

logger = logging.getLogger(__name__)


class Screensaver:
    def __init__(self, display):
        self._display = display
        self._lock = threading.Lock()
        self._active = False
        self._last_activity = time.time()
        self._thread = None
        self._running = False
        self._gif_frames = []
        self._gif_durations = []
        self._on_deactivate = None
        self._preview_until = 0

    @property
    def active(self):
        return self._active

    def start(self):
        self._running = True
        self._last_activity = time.time()
        self._load_gif()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Screensaver monitor started")

    def stop(self):
        self._running = False
        self._active = False

    def reset_timer(self):
        self._last_activity = time.time()
        if self._active:
            self.deactivate()

    def activate(self):
        if self._active:
            return
        if not self._gif_frames:
            return
        self._active = True
        logger.info("Screensaver activated")

    def deactivate(self):
        if not self._active:
            return
        self._active = False
        logger.info("Screensaver deactivated")
        # restore player display
        if self._on_deactivate:
            try:
                self._on_deactivate()
            except Exception as e:
                logger.error("on_deactivate error: %s", e)

    def reload_gif(self):
        self._load_gif()

    def _load_gif(self):
        self._gif_frames = []
        self._gif_durations = []
        if not os.path.exists(SCREENSAVER_GIF_PATH):
            logger.info("No screensaver GIF found")
            return
        try:
            gif = Image.open(SCREENSAVER_GIF_PATH)
            frame_idx = 0
            while True:
                gif.seek(frame_idx)
                frame = gif.copy().convert("RGB")
                frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.LANCZOS)
                self._gif_frames.append(frame)
                duration = gif.info.get("duration", 100)
                self._gif_durations.append(max(duration, 20))
                frame_idx += 1
        except EOFError:
            pass
        except Exception as e:
            logger.error("GIF load error: %s", e)
        logger.info("Loaded %d screensaver frames", len(self._gif_frames))

    def _get_timeout(self):
        try:
            val = int(playlist_manager.get_setting("screensaver_timeout", 10))
            return max(1, min(60, val)) * 60
        except (ValueError, TypeError):
            return 10 * 60

    def _is_enabled(self):
        return playlist_manager.get_setting("screensaver_enabled", "1") == "1"

    def preview(self, duration=10):
        """Immediately show screensaver for duration seconds."""
        if not self._gif_frames:
            self._load_gif()
        if not self._gif_frames:
            logger.warning("Preview requested but no GIF frames")
            return False
        self._preview_until = time.time() + duration
        if not self._active:
            self._active = True
            logger.info("Screensaver preview started (%ds)", duration)
        return True

    def _monitor_loop(self):
        frame_idx = 0
        while self._running:
            # Check preview timeout
            if self._preview_until > 0 and time.time() >= self._preview_until:
                self._preview_until = 0
                self.deactivate()
                continue

            if not self._active:
                if (self._is_enabled()
                        and self._gif_frames
                        and time.time() - self._last_activity >= self._get_timeout()):
                    self.activate()
                else:
                    time.sleep(1)
                    continue

            if not self._gif_frames:
                time.sleep(1)
                continue

            frame_idx = frame_idx % len(self._gif_frames)
            self._display.render_screensaver_frame(self._gif_frames[frame_idx])
            delay = self._gif_durations[frame_idx] / 1000.0
            frame_idx += 1
            time.sleep(delay)
