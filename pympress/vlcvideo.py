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

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GObject, GdkX11

import ctypes
import sys
import vlc

# Create a single vlc.Instance() to be shared by (possible) multiple players.
instance = vlc.Instance()
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
    gdkdll = ctypes.CDLL ("libgdk-3-0.dll")
    return gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)

class VLCVideo(Gtk.DrawingArea):
    """Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which
    is a vlc.MediaPlayer() instance.
    """
    player = None
    overlay = None

    def __init__(self, overlay):
        Gtk.DrawingArea.__init__(self)

        self.overlay = overlay

        self.player = instance.media_player_new()
        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.hide)

        def handle_embed(*args):
            global window_handle
            # we need to be on the main thread (espcially for the mess from the win32 window handle)
            #assert isinstance(threading.current_thread(), threading._MainThread)
            if sys.platform == 'win32':
                self.player.set_hwnd(get_window_handle(self.get_window())) # get_property("window")
            else:
                self.player.set_xwindow(self.get_window().get_xid())
            return True

        self.connect("map", handle_embed)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_click)

    def set_file(self, filepath):
        self.player.set_media(instance.media_new(filepath))

    def preview(self):
        if not self.get_parent():
            self.overlay.add_overlay(self)
            self.overlay.show_all()
        self.player.next_frame()

    def play(self):
        if not self.get_parent():
            self.overlay.add_overlay(self)
            self.overlay.show_all()
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
            if self.player.is_playing():
                self.player.set_time(0) # en ms
            else:
                self.player.play()

    def stop_and_remove(self):
        if self.player.is_playing():
            self.player.stop()
        self.hide()

    def hide(self, *args):
        if self.get_parent():
            self.overlay.remove(self)

