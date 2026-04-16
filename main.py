#!/usr/bin/env python3
"""YouTube Playlist Network Radio – 메인 엔트리포인트"""

import signal
import sys

from config import MOCK, WEB_PORT
import playlist_manager
from player import Player
from display import Display
from screensaver import Screensaver
from buttons import Buttons
from alarm_manager import AlarmScheduler, init_alarm_table
from web.app import app, socketio, init_web, broadcast_state


def main():
    playlist_manager.init_db()
    init_alarm_table()

    display = Display()
    player = Player()
    screensaver = Screensaver(display)

    init_web(player)

    def on_state_change(state):
        broadcast_state(state)
        screensaver.notify_activity()

    player.on_state_change = on_state_change

    def on_activity():
        screensaver.notify_activity()

    buttons = Buttons()
    buttons.on_volume_up = lambda: (player.volume_up(), on_activity())
    buttons.on_volume_down = lambda: (player.volume_down(), on_activity())
    buttons.on_next = lambda: (player.next_track(), on_activity())
    buttons.on_prev = lambda: (player.prev_track(), on_activity())
    buttons.on_any = on_activity

    alarm = AlarmScheduler(player)

    # 종료 시그널
    def shutdown(sig, frame):
        print("\n[main] 종료 중...")
        screensaver.stop()
        buttons.stop()
        alarm.stop()
        player.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 백그라운드 스레드 시작
    screensaver.start()
    buttons.start()
    alarm.start()

    mode = "MOCK" if MOCK else "HARDWARE"
    print(f"[main] 라디오 시작 ({mode}) – http://0.0.0.0:{WEB_PORT}")

    socketio.run(app, host='0.0.0.0', port=WEB_PORT, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
