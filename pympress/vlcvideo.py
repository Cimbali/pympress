#! /usr/bin/python

#
# Vaguely inspred from:
# gtk example/widget for VLC Python bindings
# Copyright (C) 2009-2010 the VideoLAN team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
#

from __future__ import print_function

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject

try:
    gi.require_version('GdkX11', '3.0')
    from gi.repository import GdkX11
except:
    pass

import ctypes
import sys
import vlc

import pympress.util

vlc_opts=[]
if pympress.util.IS_POSIX:
    try:
        x11 = ctypes.cdll.LoadLibrary('libX11.so')
        x11.XInitThreads()
    except:
        vlc_opts.append("--no-xlib")


# Create a single vlc.Instance() to be shared by (possible) multiple players.
instance = vlc.Instance(vlc_opts)
window_handle = None

def get_window_handle(window):
    """ Uses ctypes to call gdk_win32_window_get_handle which is not available
    in python gobject introspection porting (yet ?)
    Solution from http://stackoverflow.com/a/27236258/1387346
    """
    # get the c gpointer of the gdk window
    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
    drawingarea_gpointer = ctypes.pythonapi.PyCapsule_GetPointer(window.__gpointer__, None)
    # get the win32 handle
    gdkdll = ctypes.CDLL("libgdk-3-0.dll")
    return gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)


class VLCVideo(Gtk.VBox):
    """Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which
    is a vlc.MediaPlayer() instance.
    """
    player = None
    overlay = None
    controls = None
    movie_zone = None
    relative_margins = None

    def __init__(self, overlay, show_controls, relative_margins):
        Gtk.VBox.__init__(self)

        self.overlay = overlay
        self.relative_margins = relative_margins
        self.movie_zone = Gtk.DrawingArea()
        self.pack_start(self.movie_zone, True, True, 0)

        if show_controls:
            self.pack_end(self.get_player_control_toolbar(), False, False, 0)

        self.player = instance.media_player_new()
        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.hide)

        def handle_embed(*args):
            global window_handle
            # we need to be on the main thread (espcially for the mess from the win32 window handle)
            #assert isinstance(threading.current_thread(), threading._MainThread)
            if sys.platform == 'win32':
                self.player.set_hwnd(get_window_handle(self.movie_zone.get_window())) # get_property("window")
            else:
                self.player.set_xwindow(self.movie_zone.get_window().get_xid())
            return True

        self.connect("map", handle_embed)

        self.movie_zone.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.movie_zone.connect("button-press-event", self.on_click)

    def get_player_control_toolbar(self):
        """Return a player control toolbar
        """
        tb = Gtk.Toolbar()
        tb.set_style(Gtk.ToolbarStyle.ICONS)
        tb.modify_bg(Gtk.StateType.NORMAL, Gdk.Color(0, 0, 0))
        for text, tooltip, stock, callback in (
            ("Play", "Play", Gtk.STOCK_MEDIA_PLAY, lambda b: self.player.play()),
            ("Pause", "Pause", Gtk.STOCK_MEDIA_PAUSE, lambda b: self.player.pause()),
            ("Stop", "Stop", Gtk.STOCK_MEDIA_STOP, lambda b: self.player.stop()),
        ):
            b=Gtk.ToolButton(stock)
            b.set_tooltip_text(tooltip)
            b.connect("clicked", callback)
            tb.insert(b, -1)
        return tb

    def resize(self):
        parent = self.get_parent()
        if not parent:
            return
        pw, ph = parent.get_allocated_width(), parent.get_allocated_height()
        self.props.margin_left   = pw * self.relative_margins.x1
        self.props.margin_right  = pw * self.relative_margins.x2
        self.props.margin_bottom = ph * self.relative_margins.y1
        self.props.margin_top    = ph * self.relative_margins.y2

    def set_file(self, filepath):
        self.player.set_media(instance.media_new(filepath))

    def play(self):
        if not self.get_parent():
            self.overlay.add_overlay(self)
            self.resize()
            self.overlay.show_all()
        if self.player.get_state() == vlc.State.Ended:
            self.player.stop()
        self.player.play()

    def on_click(self, widget, event):
        if not self.get_parent():
            # How was this even clicked on?
            return
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if self.player.is_playing():
                self.player.pause()
            else:
                self.player.play()
        elif event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.player.set_time(0) # en ms

    def stop_and_remove(self):
        if self.player.is_playing():
            self.player.stop()
        self.hide()

    def hide(self, *args):
        if self.get_parent():
            self.overlay.remove(self)

