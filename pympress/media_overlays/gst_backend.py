# -*- coding: utf-8 -*-
#
#       media_overlays/gst.py
#
#       Copyright 2018 Cimbali <me@cimba.li>
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
#
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
#
"""
:mod:`pympress.media_overlays.gst` -- widget to play videos using Gstreamer's Gst
---------------------------------------------------------------------------------------
"""

import logging
import os
import sys
import pathlib
import ctypes
from ctypes import wintypes
import cairo
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gst, GstVideo, Gtk  # noqa: E402


from pympress import util
from pympress.media_overlays import base


#: Delay (ms) between the first frame reaching d3d12videosink and showing its window
D3D12_REVEAL_DELAY_MS = 60
#: Show the video window after this delay (ms) even if no frame arrived
D3D12_REVEAL_TIMEOUT_MS = 1500
#: Window class of the persistent Direct3D 12 popups
D3D12_POPUP_CLASS = 'PympressD3D12Popup'

_win32 = None

def win32():
    """ user32, kernel32, and gdk functions used for native Win32 video popups (Windows only).

    Returns:
        `tuple`: (user32, kernel32, gdk) :class:`~ctypes.CDLL` objects with argument types set
    """
    global _win32
    if _win32 is not None:
        return _win32

    user32 = ctypes.WinDLL('user32')
    kernel32 = ctypes.WinDLL('kernel32')
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.CreateWindowExW.argtypes = [
        ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    ]
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint
    ]
    user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.SetLayeredWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ubyte, ctypes.c_uint]
    user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassExW.restype = ctypes.c_ushort
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    user32.TranslateMessage.argtypes = [ctypes.c_void_p]
    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]

    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.c_uint), ('style', ctypes.c_uint), ('lpfnWndProc', ctypes.c_void_p),
            ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int), ('hInstance', ctypes.c_void_p),
            ('hIcon', ctypes.c_void_p), ('hCursor', ctypes.c_void_p), ('hbrBackground', ctypes.c_void_p),
            ('lpszMenuName', ctypes.c_wchar_p), ('lpszClassName', ctypes.c_wchar_p),
            ('hIconSm', ctypes.c_void_p)
        ]

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = ctypes.cast(user32.DefWindowProcW, ctypes.c_void_p).value
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = D3D12_POPUP_CLASS
    if not user32.RegisterClassExW(ctypes.byref(wc)):
        logger.warning('GStreamer: video popup window class not registered')

    gdi32 = ctypes.WinDLL('gdi32')
    user32.UpdateLayeredWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint
    ]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL

    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint
    ]

    gdk = ctypes.CDLL('libgdk-3-0.dll')
    gdk.gdk_win32_window_get_handle.restype = ctypes.c_void_p
    gdk.gdk_win32_window_get_handle.argtypes = [ctypes.c_void_p]
    _win32 = (user32, kernel32, gdk, gdi32)
    return _win32


class POINT(ctypes.Structure):
    """ Win32 POINT structure for client coordinate mapping. """
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class SIZE(ctypes.Structure):
    """ Win32 SIZE structure for window dimensions. """
    _fields_ = [('cx', ctypes.c_long), ('cy', ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    """ Win32 BLENDFUNCTION structure for alpha blending. """
    _fields_ = [
        ('BlendOp', ctypes.c_ubyte),
        ('BlendFlags', ctypes.c_ubyte),
        ('SourceConstantAlpha', ctypes.c_ubyte),
        ('AlphaFormat', ctypes.c_ubyte)
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    """ Win32 BITMAPINFOHEADER structure for 32-bit ARGB DIB creation. """
    _fields_ = [
        ('biSize', ctypes.c_uint),
        ('biWidth', ctypes.c_long),
        ('biHeight', ctypes.c_long),
        ('biPlanes', ctypes.c_ushort),
        ('biBitCount', ctypes.c_ushort),
        ('biCompression', ctypes.c_uint),
        ('biSizeImage', ctypes.c_uint),
        ('biXPelsPerMeter', ctypes.c_long),
        ('biYPelsPerMeter', ctypes.c_long),
        ('biClrUsed', ctypes.c_uint),
        ('biClrImportant', ctypes.c_uint)
    ]


class BITMAPINFO(ctypes.Structure):
    """ Win32 BITMAPINFO structure wrapping header and color table entries. """
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', ctypes.c_uint * 3)]


class D3D12OverlayPlayer(object):
    """ Persistent Direct3D 12 video player for the Content window on Windows.

    Recycles a single native Win32 popup window and a single GStreamer playbin pipeline with
    d3d12videosink (direct-swapchain=True, external-window-only=True). Reusing the pipeline and
    HWND across video slides eliminates swapchain churn, the 12,998-handle leak, and the Intel
    driver teardown crash (igd10um64gen11.dll) while achieving sub-20ms slide transitions.
    """
    _instance = None

    @classmethod
    def get(cls):
        """ Get or create the singleton persistent Direct3D 12 player instance.

        Returns:
            :class:`~D3D12OverlayPlayer`: the singleton player instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        user32, kernel32, gdk, gdi32 = win32()
        self.user32 = user32
        self.gdi32 = gdi32

        # Create persistent GStreamer playbin and d3d12videosink
        self.playbin = Gst.ElementFactory.make('playbin', 'pympress_d3d12_playbin')
        self.sink = Gst.ElementFactory.make('d3d12videosink', 'pympress_d3d12_sink')
        self.sink.set_property('direct-swapchain', True)
        self.sink.set_property('external-window-only', True)
        self.sink.set_property('enable-navigation-events', False)

        # Content window is muted in Pympress; presenter window plays audio
        self.playbin.set_property('video-sink', self.sink)
        self.playbin.set_property('audio-sink', Gst.ElementFactory.make('fakesink', 'd3d12_fake_audio'))

        # Reveal and flash avoidance
        self.reveal_pending = False
        self.reveal_gen = 0
        sink_pad = self.sink.get_static_pad('sink')
        if sink_pad is not None:
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, self.on_sink_buffer)

        # Video crop filter for zoom (d3d12videosink scales on GPU, no CPU videoscale needed)
        self.crop_filter = Gst.ElementFactory.make('videocrop', 'd3d12_zoomcrop')
        if self.crop_filter is not None:
            self.playbin.set_property('video-filter', self.crop_filter)
            self.crop_filter.get_static_pad('sink').add_probe(
                Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_crop_sink_event
            )
        self.crop_input_size = None

        self.popup = None
        self.popup_owner = None
        self.active_overlay = None
        self.selection_popup = None
        self.sel_dib = None
        self.sel_dc = None
        self.sel_bits = None
        self.sel_old_bm = None
        self.sel_size = (0, 0)

        # GStreamer bus listeners
        bus = self.playbin.get_bus()
        bus.enable_sync_message_emission()
        bus.connect('sync-message', self.on_sync_message)
        bus.add_signal_watch()
        bus.connect('message::eos', self.on_bus_eos)
        bus.connect('message::error', self.on_bus_error)
        bus.connect('message::state-changed', self.on_bus_state_changed)
        bus.connect('message::duration-changed', self.on_bus_duration_changed)

        # Continuous Win32 message pump for DXGI presentation
        self.msg_struct = wintypes.MSG()
        self.pump_id = GLib.timeout_add(10, self.pump_messages)

    def pump_messages(self):
        """ Pump Win32 messages on Python's thread to keep DXGI swapchain presentation active. """
        while self.user32.PeekMessageW(ctypes.byref(self.msg_struct), None, 0, 0, 1):
            self.user32.TranslateMessage(ctypes.byref(self.msg_struct))
            self.user32.DispatchMessageW(ctypes.byref(self.msg_struct))
        return True

    def on_sync_message(self, bus, msg):
        """ Bind popup HWND synchronously when requested by playsink / videosink. """
        if self.popup and GstVideo.is_video_overlay_prepare_window_handle_message(msg):
            msg.src.set_window_handle(self.popup)
            self.sink.set_window_handle(self.popup)

    def on_bus_eos(self, *args):
        """ Handle end-of-stream from the GStreamer bus on the main thread. """
        if self.active_overlay:
            GLib.idle_add(self.active_overlay.handle_end)

    def on_bus_error(self, _, msg):
        """ Log GStreamer bus errors. """
        err, debug = msg.parse_error()
        logger.error('D3D12 GStreamer Error: {} ({})'.format(err, debug))

    def on_bus_state_changed(self, bus, msg):
        """ Notify active overlay when transitioning to PAUSED. """
        if msg.src == self.playbin and self.active_overlay:
            old, new, pending = msg.parse_state_changed()
            if old == Gst.State.READY and new == Gst.State.PAUSED:
                self.active_overlay.on_initial_play()

    def on_bus_duration_changed(self, *args):
        """ Notify active overlay when duration becomes available. """
        if self.active_overlay:
            GLib.idle_add(self.active_overlay.do_update_duration)

    def on_sink_buffer(self, pad, info):
        """ First frame reached d3d12videosink: ensure check_rendered is polling (streaming thread, no GTK calls). """
        if self.reveal_pending:
            GLib.idle_add(self.check_rendered, self.reveal_gen)
        return Gst.PadProbeReturn.OK

    def check_rendered(self, gen):
        """ Poll d3d12videosink rendered count and unmask popup only after frame 0 is presented (main thread). """
        if gen != self.reveal_gen or self.popup is None or not self.user32.IsWindow(self.popup):
            return False
        if not self.reveal_pending:
            return False

        st = self.sink.get_property('stats')
        ok, rendered = st.get_uint64('rendered') if st else (False, 0)
        if ok and rendered >= 1:
            self.reveal_gen += 1
            self.reveal_pending = False
            self.user32.SetLayeredWindowAttributes(self.popup, 0, 255, 2)
            return False

        return True

    def reveal_popup(self, gen):
        """ Fallback: make popup opaque if rendered check timed out (main thread). """
        if gen == self.reveal_gen and self.popup is not None and self.user32.IsWindow(self.popup):
            self.reveal_gen += 1
            self.reveal_pending = False
            self.user32.SetLayeredWindowAttributes(self.popup, 0, 255, 2)
        return False

    def on_crop_sink_event(self, pad, info):
        """ Follow the size of frames reaching videocrop (streaming thread). """
        event = info.get_event()
        if event.type != Gst.EventType.CAPS:
            return Gst.PadProbeReturn.OK
        s = event.parse_caps().get_structure(0)
        ok_w, w = s.get_int('width')
        ok_h, h = s.get_int('height')
        if ok_w and ok_h and w > 0 and h > 0:
            self.crop_input_size = (w, h)
            if self.active_overlay and any(self.active_overlay.crop_fractions):
                GLib.idle_add(self.apply_crop, self.active_overlay)
        return Gst.PadProbeReturn.OK

    def set_crop(self, w, h, crop_fractions):
        """ Set the crop of videocrop from crop_fractions, for frames of w x h. """
        new = [round(f * size) for f, size in zip(crop_fractions, (w, w, h, h))]
        new[1] = max(0, min(new[1], w - new[0] - 2))
        new[3] = max(0, min(new[3], h - new[2] - 2))
        names = ('left', 'right', 'top', 'bottom')
        old = [self.crop_filter.get_property(name) for name in names]
        for values in ([min(o, n) for o, n in zip(old, new)], new):
            for name, value in zip(names, values):
                self.crop_filter.set_property(name, value)
        return new

    def apply_crop(self, overlay):
        """ Apply crop_fractions from overlay to videocrop (main thread). """
        if self.active_overlay is None:
            self.active_overlay = overlay
        if self.crop_filter is None or self.crop_input_size is None or self.active_overlay != overlay:
            return False
        w, h = self.crop_input_size
        self.set_crop(w, h, overlay.crop_fractions)
        self.repaint_still_frame()
        return False

    def repaint_still_frame(self):
        """ Seek to current position to draw frame again when paused or frozen. """
        ret, state, pending = self.playbin.get_state(0)
        is_frozen = bool(self.active_overlay and self.active_overlay.is_frozen)
        is_actively_playing = (state == Gst.State.PLAYING and pending != Gst.State.PAUSED and not is_frozen)
        if is_actively_playing or state in {Gst.State.NULL, Gst.State.READY}:
            return
        if is_frozen:
            self.playbin.set_state(Gst.State.PAUSED)
        ok_pos, pos = self.playbin.query_position(Gst.Format.TIME)
        ok_dur, dur = self.playbin.query_duration(Gst.Format.TIME)
        last_ts = getattr(self.active_overlay, 'last_timestamp', 0) if self.active_overlay else 0
        seek_pos = pos if ok_pos and pos > 0 else int(last_ts * Gst.SECOND)
        if ok_dur and dur > 0:
            seek_pos = min(seek_pos, max(0, dur - 5 * Gst.MSECOND))
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, seek_pos)

    def hide_selection_popup(self):
        """ Hide the native layered selection popup window. """
        if self.selection_popup and self.user32.IsWindow(self.selection_popup):
            self.user32.ShowWindow(self.selection_popup, 0)

    def ensure_selection_popup(self, owner, vx, vy, vw, vh):
        """ Ensure the native layered selection popup exists and matches geometry. """
        if self.selection_popup is not None and (owner != self.popup_owner or
                                                 not self.user32.IsWindow(self.selection_popup)):
            self.user32.DestroyWindow(self.selection_popup)
            self.selection_popup = None

        if self.selection_popup is None:
            ex_style = 0x08000000 | 0x80 | 0x20 | 0x00080000
            style = 0x80000000
            self.selection_popup = self.user32.CreateWindowExW(
                ex_style, D3D12_POPUP_CLASS, None, style,
                vx, vy, vw, vh, owner, None, None, None
            )

        if (vw, vh) != self.sel_size:
            if self.sel_dib:
                self.gdi32.SelectObject(self.sel_dc, self.sel_old_bm)
                self.gdi32.DeleteObject(self.sel_dib)
                self.gdi32.DeleteDC(self.sel_dc)
                self.sel_dib = None
                self.sel_dc = None
                self.sel_bits = None

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = vw
            bmi.bmiHeader.biHeight = -vh
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0

            self.sel_dc = self.gdi32.CreateCompatibleDC(None)
            bits = ctypes.c_void_p()
            self.sel_dib = self.gdi32.CreateDIBSection(
                self.sel_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0
            )
            self.sel_old_bm = self.gdi32.SelectObject(self.sel_dc, self.sel_dib)
            self.sel_bits = bits
            self.sel_size = (vw, vh)

        return bool(self.selection_popup and self.sel_dib)

    def update_zoom_selection(self, overlay, zoom_points, scale, shift):
        """ Render the zoom selection rectangle onto the native layered selection popup. """
        if not zoom_points or self.active_overlay != overlay or not self.popup:
            self.hide_selection_popup()
            return

        geom = overlay.popup_geometry()
        if not geom:
            self.hide_selection_popup()
            return
        owner, vx, vy, vw, vh = geom
        if vw < 16 or vh < 16:
            self.hide_selection_popup()
            return

        if not self.ensure_selection_popup(owner, vx, vy, vw, vh):
            return

        buf_len = vw * vh * 4
        ctypes.memset(self.sel_bits, 0, buf_len)

        buf = (ctypes.c_char * buf_len).from_address(self.sel_bits.value)
        surface = cairo.ImageSurface.create_for_data(buf, cairo.Format.ARGB32, vw, vh, vw * 4)
        ctx = cairo.Context(surface)

        cw = overlay.parent.get_allocated_width()
        ch = overlay.parent.get_allocated_height()
        dpi_scale = overlay.parent.get_scale_factor()
        mo = overlay.media_overlay
        ml = mo.props.margin_left
        mt = mo.props.margin_top

        ctx.scale(dpi_scale, dpi_scale)
        ctx.translate(-ml, -mt)
        ctx.transform(cairo.Matrix(xx=scale, x0=cw * shift[0], yy=scale, y0=ch * shift[1]))

        xmin, xmax = sorted(p[0] * cw for p in zoom_points)
        ymin, ymax = sorted(p[1] * ch for p in zoom_points)

        ctx.set_line_width(3)
        ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
        ctx.rectangle(xmin, ymin, xmax - xmin, ymax - ymin)
        ctx.set_source_rgba(0.1, 0.1, 1.0, 0.4)
        ctx.stroke()

        ctx.rectangle(xmin, ymin, xmax - xmin, ymax - ymin)
        ctx.set_source_rgba(0.5, 0.5, 1.0, 0.2)
        ctx.fill()
        surface.flush()

        pt_dst = POINT(vx, vy)
        size = SIZE(vw, vh)
        pt_src = POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)

        self.user32.UpdateLayeredWindow(
            self.selection_popup, None, ctypes.byref(pt_dst), ctypes.byref(size),
            self.sel_dc, ctypes.byref(pt_src), 0, ctypes.byref(blend), 2
        )
        self.user32.SetWindowPos(self.selection_popup, 0, vx, vy, vw, vh, 0x0010)
        self.user32.ShowWindow(self.selection_popup, 8)

    def ensure_popup(self, owner, x, y, w, h):
        """ Ensure the persistent popup HWND exists, is owned by toplevel, and matches geometry. """
        if self.popup is not None and (owner != self.popup_owner or not self.user32.IsWindow(self.popup)):
            self.user32.DestroyWindow(self.popup)
            self.popup = None
            self.popup_owner = None

        if self.popup is None:
            # WS_EX_NOACTIVATE (0x08000000) | WS_EX_TOOLWINDOW (0x80) | WS_EX_TRANSPARENT (0x20)
            # | WS_EX_LAYERED (0x00080000)
            # WS_POPUP (0x80000000)
            ex_style = 0x08000000 | 0x80 | 0x20 | 0x00080000
            style = 0x80000000
            self.popup = self.user32.CreateWindowExW(
                ex_style, D3D12_POPUP_CLASS, None, style,
                x, y, w, h, owner, None, None, None
            )
            self.popup_owner = owner
            self.user32.SetLayeredWindowAttributes(self.popup, 0, 0, 2)  # fully transparent initially
            self.sink.set_window_handle(self.popup)
        else:
            # SWP_NOZORDER (0x0004) | SWP_NOACTIVATE (0x0010)
            self.user32.SetWindowPos(self.popup, None, x, y, w, h, 0x0004 | 0x0010)

        return bool(self.popup)

    def play(self, overlay):
        """ Switch to overlay's clip and start playback on the persistent D3D12 pipeline. """
        geometry = overlay.popup_geometry()
        if not geometry:
            logger.warning('D3D12: cannot play, geometry not ready')
            return False

        owner, x, y, w, h = geometry
        if not self.ensure_popup(owner, x, y, w, h):
            return False

        self.active_overlay = overlay
        uri = overlay.file.as_uri()

        # Update URI on persistent playbin
        self.playbin.set_state(Gst.State.READY)
        self.playbin.set_property('uri', uri)

        # Show native HWND transparently first (SW_SHOWNA = 8), reveal only when frame 0 is rendered
        self.user32.SetLayeredWindowAttributes(self.popup, 0, 0, 2)
        self.user32.ShowWindow(self.popup, 8)
        self.reveal_pending = True
        GLib.timeout_add(10, self.check_rendered, self.reveal_gen)
        GLib.timeout_add(D3D12_REVEAL_TIMEOUT_MS, self.reveal_popup, self.reveal_gen)
        self.playbin.set_state(Gst.State.PLAYING)
        return True

    def pause(self):
        """ Pause the persistent GStreamer playbin pipeline. """
        self.playbin.set_state(Gst.State.PAUSED)

    def resume(self):
        """ Resume playback on the persistent GStreamer playbin pipeline. """
        if self.popup:
            self.user32.ShowWindow(self.popup, 8)
        self.playbin.set_state(Gst.State.PLAYING)

    def stop(self):
        """ Hide the popup window and pause the persistent pipeline. """
        self.reveal_gen += 1
        self.reveal_pending = False
        self.hide_selection_popup()
        if self.popup:
            self.user32.SetLayeredWindowAttributes(self.popup, 0, 0, 2)
            self.user32.ShowWindow(self.popup, 0)  # SW_HIDE = 0
        self.playbin.set_state(Gst.State.READY)

    def seek(self, time_sec):
        """ Seek the persistent pipeline to time `time_sec` in seconds. """
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, time_sec * Gst.SECOND)

    def is_playing(self, overlay):
        """ Return whether the given overlay is currently playing on the pipeline. """
        if self.active_overlay == overlay:
            return self.playbin.get_state(0).state == Gst.State.PLAYING
        return False

    def query_position(self):
        """ Query current playback position from the playbin pipeline. """
        return self.playbin.query_position(Gst.Format.TIME)

    def query_duration(self):
        """ Query duration from the playbin pipeline. """
        return self.playbin.query_duration(Gst.Format.TIME)

    def update_geometry(self, overlay):
        """ Update native popup window position and size to match the active overlay. """
        if self.active_overlay == overlay and self.popup:
            geom = overlay.popup_geometry()
            if geom:
                owner, x, y, w, h = geom
                self.user32.SetWindowPos(self.popup, None, x, y, w, h, 0x0004 | 0x0010)

    def shutdown(self):
        """ Clean up the message pump timer, playbin pipeline, and native popup HWND. """
        if self.pump_id:
            GLib.source_remove(self.pump_id)
            self.pump_id = None
        if self.playbin:
            self.playbin.set_state(Gst.State.NULL)
        self.hide_selection_popup()
        if self.selection_popup:
            self.user32.DestroyWindow(self.selection_popup)
            self.selection_popup = None
        if self.sel_dib:
            self.gdi32.SelectObject(self.sel_dc, self.sel_old_bm)
            self.gdi32.DeleteObject(self.sel_dib)
            self.gdi32.DeleteDC(self.sel_dc)
            self.sel_dib = None
            self.sel_dc = None
        if self.popup:
            self.user32.DestroyWindow(self.popup)
            self.popup = None


class GstOverlay(base.VideoOverlay):
    """ Simple Gstreamer widget.

    Wraps a GStreamer playbin pipeline with gtksink (preview/fallback) or a persistent Direct3D 12 overlay
    (Content window on Windows).
    """

    #: A :class:`~Gst.Playbin` to play videos
    playbin = None
    #: A :class:`~Gst.Base.Sink` to display video content
    sink = None

    #: `int` number of milliseconds between updates
    update_freq = 200

    #: :class:`~Gst.Element` capsfilter setting the size of the frames converted on the GPU, if any
    gpu_size_filter = None
    #: `tuple` of the video widget's size in device pixels, computed before playback
    gpu_target = None
    #: `tuple` of the size currently set on :attr:`gpu_size_filter`
    gpu_size = None
    #: `int` id of the tick callback that keeps the frame clock running during playback, if any
    frame_tick_id = None
    #: native clip dimensions and display aspect ratio from the decoder
    clip_w = None
    clip_h = None
    clip_dar = None
    #: pending timer id for debounced dynamic preview scaling
    preview_resize_timer_id = None
    #: whether playback has reached its end and is holding the last frame
    is_frozen = False

    #: `Gst.Element` the `videocrop` element that zooms into the video, or `None` if it is not available
    crop_filter = None
    #: `Gst.Element` the `capsfilter` after `videocrop` that keeps the frames at the size they had before the crop
    crop_size_filter = None
    #: `tuple` of `int` width and height of the frames that reach :attr:`crop_filter`, once known
    crop_input_size = None

    #: `Gst.Element` the `level` element that reports the audio levels shown by the meter, or `None`
    audio_level_filter = None

    #: `bool` whether this overlay uses the persistent Direct3D 12 player (Content window on Windows)
    use_d3d12_sink = False
    #: `pathlib.Path` path to the media file
    file = None

    def __init__(self, *args, **kwargs):
        container = args[0] if args else kwargs.get('container')
        self.use_d3d12_sink = (
            os.name == 'nt' and
            os.environ.get('PYMPRESS_GSTSINK', 'd3d12').lower() in ('d3d12', 'direct3d12') and
            container is not None and Gtk.Buildable.get_name(container) == 'c_overlay' and
            Gst.ElementFactory.find('d3d12videosink') is not None
        )

        if self.use_d3d12_sink:
            self.video_widget = Gtk.DrawingArea()
        else:
            # Create GStreamer playbin for gtksink (Linux, Windows fallback, Presenter window preview)
            self.playbin = Gst.ElementFactory.make('playbin', None)
            self.sink = Gst.ElementFactory.make('gtksink', None)
            self.playbin.set_property('video-sink', self.sink)
            self.setup_gpu_conversion()
            self.setup_crop_filter()
            self.setup_audio_filter()
            self.video_widget = self.sink.props.widget

        super(GstOverlay, self).__init__(*args, **kwargs)

        self.media_overlay.remove(self.movie_zone)
        if isinstance(self.media_overlay, Gtk.Overlay):
            self.media_overlay.add(self.video_widget)
        else:
            self.media_overlay.pack_start(self.video_widget, True, True, 0)
            self.media_overlay.reorder_child(self.video_widget, 0)
        self.video_widget.hide()

        if self.use_d3d12_sink:
            # Reposition persistent D3D12 popup when parent or overlay changes allocation or moves
            self.parent.connect('size-allocate', lambda *args: D3D12OverlayPlayer.get().update_geometry(self))
            self.media_overlay.connect('size-allocate', lambda *args: D3D12OverlayPlayer.get().update_geometry(self))
            toplevel = self.parent.get_toplevel()
            if toplevel is not None and toplevel.is_toplevel():
                toplevel.connect(
                    'configure-event',
                    lambda *args: GLib.idle_add(
                        lambda: D3D12OverlayPlayer.get().update_geometry(self) and False
                    ) and False
                )
        else:
            # Create bus to get events from GStreamer playbin
            bus = self.playbin.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect('message::eos', lambda *args: GLib.idle_add(self.handle_end))
            bus.connect('message::error', lambda _, msg: logger.error('{} {}'.format(*msg.parse_error())))
            bus.connect('message::state-changed', self.on_state_changed)
            bus.connect('message::element', self.on_element_message)
            bus.connect('message::duration-changed', lambda *args: GLib.idle_add(self.do_update_duration))

    def setup_gpu_conversion(self):
        """ Convert and scale the frames on the GPU (Direct3D 11) before they reach gtksink, if available.

        gtksink only takes BGRx or BGRA frames in system memory. Without this, playbin copies every decoded frame off
        the GPU and converts it on the CPU, then gtksink scales it to the widget with Cairo on the main thread, for
        each window. Here d3d11convert converts the colours (with the clip's colorimetry) and scales the frame to the
        widget's size, so the copy is smaller and gtksink draws it 1:1.
        """
        if Gst.ElementFactory.find('d3d11convert') is None or Gst.ElementFactory.find('d3d11download') is None:
            return

        try:
            video_filter = Gst.parse_bin_from_description(
                'd3d11convert name=gpuconvert add-borders=false ! '
                'capsfilter name=gpusize caps="video/x-raw(memory:D3D11Memory),format=BGRx" ! d3d11download', True
            )
        except GLib.Error as e:
            logger.warning('GPU conversion not set up: {}'.format(e))
            return

        flags = self.playbin.get_property('flags')
        for nick, fallback in (('deinterlace', 0x200), ('soft-colorbalance', 0x400)):
            flags = flags & ~util.introspect_flag_value(type(flags), nick, fallback)

        self.playbin.set_property('video-filter', video_filter)
        self.playbin.set_property('flags', flags)
        self.gpu_size_filter = video_filter.get_by_name('gpusize')
        video_filter.get_by_name('gpuconvert').get_static_pad('sink').add_probe(
            Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_gpu_convert_event)
        if self.sink.find_property('widget') is not None:
            self.sink.props.widget.connect('size-allocate', self.on_video_widget_allocated)

    def setup_crop_filter(self):
        """ Add `videocrop` and a `videoscale` back to the original size to the video filter, to follow the zoom.

        `videocrop` works on frames in system memory. Without a GPU conversion bin the crop is the playbin's video
        filter, with one it goes after `d3d11download` in that bin, so that the crop is the same code on every platform.
        """
        if any(Gst.ElementFactory.find(name) is None for name in ('videocrop', 'videoscale', 'capsfilter')):
            return

        crop = Gst.ElementFactory.make('videocrop', 'zoomcrop')
        elements = [crop]
        size = None
        if not self.use_d3d12_sink:
            size = Gst.ElementFactory.make('capsfilter', 'zoomsize')
            elements += [Gst.ElementFactory.make('videoscale', 'zoomscale'), size]
        video_filter = self.playbin.get_property('video-filter')

        if video_filter is None:
            video_filter = Gst.Bin.new('zoomfilter')
            for element in elements:
                video_filter.add(element)
            if not all(a.link(b) for a, b in zip(elements, elements[1:])):
                logger.warning('Zoom crop not set up: cannot link videocrop and videoscale')
                return
            video_filter.add_pad(Gst.GhostPad.new('sink', crop.get_static_pad('sink')))
            video_filter.add_pad(Gst.GhostPad.new('src', elements[-1].get_static_pad('src')))
            self.playbin.set_property('video-filter', video_filter)
        elif isinstance(video_filter, Gst.Bin):
            ghost = video_filter.get_static_pad('src')
            last = ghost.get_target().get_parent_element()
            for element in elements:
                video_filter.add(element)
            ghost.set_target(None)
            linked = (last.link(crop) and all(a.link(b) for a, b in zip(elements, elements[1:])) and
                      ghost.set_target(elements[-1].get_static_pad('src')))
            if not linked:
                logger.warning('Zoom crop not set up: cannot add videocrop to the GPU conversion')
                return
        else:
            return

        self.crop_filter = crop
        self.crop_size_filter = size
        crop.get_static_pad('sink').add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_crop_sink_event)

    def on_crop_sink_event(self, pad, info):
        """ Record the size of the frames reaching videocrop and set its initial crop (streaming thread).
        """
        event = info.get_event()
        if event.type != Gst.EventType.CAPS:
            return Gst.PadProbeReturn.OK

        s = event.parse_caps().get_structure(0)
        ok_w, w = s.get_int('width')
        ok_h, h = s.get_int('height')
        if not ok_w or not ok_h or w <= 0 or h <= 0:
            return Gst.PadProbeReturn.OK

        self.crop_input_size = (w, h)
        if self.crop_size_filter is not None:
            self.crop_size_filter.set_property(
                'caps', Gst.Caps.from_string('video/x-raw,width={},height={}'.format(w, h)))
        self.set_crop(w, h)
        return Gst.PadProbeReturn.OK

    def set_crop(self, w, h):
        """ Set the crop of `videocrop` from :attr:`crop_fractions`, for frames of `w` by `h` pixels.

        Frames may be flowing, so every step must leave a frame: the values that grow are first set to the smaller of
        the old and new value, then to the new one. Each step is then no bigger than the old or the new crop.
        """
        new = [round(f * size) for f, size in zip(self.crop_fractions, (w, w, h, h))]
        # never crop the whole frame
        new[1] = max(0, min(new[1], w - new[0] - 2))
        new[3] = max(0, min(new[3], h - new[2] - 2))
        names = ('left', 'right', 'top', 'bottom')
        old = [self.crop_filter.get_property(name) for name in names]
        for values in ([min(o, n) for o, n in zip(old, new)], new):
            for name, value in zip(names, values):
                self.crop_filter.set_property(name, value)
        return new

    def update_zoom_selection(self, zoom_points, scale, shift):
        """ Update zoom selection rectangle on the Direct3D 12 popup. """
        if self.use_d3d12_sink:
            D3D12OverlayPlayer.get().update_zoom_selection(self, zoom_points, scale, shift)

    def apply_crop(self):
        """ Apply :attr:`crop_fractions` to `videocrop` and repaint a paused or frozen frame (main thread).
        """
        if self.use_d3d12_sink:
            return D3D12OverlayPlayer.get().apply_crop(self)

        if self.crop_filter is None or self.crop_input_size is None:
            return False

        w, h = self.crop_input_size
        left, right, top, bottom = self.set_crop(w, h)
        logger.debug('GStreamer: zoom crop left=%d right=%d top=%d bottom=%d on %dx%d', left, right, top, bottom, w, h)

        self.repaint_still_frame()
        return False

    def setup_audio_filter(self):
        """ Add a `level` element to the playbin audio filter, to report the levels for the audio meter.
        """
        if Gst.ElementFactory.find('level') is None or self.playbin.get_property('audio-filter') is not None:
            return

        self.audio_level_filter = Gst.ElementFactory.make('level', None)
        self.audio_level_filter.set_property('interval', 50 * Gst.MSECOND)
        self.audio_level_filter.set_property('post-messages', True)
        self.playbin.set_property('audio-filter', self.audio_level_filter)

    def on_element_message(self, bus, msg):
        """ Show the peak level reported by the `level` element on the audio meter.

        Args:
            bus (:class:`~Gst.Bus`): the bus that sent the message
            msg (:class:`~Gst.Message`): the element message
        """
        s = msg.get_structure()
        if s is None or s.get_name() != 'level':
            return

        peaks = s.get_value('peak')
        if peaks:
            GLib.idle_add(self.update_audio_meter, max(0.0, min(1.0, (max(peaks) + 60.0) / 60.0)))

    def repaint_still_frame(self):
        """ Seek to the current position to draw the frame again, if the video is paused or frozen at its end.
        """
        if self.use_d3d12_sink:
            return
        ret, state, pending = self.playbin.get_state(0)
        is_actively_playing = (state == Gst.State.PLAYING and pending != Gst.State.PAUSED and not self.is_frozen)
        if is_actively_playing or state in {Gst.State.NULL, Gst.State.READY}:
            return

        if self.is_frozen:
            self.playbin.set_state(Gst.State.PAUSED)
        ok_pos, pos = self.playbin.query_position(Gst.Format.TIME)
        ok_dur, dur = self.playbin.query_duration(Gst.Format.TIME)
        seek_pos = pos if ok_pos and pos > 0 else int(self.last_timestamp * Gst.SECOND)
        if ok_dur and dur > 0:
            seek_pos = min(seek_pos, max(0, dur - 5 * Gst.MSECOND))
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, seek_pos)

    def update_gpu_target(self):
        """ Compute the video widget's size in device pixels from the overlay margins (main thread).

        Runs before playback starts, when the widget is still hidden and not allocated.
        """
        if self.gpu_size_filter is None:
            return
        mo = self.media_overlay
        w = self.parent.get_allocated_width() - mo.props.margin_left - mo.props.margin_right
        h = self.parent.get_allocated_height() - mo.props.margin_top - mo.props.margin_bottom
        if not isinstance(self.media_overlay, Gtk.Overlay) and self.toolbar.get_visible():
            h -= self.toolbar.get_preferred_height()[1]
        scale = self.parent.get_scale_factor()
        self.gpu_target = (int(w * scale), int(h * scale)) if w >= 16 and h >= 16 else None

    def on_gpu_convert_event(self, pad, info):
        """ Set the GPU output size when caps reach d3d11convert (streaming thread, no GTK calls).

        The size is the largest frame with the video's aspect ratio that fits the widget.
        """
        event = info.get_event()
        target = self.gpu_target
        if event.type != Gst.EventType.CAPS or target is None:
            return Gst.PadProbeReturn.OK

        s = event.parse_caps().get_structure(0)
        ok_w, w = s.get_int('width')
        ok_h, h = s.get_int('height')
        ok_par, par_n, par_d = s.get_fraction('pixel-aspect-ratio')
        if not ok_par or not par_n or not par_d:
            par_n, par_d = 1, 1
        if not ok_w or not ok_h or w <= 0 or h <= 0:
            return Gst.PadProbeReturn.OK

        self.clip_w = w
        self.clip_h = h
        dar = w * par_n / (h * par_d)
        self.clip_dar = dar

        aw, ah = target
        if aw / ah <= dar:
            size = (aw, min(ah, max(2, round(aw / dar))))
        else:
            size = (min(aw, max(2, round(ah * dar))), ah)

        if size != self.gpu_size:
            self.gpu_size = size
            self.gpu_size_filter.set_property('caps', Gst.Caps.from_string(
                'video/x-raw(memory:D3D11Memory),format=BGRx,width={},height={},pixel-aspect-ratio=1/1'.format(*size)
            ))
        return Gst.PadProbeReturn.OK

    def on_video_widget_allocated(self, widget, allocation):
        """ Handle widget allocation changes for dynamic preview sizing (main thread).

        Caps dimensions only ever increase to avoid gtksink shrink issues (gitlab issue #1082).
        """
        if self.gpu_size_filter is None or self.clip_dar is None:
            return

        scale = widget.get_scale_factor()
        aw = int(allocation.width * scale)
        ah = int(allocation.height * scale)
        dar = self.clip_dar
        if aw <= 16 or ah <= 16:
            return

        if aw / ah <= dar:
            target_w = aw
            target_h = min(ah, max(2, round(aw / dar)))
        else:
            target_w = min(aw, max(2, round(ah * dar)))
            target_h = ah

        # Cap at native clip size
        if target_w > self.clip_w or target_h > self.clip_h:
            target_w = self.clip_w if self.clip_w / dar <= self.clip_h else max(2, round(self.clip_h * dar))
            target_h = min(self.clip_h, max(2, round(target_w / dar)))

        target_w, target_h = int(target_w), int(target_h)
        current_w, current_h = self.gpu_size if self.gpu_size else (0, 0)

        # Growth only: update if either dimension exceeds the current frame by > 5%
        if target_w > current_w * 1.05 or target_h > current_h * 1.05:
            if self.preview_resize_timer_id is not None:
                GLib.source_remove(self.preview_resize_timer_id)
            self.preview_resize_timer_id = GLib.timeout_add(250, self.apply_dynamic_preview_size, target_w, target_h)

    def apply_dynamic_preview_size(self, target_w, target_h):
        """ Update the GPU scaling caps on the fly when the widget grows (main thread).
        """
        self.preview_resize_timer_id = None
        if self.gpu_size_filter is None or not self.is_shown():
            return False

        current_w, current_h = self.gpu_size if self.gpu_size else (0, 0)
        if target_w <= current_w and target_h <= current_h:
            return False

        target_w, target_h = int(target_w), int(target_h)
        self.gpu_size = (target_w, target_h)
        new_caps = Gst.Caps.from_string(
            'video/x-raw(memory:D3D11Memory),format=BGRx,width={},height={},pixel-aspect-ratio=1/1'.format(
                target_w, target_h)
        )
        self.gpu_size_filter.set_property('caps', new_caps)

        self.repaint_still_frame()

        return False

    def start_frame_tick(self):
        """ Keep GTK's frame clock running while the video plays (main thread, Windows only).
        """
        if os.name != 'nt' or self.frame_tick_id is not None or self.use_d3d12_sink:
            return
        self.frame_tick_id = self.video_widget.add_tick_callback(self.on_frame_tick)

    def on_frame_tick(self, widget, frame_clock):
        """ Frame clock tick: stop ticking once the player is no longer playing or about to play.

        Returns:
            `bool`: `True` to keep ticking (:meth:`~Gtk.Widget.add_tick_callback` convention)
        """
        ret, state, pending = self.playbin.get_state(0)
        if state == Gst.State.PLAYING or pending == Gst.State.PLAYING:
            return True
        self.frame_tick_id = None
        return False

    def stop_frame_tick(self):
        """ Remove the frame clock tick callback, if any (main thread).
        """
        if self.frame_tick_id is not None:
            self.video_widget.remove_tick_callback(self.frame_tick_id)
            self.frame_tick_id = None

    def popup_geometry(self):
        """ Where the video goes, in screen pixels, from the overlay margins (main thread).

        Returns:
            `tuple`: (owner window handle, x, y, width, height), or `None` if the content window is not ready
        """
        toplevel = self.parent.get_toplevel()
        top_window = toplevel.get_window() if toplevel is not None else None
        parent_window = self.parent.get_window()
        if top_window is None or parent_window is None:
            return None
        mo = self.media_overlay
        w = self.parent.get_allocated_width() - mo.props.margin_left - mo.props.margin_right
        h = self.parent.get_allocated_height() - mo.props.margin_top - mo.props.margin_bottom
        if not isinstance(self.media_overlay, Gtk.Overlay) and self.toolbar.get_visible():
            h -= self.toolbar.get_preferred_height()[1]
        if w < 16 or h < 16:
            return None
        x0, y0 = parent_window.get_origin()[1:]
        tx, ty = top_window.get_origin()[1:]
        px, py = (
            (0, 0) if self.parent.get_has_window()
            else (self.parent.get_allocation().x, self.parent.get_allocation().y)
        )
        user32, kernel32, gdk, _ = win32()
        owner = gdk.gdk_win32_window_get_handle(hash(top_window))
        scale = self.parent.get_scale_factor()
        point = (ctypes.c_long * 2)((x0 - tx + px + mo.props.margin_left) * scale,
                                    (y0 - ty + py + mo.props.margin_top) * scale)
        user32.ClientToScreen(owner, point)
        return owner, point[0], point[1], w * scale, h * scale

    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        if self.use_d3d12_sink:
            return D3D12OverlayPlayer.get().is_playing(self)
        return self.playbin.get_state(0).state == Gst.State.PLAYING

    def _set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`pathlib.Path`): The path to the media file path
        """
        self.file = filepath
        if not self.use_d3d12_sink:
            self.playbin.set_property('uri', filepath.as_uri())
            self.playbin.set_state(Gst.State.READY)

    def mute(self, value):
        """ Mutes or unmutes the player.

        Args:
            value (`bool`): `True` iff this player should be muted
        """
        if self.use_d3d12_sink:
            return False
        flags = self.playbin.get_property('flags')
        audio_flag = util.introspect_flag_value(type(flags), 'audio', 0x02)
        if value:
            flags = flags & ~audio_flag
        else:
            flags = flags | audio_flag
        self.playbin.set_property('flags', flags)
        return False

    def on_state_changed(self, bus, msg):
        """ Callback triggered by playbin state changes.

        Args:
            bus (:class:`~Gst.Bus`): the bus that we are connected to
            msg (:class:`~Gst.Message`): the "state-changed" message
        """
        if msg.src != self.playbin:
            return
        old, new, pending = msg.parse_state_changed()
        if old == Gst.State.READY and new == Gst.State.PAUSED:
            self.on_initial_play()

    def on_initial_play(self):
        """ Set starting position, start scrollbar updates, unhide overlay. """
        if self.start_pos:
            self.do_set_time(self.start_pos)
        GLib.idle_add(self.do_update_duration)
        GLib.timeout_add(self.update_freq, self.do_update_time)
        if not self.media_type.startswith('audio') and not self.use_d3d12_sink:
            self.video_widget.show()
            self.start_frame_tick()

    def do_update_duration(self, *args):
        """ Transmit the change of file duration to the UI to adjust the scroll bar.
        """
        if self.use_d3d12_sink:
            changed, time_ns = D3D12OverlayPlayer.get().query_duration()
        else:
            changed, time_ns = self.playbin.query_duration(Gst.Format.TIME)
        self.update_range(max(0, time_ns) / 1e9)

    def do_update_time(self):
        """ Update the current position in the progress bar.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.timeout_add` convention)
        """
        if self.use_d3d12_sink:
            changed, time_ns = D3D12OverlayPlayer.get().query_position()
            playing = D3D12OverlayPlayer.get().is_playing(self)
        else:
            changed, time_ns = self.playbin.query_position(Gst.Format.TIME)
            playing = self.playbin.get_state(0).state in {Gst.State.PLAYING, Gst.State.PAUSED}
        time = time_ns / 1e9
        self.update_progress(time)
        if self.last_timestamp <= self.end_pos <= time:
            self.handle_end()
        self.last_timestamp = time
        return playing

    def handle_end(self):
        """ End of the stream reached: mark frozen and stop frame tick.
        """
        GLib.idle_add(self.update_audio_meter, 0.0)
        self.is_frozen = True
        self.stop_frame_tick()
        super(GstOverlay, self).handle_end()

    def do_play(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.is_frozen = False
        replay = self.restart_if_ended()
        if self.use_d3d12_sink:
            if replay:
                D3D12OverlayPlayer.get().seek(0)
            return not D3D12OverlayPlayer.get().play(self)
        self.update_gpu_target()
        self.playbin.set_state(Gst.State.PLAYING)
        if replay:
            self.start_frame_tick()
        return False

    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.is_frozen = False
        replay = self.restart_if_ended()
        if self.use_d3d12_sink:
            player = D3D12OverlayPlayer.get()
            if replay:
                player.seek(0)
                player.play(self)
            elif self.is_playing():
                player.pause()
            else:
                player.resume()
            return False
        self.update_gpu_target()
        new_state = Gst.State.PLAYING if replay or not self.is_playing() else Gst.State.PAUSED
        if new_state == Gst.State.PAUSED:
            GLib.idle_add(self.update_audio_meter, 0.0)
        self.playbin.set_state(new_state)
        self.start_frame_tick()
        return False

    def do_pause(self):
        """ Pauses the media, keeping its current frame on screen.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        if self.use_d3d12_sink:
            if self.is_playing() and not self.ended:
                D3D12OverlayPlayer.get().pause()
            return False
        ret, state, pending = self.playbin.get_state(0)
        if (state == Gst.State.PLAYING or pending == Gst.State.PLAYING) and not self.ended:
            GLib.idle_add(self.update_audio_meter, 0.0)
            self.playbin.set_state(Gst.State.PAUSED)
        return False

    def do_stop(self):
        """ Stops playing in the backend player.
        """
        GLib.idle_add(self.update_audio_meter, 0.0)
        if self.preview_resize_timer_id is not None:
            GLib.source_remove(self.preview_resize_timer_id)
            self.preview_resize_timer_id = None
        self.is_frozen = False
        if self.use_d3d12_sink:
            D3D12OverlayPlayer.get().stop()
            return False
        self.stop_frame_tick()
        self.playbin.set_state(Gst.State.NULL)
        self.playbin.set_state(Gst.State.READY)
        self.video_widget.hide()
        return False

    def do_set_time(self, time):
        """ Set the player at time `~time`.

        Should run on the main thread to ensure we avoid reentrency problems.

        Args:
            time (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.last_timestamp = time
        self.ended = False
        if self.use_d3d12_sink:
            D3D12OverlayPlayer.get().seek(time)
        else:
            self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, time * Gst.SECOND)
        return False

    @classmethod
    def setup_backend(cls, gst_opts = []):
        """ Prepare/check the Gst backend.

        Returns:
            `str`: the version of Gst used by the backend
        """
        if getattr(sys, 'frozen', False):
            # Frozen packages bring their own plugins, and must not pick up another install's
            plugins = pathlib.Path(sys.executable).parent.joinpath('lib', 'gstreamer-1.0')
            os.environ['GST_PLUGIN_PATH'] = str(plugins)
            os.environ['GST_PLUGIN_SYSTEM_PATH'] = ''

            cache_dir = pathlib.Path(GLib.get_user_cache_dir(), 'pympress')
            cache_dir.mkdir(parents = True, exist_ok = True)
            os.environ['GST_REGISTRY'] = str(cache_dir.joinpath('gstreamer-registry.bin'))

        Gst.init(gst_opts)

        if Gst.ElementFactory.make('gtksink', None) is None:
            logger.warning('Can not create a gtksink. Check the gtk plugin for GStreamer is installed.')
            logger.warning('See https://github.com/Cimbali/pympress/issues/240')
            raise ValueError('Can not create a gtksink.')

        if os.name == 'nt' and Gst.ElementFactory.find('d3d12videosink') is not None:
            logger.info('GStreamer backend: Direct3D 12 video sink (d3d12videosink) available')

        return Gst.version_string()
