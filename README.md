# 🎵 YouTube Playlist Network Radio

Raspberry Pi Zero 2 W + Pirate Audio Small Speaker 기반의 YouTube 플레이리스트 네트워크 라디오.

웹 브라우저에서 YouTube 플레이리스트를 등록하면, 라즈베리파이가 음악을 스트리밍 재생하고 240×240 LCD에 앨범아트를 표시합니다.

---

## 하드웨어

| 부품 | 설명 |
|------|------|
| Raspberry Pi Zero 2 W | 메인 보드 |
| [Pirate Audio: Small Speaker](https://shop.pimoroni.com/products/pirate-audio-small-speaker) | I2S DAC + 모노 스피커 + ST7789 240×240 LCD + 4 버튼 |

### 버튼 매핑 (BCM)

| 핀 | 위치 | 기능 |
|----|------|------|
| GPIO 5 | 상단 좌측 (A) | 볼륨 업 |
| GPIO 16 | 상단 우측 (X) | 볼륨 다운 |
| GPIO 6 | 하단 좌측 (B) | 이전곡 |
| GPIO 24 | 하단 우측 (Y) | 다음곡 |

---

## 주요 기능

### 🎶 재생
- YouTube 플레이리스트 URL로 곡 목록 자동 불러오기 (`yt-dlp`)
- `mpv` IPC 소켓을 통한 오디오 스트리밍 재생
- 재생 모드: 연속 재생(`sequential`), 한곡 재생(`single`), 한곡 반복(`repeat_one`)
- 재생/일시정지, 이전곡/다음곡, 볼륨 조절
- 실시간 재생 상태 동기화 (WebSocket)

### 🖥 LCD 디스플레이
- 현재 재생 중인 곡의 썸네일 표시 (240×240)
- 곡 제목 한글 표시 (나눔고딕)
- 재생 상태 아이콘

### 🖼 화면보호기
- 사용자 GIF 업로드 (최대 2MB)
- 물리 버튼 미조작 시 설정 시간(1~60분) 후 자동 활성화
- 아무 버튼이나 누르면 해제되고 재생 화면으로 복귀
- 웹 UI에서 미리보기 기능

### ⏰ 알람
- 최대 5개 알람 설정
- 반복 유형: 매일, 한번만, 평일, 주말, 사용자 지정 요일
- 알람 시간에 지정한 플레이리스트 자동 재생
- 활성화/비활성화 토글

### 🌐 웹 UI
- 모바일 최적화 반응형 인터페이스
- 3개 탭: **재생** / **플레이리스트** / **설정**
- Socket.IO 실시간 상태 동기화
- `http://<라즈베리파이IP>:8080`

---

## 프로젝트 구조

```
ra/
├── main.py                 # 엔트리포인트 – 모든 컴포넌트 연결
├── config.py               # 설정 상수 (GPIO, 디스플레이, 경로 등)
├── player.py               # mpv IPC 기반 오디오 플레이어
├── display.py              # ST7789 LCD 렌더링 (Pillow)
├── buttons.py              # 물리 버튼 입력 (gpiozero)
├── screensaver.py          # GIF 화면보호기
├── alarm_manager.py        # 알람 스케줄러 + CRUD
├── playlist_manager.py     # 플레이리스트/트랙 DB 관리 (SQLite)
├── requirements.txt        # Python 패키지 의존성
├── install.sh              # 라즈베리파이 초기 설치 스크립트
├── deploy.sh               # 개발 PC → 라즈베리파이 배포 스크립트
├── .env.example            # 환경 변수 예시
├── .gitignore
├── service/
│   └── radio.service       # systemd 서비스 파일
├── web/
│   ├── app.py              # Flask + Socket.IO 웹 서버
│   ├── templates/
│   │   └── index.html      # 웹 UI (SPA)
│   └── static/
│       ├── app.js          # 프론트엔드 JavaScript
│       └── style.css       # 스타일시트
└── data/                   # (런타임 생성, git 제외)
    ├── radio.db            # SQLite 데이터베이스
    ├── thumbnails/         # 썸네일 캐시
    └── screensaver.gif     # 업로드된 GIF
```

---

## 설치

### 1. 라즈베리파이 초기 설정

```bash
# 프로젝트 클론
git clone https://github.com/ksthink/ra.git ~/radio
cd ~/radio

# 설치 스크립트 실행
bash install.sh
```

`install.sh`가 수행하는 작업:
- 시스템 패키지 설치 (`mpv`, `fonts-nanum`, `libtiff6` 등)
- Python 가상환경(`.venv`) 생성 및 패키지 설치
- SPI, HifiBerry DAC I2S 오버레이 설정 (`/boot/config.txt`)
- Pirate Audio 라이브러리 설치 (`st7789`, `gpiozero`, `lgpio`, `spidev`)
- systemd 서비스 등록 및 활성화

```bash
# 설치 후 재부팅 필요 (I2S 오버레이 적용)
sudo reboot
```

### 2. 서비스 시작

```bash
sudo systemctl start radio
```

### 3. 접속

브라우저에서 `http://<라즈베리파이IP>:8080` 접속

---

## 개발 (Mac)

Mac에서 LCD/GPIO 없이 개발할 수 있습니다.

### 환경 설정

```bash
cd ra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env 파일 생성
cp .env.example .env
```

### 실행 모드

```bash
# Mock 모드 (LCD/GPIO/mpv 모두 비활성)
RADIO_MOCK=1 python3 main.py

# Mock + 실제 오디오 (Mac 스피커로 재생)
RADIO_MOCK=1 RADIO_MOCK_AUDIO=0 python3 main.py
```

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `RADIO_MOCK` | `0` | `1`: LCD, GPIO를 Mock으로 대체 |
| `RADIO_MOCK_AUDIO` | MOCK일 때 `1` | `0`: Mock 모드에서도 mpv로 실제 오디오 재생 |

### 배포

개발 PC에서 라즈베리파이로 코드를 배포합니다.

```bash
# .env에서 PI_HOST, PI_USER, PI_PATH 설정 후
bash deploy.sh
```

`deploy.sh`는 `rsync`로 파일을 동기화한 뒤 `systemctl restart radio`를 실행합니다.  
`.venv`, `data/`, `.env`는 배포에서 제외됩니다.

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3 |
| 웹 프레임워크 | Flask + Flask-SocketIO |
| 오디오 | mpv (IPC 소켓 제어) |
| 음원 추출 | yt-dlp |
| 디스플레이 | ST7789 SPI LCD + Pillow |
| 버튼 | gpiozero (lgpio backend) |
| 데이터베이스 | SQLite (WAL 모드) |
| 오디오 DAC | HifiBerry DAC (I2S, ALSA direct) |
| 프론트엔드 | Vanilla JS + Socket.IO |
| 프로세스 관리 | systemd |

---

## API

### 플레이어

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/state` | 현재 재생 상태 |
| POST | `/api/play` | 재생/재개 |
| POST | `/api/pause` | 일시정지 |
| POST | `/api/next` | 다음곡 |
| POST | `/api/prev` | 이전곡 |
| POST | `/api/volume` | 볼륨 설정 `{ "volume": 70 }` |
| POST | `/api/play_mode` | 재생 모드 `{ "mode": "sequential" }` |
| POST | `/api/load` | 플레이리스트 로드 `{ "playlist_id": 1 }` |

### 플레이리스트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/playlists` | 플레이리스트 목록 |
| POST | `/api/playlists` | 추가 `{ "url": "https://..." }` |
| DELETE | `/api/playlists/<id>` | 삭제 |

### 알람

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/alarms` | 알람 목록 |
| POST | `/api/alarms` | 추가 `{ "time": "07:00", "playlist_id": 1, "repeat_type": "daily" }` |
| PUT | `/api/alarms/<id>` | 수정 |
| DELETE | `/api/alarms/<id>` | 삭제 |

### 화면보호기

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/screensaver/gif` | GIF 파일 조회 |
| POST | `/api/screensaver/gif` | GIF 업로드 (multipart) |
| DELETE | `/api/screensaver/gif` | GIF 삭제 |
| POST | `/api/screensaver/test` | 미리보기 (10초) |

### 설정

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/settings` | 전체 설정 조회 |
| POST | `/api/settings` | 설정 저장 `{ "key": "value" }` |

### WebSocket 이벤트

| 이벤트 | 방향 | 설명 |
|--------|------|------|
| `state` | Server → Client | 재생 상태 실시간 업데이트 |

---

## 로그 확인

```bash
# 실시간 로그
journalctl -u radio -f

# 최근 100줄
journalctl -u radio --no-pager -n 100

# mpv 로그
cat /tmp/mpv-radio.log
```

---

## 라이선스

개인 프로젝트
