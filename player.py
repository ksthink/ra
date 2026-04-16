import subprocess
import json
import socket
import sys
import threading
import time
import logging
import os
import platform

from config import MPV_SOCKET, MOCK, MOCK_AUDIO, VOLUME_DEFAULT, VOLUME_STEP, VOLUME_MIN, VOLUME_MAX
import playlist_manager

logger = logging.getLogger(__name__)

_is_mac = platform.system() == "Darwin"
_venv_bin = os.path.dirname(sys.executable)
_ytdlp = os.path.join(_venv_bin, "yt-dlp") if os.path.exists(os.path.join(_venv_bin, "yt-dlp")) else "yt-dlp"


class Player:
    def __init__(self):
        self._lock = threading.Lock()
        self._mpv_proc = None
        self._running = False
        self._poll_thread = None
        self._use_mpv = not MOCK_AUDIO  # MOCK_AUDIO=False → mpv 사용

        # State
        self.state = {
            "playing": False,
            "paused": False,
            "volume": int(playlist_manager.get_setting("volume", VOLUME_DEFAULT)),
            "position": 0.0,
            "duration": 0.0,
            "track": None,
            "track_index": -1,
            "playlist_id": None,
            "playlist_name": "",
            "tracks": [],
        }

        self.on_state_change = None

    def start(self):
        self._running = True
        if self._use_mpv:
            self._start_mpv()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Player started (mock_audio=%s, use_mpv=%s)", MOCK_AUDIO, self._use_mpv)

    def stop(self):
        self._running = False
        if self._mpv_proc:
            try:
                self._mpv_cmd("quit")
            except Exception:
                pass
            self._mpv_proc.terminate()
            self._mpv_proc = None
        if os.path.exists(MPV_SOCKET):
            os.unlink(MPV_SOCKET)

    def _start_mpv(self):
        if os.path.exists(MPV_SOCKET):
            os.unlink(MPV_SOCKET)
        cmd = [
            "mpv",
            "--idle=yes",
            "--no-video",
            "--no-terminal",
            f"--input-ipc-server={MPV_SOCKET}",
            f"--volume={self.state['volume']}",
            "--network-timeout=30",
            "--demuxer-max-bytes=50MiB",
            "--log-file=/tmp/mpv-radio.log",
        ]
        if not _is_mac:
            cmd.append("--audio-device=alsa/default")
        self._mpv_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        for _ in range(30):
            if os.path.exists(MPV_SOCKET):
                break
            time.sleep(0.1)

    def _mpv_cmd(self, *args):
        if not self._use_mpv:
            return None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(MPV_SOCKET)
            cmd = json.dumps({"command": list(args)}) + "\n"
            sock.sendall(cmd.encode())
            data = sock.recv(8192)
            sock.close()
            resp = json.loads(data.decode().strip().split("\n")[0])
            if resp.get("error") and resp["error"] != "success":
                logger.warning("mpv cmd %s error: %s", args[0] if args else '?', resp["error"])
            return resp
        except Exception as e:
            logger.error("mpv IPC error (%s): %s", args[0] if args else '?', e)
            return None

    def _mpv_get_property(self, prop):
        result = self._mpv_cmd("get_property", prop)
        if result and "data" in result:
            return result["data"]
        return None

    def _poll_loop(self):
        while self._running:
            time.sleep(1)
            if not self.state["playing"]:
                continue

            if not self._use_mpv:
                if self.state["playing"] and not self.state["paused"]:
                    self.state["position"] = min(
                        self.state["position"] + 1.0,
                        self.state["duration"] or 999,
                    )
                    if self.state["duration"] > 0 and self.state["position"] >= self.state["duration"]:
                        self._on_track_end()
                    self._notify()
                continue

            pos = self._mpv_get_property("time-pos")
            dur = self._mpv_get_property("duration")
            idle = self._mpv_get_property("core-idle")

            if pos is not None:
                self.state["position"] = round(pos, 1)
            if dur is not None:
                self.state["duration"] = round(dur, 1)

            if idle and self.state["playing"] and not self.state["paused"]:
                eof = self._mpv_get_property("eof-reached")
                if eof:
                    self._on_track_end()

            self._notify()

    def _on_track_end(self):
        self.next_track()

    def _notify(self):
        if self.on_state_change:
            try:
                self.on_state_change(self.get_state())
            except Exception as e:
                logger.error("State change callback error: %s", e)

    def get_state(self):
        return dict(self.state)

    def load_playlist(self, playlist_id, start_index=0):
        pl = playlist_manager.get_playlist(playlist_id)
        if not pl:
            logger.error("Playlist %s not found", playlist_id)
            return
        tracks = playlist_manager.get_tracks(playlist_id)
        if not tracks:
            logger.error("Playlist %s has no tracks", playlist_id)
            return

        self.state["playlist_id"] = playlist_id
        self.state["playlist_name"] = pl["name"]
        self.state["tracks"] = tracks
        self.state["track_index"] = start_index
        self._play_current()

    def _play_current(self):
        idx = self.state["track_index"]
        tracks = self.state["tracks"]
        if not tracks or idx < 0 or idx >= len(tracks):
            self.state["playing"] = False
            self._notify()
            return

        track = tracks[idx]
        self.state["track"] = track
        self.state["position"] = 0.0
        self.state["duration"] = float(track.get("duration", 0))
        self.state["playing"] = True
        self.state["paused"] = False

        threading.Thread(target=self._resolve_and_play, args=(track["video_id"],), daemon=True).start()

    def _resolve_and_play(self, video_id):
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            cmd = [
                _ytdlp,
                "-f", "bestaudio[ext=m4a]/bestaudio/best",
                "--get-url",
                "--no-warnings",
                "--no-check-certificates",
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error("yt-dlp resolve failed for %s: %s", video_id, result.stderr[:200])
                self._on_track_end()
                return

            audio_url = result.stdout.strip().split("\n")[0]
            if not audio_url:
                logger.error("yt-dlp returned empty URL for %s", video_id)
                self._on_track_end()
                return

            logger.info("Resolved %s -> URL length %d", video_id, len(audio_url))

            if not self._use_mpv:
                logger.info("MOCK play: %s", self.state["track"]["title"])
                if self.state["duration"] == 0:
                    self.state["duration"] = 180.0
                self._notify()
                return

            resp = self._mpv_cmd("loadfile", audio_url, "replace")
            logger.info("mpv loadfile response: %s", resp)
            self._notify()

        except Exception as e:
            logger.error("Resolve error for %s: %s", video_id, e)
            self._on_track_end()

    def play(self):
        if self.state["paused"]:
            self.state["paused"] = False
            if self._use_mpv:
                self._mpv_cmd("set_property", "pause", False)
            self._notify()
        elif not self.state["playing"] and self.state["tracks"]:
            self._play_current()

    def pause(self):
        if self.state["playing"] and not self.state["paused"]:
            self.state["paused"] = True
            if self._use_mpv:
                self._mpv_cmd("set_property", "pause", True)
            self._notify()

    def toggle_play(self):
        if self.state["paused"]:
            self.play()
        elif self.state["playing"]:
            self.pause()
        elif self.state["tracks"]:
            self._play_current()

    def next_track(self):
        if not self.state["tracks"]:
            return
        idx = self.state["track_index"] + 1
        if idx >= len(self.state["tracks"]):
            idx = 0
        self.state["track_index"] = idx
        self._play_current()

    def prev_track(self):
        if not self.state["tracks"]:
            return
        if self.state["position"] > 3.0:
            self.state["position"] = 0.0
            if self._use_mpv:
                self._mpv_cmd("seek", 0, "absolute")
            self._notify()
            return
        idx = self.state["track_index"] - 1
        if idx < 0:
            idx = len(self.state["tracks"]) - 1
        self.state["track_index"] = idx
        self._play_current()

    def set_volume(self, vol):
        vol = max(VOLUME_MIN, min(VOLUME_MAX, int(vol)))
        self.state["volume"] = vol
        playlist_manager.set_setting("volume", vol)
        if self._use_mpv:
            self._mpv_cmd("set_property", "volume", vol)
        self._notify()

    def volume_up(self):
        self.set_volume(self.state["volume"] + VOLUME_STEP)

    def volume_down(self):
        self.set_volume(self.state["volume"] - VOLUME_STEP)

    def seek(self, position):
        position = max(0, min(float(position), self.state["duration"]))
        self.state["position"] = position
        if self._use_mpv:
            self._mpv_cmd("seek", position, "absolute")
        self._notify()
