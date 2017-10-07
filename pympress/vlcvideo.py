#       document.py
#
#       Copyright 2015 Cimbali <me@cimba.li>
#
#       Vaguely inspired from:
#       gtk example/widget for VLC Python bindings
#       Copyright (C) 2009-2010 the VideoLAN team
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
:mod:`pympress.vlcvideo` -- widget to play videos with VLC backend
------------------------------------------------------------------
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GLib

try:
    gi.require_version('GdkX11', '3.0')
    from gi.repository import GdkX11
except:
    pass

import ctypes
import sys, os
import vlc

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS

vlc_opts=['--no-video-title-show']
if IS_POSIX:
    vlc_opts.append('--no-xlib')

if IS_WINDOWS and vlc.plugin_path:
    # let python find the DLLs
    os.environ['PATH'] = vlc.plugin_path + ';' + os.environ['PATH']

#: A single vlc.Instance() to be shared by (possible) multiple players.
instance = vlc.Instance(vlc_opts)

def get_window_handle(window):
    """ Uses ctypes to call gdk_win32_window_get_handle which is not available
    in python gobject introspection porting (yet ?)
    Solution from http://stackoverflow.com/a/27236258/1387346

    Args:
        window (:class:`~Gdk.Window`): The window for which we want to get the handle

    Returns:
        The handle to the win32 window
    """
    # get the c gpointer of the gdk window
    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
    drawingarea_gpointer = ctypes.pythonapi.PyCapsule_GetPointer(window.__gpointer__, None)
    # get the win32 handle
    gdkdll = ctypes.CDLL('libgdk-3-0.dll')
    return gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)


class VLCVideo(Gtk.VBox):
    """ Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which
    is a vlc.MediaPlayer() instance.

    Args:
        overlay (:class:`~Gtk.Overlay`): The overlay with the slide, at the top of which we add the movie area
        show_controls (`bool`): whether to display controls on the video player
        relative_margins (:class:`~Poppler.Rectangle`): the margins defining the position of the video in the frame.
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

        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)

        if show_controls:
            self.pack_end(self.get_player_control_toolbar(), False, False, 0)

        self.player = instance.media_player_new()
        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda e: GLib.idle_add(self.hide))

        def handle_embed(*args):
            # Do we need to be on the main thread? (especially for the mess from the win32 window handle)
            #assert(isinstance(threading.current_thread(), threading._MainThread))
            if sys.platform == 'win32':
                self.player.set_hwnd(get_window_handle(self.movie_zone.get_window())) # get_property('window')
            else:
                self.player.set_xwindow(self.movie_zone.get_window().get_xid())
            return True

        self.connect('map', handle_embed)

        self.movie_zone.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.movie_zone.connect('button-press-event', self.on_click)


    def get_player_control_toolbar(self):
        """ Return a player control toolbar.
        """
        tb = Gtk.Toolbar()
        tb.set_style(Gtk.ToolbarStyle.ICONS)
        tb.modify_bg(Gtk.StateType.NORMAL, Gdk.Color(0, 0, 0))
        for text, tooltip, stock, callback in (
            ('Play', 'Play', Gtk.STOCK_MEDIA_PLAY, lambda b: self.play()),
            ('Pause', 'Pause', Gtk.STOCK_MEDIA_PAUSE, lambda b: self.pause()),
            ('Stop', 'Stop', Gtk.STOCK_MEDIA_STOP, lambda b: GLib.idle_add(self.hide)),
        ):
            b=Gtk.ToolButton(stock)
            b.set_tooltip_text(tooltip)
            b.connect('clicked', callback)
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
        """ Sets the media file to be played bu the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        GLib.idle_add(self.player.set_media, instance.media_new(filepath))


    def play(self):
        """ Start playing the media file.
        Bring the widget to the top of the overlays if necessary.
        """
        self.movie_zone.show()
        if not self.get_parent():
            self.overlay.add_overlay(self)
            self.overlay.reorder_overlay(self, 2)
            self.set_halign(Gtk.Align.FILL)
            self.set_valign(Gtk.Align.FILL)
            self.resize()
            self.overlay.show_all()
        GLib.idle_add(self.player.play)


    def on_click(self, widget, event):
        """ React to click events by playing or pausing the media.

        Args:
            widget (:class:`~Gtk.Widget`): the widget which has received the click.
            event (:class:`~Gdk.Event`): the GTK event containing the position.
        """
        if not self.get_parent():
            # How was this even clicked on?
            return

        if event.type == Gdk.EventType.BUTTON_PRESS:
            GLib.idle_add(lambda p: p.pause() if p.is_playing() else p.play(), self.player)
        elif event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            GLib.idle_add(self.player.set_time, 0) # in ms


    def hide(self, *args):
        """ Remove widget from overlays. Needs to be callded via GLib.idle_add
        """
        self.player.stop()
        self.movie_zone.hide()

        if self.get_parent():
            self.overlay.remove(self)

