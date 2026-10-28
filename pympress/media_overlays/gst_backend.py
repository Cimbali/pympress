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
    #: native clip dimensions and display aspect ratio from the decoder
    clip_w = None
    clip_h = None
    clip_dar = None
    #: pending timer id for debounced dynamic preview scaling
    preview_resize_timer_id = None
    #: whether playback has reached its end and is holding the last frame
    is_frozen = False

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
        video_filter.get_by_name('gpuconvert').get_static_pad('sink').add_probe(
            Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_gpu_convert_event)
        if self.sink.find_property('widget') is not None:    # not every sink has a widget to follow
            self.sink.props.widget.connect('size-allocate', self.on_video_widget_allocated)
        # The size is set when the caps reach d3d11convert, before it negotiates. While playing it only grows (see
        # on_video_widget_allocated): gtksink can get stuck on the old size when the size shrinks mid-stream.


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

        # Repaint if paused or frozen at EOS
        ret, state, pending = self.playbin.get_state(0)
        is_actively_playing = (state == Gst.State.PLAYING and pending != Gst.State.PAUSED and not self.is_frozen)
        if not is_actively_playing:
            if self.is_frozen:
                self.playbin.set_state(Gst.State.PAUSED)
            ok_pos, pos = self.playbin.query_position(Gst.Format.TIME)
            ok_dur, dur = self.playbin.query_duration(Gst.Format.TIME)
            seek_pos = pos if ok_pos and pos > 0 else int(self.last_timestamp * Gst.SECOND)
            if ok_dur and dur > 0:
                # a position at the very end has no frame left to decode: stay inside the last frame
                seek_pos = min(seek_pos, max(0, dur - 5 * Gst.MSECOND))
            self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, seek_pos)

        return False


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


    def handle_end(self):
        """ End of the stream reached: mark frozen and stop frame tick.
        """
        self.is_frozen = True
        self.stop_frame_tick()
        super(GstOverlay, self).handle_end()


    def do_play(self):
        """ Start playing the media file.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.is_frozen = False
        self.update_gpu_target()
        self.playbin.set_state(Gst.State.PLAYING)

        return False


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.is_frozen = False
        self.update_gpu_target()
        self.playbin.set_state(Gst.State.PLAYING if not self.is_playing() else Gst.State.PAUSED)
        self.start_frame_tick()

        return False


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        if self.preview_resize_timer_id is not None:
            GLib.source_remove(self.preview_resize_timer_id)
            self.preview_resize_timer_id = None
        self.is_frozen = False
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
