# -*- coding: utf-8 -*-
#
#       browser.py
#
#       Copyright 2026
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
"""
:mod:`pympress.browser` -- Launch and mirror an isolated Chromium window
------------------------------------------------------------------------
"""

import base64
import json
import logging
import os
import pathlib
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk

import websocket

from pympress import extras, util


logger = logging.getLogger(__name__)
_ = util.get_translation('pympress').gettext


class BrowserMirror(object):
    """Manage an isolated Chromium session and mirror its output to the content window."""

    c_win = None
    c_frame = None
    c_da = None
    p_win = None

    chromium_process = None
    websocket_conn = None
    receiver_thread = None
    profile_dir = None
    debug_port = None
    browser_url = None

    frame_pixbuf = None
    frame_aspect_ratio = 16 / 9
    mirror_to_content = False
    browser_running = False

    cursor_pos = None
    cursor_visible = False
    cursor_style = 'default'
    click_feedback = []
    active_drag_points = []
    active_drag_button_kind = 'primary'
    drag_feedback = []
    click_feedback_timeout = 0

    _receiver_running = False
    _command_id = 0
    _command_lock = None
    _pending_commands = None

    BINDING_NAME = 'pympressBrowserEvent'
    MIN_WINDOW_WIDTH = 800
    MIN_WINDOW_HEIGHT = 600
    CLICK_FEEDBACK_TTL = 0.35
    DRAG_FEEDBACK_TTL = CLICK_FEEDBACK_TTL
    ACTIVE_DRAG_TTL = CLICK_FEEDBACK_TTL
    DRAG_POINT_EPSILON = 0.003

    def __init__(self, builder):
        super(BrowserMirror, self).__init__()
        self.ui = builder
        self._command_lock = threading.Lock()
        self._pending_commands = {}
        self.chromium_process = None
        self.websocket_conn = None
        self.receiver_thread = None
        self.profile_dir = None
        self.debug_port = None
        self.browser_url = None
        self.frame_pixbuf = None
        self.frame_aspect_ratio = 16 / 9
        self.mirror_to_content = False
        self.browser_running = False
        self.cursor_pos = None
        self.cursor_visible = False
        self.cursor_style = 'default'
        self.click_feedback = []
        self.active_drag_points = []
        self.active_drag_button_kind = 'primary'
        self.drag_feedback = []
        self.click_feedback_timeout = 0
        self._receiver_running = False
        self._command_id = 0

        builder.load_widgets(self)
        builder.setup_actions({
            'browser-open':   dict(activate=self.show_browser_dialog),
            'browser-stop':   dict(activate=self.stop_browser, enabled=False),
            'browser-mirror': dict(activate=self.toggle_mirror, state=False, enabled=False),
        })


    @staticmethod
    def _normalize_url(url):
        url = url.strip()
        if not url:
            return None
        if '://' not in url:
            return 'http://' + url
        return url


    @staticmethod
    def _allocate_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]


    @staticmethod
    def _get_candidate_binaries():
        candidates = ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'chrome']

        if util.IS_MAC_OS:
            candidates.extend([
                '/Applications/Chromium.app/Contents/MacOS/Chromium',
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            ])
        elif util.IS_WINDOWS:
            for root in filter(None, [
                pathlib.Path.home() / 'AppData' / 'Local' / 'Chromium' / 'Application',
                pathlib.Path.home() / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'Application',
            ]):
                candidates.append(str(root / 'chrome.exe'))

        return candidates


    def _find_chromium(self):
        for candidate in self._get_candidate_binaries():
            path = shutil.which(candidate) if not pathlib.Path(candidate).is_absolute() else candidate
            if path and pathlib.Path(path).exists():
                return str(path)
        return None


    def _get_browser_monitor(self):
        display = Gdk.Display.get_default()
        try:
            c_monitor, p_monitor, primary, non_primary = util.Monitor.lookup_monitors(display, self.c_win, self.p_win)
        except util.NoMonitorPositions:
            x, y = self.p_win.get_position()
            w, h = self.p_win.get_size()
            return util.ScreenArea((x, y, w, h))

        if self.mirror_to_content and not p_monitor.equal(c_monitor):
            return p_monitor
        if not primary.equal(non_primary) and c_monitor.equal(p_monitor):
            return c_monitor.least_intersection([primary, non_primary])
        return p_monitor


    def _target_window_aspect_ratio(self):
        ratio = self.frame_aspect_ratio

        if self.c_frame is not None:
            try:
                frame_ratio = float(self.c_frame.get_property('ratio'))
            except (TypeError, ValueError):
                frame_ratio = 0

            if frame_ratio > 0:
                ratio = frame_ratio

        if ratio <= 0:
            return 16 / 9

        return ratio


    def _compute_window_geometry(self, monitor):
        margin_x = max(40, int(monitor.width * 0.04))
        margin_y = max(40, int(monitor.height * 0.04))
        max_width = max(self.MIN_WINDOW_WIDTH, int(monitor.width - 2 * margin_x))
        max_height = max(self.MIN_WINDOW_HEIGHT, int(monitor.height - 2 * margin_y))
        aspect_ratio = self._target_window_aspect_ratio()

        window_width = min(max_width, int(max_height * aspect_ratio))
        window_height = int(window_width / aspect_ratio) if aspect_ratio else max_height

        if window_height > max_height:
            window_height = max_height
            window_width = int(window_height * aspect_ratio)

        window_width = max(self.MIN_WINDOW_WIDTH, min(window_width, int(monitor.width)))
        window_height = max(self.MIN_WINDOW_HEIGHT, min(window_height, int(monitor.height)))

        min_x = int(monitor.x + margin_x)
        max_x = int(monitor.x + monitor.width - margin_x - window_width)
        min_y = int(monitor.y + margin_y)
        max_y = int(monitor.y + monitor.height - margin_y - window_height)

        presenter_x, presenter_y = self.p_win.get_position()
        presenter_width, presenter_height = self.p_win.get_size()

        presenter_span_x = max(1, monitor.width - presenter_width)
        presenter_span_y = max(1, monitor.height - presenter_height)
        browser_span_x = max(0, max_x - min_x)
        browser_span_y = max(0, max_y - min_y)

        presenter_ratio_x = min(max((presenter_x - monitor.x) / presenter_span_x, 0.0), 1.0)
        presenter_ratio_y = min(max((presenter_y - monitor.y) / presenter_span_y, 0.0), 1.0)

        preferred_x = min_x + presenter_ratio_x * browser_span_x
        preferred_y = min_y + presenter_ratio_y * browser_span_y

        window_x = int(min(max(preferred_x, min_x), max_x if max_x >= min_x else min_x))
        window_y = int(min(max(preferred_y, min_y), max_y if max_y >= min_y else min_y))

        return window_x, window_y, window_width, window_height


    def _show_error(self, message, secondary=None):
        dialog = Gtk.MessageDialog(
            transient_for=self.p_win,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            message_format=message,
        )
        if secondary:
            dialog.format_secondary_text(secondary)
        dialog.run()
        dialog.destroy()


    @staticmethod
    def _jupyter_runtime_dirs():
        runtime_dirs = []

        env_dir = GLib.getenv('JUPYTER_RUNTIME_DIR')
        if env_dir:
            runtime_dirs.append(pathlib.Path(env_dir).expanduser())

        if util.IS_MAC_OS:
            runtime_dirs.append(pathlib.Path('~/Library/Jupyter/runtime').expanduser())
        elif util.IS_WINDOWS:
            appdata = GLib.getenv('APPDATA')
            if appdata:
                runtime_dirs.append(pathlib.Path(appdata) / 'jupyter' / 'runtime')
        else:
            runtime_dirs.append(pathlib.Path(GLib.getenv('XDG_RUNTIME_DIR', '~/.local/share')).expanduser() /
                                'jupyter' / 'runtime')
            runtime_dirs.append(pathlib.Path('~/.local/share/jupyter/runtime').expanduser())

        seen = set()
        unique_dirs = []
        for runtime_dir in runtime_dirs:
            key = str(runtime_dir)
            if key not in seen:
                seen.add(key)
                unique_dirs.append(runtime_dir)

        return unique_dirs


    @staticmethod
    def _tokenized_url(url, token):
        if not token:
            return url

        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault('token', token)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


    def _detect_jupyter_url(self):
        candidates = []

        for runtime_dir in self._jupyter_runtime_dirs():
            if not runtime_dir.exists():
                continue

            for pattern in ('jpserver-*.json', 'nbserver-*.json'):
                for server_file in runtime_dir.glob(pattern):
                    try:
                        server_info = json.loads(server_file.read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        logger.debug('Failed reading Jupyter server file %s', server_file, exc_info=True)
                        continue

                    base_url = server_info.get('url')
                    if not base_url:
                        continue

                    token_url = self._tokenized_url(base_url, server_info.get('token'))
                    candidates.append((server_file.stat().st_mtime, token_url))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        detected = candidates[0][1]
        logger.debug('Auto-detected Jupyter URL for browser mode: %s', detected)
        return detected


    def _update_actions(self):
        self.ui.app.set_action_enabled('browser-stop', self.browser_running)
        self.ui.app.set_action_enabled('browser-mirror', self.browser_running)
        self.ui.app.set_action_state('browser-mirror', self.mirror_to_content)


    def show_browser_dialog(self, gaction=None, param=None):
        """Ask for a URL and whether the browser session should be mirrored."""
        detected_jupyter_url = self._detect_jupyter_url()
        dialog = Gtk.Dialog(title=_('Open browser window'), transient_for=self.p_win)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(8)

        label = Gtk.Label(label=_('URL to open in an isolated Chromium window'))
        label.set_halign(Gtk.Align.START)
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        entry.set_text(self.browser_url or detected_jupyter_url or 'http://127.0.0.1:8888')

        mirror_toggle = Gtk.CheckButton.new_with_label(_('Mirror in content window'))
        mirror_toggle.set_active(self.mirror_to_content if self.browser_running else True)

        box.add(label)
        box.add(entry)
        box.add(mirror_toggle)
        dialog.show_all()

        response = dialog.run()
        url = entry.get_text()
        mirror = mirror_toggle.get_active()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            return False

        url = self._normalize_url(url)
        if url is None:
            self._show_error(_('A browser URL is required.'))
            return False

        return self.launch_browser(url, mirror)


    def launch_browser(self, url, mirror=False):
        """Launch Chromium with an isolated profile and begin mirroring via DevTools."""
        chromium = self._find_chromium()
        if chromium is None:
            self._show_error(
                _('Chromium could not be found.'),
                _('Install Chromium or Google Chrome and ensure the executable is available in PATH.'),
            )
            return False

        self.stop_browser()

        self.browser_url = url
        self.mirror_to_content = mirror
        self.debug_port = self._allocate_port()
        self.profile_dir = tempfile.mkdtemp(prefix='pympress-browser-')
        monitor = self._get_browser_monitor()
        window_x, window_y, window_width, window_height = self._compute_window_geometry(monitor)
        allowed_origins = ','.join([
            'http://127.0.0.1:{}'.format(self.debug_port),
            'http://localhost:{}'.format(self.debug_port),
        ])

        args = [
            chromium,
            '--new-window',
            '--user-data-dir=' + self.profile_dir,
            '--remote-debugging-port={}'.format(self.debug_port),
            '--remote-allow-origins={}'.format(allowed_origins),
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-session-crashed-bubble',
            '--disable-features=Translate,AutofillServerCommunication',
            '--window-position={},{}'.format(window_x, window_y),
            '--window-size={},{}'.format(window_width, window_height),
            url,
        ]
        if util.IS_MAC_OS:
            args.append('--use-mock-keychain')
        chromium_env = dict(os.environ)
        chromium_env.setdefault('GOOGLE_API_KEY', 'pympress-browser-mode')

        try:
            self.chromium_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=chromium_env,
            )
            websocket_url = self._wait_for_websocket_url()
            self.websocket_conn = websocket.create_connection(
                websocket_url,
                timeout=5,
                enable_multithread=True,
                origin='http://127.0.0.1:{}'.format(self.debug_port),
            )
            self.websocket_conn.settimeout(None)
        except Exception as e:
            logger.exception('Failed launching Chromium browser mode', exc_info=True)
            self._show_error(_('Failed launching Chromium browser mode.'), str(e))
            self.stop_browser()
            return False

        self.browser_running = True
        self._receiver_running = True
        self.receiver_thread = threading.Thread(target=self._receiver_loop, name='pympress-browser-mirror', daemon=True)
        self.receiver_thread.start()

        try:
            self._send_command('Page.enable')
            self._send_command('Runtime.enable')
            self._send_command('Runtime.addBinding', {'name': self.BINDING_NAME})
            self._send_command('Page.addScriptToEvaluateOnNewDocument', {'source': self._binding_script()})
            self._send_command('Runtime.evaluate', {'expression': self._binding_script()})
            self._send_command('Page.startScreencast', {
                'format': 'png',
                'everyNthFrame': 1,
                'maxWidth': max(self.MIN_WINDOW_WIDTH, int(monitor.width)),
                'maxHeight': max(self.MIN_WINDOW_HEIGHT, int(monitor.height)),
            })
        except Exception as e:
            logger.exception('Failed initializing browser mirror session', exc_info=True)
            self._show_error(_('Failed initializing browser mirror session.'), str(e))
            self.stop_browser()
            return False

        if self.mirror_to_content:
            extras.Cursor.set_cursor(self.c_da, 'invisible')

        self._update_actions()
        self.ui.c_da.queue_draw()
        return True


    def _wait_for_websocket_url(self, timeout=10):
        deadline = time.monotonic() + timeout
        endpoint = 'http://127.0.0.1:{}/json/list'.format(self.debug_port)

        while time.monotonic() < deadline:
            if self.chromium_process is not None and self.chromium_process.poll() is not None:
                raise RuntimeError(_('Chromium exited before the DevTools endpoint became available.'))

            try:
                with urllib.request.urlopen(endpoint, timeout=1) as response:
                    targets = json.loads(response.read().decode('utf-8'))
            except (urllib.error.URLError, ValueError):
                time.sleep(0.2)
                continue

            for target in targets:
                if target.get('type') == 'page' and target.get('webSocketDebuggerUrl'):
                    return target['webSocketDebuggerUrl']

            time.sleep(0.2)

        raise RuntimeError(_('Timed out while waiting for Chromium DevTools.'))


    def _send_command(self, method, params=None, wait=True, timeout=5):
        if self.websocket_conn is None:
            raise RuntimeError(_('Browser mirror is not connected.'))

        payload = {'method': method, 'params': params or {}}
        with self._command_lock:
            self._command_id += 1
            payload['id'] = self._command_id

            if wait:
                event = threading.Event()
                self._pending_commands[payload['id']] = {'event': event, 'response': None}
        try:
            self.websocket_conn.send(json.dumps(payload))
        except Exception:
            if wait:
                with self._command_lock:
                    self._pending_commands.pop(payload['id'], None)
            raise

        if not wait:
            return None

        if not event.wait(timeout):
            with self._command_lock:
                self._pending_commands.pop(payload['id'], None)
            raise RuntimeError(_('Timed out waiting for browser mirror command {}').format(method))

        with self._command_lock:
            response = self._pending_commands.pop(payload['id'])['response']

        if 'error' in response:
            raise RuntimeError(response['error'].get('message', _('Unknown browser error')))

        return response.get('result')


    @classmethod
    def _binding_script(cls):
        return """
(() => {
    if (window.__pympressMirrorInstalled) {
        return;
    }
    window.__pympressMirrorInstalled = true;
    const emit = (payload) => {
        try {
            window.%s(JSON.stringify(payload));
        }
        catch (e) {}
    };

    const isEditable = (target) => {
        if (!target || target.nodeType !== Node.ELEMENT_NODE) {
            return false;
        }
        if (target.isContentEditable) {
            return true;
        }
        const tag = target.tagName;
        if (tag === 'TEXTAREA') {
            return true;
        }
        if (tag !== 'INPUT') {
            return false;
        }
        const type = (target.getAttribute('type') || 'text').toLowerCase();
        return !['button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit'].includes(type);
    };

    const currentCursor = (event) => {
        const target = event && event.target && event.target.nodeType === Node.ELEMENT_NODE ? event.target : document.body;
        const style = target ? window.getComputedStyle(target) : null;
        const cursor = style && style.cursor ? style.cursor : window.getComputedStyle(document.body).cursor;
        if ((!cursor || cursor === 'auto') && isEditable(target)) {
            return 'text';
        }
        return cursor || 'default';
    };

    const sendPointer = (type, event) => emit({
        type,
        x: event.clientX,
        y: event.clientY,
        button: typeof event.button === 'number' ? event.button : -1,
        button_kind: (() => {
            if ((event.buttons || 0) & 2) {
                return 'secondary';
            }
            if ((event.buttons || 0) & 4) {
                return 'auxiliary';
            }
            if (event.ctrlKey && event.button === 0) {
                return 'secondary';
            }
            if (event.button === 2) {
                return 'secondary';
            }
            if (event.button === 1) {
                return 'auxiliary';
            }
            return 'primary';
        })(),
        buttons: event.buttons || 0,
        width: window.innerWidth,
        height: window.innerHeight,
        cursor: currentCursor(event),
        time: Date.now(),
    });

    window.addEventListener('pointermove', event => sendPointer('pointermove', event), true);
    window.addEventListener('pointerenter', event => sendPointer('pointerenter', event), true);
    window.addEventListener('pointerleave', event => sendPointer('pointerleave', event), true);
    window.addEventListener('pointerdown', event => sendPointer('pointerdown', event), true);
    window.addEventListener('pointerup', event => sendPointer('pointerup', event), true);
    window.addEventListener('blur', () => emit({type: 'blur'}), true);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') {
            emit({type: 'hidden'});
        }
    }, true);
})();
        """ % cls.BINDING_NAME


    def _receiver_loop(self):
        try:
            while self._receiver_running and self.websocket_conn is not None:
                raw_message = self.websocket_conn.recv()
                if raw_message is None:
                    break

                message = json.loads(raw_message)
                if 'id' in message:
                    with self._command_lock:
                        pending = self._pending_commands.get(message['id'])
                    if pending is not None:
                        pending['response'] = message
                        pending['event'].set()
                    continue

                method = message.get('method')
                if method == 'Page.screencastFrame':
                    params = message.get('params', {})
                    self._send_command('Page.screencastFrameAck', {'sessionId': params.get('sessionId')}, wait=False)
                    GLib.idle_add(self._apply_frame, base64.b64decode(params.get('data', '')))
                elif method == 'Runtime.bindingCalled':
                    params = message.get('params', {})
                    if params.get('name') == self.BINDING_NAME:
                        GLib.idle_add(self._apply_browser_event, params.get('payload'))
        except Exception:
            if self.browser_running:
                logger.info('Browser mirror receiver loop exited', exc_info=True)
        finally:
            GLib.idle_add(self._browser_closed)


    def _apply_frame(self, png_bytes):
        if not png_bytes:
            return False

        try:
            loader = GdkPixbuf.PixbufLoader.new_with_type('png')
            loader.write(png_bytes)
            loader.close()
            pixbuf = loader.get_pixbuf()
        except GLib.Error:
            logger.debug('Failed decoding browser mirror frame', exc_info=True)
            return False

        if pixbuf is None:
            return False

        self.frame_pixbuf = pixbuf
        if pixbuf.get_height() > 0:
            self.frame_aspect_ratio = pixbuf.get_width() / pixbuf.get_height()

        if self.mirror_to_content:
            self.c_frame.set_property('ratio', self.frame_aspect_ratio)
            self.ui.c_da.queue_draw()
        return False


    def _apply_browser_event(self, payload):
        try:
            event = json.loads(payload)
        except (TypeError, ValueError):
            return False

        width = max(1, int(event.get('width', 1)))
        height = max(1, int(event.get('height', 1)))
        x = min(max(float(event.get('x', 0)) / width, 0.0), 1.0)
        y = min(max(float(event.get('y', 0)) / height, 0.0), 1.0)
        button = int(event.get('button', -1))
        event_type = event.get('type')
        buttons = int(event.get('buttons', 0))
        button_kind = self._infer_button_kind(button, buttons, event.get('button_kind'))
        self.cursor_style = event.get('cursor', self.cursor_style or 'default')

        if event_type in {'pointerleave', 'blur', 'hidden'}:
            self.cursor_visible = False
            self._finish_drag_path()
        else:
            self.cursor_visible = True
            self.cursor_pos = (x, y)

        if event_type == 'pointerdown':
            self.active_drag_points = [(x, y, time.monotonic())]
            self.active_drag_button_kind = button_kind
        elif event_type == 'pointermove' and buttons:
            self.active_drag_button_kind = self._infer_button_kind(button, buttons, self.active_drag_button_kind)
            self._append_drag_point(x, y)
        elif event_type == 'pointerup':
            self._append_drag_point(x, y)
            self._finish_drag_path()

        if event_type in {'pointerdown', 'pointerup'}:
            self.click_feedback.append({'x': x, 'y': y, 'time': time.monotonic(), 'button_kind': button_kind})
            if not self.click_feedback_timeout:
                self.click_feedback_timeout = GLib.timeout_add(16, self._animate_click_feedback)

        if self.mirror_to_content:
            self.ui.c_da.queue_draw()
        return False


    @staticmethod
    def _infer_button_kind(button, buttons, reported_kind=None):
        if buttons & 2:
            return 'secondary'
        elif buttons & 4:
            return 'auxiliary'
        elif buttons & 1:
            return 'primary'
        elif reported_kind in {'primary', 'secondary', 'auxiliary'}:
            return reported_kind
        elif button == 2:
            return 'secondary'
        elif button == 1:
            return 'auxiliary'
        return 'primary'


    def _append_drag_point(self, x, y):
        now = time.monotonic()
        if not self.active_drag_points:
            self.active_drag_points = [(x, y, now)]
            return

        self._prune_active_drag_points(now)

        last_x, last_y, _last_t = self.active_drag_points[-1]
        if abs(last_x - x) < self.DRAG_POINT_EPSILON and abs(last_y - y) < self.DRAG_POINT_EPSILON:
            return

        self.active_drag_points.append((x, y, now))


    def _prune_active_drag_points(self, now=None):
        if not self.active_drag_points:
            return

        now = time.monotonic() if now is None else now
        cutoff = now - self.ACTIVE_DRAG_TTL
        kept_points = []
        previous_point = None

        for point in self.active_drag_points:
            if point[2] < cutoff:
                previous_point = point
                continue

            if previous_point is not None and not kept_points:
                kept_points.append(previous_point)
                previous_point = None

            kept_points.append(point)

        self.active_drag_points = kept_points or self.active_drag_points[-1:]


    def _finish_drag_path(self):
        if len(self.active_drag_points) > 1:
            self.drag_feedback.append({
                'points': [(point_x, point_y) for point_x, point_y, _point_t in self.active_drag_points],
                'button_kind': self.active_drag_button_kind,
                'time': time.monotonic(),
            })
            if not self.click_feedback_timeout:
                self.click_feedback_timeout = GLib.timeout_add(16, self._animate_click_feedback)

        self.active_drag_points = []
        self.active_drag_button_kind = 'primary'


    def _animate_click_feedback(self):
        now = time.monotonic()
        self.click_feedback = [pulse for pulse in self.click_feedback if now - pulse['time'] < self.CLICK_FEEDBACK_TTL]
        self.drag_feedback = [trail for trail in self.drag_feedback if now - trail['time'] < self.DRAG_FEEDBACK_TTL]
        self._prune_active_drag_points(now)
        if self.mirror_to_content:
            self.ui.c_da.queue_draw()

        if self.click_feedback or self.drag_feedback or self.active_drag_points:
            return True

        self.click_feedback_timeout = 0
        return False


    def _browser_closed(self):
        if not self.browser_running and self.chromium_process is None and self.websocket_conn is None:
            return False
        self.stop_browser()
        return False


    def stop_browser(self, gaction=None, param=None):
        """Stop the Chromium session and clear the mirrored content."""
        self.browser_running = False
        self._receiver_running = False

        if self.click_feedback_timeout:
            GLib.Source.remove(self.click_feedback_timeout)
            self.click_feedback_timeout = 0

        ws = self.websocket_conn
        self.websocket_conn = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                logger.debug('Failed closing browser mirror websocket', exc_info=True)

        proc = self.chromium_process
        self.chromium_process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

        if self.profile_dir:
            shutil.rmtree(self.profile_dir, ignore_errors=True)
            self.profile_dir = None

        self.frame_pixbuf = None
        self.cursor_pos = None
        self.cursor_visible = False
        self.cursor_style = 'default'
        self.click_feedback = []
        self.active_drag_points = []
        self.active_drag_button_kind = 'primary'
        self.drag_feedback = []
        self.mirror_to_content = False
        extras.Cursor.set_cursor(self.c_da, 'parent')

        page_type = self.ui.notes_mode.complement()
        self.c_frame.set_property('ratio', self.ui.doc.page(self.ui.current_page).get_aspect_ratio(page_type))
        self._update_actions()
        self.ui.c_da.queue_draw()
        return True


    def toggle_mirror(self, gaction, param=None):
        """Toggle whether the browser session is mirrored in the content window."""
        if not self.browser_running:
            return False

        self.mirror_to_content = not gaction.get_state().get_boolean()
        gaction.change_state(GLib.Variant.new_boolean(self.mirror_to_content))

        if self.mirror_to_content:
            extras.Cursor.set_cursor(self.c_da, 'invisible')
            self.c_frame.set_property('ratio', self.frame_aspect_ratio)
        else:
            extras.Cursor.set_cursor(self.c_da, 'parent')
            page_type = self.ui.notes_mode.complement()
            self.c_frame.set_property('ratio', self.ui.doc.page(self.ui.current_page).get_aspect_ratio(page_type))

        self.ui.c_da.queue_draw()
        return True


    def is_mirroring_content(self):
        """Return whether browser frames should replace the content slide."""
        return self.browser_running and self.mirror_to_content


    def draw_mirror(self, cairo_context, ww, wh):
        """Draw the latest browser frame and synthetic cursor on the content window."""
        if not self.is_mirroring_content():
            return False

        cairo_context.save()
        cairo_context.set_source_rgb(0, 0, 0)
        cairo_context.paint()
        cairo_context.restore()

        if self.frame_pixbuf is not None:
            pixbuf = self.frame_pixbuf
            cairo_context.save()
            cairo_context.scale(ww / pixbuf.get_width(), wh / pixbuf.get_height())
            Gdk.cairo_set_source_pixbuf(cairo_context, pixbuf, 0, 0)
            cairo_context.paint()
            cairo_context.restore()

        self._draw_drag_feedback(cairo_context, ww, wh)
        self._draw_cursor(cairo_context, ww, wh)
        self._draw_click_feedback(cairo_context, ww, wh)
        return True


    @staticmethod
    def draw_cursor_feedback(cairo_context, ww, wh, cursor_pos, cursor_style='default'):
        if cursor_pos is None:
            return

        x = ww * cursor_pos[0]
        y = wh * cursor_pos[1]
        size = max(18, min(36, min(ww, wh) * 0.035))

        if cursor_style in {'ew-resize', 'col-resize', 'e-resize', 'w-resize'}:
            BrowserMirror._draw_resize_cursor(cairo_context, x, y, size, horizontal=True)
            return
        elif cursor_style in {'ns-resize', 'row-resize', 'n-resize', 's-resize'}:
            BrowserMirror._draw_resize_cursor(cairo_context, x, y, size, horizontal=False)
            return
        elif cursor_style in {'text', 'vertical-text'}:
            BrowserMirror._draw_text_cursor(cairo_context, x, y, size, vertical=(cursor_style == 'vertical-text'))
            return
        elif cursor_style == 'pointer':
            BrowserMirror._draw_hand_cursor(cairo_context, x, y, size)
            return

        cairo_context.save()
        cairo_context.translate(x, y)
        cairo_context.move_to(0, 0)
        cairo_context.line_to(size * 0.68, size * 0.86)
        cairo_context.line_to(size * 0.40, size * 0.88)
        cairo_context.line_to(size * 0.54, size * 1.18)
        cairo_context.line_to(size * 0.36, size * 1.26)
        cairo_context.line_to(size * 0.21, size * 0.98)
        cairo_context.line_to(0, size * 1.12)
        cairo_context.close_path()
        cairo_context.set_source_rgba(1, 1, 1, 0.95)
        cairo_context.fill_preserve()
        cairo_context.set_source_rgba(0, 0, 0, 0.95)
        cairo_context.set_line_width(max(1.5, size * 0.08))
        cairo_context.stroke()
        cairo_context.restore()


    def _draw_cursor(self, cairo_context, ww, wh):
        if not self.cursor_visible or self.cursor_pos is None:
            return

        self.draw_cursor_feedback(cairo_context, ww, wh, self.cursor_pos, self.cursor_style)


    @staticmethod
    def _draw_text_cursor(cairo_context, x, y, size, vertical=False):
        height = size * 1.4
        width = max(2.5, size * 0.14)
        cap = size * 0.36

        cairo_context.save()
        cairo_context.translate(x, y)
        if vertical:
            cairo_context.rotate(3.141592653589793 / 2)

        cairo_context.set_line_cap(1)
        cairo_context.set_line_width(width + 2)
        cairo_context.set_source_rgba(0, 0, 0, 0.95)
        cairo_context.move_to(0, -height / 2)
        cairo_context.line_to(0, height / 2)
        cairo_context.move_to(-cap, -height / 2)
        cairo_context.line_to(cap, -height / 2)
        cairo_context.move_to(-cap, height / 2)
        cairo_context.line_to(cap, height / 2)
        cairo_context.stroke()

        cairo_context.set_line_width(width)
        cairo_context.set_source_rgba(1, 1, 1, 0.95)
        cairo_context.move_to(0, -height / 2)
        cairo_context.line_to(0, height / 2)
        cairo_context.move_to(-cap, -height / 2)
        cairo_context.line_to(cap, -height / 2)
        cairo_context.move_to(-cap, height / 2)
        cairo_context.line_to(cap, height / 2)
        cairo_context.stroke()
        cairo_context.restore()


    @staticmethod
    def _draw_hand_cursor(cairo_context, x, y, size):
        palm_w = size * 0.52
        palm_h = size * 0.48
        finger_w = size * 0.10
        finger_h = size * 0.54
        gap = size * 0.04

        cairo_context.save()
        cairo_context.translate(x - palm_w * 0.15, y + size * 0.08)
        cairo_context.move_to(0, 0)
        cairo_context.line_to(0, -finger_h)
        cairo_context.line_to(finger_w, -finger_h)
        cairo_context.line_to(finger_w, -palm_h * 0.3)
        cairo_context.line_to(finger_w * 2 + gap, -palm_h * 0.72)
        cairo_context.line_to(finger_w * 3 + gap, -palm_h * 0.72)
        cairo_context.line_to(finger_w * 3 + gap, -palm_h * 0.18)
        cairo_context.line_to(finger_w * 4 + gap * 2, -palm_h * 0.6)
        cairo_context.line_to(finger_w * 5 + gap * 2, -palm_h * 0.6)
        cairo_context.line_to(finger_w * 5 + gap * 2, palm_h * 0.35)
        cairo_context.line_to(finger_w * 3.1, palm_h)
        cairo_context.line_to(finger_w * 1.1, palm_h)
        cairo_context.line_to(-palm_w * 0.28, palm_h * 0.28)
        cairo_context.close_path()
        cairo_context.set_source_rgba(1, 1, 1, 0.95)
        cairo_context.fill_preserve()
        cairo_context.set_line_width(max(1.5, size * 0.08))
        cairo_context.set_source_rgba(0, 0, 0, 0.95)
        cairo_context.stroke()
        cairo_context.restore()


    @staticmethod
    def _draw_resize_cursor(cairo_context, x, y, size, horizontal):
        half = size * 0.75
        head = size * 0.35
        shaft = max(2, size * 0.16)

        cairo_context.save()
        cairo_context.translate(x, y)
        if not horizontal:
            cairo_context.rotate(3.141592653589793 / 2)

        cairo_context.set_line_cap(1)
        cairo_context.set_line_join(1)
        cairo_context.set_line_width(shaft + 2)
        cairo_context.set_source_rgba(0, 0, 0, 0.95)
        cairo_context.move_to(-half, 0)
        cairo_context.line_to(half, 0)
        cairo_context.stroke()

        cairo_context.set_line_width(shaft)
        cairo_context.set_source_rgba(1, 1, 1, 0.95)
        cairo_context.move_to(-half, 0)
        cairo_context.line_to(half, 0)
        cairo_context.stroke()

        for direction in (-1, 1):
            cairo_context.move_to(direction * half, 0)
            cairo_context.line_to(direction * (half - head), -head)
            cairo_context.line_to(direction * (half - head), head)
            cairo_context.close_path()
            cairo_context.set_source_rgba(1, 1, 1, 0.95)
            cairo_context.fill_preserve()
            cairo_context.set_line_width(max(1.5, size * 0.08))
            cairo_context.set_source_rgba(0, 0, 0, 0.95)
            cairo_context.stroke()

        cairo_context.restore()


    def _draw_click_feedback(self, cairo_context, ww, wh):
        self.draw_click_feedback_items(cairo_context, ww, wh, self.click_feedback, self.CLICK_FEEDBACK_TTL)


    @staticmethod
    def draw_click_feedback_items(cairo_context, ww, wh, click_feedback, ttl):
        now = time.monotonic()
        for pulse in click_feedback:
            age = now - pulse['time']
            if age >= ttl:
                continue

            progress = age / ttl
            radius = max(10, min(44, min(ww, wh) * (0.015 + 0.03 * progress)))
            alpha = 0.85 * (1 - progress)
            x = ww * pulse['x']
            y = wh * pulse['y']
            color = BrowserMirror._feedback_color(pulse.get('button_kind', 'primary'))

            cairo_context.save()
            cairo_context.arc(x, y, radius, 0, 2 * 3.141592653589793)
            cairo_context.set_line_width(max(2, radius * 0.2))
            cairo_context.set_source_rgba(*color, alpha)
            cairo_context.stroke()
            cairo_context.restore()


    def _draw_drag_feedback(self, cairo_context, ww, wh):
        now = time.monotonic()

        for trail in self.drag_feedback:
            age = now - trail['time']
            if age >= self.DRAG_FEEDBACK_TTL:
                continue
            self._draw_drag_path(
                cairo_context,
                ww,
                wh,
                trail['points'],
                1 - age / self.DRAG_FEEDBACK_TTL,
                trail.get('button_kind', 'primary'),
            )

        if self.active_drag_points:
            self._draw_active_drag_path(
                cairo_context,
                ww,
                wh,
                self.active_drag_points,
                self.active_drag_button_kind,
            )


    @staticmethod
    def _feedback_color(button_kind):
        if button_kind == 'secondary':
            return 0.24, 0.56, 1.0
        elif button_kind == 'auxiliary':
            return 0.36, 0.8, 0.42
        return 1.0, 0.2, 0.2


    @staticmethod
    def _base_trail_alpha(button_kind):
        return 0.85 * (0.72 if button_kind == 'primary' else 1.0)


    @staticmethod
    def _draw_drag_path(cairo_context, ww, wh, points, alpha, button_kind='primary'):
        if len(points) < 2:
            return

        cairo_context.save()
        cairo_context.set_line_cap(1)
        cairo_context.set_line_join(1)
        outer_width = max(2.2, min(5.0, min(ww, wh) * 0.0046))
        inner_width = max(1.3, min(3.0, min(ww, wh) * 0.0026))
        inner_alpha = BrowserMirror._base_trail_alpha(button_kind) * alpha
        outer_alpha = inner_alpha * (0.38 / 0.9)
        cairo_context.set_line_width(outer_width)
        red, green, blue = BrowserMirror._feedback_color(button_kind)

        BrowserMirror._trace_smooth_path(cairo_context, ww, wh, points)

        cairo_context.set_source_rgba(red * 0.35, green * 0.35, blue * 0.35, outer_alpha)
        cairo_context.stroke_preserve()
        cairo_context.set_line_width(inner_width)
        cairo_context.set_source_rgba(red, green, blue, inner_alpha)
        cairo_context.stroke()
        cairo_context.restore()


    @staticmethod
    def _draw_active_drag_path(cairo_context, ww, wh, points, button_kind='primary'):
        if len(points) < 2:
            return

        now = time.monotonic()
        red, green, blue = BrowserMirror._feedback_color(button_kind)
        outer_width = max(2.2, min(5.0, min(ww, wh) * 0.0046))
        inner_width = max(1.3, min(3.0, min(ww, wh) * 0.0026))
        base_alpha = BrowserMirror._base_trail_alpha(button_kind)
        layer_count = 8
        layer_alpha = base_alpha / layer_count

        cairo_context.save()
        cairo_context.set_line_cap(1)
        cairo_context.set_line_join(1)

        for layer_index in range(layer_count):
            cutoff = now - BrowserMirror.ACTIVE_DRAG_TTL * (layer_count - layer_index) / layer_count
            layer_points = BrowserMirror._active_drag_layer_points(points, cutoff)
            if len(layer_points) < 2:
                continue

            cairo_context.set_line_width(outer_width)
            BrowserMirror._trace_smooth_path(cairo_context, ww, wh, layer_points)
            cairo_context.set_source_rgba(red * 0.35, green * 0.35, blue * 0.35, layer_alpha * (0.38 / 0.9))
            cairo_context.stroke_preserve()

            cairo_context.set_line_width(inner_width)
            cairo_context.set_source_rgba(red, green, blue, layer_alpha)
            cairo_context.stroke()

        cairo_context.restore()


    @staticmethod
    def _active_drag_layer_points(points, cutoff):
        layer_points = []
        previous_point = None

        for point_x, point_y, point_t in points:
            if point_t < cutoff:
                previous_point = (point_x, point_y)
                continue

            if previous_point is not None and not layer_points:
                layer_points.append(previous_point)
                previous_point = None

            layer_points.append((point_x, point_y))

        return layer_points


    @staticmethod
    def _trace_smooth_path(cairo_context, ww, wh, points):
        scaled_points = [(ww * point_x, wh * point_y) for point_x, point_y in points]

        first_x, first_y = scaled_points[0]
        cairo_context.move_to(first_x, first_y)

        if len(scaled_points) == 2:
            cairo_context.line_to(*scaled_points[1])
            return

        extended_points = [scaled_points[0], *scaled_points, scaled_points[-1]]

        for idx in range(1, len(extended_points) - 2):
            point_0 = extended_points[idx - 1]
            point_1 = extended_points[idx]
            point_2 = extended_points[idx + 1]
            point_3 = extended_points[idx + 2]

            control_1 = (
                point_1[0] + (point_2[0] - point_0[0]) / 6.0,
                point_1[1] + (point_2[1] - point_0[1]) / 6.0,
            )
            control_2 = (
                point_2[0] - (point_3[0] - point_1[0]) / 6.0,
                point_2[1] - (point_3[1] - point_1[1]) / 6.0,
            )
            cairo_context.curve_to(control_1[0], control_1[1], control_2[0], control_2[1], point_2[0], point_2[1])
