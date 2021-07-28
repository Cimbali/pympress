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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst


from pympress.media_overlays import base


class GstOverlay(base.VideoOverlay):
    """ Simple Gstramer widget.

    Wraps a simple gstreamer playbin.
    """

    #: A :class:`~Gst.Playbin` to be play videos
    playbin = None

    #: `str` holding the path to the current file
    uri = None

    def __init__(self, *args, **kwargs):
        super(GstOverlay, self).__init__(*args, **kwargs)

        # Create GStreamer playbin
        self.playbin = Gst.ElementFactory.make('playbin', None)
        self.sink = Gst.ElementFactory.make('gtksink', None)
        self.playbin.set_property('video-sink', self.sink)

        self.media_overlay.remove(self.movie_zone)
        self.media_overlay.pack_start(self.sink.props.widget, True, True,  0)
        self.media_overlay.reorder_child(self.sink.props.widget, 0)
        self.sink.props.widget.show()

        # Create bus to get events from GStreamer playin
        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('message::eos', lambda *args: GLib.idle_add(self.do_hide))
        bus.connect('message::error', lambda _, msg: logger.error('{} {}'.format(*msg.parse_error())))
        bus.connect('message::async-done', self.on_play)
        bus.connect('message::duration-changed', lambda *args: GLib.idle_add(self.do_update_duration))


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        return self.playbin.get_state(0).state == Gst.State.PLAYING


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        self.uri = 'file://' + filepath


    def mute(self, value):
        """ Mutes or unmutes the player.

        Args:
            value (`bool`): `True` iff this player should be muted
        """
        self.playbin.set_property('mute', value)
        return False


    def on_play(self, *args):
        """ Start the scroll bar updating process.
        """
        GLib.idle_add(self.do_update_duration)
        GLib.timeout_add(200, self.do_update_time)


    def do_update_duration(self, *args):
        """ Transmit the change of file duration to the UI to adjust the scroll bar.
        """
        changed, time_ns = self.playbin.query_duration(Gst.Format.TIME)
        self.update_range(max(0, time_ns) / 1e9)


    def do_update_time(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        changed, time_ns = self.playbin.query_position(Gst.Format.TIME)
        self.update_progress(time_ns / 1e9)
        return True


    def do_play(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.playbin.set_property('uri', self.uri)
        self.playbin.set_state(Gst.State.PLAYING)

        return False


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.playbin.set_state(Gst.State.PLAYING if not self.is_playing() else Gst.State.PAUSED)

        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.playbin.set_state(Gst.State.NULL)

        return False


    def do_set_time(self, t):
        """ Set the player at time t.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, t * Gst.SECOND)
        return False


    @classmethod
    def setup_backend(cls, gst_opts = []):
        """ Prepare/check the Gst backend.

        Returns:
            `str`: the version of Gst used by the backend
        """
        Gst.init(gst_opts)

        return Gst.version_string()
