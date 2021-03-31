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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import os
import vlc

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

from pympress.util import IS_WINDOWS
from pympress.media_overlays import base


class VlcOverlay(base.VideoOverlay):
    """ Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which is a :class:`~vlc.MediaPlayer` instance.
    """

    #: A single vlc.Instance() to be shared by (possible) multiple players.
    _instance = None

    def __init__(self, *args, **kwargs):
        self.player = self._instance.media_player_new()  # before loading UI, needed to connect "map" signal

        super(VlcOverlay, self).__init__(*args, **kwargs)

        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached,
                                   lambda e, act=self.action_map.lookup_action('stop'): GLib.idle_add(act.activate))
        event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged,
                                   lambda e: self.update_range(self.player.get_length() / 1000. or 1.))
        event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged,
                                   lambda e: self.update_progress(self.player.get_time() / 1000. or 1.))


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
            self.player.set_hwnd(base.get_window_handle(window))  # get_property('window')
        else:
            self.player.set_xwindow(window.get_xid())
        return False


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        return self.player.is_playing()


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        self.player.set_media(self._instance.media_new(filepath))


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
        self.player.play()
        return False


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.pause() if self.player.is_playing() else self.player.play()
        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.player.stop()


    def do_set_time(self, t):
        """ Set the player at time t.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.set_time(int(round(t * 1000.)))
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
