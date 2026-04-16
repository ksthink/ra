#!/usr/bin/env bash
# Raspberry Pi 설치 스크립트
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="$(whoami)"

echo "=== YouTube Playlist Radio 설치 ==="
echo "설치 경로: $INSTALL_DIR"
echo "사용자: $USER"

# 시스템 패키지
echo ">>> apt 패키지 설치..."
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  mpv \
  libopenjp2-7 libtiff5 libatlas-base-dev \
  fonts-nanum

# Python 가상환경
echo ">>> Python 가상환경 생성..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Pirate Audio (SPI + I2S) 하드웨어 설정
echo ">>> 하드웨어 오버레이 설정..."
BOOT_CONFIG="/boot/config.txt"
if [[ -f /boot/firmware/config.txt ]]; then
  BOOT_CONFIG="/boot/firmware/config.txt"
fi

grep -q "^dtparam=spi=on" "$BOOT_CONFIG" || echo "dtparam=spi=on" | sudo tee -a "$BOOT_CONFIG"
grep -q "^gpio=25=op,dh" "$BOOT_CONFIG" || echo "gpio=25=op,dh" | sudo tee -a "$BOOT_CONFIG"
grep -q "^dtoverlay=hifiberry-dac" "$BOOT_CONFIG" || echo "dtoverlay=hifiberry-dac" | sudo tee -a "$BOOT_CONFIG"

# Pirate Audio Python 라이브러리 (venv)
"$INSTALL_DIR/.venv/bin/pip" install st7789 RPi.GPIO spidev numpy

# data 디렉토리
mkdir -p "$INSTALL_DIR/data"

# systemd 서비스
echo ">>> systemd 서비스 등록..."
sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" -e "s|__USER__|$USER|g" \
  "$INSTALL_DIR/service/radio.service" | sudo tee /etc/systemd/system/radio.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable radio.service

echo ""
echo "=== 설치 완료 ==="
echo "시작: sudo systemctl start radio"
echo "로그: journalctl -u radio -f"
echo "* 재부팅 필요 (I2S 오버레이 적용)"
