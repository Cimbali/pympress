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
:mod:`pympress.media_overlays.gst` -- widget to play videos using Gstreamer's GstPlayer
---------------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
gi.require_version('GstPlayer', '1.0')
from gi.repository import GLib, Gst, GstPlayer


from pympress.util import IS_WINDOWS
from pympress.media_overlays import base


class GstOverlay(base.VideoOverlay):
    """ Simple Gstramer widget.

    Its player can be controlled through the 'player' attribute, which is a :class:`~GstPlayer.Player` instance.
    """

    #: A :class:`~GstPlayer.Player` to be play videos
    player = None

    #: A :class:`~GstPlayer.PlayerVideoOverlayVideoRenderer` to be display the videos
    renderer = None

    # A :class:`~GstPlayer.PlayerState` representing the current state of the player
    player_state = GstPlayer.PlayerState.STOPPED

    def __init__(self, *args, **kwargs):
        super(GstOverlay, self).__init__(*args, **kwargs)


    def track_state(self, player, state):
        """ Update the current state of the player for easy reference.

        Args:
            player (:class:`~GstPlayer.Player`): The player for which the position changed
            state (:class:`~GstPlayer.PlayerState`): The player's new state
        """
        self.player_state = state
        if not self.is_playing() and self.renderer:
            self.renderer.expose()


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        return self.player_state == GstPlayer.PlayerState.PLAYING


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        self.uri = 'file://' + filepath


    def mute(self, value):
        """ Mutes the player.

        Args:
            value (`bool`): `True` iff this player should be muted
        """
        self.muted = value
        return False


    def do_play(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.renderer = GstPlayer.PlayerVideoOverlayVideoRenderer()
        self.player = GstPlayer.Player.new(self.renderer)
        self.player.set_uri(self.uri)
        self.player.set_mute(self.muted)

        self.player.connect('state-changed', self.track_state)
        self.player.connect('duration-changed', lambda p, ns: self.update_range(ns / 1e9))
        self.player.connect('position-updated', lambda p, ns: self.update_progress(ns / 1e9))

        stop_action = self.action_map.lookup_action('stop')
        self.player.connect('end-of-stream', lambda e, act=stop_action: GLib.idle_add(act.activate))

        window = self.movie_zone.get_window()
        if self.renderer.get_window_handle():
            pass
        elif window is None:
            logger.error('No window in which to embed the Gst player!')
            return False
        elif IS_WINDOWS:
            # TODO test in windows
            # get_property('window')
            self.renderer.set_window_handle(base.get_window_handle(window))
        else:
            self.renderer.set_window_handle(window.get_xid())

        self.player.play()
        return False


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.pause() if self.is_playing() else self.player.play()
        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.player.stop()
        self.player = None
        self.renderer = None


    def do_set_time(self, t):
        """ Set the player at time t.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.seek(int(t * 1e9))
        return False


    @classmethod
    def setup_backend(cls, gst_opts = []):
        """ Prepare/check the Gst backend.

        Returns:
            `str`: the version of Gst used by the backend
        """
        Gst.init(gst_opts)

        return Gst.version_string()
