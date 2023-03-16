# -*- coding: utf-8 -*-
#
#       media_overlays/base.py
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
:mod:`pympress.media_overlays.base` -- base widget to play videos with an unspecified backend
---------------------------------------------------------------------------------------------
"""

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio

from pympress import builder


class VideoOverlay(builder.Builder):
    """ Simple Video widget.

    All do_X() functions are meant to be called from the main thread, through e.g. :func:`~GLib.idle_add`,
    for thread-safety in the handling of video backends.

    Args:
        container (:class:`~Gtk.Overlay`): The container with the slide, at the top of which we add the movie area
        page_type (:class:`~pympress.document.PdfPage`): the part of the page to display
        action_map (:class:`~Gio.ActionMap`): the action map that contains the actions for this media
        media (:class:`~pympress.document.Media`): the object defining the properties of the video such as position etc.
    """
    #: :class:`~Gtk.Overlay` that is the parent of the VideoOverlay widget.
    parent = None
    #: :class:`~Gtk.VBox` that contains all the elements to be overlayed.
    media_overlay = None
    #: A :class:`~Gtk.HBox` containing a toolbar with buttons and :attr:`~progress` the progress bar
    toolbar = None
    #: :class:`~Gtk.Scale` that is the progress bar in the controls toolbar - if we have one.
    progress = None
    #: :class:`~Gtk.DrawingArea` where the media is rendered.
    movie_zone = None
    #: `tuple` containing the left/top/right/bottom space around the drawing area in the PDF page
    relative_page_margins = None
    #: `tuple` containing the left/top/right/bottom space around the drawing area in the visible slide
    relative_margins = None
    #: `bool` that tracks whether we should play automatically
    autoplay = False
    #: `bool` that tracks whether we should play after we finished playing
    repeat = False
    #: `str` representing the mime type of the media file
    media_type = ''
    #: `float` giving the initial starting position for playback
    start_pos = 0.
    #: `float` giving the end position for playback, if any
    end_pos = None
    #: `float` representing the last know timestamp at which the progress bar updated
    last_timestamp = 0.

    #: `bool` that tracks whether the user is dragging the position
    dragging_position = False
    #: `bool` that tracks whether the playback was paused when the user started dragging the position
    dragging_paused = False
    #: Format of the video time, defaults to m:ss, changed to m:ss / m:ss when the max time is known
    time_format = '{:01}:{:02}'
    #: `float` holding the max time in s
    maxval = 1

    #: :class:`~Gio.ActionMap` containing the actios for this video overlay
    action_map = None

    def __init__(self, container, page_type, action_map, media):
        super(VideoOverlay, self).__init__()

        self.parent = container
        self.relative_page_margins = tuple(getattr(media.relative_margins, v) for v in ('x1', 'y2', 'x2', 'y1'))
        self.update_margins_for_page(page_type)

        self.load_ui('media_overlay')
        self.toolbar.set_visible(media.show_controls)

        self.connect_signals(self)

        # medias, here the actions are scoped to the current widget
        self.action_map = action_map
        self.media_overlay.insert_action_group('media', self.action_map)
        if media.type:
            self.media_type = media.type
        else:
            content_type, uncertain = Gio.content_type_guess(media.filename.as_uri())
            self.media_type = Gio.content_type_get_mime_type(content_type)
        self.start_pos = media.start_pos
        self.end_pos = float('inf') if media.duration == 0 else media.start_pos + media.duration
        self._set_file(media.filename)

        self.autoplay = media.autoplay
        self.repeat = media.repeat
        # TODO: handle poster


    def handle_embed(self, mapped_widget):
        """ Handler to embed the video player in the window, connected to the :attr:`~.Gtk.Widget.signals.map` signal.
        """
        return False


    def format_millis(self, sc, prog):
        """ Callback to format the current timestamp (in milliseconds) as minutes:seconds.

        Args:
            sc (:class:`~Gtk.Scale`): The scale whose position we are formatting
            prog (`float`): The position of the :class:`~Gtk.Scale`, i.e. the number of seconds elapsed
        """
        return self.time_format.format(*divmod(int(round(prog)), 60))


    def update_range(self, max_time):
        """ Update the toolbar slider size.

        Args:
            max_time (`float`): The maximum time in this video in s
        """
        self.maxval = max_time
        self.progress.set_range(0, self.maxval)
        self.progress.set_increments(min(5., self.maxval / 10.), min(60., self.maxval / 10.))
        sec = round(self.maxval) if self.maxval > .5 else 1.
        self.time_format = '{{:01}}:{{:02}} / {:01}:{:02}'.format(*divmod(int(sec), 60))


    def update_progress(self, time):
        """ Update the toolbar slider to the current time.

        Args:
            time (`float`): The time in this video in s
        """
        self.progress.set_value(time)


    def progress_moved(self, rng, sc, val):
        """ Callback to update the position of the video when the user moved the progress bar.

        Args:
            rng (:class:`~Gtk.Range`): The range corresponding to the scale whose position we are formatting
            sc (:class:`~Gtk.Scale`): The scale whose position we are updating
            val (`float`): The position of the :class:`~Gtk.Scale`, which is the number of seconds elapsed in the video
        """
        return self.action_map.lookup_action('set_time').activate(GLib.Variant.new_double(val))


    def play_pause(self, *args):
        """ Callback to toggle play/pausing from clicking on the DrawingArea
        """
        return self.action_map.lookup_action('pause').activate()


    def handle_end(self):
        """ End of the stream reached: restart if looping, otherwise hide overlay
        """
        if not self.repeat:
            self.action_map.lookup_action('stop').activate()
        else:
            self.action_map.lookup_action('set_time').activate(GLib.Variant.new_double(self.start_pos))


    def update_margins_for_page(self, page_type):
        """ Recalculate the margins around the media in the event of a page type change.

        Arguments:
            page_type (:class:`~pympress.document.PdfPage`): the part of the page to display
        """
        self.relative_margins = page_type.to_screen(*self.relative_page_margins)


    def resize(self):
        """ Adjust the position and size of the media overlay.
        """
        if not self.is_shown():
            return

        pw, ph = self.parent.get_allocated_width(), self.parent.get_allocated_height()
        self.media_overlay.props.margin_left   = pw * max(self.relative_margins[0], 0)
        self.media_overlay.props.margin_right  = pw * max(self.relative_margins[2], 0)
        self.media_overlay.props.margin_bottom = ph * max(self.relative_margins[3], 0)
        self.media_overlay.props.margin_top    = ph * max(self.relative_margins[1], 0)


    def is_shown(self):
        """ Returns whether the media overlay is currently added to the overlays, or hidden.

        Returns:
            `bool`: `True` iff the overlay is currently displayed.
        """
        return self.media_overlay.get_parent() is not None


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        raise NotImplementedError


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        raise NotImplementedError


    def _set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`pathlib.Path`): The path to the media file path
        """
        raise NotImplementedError


    def show(self):
        """ Bring the widget to the top of the overlays if necessary.
        """
        if min(self.relative_margins) < 0:
            logger.warning('Negative margin(s) clipped to 0 (might alter the aspect ratio?): ' +
                           'LTRB = {}'.format(self.relative_margins))

        if not self.media_overlay.get_parent():
            self.parent.add_overlay(self.media_overlay)
            self.parent.reorder_overlay(self.media_overlay, 2)
            self.resize()
            self.parent.queue_draw()
        self.media_overlay.show()


    def do_hide(self, *args):
        """ Remove widget from overlays. Needs to be called via :func:`~GLib.idle_add`.

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.do_stop()
        self.media_overlay.hide()

        if self.media_overlay.get_parent():
            self.parent.remove(self.media_overlay)
        self.parent.queue_draw()
        return False


    def do_play(self):
        """ Start playing the media file.

        Should run on the main thread to ensure we avoid reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_play_pause(self):
        """ Toggle pause mode of the media.

        Should run on the main thread to ensure we avoid reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_set_time(self, t):
        """ Set the player at time t.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError
