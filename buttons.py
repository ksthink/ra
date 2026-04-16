import threading
import sys
import select
import time
import logging

from config import MOCK, PIN_A, PIN_B, PIN_X, PIN_Y, BUTTON_DEBOUNCE_MS

logger = logging.getLogger(__name__)


class Buttons:
    def __init__(self):
        self._running = False
        self._thread = None

        self.on_volume_up = None    # A
        self.on_prev = None         # B
        self.on_volume_down = None  # X
        self.on_next = None         # Y
        self.on_any = None

    def start(self):
        self._running = True
        if MOCK:
            self._thread = threading.Thread(target=self._mock_input_loop, daemon=True)
            self._thread.start()
            logger.info("Buttons started (mock keyboard: a/b/x/y)")
        else:
            self._setup_gpio()
            logger.info("Buttons started (GPIO)")

    def stop(self):
        self._running = False
        if not MOCK:
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except Exception:
                pass

    def _setup_gpio(self):
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for pin in (PIN_A, PIN_B, PIN_X, PIN_Y):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(PIN_A, GPIO.FALLING,
                              callback=lambda _: self._handle(self.on_volume_up),
                              bouncetime=BUTTON_DEBOUNCE_MS)
        GPIO.add_event_detect(PIN_B, GPIO.FALLING,
                              callback=lambda _: self._handle(self.on_prev),
                              bouncetime=BUTTON_DEBOUNCE_MS)
        GPIO.add_event_detect(PIN_X, GPIO.FALLING,
                              callback=lambda _: self._handle(self.on_volume_down),
                              bouncetime=BUTTON_DEBOUNCE_MS)
        GPIO.add_event_detect(PIN_Y, GPIO.FALLING,
                              callback=lambda _: self._handle(self.on_next),
                              bouncetime=BUTTON_DEBOUNCE_MS)

    def _handle(self, callback):
        if self.on_any:
            try:
                self.on_any()
            except Exception as e:
                logger.error("on_any error: %s", e)
        if callback:
            try:
                callback()
            except Exception as e:
                logger.error("Button callback error: %s", e)

    def _mock_input_loop(self):
        key_map = {
            "a": lambda: self._handle(self.on_volume_up),
            "x": lambda: self._handle(self.on_volume_down),
            "b": lambda: self._handle(self.on_prev),
            "y": lambda: self._handle(self.on_next),
        }
        while self._running:
            try:
                if not sys.stdin.isatty():
                    time.sleep(1)
                    continue
                if select.select([sys.stdin], [], [], 1.0)[0]:
                    line = sys.stdin.readline().strip().lower()
                    if line in key_map:
                        key_map[line]()
                    elif line == "q":
                        break
            except (EOFError, OSError):
                break
            except Exception:
                continue
