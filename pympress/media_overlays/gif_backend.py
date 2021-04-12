# -*- coding: utf-8 -*-
#
#       media_overlays/gif.py
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
:mod:`pympress.media_overlays.gif` -- widget to play gif images as videos
-------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, GdkPixbuf


from pympress.media_overlays import base


class GifOverlay(base.VideoOverlay):
    """ A simple overlay mimicking the functionality of showing videos, but showing gifs instead.
    """
    #: A :class:`~GdkPixbuf.PixbufAnimation` containing all the frames and their timing for the displayed gif
    anim = None
    #: A :class:`~GdkPixbuf.PixbufAnimationIter` which will provide the timely access to the frames in `~anim`
    iter = None
    #: A `tuple` of (`int`, `int`) indicating the size of the bounding box of the gif
    base_size = None
    #: The :class:`~cairo.Matrix` defining the zoom & shift to scale the gif
    transform = None

    def __init__(self, container, show_controls, relative_margins, page_type, callback_getter):
        # override: no toolbar or interactive stuff for a gif, replace the whole widget area with a GdkPixbuf
        super(GifOverlay, self).__init__(container, False, relative_margins, page_type, callback_getter)

        # we'll manually draw on the movie zone
        self.movie_zone.connect('draw', self.draw)
        self.movie_zone.connect('configure-event', self.set_transform)

        # automatically show
        self.autoplay = True


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        self.anim = GdkPixbuf.PixbufAnimation.new_from_file(filepath)
        self.base_size = (self.anim.get_width(), self.anim.get_height())
        self.iter = self.anim.get_iter(None)

        self.set_transform()
        self.advance_gif()


    def set_transform(self, *args):
        """ Compute the transform to scale (not stretch nor crop) the gif.
        """
        widget_size = (self.movie_zone.get_allocated_width(), self.movie_zone.get_allocated_height())
        scale = min(widget_size[0] / self.base_size[0], widget_size[1] / self.base_size[1])
        dx = widget_size[0] - scale * self.base_size[0]
        dy = widget_size[1] - scale * self.base_size[1]

        self.transform = cairo.Matrix(xx = scale, yy = scale, x0 = dx / 2, y0 = dy / 2)


    def draw(self, widget, ctx):
        """ Simple resized drawing: get the pixbuf, set the transform, draw the image.
        """
        if self.iter is None:
            return False

        try:
            ctx.transform(self.transform)
            Gdk.cairo_set_source_pixbuf(ctx, self.iter.get_pixbuf(), 0, 0)
            ctx.paint()
        except cairo.Error:
            logger.error(_('Cairo can not draw gif'), exc_info = True)


    def advance_gif(self):
        """ Advance the gif,  queue redrawing if the frame changed, and schedule the next frame.
        """
        if self.iter.advance():
            self.movie_zone.queue_draw()

        delay = self.iter.get_delay_time()
        if delay >= 0:
            GLib.timeout_add(delay, self.advance_gif)


    def do_set_time(self, t):
        """ Set the player at time t.

        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`int`): the timestamp, in ms

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        start = GLib.TimeVal()
        GLib.DateTime.new_now_local().to_timeval(start)
        start.add(-t)
        self.iter = self.anim.get_iter(start)
        self.advance_gif()
        return False


    # a bunch of inherited functions that do nothing, for gifs
    def mute(self, *args): pass
    def is_playing(self): return True
    def do_stop(self): pass
    def do_play(self): return False
    def do_play_pause(self): return False

    @classmethod
    def setup_backend(cls):
        """ Returns the name of this backend.
        """
        return _('GdkPixbuf gif player')
