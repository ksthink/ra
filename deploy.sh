#!/usr/bin/env bash
# 라즈베리파이 배포 스크립트
set -euo pipefail

PI_HOST="${PI_HOST:-radio.local}"
PI_USER="${PI_USER:-radio}"
PI_PATH="${PI_PATH:-/home/$PI_USER/radio}"

echo ">>> $PI_USER@$PI_HOST:$PI_PATH 로 배포 중..."

rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'data' \
  --exclude '.env' \
  --exclude 'display_preview.png' \
  --exclude '.DS_Store' \
  ./ "$PI_USER@$PI_HOST:$PI_PATH/"

echo ">>> 서비스 재시작..."
ssh "$PI_USER@$PI_HOST" "sudo systemctl restart radio"

echo ">>> 배포 완료!"
