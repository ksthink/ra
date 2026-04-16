(function() {
  'use strict';

  const socket = io();
  let currentState = {};
  let playlists = [];
  let seeking = false;

  // ===== Tabs =====
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'playlists') loadPlaylists();
      if (btn.dataset.tab === 'settings') { loadAlarms(); loadSettings(); loadScreensaverPreview(); }
    });
  });

  // ===== Utility =====
  function fmt(sec) {
    sec = Math.floor(sec || 0);
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ':' + String(s).padStart(2, '0');
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    return res.json();
  }

  function postJson(url, body) {
    return api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }

  function putJson(url, body) {
    return api(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }

  function del(url) {
    return api(url, { method: 'DELETE' });
  }

  function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  // ===== Player State =====
  const modeIcons = { sequential: '🔁', single: '🔂', repeat_one: '🔂¹' };
  const modeLabels = { sequential: '연속 재생', single: '한곡 재생', repeat_one: '한곡 반복' };
  const modeOrder = ['sequential', 'single', 'repeat_one'];

  function updateUI(state) {
    currentState = state;
    const thumb = document.getElementById('player-thumb');
    const noTrack = document.getElementById('no-track');
    const title = document.getElementById('player-title');
    const pos = document.getElementById('player-pos');
    const dur = document.getElementById('player-dur');
    const seekBar = document.getElementById('player-seek');
    const toggleBtn = document.getElementById('btn-toggle');
    const volBar = document.getElementById('player-vol');
    const volLabel = document.getElementById('vol-label');
    const modeBtn = document.getElementById('btn-mode');

    if (state.track) {
      thumb.src = state.track.thumbnail_url || '';
      thumb.style.display = state.track.thumbnail_url ? 'block' : 'none';
      noTrack.style.display = state.track.thumbnail_url ? 'none' : 'flex';
      title.textContent = state.track.title || '';
    } else {
      thumb.style.display = 'none';
      noTrack.style.display = 'flex';
      title.textContent = '';
    }

    pos.textContent = fmt(state.position);
    dur.textContent = fmt(state.duration);
    if (!seeking) {
      seekBar.max = state.duration || 100;
      seekBar.value = state.position || 0;
    }

    toggleBtn.textContent = (state.playing && !state.paused) ? '⏸' : '▶';
    volBar.value = state.volume || 0;
    volLabel.textContent = state.volume || 0;

    const mode = state.play_mode || 'sequential';
    modeBtn.textContent = modeIcons[mode] || '🔁';
    modeBtn.title = modeLabels[mode] || '연속 재생';

    renderTracklist(state.tracks || [], state.track_index);
  }

  function renderTracklist(tracks, activeIdx) {
    const ul = document.getElementById('tracklist');
    ul.innerHTML = '';
    tracks.forEach((t, i) => {
      const li = document.createElement('li');
      li.className = i === activeIdx ? 'active' : '';
      li.innerHTML = `<span class="track-idx">${i + 1}</span><span>${escHtml(t.title)}</span><span class="track-dur">${fmt(t.duration)}</span>`;
      li.addEventListener('click', () => {
        if (currentState.playlist_id) postJson(`/api/playlists/${currentState.playlist_id}/load`, { start_index: i });
      });
      ul.appendChild(li);
    });
  }

  socket.on('state_update', updateUI);
  api('/api/state').then(updateUI);

  // ===== Player Controls =====
  document.getElementById('btn-toggle').addEventListener('click', () => postJson('/api/toggle'));
  document.getElementById('btn-next').addEventListener('click', () => postJson('/api/next'));
  document.getElementById('btn-prev').addEventListener('click', () => postJson('/api/prev'));
  document.getElementById('btn-mode').addEventListener('click', () => {
    const cur = currentState.play_mode || 'sequential';
    const idx = modeOrder.indexOf(cur);
    const next = modeOrder[(idx + 1) % modeOrder.length];
    postJson('/api/play_mode', { mode: next });
  });

  const seekBar = document.getElementById('player-seek');
  seekBar.addEventListener('mousedown', () => seeking = true);
  seekBar.addEventListener('touchstart', () => seeking = true);
  seekBar.addEventListener('change', () => { seeking = false; postJson('/api/seek', { position: parseFloat(seekBar.value) }); });

  const volBar = document.getElementById('player-vol');
  volBar.addEventListener('input', () => { document.getElementById('vol-label').textContent = volBar.value; });
  volBar.addEventListener('change', () => { postJson('/api/volume', { volume: parseInt(volBar.value) }); });

  // ===== Playlists Tab =====
  async function loadPlaylists() {
    playlists = await api('/api/playlists');
    renderPlaylists();
  }

  function renderPlaylists() {
    const ul = document.getElementById('pl-list');
    ul.innerHTML = '';
    playlists.forEach(pl => {
      const li = document.createElement('li');
      li.className = 'pl-item';
      li.innerHTML = `
        <img class="pl-item-thumb" src="${escHtml(pl.thumbnail_url || '')}" alt="" onerror="this.style.display='none'">
        <div class="pl-item-info">
          <div class="pl-item-name">${escHtml(pl.name)}</div>
          <div class="pl-item-meta">${pl.track_count || 0}곡</div>
        </div>
        <div class="pl-item-actions">
          <button class="btn-load">재생</button>
          <button class="btn-del">삭제</button>
        </div>`;
      li.querySelector('.btn-load').addEventListener('click', (e) => {
        e.stopPropagation();
        postJson(`/api/playlists/${pl.id}/load`, {});
        document.querySelector('[data-tab="player"]').click();
      });
      li.querySelector('.btn-del').addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm(`"${pl.name}" 삭제?`)) del(`/api/playlists/${pl.id}`).then(loadPlaylists);
      });
      ul.appendChild(li);
    });
  }

  document.getElementById('btn-add-pl').addEventListener('click', async () => {
    const input = document.getElementById('pl-url');
    const status = document.getElementById('pl-status');
    const url = input.value.trim();
    if (!url) return;

    status.textContent = '플레이리스트 로딩 중...';
    status.className = 'pl-status loading';
    try {
      const res = await postJson('/api/playlists', { url });
      if (res.error) { status.textContent = res.error; status.className = 'pl-status error'; }
      else { status.textContent = `"${res.name}" 추가됨 (${res.track_count}곡)`; status.className = 'pl-status'; input.value = ''; loadPlaylists(); }
    } catch (e) { status.textContent = '오류 발생'; status.className = 'pl-status error'; }
  });

  // ===== Alarms =====
  const repeatLabels = { daily: '매일', once: '한번만', weekdays: '평일', weekends: '주말', custom: '사용자 지정' };
  const dayNames = ['월','화','수','목','금','토','일'];

  async function loadAlarms() {
    const alarms = await api('/api/alarms');
    await ensurePlaylists();
    renderAlarms(alarms);
    populateAlarmPlaylistSelect();
  }

  async function ensurePlaylists() {
    if (!playlists.length) playlists = await api('/api/playlists');
  }

  function renderAlarms(alarms) {
    const container = document.getElementById('alarm-list');
    container.innerHTML = '';
    alarms.forEach(a => {
      const div = document.createElement('div');
      div.className = 'alarm-item';
      let repeatText = repeatLabels[a.repeat_type] || a.repeat_type;
      if (a.repeat_type === 'custom' && a.repeat_days) {
        repeatText = a.repeat_days.split(',').map(d => dayNames[parseInt(d)] || d).join(', ');
      }
      div.innerHTML = `
        <div class="alarm-time">${escHtml(a.time)}</div>
        <div class="alarm-info">
          <div class="alarm-pl">${escHtml(a.playlist_name || '(삭제된 플레이리스트)')}</div>
          <div class="alarm-repeat">${repeatText}</div>
        </div>
        <div class="alarm-actions">
          <label class="toggle"><input type="checkbox" ${a.enabled ? 'checked' : ''}><span class="toggle-slider"></span></label>
          <button class="btn-danger" style="padding:4px 10px;font-size:12px">삭제</button>
        </div>`;
      div.querySelector('input[type=checkbox]').addEventListener('change', (e) => {
        putJson(`/api/alarms/${a.id}`, { enabled: e.target.checked ? 1 : 0 });
      });
      div.querySelector('.btn-danger').addEventListener('click', () => { del(`/api/alarms/${a.id}`).then(loadAlarms); });
      container.appendChild(div);
    });
  }

  function populateAlarmPlaylistSelect() {
    const sel = document.getElementById('alarm-playlist');
    sel.innerHTML = '';
    playlists.forEach(pl => {
      const opt = document.createElement('option');
      opt.value = pl.id;
      opt.textContent = pl.name;
      sel.appendChild(opt);
    });
  }

  document.getElementById('btn-add-alarm').addEventListener('click', () => {
    document.getElementById('alarm-form').style.display = 'block';
    document.getElementById('btn-add-alarm').style.display = 'none';
  });
  document.getElementById('btn-cancel-alarm').addEventListener('click', () => {
    document.getElementById('alarm-form').style.display = 'none';
    document.getElementById('btn-add-alarm').style.display = 'block';
  });
  document.getElementById('alarm-repeat').addEventListener('change', (e) => {
    document.getElementById('alarm-days-row').style.display = e.target.value === 'custom' ? 'flex' : 'none';
  });
  document.getElementById('btn-save-alarm').addEventListener('click', async () => {
    const time = document.getElementById('alarm-time').value;
    const playlistId = document.getElementById('alarm-playlist').value;
    const repeatType = document.getElementById('alarm-repeat').value;
    let repeatDays = '';
    if (repeatType === 'custom') {
      repeatDays = Array.from(document.querySelectorAll('#alarm-days-row input:checked')).map(cb => cb.value).join(',');
    }
    if (!time || !playlistId) return alert('시간과 플레이리스트를 선택하세요');
    const res = await postJson('/api/alarms', { time, playlist_id: parseInt(playlistId), repeat_type: repeatType, repeat_days: repeatDays });
    if (res.error) return alert(res.error);
    document.getElementById('alarm-form').style.display = 'none';
    document.getElementById('btn-add-alarm').style.display = 'block';
    loadAlarms();
  });

  // ===== Screensaver Settings =====
  async function loadSettings() {
    const settings = await api('/api/settings');
    const timeout = parseInt(settings.screensaver_timeout || 10);
    document.getElementById('ss-timeout').value = timeout;
    document.getElementById('ss-timeout-label').textContent = timeout;
    document.getElementById('ss-enabled').checked = settings.screensaver_enabled === '1';
  }

  function loadScreensaverPreview() {
    const img = document.getElementById('ss-preview');
    const noGif = document.getElementById('ss-no-gif');
    img.src = '/api/screensaver/preview?' + Date.now();
    img.onload = () => { img.style.display = 'block'; noGif.style.display = 'none'; };
    img.onerror = () => { img.style.display = 'none'; noGif.style.display = 'flex'; };
  }

  document.getElementById('ss-timeout').addEventListener('input', (e) => {
    document.getElementById('ss-timeout-label').textContent = e.target.value;
  });
  document.getElementById('ss-timeout').addEventListener('change', (e) => {
    putJson('/api/settings', { screensaver_timeout: parseInt(e.target.value) });
  });
  document.getElementById('ss-enabled').addEventListener('change', (e) => {
    putJson('/api/settings', { screensaver_enabled: e.target.checked ? '1' : '0' });
  });

  document.getElementById('btn-upload-gif').addEventListener('click', async () => {
    const fileInput = document.getElementById('ss-file');
    if (!fileInput.files.length) return alert('GIF 파일을 선택하세요');
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    const res = await fetch('/api/screensaver/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) return alert(data.error);
    fileInput.value = '';
    loadScreensaverPreview();
  });

  document.getElementById('btn-delete-gif').addEventListener('click', async () => {
    if (!confirm('화면보호기 GIF를 삭제하시겠습니까?')) return;
    await del('/api/screensaver');
    loadScreensaverPreview();
  });

  document.getElementById('btn-test-ss').addEventListener('click', async () => {
    const res = await postJson('/api/screensaver/test', { duration: 10 });
    if (res.error) alert(res.error);
  });

})();
