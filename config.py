import os

# --- Environment ---
MOCK = os.environ.get("RADIO_MOCK", "0") == "1"
# RADIO_MOCK_AUDIO=0 → MOCK 모드에서도 mpv로 실제 오디오 재생
MOCK_AUDIO = os.environ.get("RADIO_MOCK_AUDIO", "1" if MOCK else "0") == "1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "radio.db")
SCREENSAVER_GIF_PATH = os.path.join(DATA_DIR, "screensaver.gif")
THUMBNAIL_CACHE_DIR = os.path.join(DATA_DIR, "thumbnails")

# --- GPIO (BCM) ---
PIN_A = 5   # 상단 좌측 - 볼륨 업
PIN_B = 6   # 하단 좌측 - 이전곡
PIN_X = 16  # 상단 우측 - 볼륨 다운
PIN_Y = 24  # 하단 우측 - 다음곡

BUTTON_DEBOUNCE_MS = 300

# --- Display ---
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240
DISPLAY_SPI_PORT = 0
DISPLAY_SPI_CS = 1
DISPLAY_DC = 9
DISPLAY_BACKLIGHT = 13
DISPLAY_ROTATION = 90
DISPLAY_SPI_SPEED_MHZ = 80

# --- Audio ---
VOLUME_DEFAULT = 70
VOLUME_STEP = 5
VOLUME_MIN = 0
VOLUME_MAX = 100

# --- Web Server ---
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

# --- MPV ---
MPV_SOCKET = "/tmp/mpv-radio.sock"

# --- Screensaver ---
SCREENSAVER_TIMEOUT_DEFAULT = 10  # minutes
SCREENSAVER_MAX_GIF_SIZE = 2 * 1024 * 1024  # 2MB

# --- Alarm ---
ALARM_MAX_COUNT = 5
ALARM_CHECK_INTERVAL = 30  # seconds

# --- Ensure data directories exist ---
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
