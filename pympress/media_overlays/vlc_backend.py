# -*- coding: utf-8 -*-
#
#       media_overlays/vlc.py
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
:mod:`pympress.media_overlays.vlc` -- widget to play videos using VLC
---------------------------------------------------------------------
"""

import logging
logger = logging.getLogger(__name__)

import os
import vlc
import ctypes

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

from pympress.util import IS_WINDOWS
from pympress.media_overlays import base

#: How close (ms) to the end of the video a paused player must be, to count as having ended
PAUSED_AT_END_MS = 300


def get_window_handle(window):
    """ Uses ctypes to call gdk_win32_window_get_handle which is not available in python gobject introspection porting.

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
    handle_getter = gdkdll.gdk_win32_window_get_handle
    handle_getter.restype = ctypes.c_void_p
    handle_getter.argtypes = [ctypes.c_void_p]
    return handle_getter(drawingarea_gpointer)


class VlcOverlay(base.VideoOverlay):
    """ Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which is a :class:`~vlc.MediaPlayer` instance.
    """

    #: A single vlc.Instance() to be shared by (possible) multiple players.
    _instance = None

    def __init__(self, *args, **kwargs):
        self.player = self._instance.media_player_new()  # before loading UI, needed to connect "map" signal

        super(VlcOverlay, self).__init__(*args, **kwargs)
        # Simple black background painting to avoid glitching outside of video area
        if not self.media_type.startswith('audio'):
            self.movie_zone.connect('draw', self.paint_backdrop)

        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda e: GLib.idle_add(self.handle_end))
        event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged,
                                   lambda e: self.update_range(self.player.get_length() / 1000. or 1.))
        event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged, self.time_changed)


    def handle_embed(self, mapped_widget):
        """ Handler to embed the VLC player in the window, connected to the :attr:`~.Gtk.Widget.signals.map` signal.
        """
        # Do we need to be on the main thread? (especially for the mess from the win32 window handle)
        # assert(isinstance(threading.current_thread(), threading._MainThread))
        window = self.movie_zone.get_window()
        if window is None:
            logger.error('No window in which to embed the VLC player!')
            return False
        elif IS_WINDOWS:
            self.player.set_hwnd(get_window_handle(window))  # get_property('window')
        else:
            self.player.set_xwindow(window.get_xid())
        self.movie_zone.queue_draw()
        return False


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        return self.player.is_playing()


    def _set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`pathlib.Path`): The path to the media file path
        """
        media = self._instance.media_new(filepath.resolve().as_uri())
        if self.end_action == 'loop' and not self.repeat:
            # VLC repeats the input itself: restarting the player at its end closes and reopens the video output,
            # which shows black between two loops
            media.add_option(':input-repeat=65535')
        elif self.end_action == 'freeze' and not self.repeat:
            # VLC pauses on the last frame instead of ending: an ended player has no video output left, so playing
            # it again would close VLC's window and open a new one, which shows black in between
            media.add_option(':play-and-pause')
        self.player.set_media(media)


    def handle_end(self):
        """ End of the stream reached: restart if looping, otherwise hide overlay

        Overridden because, to implement looping, vlc plugin needs to be told to start on stream end, not to seek
        """
        if self.repeat:
            self.action_map.lookup_action('play').activate()
        elif self.end_action == 'freeze':
            # VLC pauses on the last frame (:play-and-pause) and keeps showing it until the player is stopped (when
            # the slide changes) or played again
            pass
        else:
            self.action_map.lookup_action('stop').activate()


    def mute(self, value):
        """ Mutes the player.

        Args:
            value (`bool`): `True` iff this player should be muted
        """
        GLib.idle_add(self.player.audio_set_volume, 0 if value else 100)
        return False


    def do_play(self):
        """ Start playing the media file.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        play_from_state = self.player.get_state()
        if play_from_state in {vlc.State.Ended, vlc.State.Playing}:
            self.player.stop()
            play_from_state = vlc.State.Stopped
            self.ended = False
        else:
            self.ended = self.ended or self.is_paused_at_end()
            self.restart_if_ended()

        self.player.play()

        if play_from_state in {vlc.State.NothingSpecial, vlc.State.Stopped}:
            self.do_set_time(self.start_pos)

        self.movie_zone.queue_draw()
        return False


    def paint_backdrop(self, widget, context):
        """ Draw behind/around the video, aka the black bars

        Args:
            widget (:class:`~Gtk.Widget`):  the widget to update
            context (:class:`~cairo.Context`):  the Cairo context (or `None` if called directly)
        """
        context.save()
        context.set_source_rgb(0, 0, 0)
        context.fill()
        context.paint()
        context.restore()


    def show(self):
        """ Bring the widget to the top of the overlays if necessary − also force redraw of movie zone
        """
        super(VlcOverlay, self).show()
        self.movie_zone.queue_draw()


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        if self.ended or self.is_paused_at_end():
            return self.do_play()

        self.player.pause() if self.player.is_playing() else self.player.play()
        return False


    def is_paused_at_end(self):
        """ Returns whether the player sits on the last frame of the video, where `:play-and-pause` leaves it.

        VLC sends no end event then, as the input is paused instead of ending.

        Returns:
            `bool`: `True` iff the player is paused within a fraction of a second of the end of the video.
        """
        length = self.player.get_length()
        return (self.end_action == 'freeze' and self.player.get_state() == vlc.State.Paused and length > 0 and
                self.player.get_time() >= min(length, self.end_pos * 1000.) - PAUSED_AT_END_MS)


    def do_pause(self):
        """ Pauses the media, keeping its current frame on screen.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        if self.player.is_playing() and not self.ended:
            self.player.set_pause(1)
        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.player.stop()


    def time_changed(self, event):
        """ Handle time passing

        Args:
            event (:class:`~vlc.Event`): The event that triggered the handler
        """
        time = self.player.get_time() / 1000. or 1.
        if self.last_timestamp <= self.end_pos <= time:
            self.handle_end()
        self.last_timestamp = time
        self.update_progress(time)


    def do_set_time(self, time):
        """ Set the player at time `~time`.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            `~time` (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        # Update last_timestamp first, as seeking should bypass auto stop after duration
        self.last_timestamp = time
        self.ended = False
        self.player.set_time(int(round(time * 1000.)))
        return False


    @classmethod
    def setup_backend(cls, vlc_opts = ['--no-video-title-show']):
        """ Prepare/check the VLC backend.

        Args:
            vlc_opts (`list`): the arguments for starting vlc

        Returns:
            `str`: the version of VLC used by the backend
        """
        if IS_WINDOWS and vlc.plugin_path:
            # let python find the DLLs
            os.environ['PATH'] = vlc.plugin_path + ';' + os.environ['PATH']

        VlcOverlay._instance = vlc.Instance(vlc_opts)
        return 'VLC {}'.format(vlc.libvlc_get_version().decode('ascii'))
