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


#: Keep the movie zone (VLC's video window) hidden until VLC has presented its first frame, and hide it before the
#: player is stopped and the window destroyed. On Windows this removes the flash (desktop, black or white showing
#: through the slide for 100-250 ms) when a video slide opens or closes. Not tested on other platforms.
HIDE_UNTIL_FIRST_FRAME = IS_WINDOWS
#: Delay (ms) between VLC's first time change event and showing the movie zone
REVEAL_DELAY_MS = 30
#: If VLC sends no time change event within this delay (ms), show the movie zone anyway, unless VLC is still starting
#: (opening, buffering, or playing before its first frame): then check again after the same delay
REVEAL_TIMEOUT_MS = 1500
#: Delay (ms) between hiding the movie zone and stopping the player and removing the overlay
REMOVE_DELAY_MS = 150


class VlcOverlay(base.VideoOverlay):
    """ Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which is a :class:`~vlc.MediaPlayer` instance.
    """

    #: A single vlc.Instance() to be shared by (possible) multiple players.
    _instance = None
    #: `bool` that tracks whether the movie zone is hidden until VLC presents its first frame
    _reveal_pending = False
    #: `int` incremented to cancel a scheduled reveal of the movie zone
    _reveal_gen = 0
    #: `int` incremented to cancel a scheduled removal of the overlay
    _remove_gen = 0

    def __init__(self, *args, **kwargs):
        self.player = self._instance.media_player_new()  # before loading UI, needed to connect "map" signal

        super(VlcOverlay, self).__init__(*args, **kwargs)
        # Simple black background painting to avoid glitching outside of video area
        if not self.media_type.startswith('audio'):
            self.movie_zone.connect('draw', self.paint_backdrop)

        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda e: GLib.idle_add(self.handle_end))
        # VLC calls these handlers from its own threads: anything touching GTK goes through GLib.idle_add
        event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged,
                                   lambda e: GLib.idle_add(self.update_range, self.player.get_length() / 1000. or 1.))
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

        if HIDE_UNTIL_FIRST_FRAME and not self.media_type.startswith('audio'):
            # While the zone is hidden, GTK paints the slide (whose first frame matches the video) in its place.
            # Hiding it through GTK matters: if only the native window is hidden, GTK still leaves that area unpainted.
            self.movie_zone.set_child_visible(False)
            self._reveal_pending = True
            self._reveal_gen += 1
            GLib.timeout_add(REVEAL_TIMEOUT_MS, self.reveal, self._reveal_gen)

        self.movie_zone.queue_draw()
        return False


    def reveal(self, gen):
        """ Show the movie zone once VLC presents frames in it. Runs on the main thread.

        Args:
            gen (`int`): the value of :attr:`~_reveal_gen` when the reveal was scheduled

        Returns:
            `bool`: `False` (:func:`~GLib.timeout_add` convention)
        """
        if gen == self._reveal_gen:
            if self._reveal_pending and self.player.get_state() in {vlc.State.Opening, vlc.State.Buffering,
                                                                    vlc.State.Playing}:
                # VLC can take seconds to start (first video after a reboot): showing the zone before VLC presents
                # its first frame puts the black backdrop over the slide. Keep showing the slide and check again.
                GLib.timeout_add(REVEAL_TIMEOUT_MS, self.reveal, gen)
                return False
            self._reveal_gen += 1
            self._reveal_pending = False
            if self.is_shown():
                self.movie_zone.set_child_visible(True)
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
        self.player.set_media(self._instance.media_new(filepath.resolve().as_uri()))


    def handle_end(self):
        """ End of the stream reached: restart if looping, otherwise hide overlay

        Overridden because, to implement looping, vlc plugin needs to be told to start on stream end, not to seek
        """
        if self.repeat:
            self.action_map.lookup_action('play').activate()
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

        if self._reveal_pending:
            # GTK can map the zone again after handle_embed: hide it before VLC creates its video window
            self.movie_zone.set_child_visible(False)

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
        if HIDE_UNTIL_FIRST_FRAME:
            self._remove_gen += 1
            # do_hide() left the zone child-invisible: it needs its window again for handle_embed()
            self.movie_zone.set_child_visible(True)
        super(VlcOverlay, self).show()
        self.movie_zone.queue_draw()


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.pause() if self.player.is_playing() else self.player.play()
        return False


    def do_hide(self, *args):
        """ Remove widget from overlays. Needs to be called via :func:`~GLib.idle_add`.

        With :data:`HIDE_UNTIL_FIRST_FRAME`, the movie zone is hidden through GTK first, so that GTK paints the next
        slide in its place, and the player is stopped and the overlay removed a little later. Removing the zone at
        once leaves its area without valid pixels until GTK repaints it.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        if not HIDE_UNTIL_FIRST_FRAME or self.media_type.startswith('audio'):
            return super(VlcOverlay, self).do_hide(*args)

        if self.media_overlay.get_parent() is None:
            return False

        self._reveal_gen += 1
        self._reveal_pending = False
        self.movie_zone.set_child_visible(False)
        # The slide was usually redrawn before this idle callback ran, skipping the area under the (still mapped) zone.
        # Repaint that area now: otherwise the previous slide's page shows there until the next frame.
        window = self.parent.get_window()
        if window is not None:
            window.process_updates(True)
        self._remove_gen += 1
        GLib.timeout_add(REMOVE_DELAY_MS, self._remove_after_hide, self._remove_gen)
        return False


    def _remove_after_hide(self, gen):
        """ Stop the player and remove the overlay, unless it was shown again in the meantime.

        Args:
            gen (`int`): the value of :attr:`~_remove_gen` when the removal was scheduled

        Returns:
            `bool`: `False` (:func:`~GLib.timeout_add` convention)
        """
        if gen == self._remove_gen:
            super(VlcOverlay, self).do_hide()
        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.player.stop()


    def time_changed(self, event):
        """ Handle time passing.

        Called from a VLC thread, so the work is done by :meth:`~do_time_changed` on the main thread: GTK is not
        thread-safe, and updating the progress bar from here can corrupt memory.

        Args:
            event (:class:`~vlc.Event`): The event that triggered the handler
        """
        if self._reveal_pending:
            # VLC thread: frames are being presented, reveal the zone from the main thread
            self._reveal_pending = False
            GLib.timeout_add(REVEAL_DELAY_MS, self.reveal, self._reveal_gen)

        GLib.idle_add(self.do_time_changed, self.player.get_time() / 1000. or 1.)


    def do_time_changed(self, time):
        """ Update the progress bar and stop at the end position. Runs on the main thread.

        Args:
            time (`float`): The current time in the video in s

        Returns:
            `bool`: `False` (:func:`~GLib.idle_add` convention)
        """
        if self.last_timestamp <= self.end_pos <= time:
            self.handle_end()
        self.last_timestamp = time
        self.update_progress(time)
        return False


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
