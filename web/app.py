import os
import logging

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO

from config import WEB_HOST, WEB_PORT, SCREENSAVER_GIF_PATH, SCREENSAVER_MAX_GIF_SIZE
import playlist_manager
import alarm_manager

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.config["SECRET_KEY"] = "radio-secret"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

_player = None
_screensaver = None


def init_web(player, screensaver=None):
    global _player, _screensaver
    _player = player
    _screensaver = screensaver


def broadcast_state(state):
    socketio.emit("state_update", state)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(_player.get_state())


@app.route("/api/play", methods=["POST"])
def api_play():
    _player.play()
    return jsonify({"ok": True})


@app.route("/api/pause", methods=["POST"])
def api_pause():
    _player.pause()
    return jsonify({"ok": True})


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    _player.toggle_play()
    return jsonify({"ok": True})


@app.route("/api/next", methods=["POST"])
def api_next():
    _player.next_track()
    return jsonify({"ok": True})


@app.route("/api/prev", methods=["POST"])
def api_prev():
    _player.prev_track()
    return jsonify({"ok": True})


@app.route("/api/volume", methods=["POST"])
def api_volume():
    data = request.get_json(silent=True) or {}
    if "volume" in data:
        _player.set_volume(int(data["volume"]))
    elif "delta" in data:
        _player.set_volume(_player.state["volume"] + int(data["delta"]))
    return jsonify({"ok": True, "volume": _player.state["volume"]})


@app.route("/api/seek", methods=["POST"])
def api_seek():
    data = request.get_json(silent=True) or {}
    position = float(data.get("position", 0))
    _player.seek(position)
    return jsonify({"ok": True})


@app.route("/api/play_mode", methods=["POST"])
def api_play_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "")
    _player.set_play_mode(mode)
    return jsonify({"ok": True, "play_mode": _player.state["play_mode"]})


@app.route("/api/playlists")
def api_playlists():
    return jsonify(playlist_manager.get_playlists())


@app.route("/api/playlists", methods=["POST"])
def api_add_playlist():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400
    try:
        pl = playlist_manager.add_playlist(url)
        return jsonify(pl)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error("Add playlist error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/playlists/<int:pid>", methods=["DELETE"])
def api_delete_playlist(pid):
    playlist_manager.delete_playlist(pid)
    return jsonify({"ok": True})


@app.route("/api/playlists/<int:pid>/tracks")
def api_tracks(pid):
    return jsonify(playlist_manager.get_tracks(pid))


@app.route("/api/playlists/<int:pid>/load", methods=["POST"])
def api_load_playlist(pid):
    data = request.get_json(silent=True) or {}
    start = int(data.get("start_index", 0))
    _player.load_playlist(pid, start)
    return jsonify({"ok": True})


@app.route("/api/alarms")
def api_alarms():
    return jsonify(alarm_manager.get_alarms())


@app.route("/api/alarms", methods=["POST"])
def api_add_alarm():
    data = request.get_json(silent=True) or {}
    try:
        aid = alarm_manager.add_alarm(
            alarm_time=data.get("time", ""),
            playlist_id=int(data.get("playlist_id", 0)),
            repeat_type=data.get("repeat_type", "daily"),
            repeat_days=data.get("repeat_days", ""),
        )
        return jsonify({"ok": True, "id": aid})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/alarms/<int:aid>", methods=["PUT"])
def api_update_alarm(aid):
    data = request.get_json(silent=True) or {}
    try:
        alarm_manager.update_alarm(aid, **data)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/alarms/<int:aid>", methods=["DELETE"])
def api_delete_alarm(aid):
    alarm_manager.delete_alarm(aid)
    return jsonify({"ok": True})


@app.route("/api/settings")
def api_settings():
    return jsonify(playlist_manager.get_all_settings())


@app.route("/api/settings", methods=["PUT"])
def api_update_settings():
    data = request.get_json(silent=True) or {}
    for k, v in data.items():
        if k == "screensaver_timeout":
            v = str(max(1, min(60, int(v))))
        playlist_manager.set_setting(k, str(v))
    return jsonify(playlist_manager.get_all_settings())


@app.route("/api/screensaver/upload", methods=["POST"])
def api_upload_gif():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    if not f.filename.lower().endswith(".gif"):
        return jsonify({"error": "Only GIF files allowed"}), 400

    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > SCREENSAVER_MAX_GIF_SIZE:
        return jsonify({"error": f"File too large (max {SCREENSAVER_MAX_GIF_SIZE // 1024 // 1024}MB)"}), 400

    f.save(SCREENSAVER_GIF_PATH)
    if _screensaver:
        _screensaver.reload_gif()
    socketio.emit("screensaver_updated")
    return jsonify({"ok": True, "size": size})


@app.route("/api/screensaver/preview")
def api_screensaver_preview():
    if os.path.exists(SCREENSAVER_GIF_PATH):
        return send_file(SCREENSAVER_GIF_PATH, mimetype="image/gif")
    return jsonify({"error": "No GIF uploaded"}), 404


@app.route("/api/screensaver", methods=["DELETE"])
def api_delete_screensaver():
    if os.path.exists(SCREENSAVER_GIF_PATH):
        os.remove(SCREENSAVER_GIF_PATH)
    if _screensaver:
        _screensaver.reload_gif()
    return jsonify({"ok": True})


@app.route("/api/screensaver/test", methods=["POST"])
def api_screensaver_test():
    if not _screensaver:
        return jsonify({"error": "Screensaver not available"}), 500
    data = request.get_json(silent=True) or {}
    duration = min(30, max(3, int(data.get("duration", 10))))
    ok = _screensaver.preview(duration)
    if not ok:
        return jsonify({"error": "GIF가 없습니다"}), 400
    return jsonify({"ok": True, "duration": duration})


@socketio.on("connect")
def on_connect():
    if _player:
        socketio.emit("state_update", _player.get_state())


def run_web():
    socketio.run(app, host=WEB_HOST, port=WEB_PORT, allow_unsafe_werkzeug=True)
