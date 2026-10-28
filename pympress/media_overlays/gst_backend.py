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
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gst


from pympress import util
from pympress.media_overlays import base


class GstOverlay(base.VideoOverlay):
    """ Simple Gstramer widget.

    Wraps a simple gstreamer playbin.
    """

    #: A :class:`~Gst.Playbin` to be play videos
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

    def __init__(self, *args, **kwargs):
        # Create GStreamer playbin
        self.playbin = Gst.ElementFactory.make('playbin', None)
        self.sink = Gst.ElementFactory.make('gtksink', None)
        self.playbin.set_property('video-sink', self.sink)
        self.setup_gpu_conversion()

        super(GstOverlay, self).__init__(*args, **kwargs)

        self.media_overlay.remove(self.movie_zone)
        self.media_overlay.pack_start(self.sink.props.widget, True, True,  0)
        self.media_overlay.reorder_child(self.sink.props.widget, 0)
        self.sink.props.widget.hide()

        # Create bus to get events from GStreamer playin
        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('message::eos', lambda *args: GLib.idle_add(self.handle_end))
        bus.connect('message::error', lambda _, msg: logger.error('{} {}'.format(*msg.parse_error())))
        bus.connect('message::state-changed', self.on_state_changed)
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
        # The size is set when the caps reach d3d11convert, before it negotiates, and never while playing: gtksink can
        # get stuck on the old size when the size shrinks mid-stream (it reads it back from a frame it still holds).
        video_filter.get_by_name('gpuconvert').get_static_pad('sink').add_probe(
            Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_gpu_convert_event)


    def update_gpu_target(self):
        """ Compute the video widget's size in device pixels from the overlay margins (main thread).

        Runs before playback starts, when the widget is still hidden and not allocated.
        """
        if self.gpu_size_filter is None:
            return
        mo = self.media_overlay
        w = self.parent.get_allocated_width() - mo.props.margin_left - mo.props.margin_right
        h = self.parent.get_allocated_height() - mo.props.margin_top - mo.props.margin_bottom
        if self.toolbar.get_visible():
            h -= self.toolbar.get_preferred_height()[1]
        scale = self.parent.get_scale_factor()
        self.gpu_target = (w * scale, h * scale) if w >= 16 and h >= 16 else None


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

        aw, ah = target
        dar = w * par_n / (h * par_d)
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


    def start_frame_tick(self):
        """ Keep GTK's frame clock running while the video plays (main thread, Windows only).

        When the frame clock only wakes up for gtksink's redraw requests, GTK on Windows misses about one refresh in
        four and drops those frames. A tick callback keeps the clock running on every refresh.
        """
        if os.name != 'nt' or self.frame_tick_id is not None:
            return
        self.frame_tick_id = self.sink.props.widget.add_tick_callback(self.on_frame_tick)


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
            self.sink.props.widget.remove_tick_callback(self.frame_tick_id)
            self.frame_tick_id = None


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        return self.playbin.get_state(0).state == Gst.State.PLAYING


    def _set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`pathlib.Path`): The path to the media file path
        """
        self.playbin.set_property('uri', filepath.as_uri())
        self.playbin.set_state(Gst.State.READY)


    def mute(self, value):
        """ Mutes or unmutes the player.

        Args:
            value (`bool`): `True` iff this player should be muted
        """
        flags = self.playbin.get_property('flags')
        # Fall back to the documented value if introspection fails,
        # see https://gstreamer.freedesktop.org/documentation/playback/playsink.html?gi-language=python#GstPlayFlags
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
            # ignore the playbin's children
            return
        old, new, pending = msg.parse_state_changed()
        if old == Gst.State.READY and new == Gst.State.PAUSED:
            # the playbin goes from READY (= stopped) to PLAYING (via PAUSED)
            self.on_initial_play()


    def on_initial_play(self):
        """ Set starting position, start scrollbar updates, unhide overlay. """
        # set starting position, if needed
        if self.start_pos:
            self.do_set_time(self.start_pos)
        # ensure the scroll bar is updated
        GLib.idle_add(self.do_update_duration)
        GLib.timeout_add(self.update_freq, self.do_update_time)
        # ensure the overlay is visible (if needed)
        if not self.media_type.startswith('audio'):
            self.sink.props.widget.show()
            self.start_frame_tick()


    def do_update_duration(self, *args):
        """ Transmit the change of file duration to the UI to adjust the scroll bar.
        """
        changed, time_ns = self.playbin.query_duration(Gst.Format.TIME)
        self.update_range(max(0, time_ns) / 1e9)


    def do_update_time(self):
        """ Update the current position in the progress bar.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.timeout_add` convention)
        """
        changed, time_ns = self.playbin.query_position(Gst.Format.TIME)
        time = time_ns / 1e9
        self.update_progress(time)
        if self.last_timestamp <= self.end_pos <= time:
            self.handle_end()
        self.last_timestamp = time
        return self.playbin.get_state(0).state in {Gst.State.PLAYING, Gst.State.PAUSED}


    def do_play(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.update_gpu_target()
        self.playbin.set_state(Gst.State.PLAYING)

        return False


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.update_gpu_target()
        self.playbin.set_state(Gst.State.PLAYING if not self.is_playing() else Gst.State.PAUSED)
        self.start_frame_tick()

        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        self.stop_frame_tick()
        self.playbin.set_state(Gst.State.NULL)
        self.playbin.set_state(Gst.State.READY)
        self.sink.props.widget.hide()

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
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, time * Gst.SECOND)
        return False


    @classmethod
    def setup_backend(cls, gst_opts = []):
        """ Prepare/check the Gst backend.

        Returns:
            `str`: the version of Gst used by the backend
        """
        Gst.init(gst_opts)

        if Gst.ElementFactory.make('gtksink', None) is None:
            logger.warning('Can not create a gtksink. Check the gtk plugin for GStreamer is installed.')
            logger.warning('See https://github.com/Cimbali/pympress/issues/240')
            raise ValueError('Can not create a gtksink.')

        return Gst.version_string()
