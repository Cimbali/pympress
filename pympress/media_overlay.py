# -*- coding: utf-8 -*-
#
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
:mod:`pympress.media_overlay` -- widget to play videos with a backend like VLC
------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GLib, GdkPixbuf

try:
    gi.require_version('GdkX11', '3.0')
    from gi.repository import GdkX11
except:
    pass

import ctypes
import sys, os
from collections import defaultdict

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS
from pympress import builder


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


class VideoOverlay(builder.Builder):
    """ Simple Video widget.

    Args:
        container (:class:`~Gtk.Overlay`): The container with the slide, at the top of which we add the movie area
        show_controls (`bool`): whether to display controls on the video player
        relative_margins (:class:`~Poppler.Rectangle`): the margins defining the position of the video in the frame.
    """
    #: :class:`~Gtk.Overlay` that is the parent of the VLCVideo widget.
    parent = None
    #: :class:`~Gtk.VBox` that contains all the elements to be overlayed.
    media_overlay = None
    #: A :class:`~Gtk.HBox` containing a toolbar with buttons and :attr:`~progress` the progress bar
    toolbar = None
    #: :class:`~Gtk.Scale` that is the progress bar in the controls toolbar - if we have one.
    progress = None
    #: :class:`~Gtk.DrawingArea` where the media is rendered.
    movie_zone = None
    #: :class:`~Poppler.Rectangle` containing the left/right/bottom/top space around the drawing area
    relative_margins = None
    #: `bool` that tracks whether we should play automatically
    autoplay = False

    #: callback, to be connected to :meth:`~pympress.extras.Media.play`, curryfied with the correct media_id
    play = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.hide`, curryfied with the correct media_id
    hide = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.play_pause`, curryfied with the correct media_id
    play_pause = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.set_time`, curryfied with the correct media_id
    set_time = None

    #: `bool` that tracks whether the user is dragging the position
    dragging_position = False
    #: `bool` that tracks whether the playback was paused when the user started dragging the position
    dragging_paused = False
    #: Format of the video time, defaults to m:ss, changed to m:ss / m:ss when the max time is known
    time_format = '{:01}:{:02}'
    #: `int` holding the max time in ms
    maxval = 1

    #: `dict` of mime type as `str` to the `type` of a class inheriting from :class:`~VideoOverlay`
    _backends = {}

    # `list` of info on backend versions
    _backend_versions = []

    def __init__(self, container, show_controls, relative_margins, callback_getter):
        super(VideoOverlay, self).__init__()

        self.parent = container
        self.relative_margins = relative_margins.copy()

        self.load_ui('media_overlay')
        self.toolbar.set_visible(show_controls)

        self.progress.set_adjustment(Gtk.Adjustment(value = 0., lower = 0., upper = 1., step_increment=0.01))

        self.play = callback_getter('play')
        self.hide = callback_getter('hide')
        self.play_pause = callback_getter('play_pause')
        self.set_time = callback_getter('set_time')
        self.connect_signals(self)


    def __del__(self):
        self.relative_margins.free()
        #super(VideoOverlay, self).__del__()


    def handle_embed(self, mapped_widget):
        """ Handler to embed the video player in the correct window, connected to the :attr:`~.Gtk.Widget.signals.map` signal
        """
        return False


    def format_millis(self, sc, val):
        """ Callback to format the current timestamp (in milliseconds) as minutes:seconds

        Args:
            sc (:class:`~Gtk.Scale`): The scale whose position we are formatting
            val (`float`): The position of the :class:`~Gtk.Scale`, which is the number of milliseconds elapsed in the video
        """
        return self.time_format.format(*divmod(int(val // 1000), 60))


    def progress_moved(self, rng, sc, val):
        """ Callback to update the position of the video when the user moved the progress bar.

        Args:
            rng (:class:`~Gtk.Range`): The range corresponding to the scale whose position we are formatting
            sc (:class:`~Gtk.Scale`): The scale whose position we are updating
            val (`float`): The position of the :class:`~Gtk.Scale`, which is the number of milliseconds elapsed in the video
        """
        return self.set_time(int(val))


    def mouse_click(self, widget, event):
        """ Callback to update the position of the video when the user moved the progress bar.

        Args:
            widget (:class:`~Gtk.Scale`): The range that was clicked
            event (:class:`~Gdk.EventButton`): The event corresponding to the mouse click release release
        """
        if not isinstance(event, Gdk.EventButton) or event.type not in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
            logger.warning('Unexpected widget or event type, expecting mouse release from Gtk.Scale: {}'.format((widget, event, event.type)))
            return False

        # immediate update on first click, otherwise set mouse_motion do the job
        if not self.dragging_position and event.type == Gdk.EventType.BUTTON_PRESS:
            pixel_range = (float(self.progress.get_range_rect().x), float(self.progress.get_range_rect().width))
            self.set_time(int(self.maxval * (event.x - pixel_range[0]) / pixel_range[1]))

        self.dragging_position = event.type == Gdk.EventType.BUTTON_PRESS

        if self.dragging_position:
            self.dragging_paused = self.is_playing()

        return True


    def mouse_motion(self, widget, event):
        """ Callback to update the position of the video when the user moved the progress bar.

        Args:
            widget (:class:`~Gtk.Scale`): The range that was clicked
            event (:class:`~Gdk.EventButton`): The event corresponding to the mouse click release release
        """
        if not isinstance(event, Gdk.EventMotion):
            logger.warning('Unexpected widget or event type, expecting mouse release from Gtk.Scale: {}'.format((widget, event, event.type)))
            return False
        elif not self.dragging_position:
            return False

        # get both ranges as (min, size) tuples of floats
        pixel_range = (float(self.progress.get_range_rect().x), float(self.progress.get_range_rect().width))
        self.set_time(int(self.maxval * (event.x - pixel_range[0]) / pixel_range[1]))
        return True


    def resize(self):
        """ Adjust the position and size of the media overlay.
        """
        if not self.is_shown():
            return

        pw, ph = self.parent.get_allocated_width(), self.parent.get_allocated_height()
        self.media_overlay.props.margin_left   = pw * self.relative_margins.x1
        self.media_overlay.props.margin_right  = pw * self.relative_margins.x2
        self.media_overlay.props.margin_bottom = ph * self.relative_margins.y1
        self.media_overlay.props.margin_top    = ph * self.relative_margins.y2


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


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        raise NotImplementedError


    def show(self):
        """ Bring the widget to the top of the overlays if necessary.
        """
        if not self.media_overlay.get_parent():
            self.parent.add_overlay(self.media_overlay)
            self.parent.reorder_overlay(self.media_overlay, 2)
            self.resize()
            self.parent.queue_draw()
        self.media_overlay.show()


    def do_hide(self):
        """ Remove widget from overlays. Needs to be callded via GLib.idle_add

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.do_stop()
        self.media_overlay.hide()

        if self.media_overlay.get_parent():
            self.parent.remove(self.media_overlay)
        return False


    def do_play(self):
        """ Start playing the media file.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_play_pause(self):
        """ Toggle pause mode of the media.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_set_time(self, t):
        """ Set the player at time t.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`int`): the timestamp, in ms

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    @classmethod
    def get_factory(cls, mime_type):
        """ Returns a class of type :attr:`~_backend`
        """
        try: # NB don't get(mime_type, None) so that a default can be set
            return cls._backends[mime_type]
        except KeyError:
            return None


    @classmethod
    def backend_version(cls):
        """ Gets the used version of the backend
        """
        return ', '.join(cls._backend_versions)


class VLCVideo(VideoOverlay):
    """ Simple VLC widget.

    Its player can be controlled through the 'player' attribute, which is a :class:`~vlc.MediaPlayer` instance.
    """

    #: A single vlc.Instance() to be shared by (possible) multiple players.
    _instance = None

    def __init__(self, *args, **kwargs):
        self.player = self._instance.media_player_new() # before loading UI, needed to connect "map" signal

        super(VLCVideo, self).__init__(*args, **kwargs)

        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda e: GLib.idle_add(self.hide))
        event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged, self.update_range)
        event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged, self.update_progress)


    def handle_embed(self, mapped_widget):
        """ Handler to embed the VLC player in the correct window, connected to the :attr:`~.Gtk.Widget.signals.map` signal
        """
        # Do we need to be on the main thread? (especially for the mess from the win32 window handle)
        #assert(isinstance(threading.current_thread(), threading._MainThread))
        if sys.platform == 'win32':
            self.player.set_hwnd(get_window_handle(self.movie_zone.get_window())) # get_property('window')
        else:
            self.player.set_xwindow(self.movie_zone.get_window().get_xid())
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


    def update_range(self, vlc_evt = None):
        """ Update the toolbar slider size.

        Args:
            vlc_evt (:class:`~vlc.Event`): The event that triggered the function call (if any)
        """
        self.maxval = self.player.get_length() or 1.
        sec = round(self.maxval / 1000) if self.maxval > 500 else 1
        self.time_format = '{{:01}}:{{:02}} / {:01}:{:02}'.format(*divmod(sec, 60))


    def update_progress(self, *args):
        """ Update the toolbar slider to the current time.

        Args:
            vlc_evt (:class:`~vlc.Event`): The event that triggered the function call (if any)
        """
        self.progress.set_value(self.player.get_position())


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
            t (`int`): the timestamp, in ms

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.player.set_time(t)
        self.update_progress()
        return False



class GifOverlay(VideoOverlay):
    """ A simple overlay mimicking the functionality of showing videos, but showing gifs instead.
    """
    #: A :class:`~GdkPixbuf.PixbufAnimation` containing all the frames and their timing for the displayed gif
    anim = None
    #: A `tuple` of (`int`, `int`) indicating the size of the bounding box of the gif
    base_size = None
    #: The :class:`~cairo.Matrix` defining the zoom & shift to scale the gif
    transform = None

    def __init__(self, container, show_controls, relative_margins, callback_getter):
        # override: no toolbar or interactive stuff for a gif, replace the whole widget area with a Gtk.Image
        super(GifOverlay, self).__init__(container, False, relative_margins, lambda n: lambda *a: None)

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
        anim = GdkPixbuf.PixbufAnimation.new_from_file(filepath)
        self.base_size = (anim.get_width(), anim.get_height())
        self.anim = anim.get_iter(None)

        self.set_transform()
        self.advance_gif()


    def set_transform(self, *args):
        """ Compute the transform to scale (not stretch nor crop) the gif
        """
        widget_size = (self.movie_zone.get_allocated_width(), self.movie_zone.get_allocated_height())
        scale = min(widget_size[0] / self.base_size[0], widget_size[1] / self.base_size[1])
        dx = widget_size[0] - scale * self.base_size[0]
        dy = widget_size[1] - scale * self.base_size[1]

        self.transform = cairo.Matrix(xx = scale, yy = scale, x0 = dx / 2, y0 = dy /2)


    def draw(self, widget, ctx):
        """ Simple resized drawing: get the pixbuf, set the transform, draw the image.
        """
        if self.anim is None: return False

        ctx.transform(self.transform)
        Gdk.cairo_set_source_pixbuf(ctx, self.anim.get_pixbuf(), 0, 0)
        ctx.paint()


    def advance_gif(self):
        """ Advance the gif,  queue redrawing if the frame changed, and schedule the next frame.
        """
        if self.anim.advance():
            self.movie_zone.queue_draw()

        GLib.timeout_add(self.anim.get_delay_time(), self.advance_gif)


    # a bunch of inherited functions that do nothing for gifs
    def mute(self, *args): pass
    def is_playing(self): return True
    def do_stop(self): pass
    def do_play(self): return False
    def do_play_pause(self): return False
    def do_set_time(self, *args): return False


VideoOverlay._backends['image/gif'] = GifOverlay
VideoOverlay._backend_versions.append(_('GtkImage gif player'))

try:
    import vlc

    vlc_opts=['--no-video-title-show']
    if IS_POSIX:
        vlc_opts.append('--no-xlib')
    elif IS_WINDOWS and vlc.plugin_path:
        # let python find the DLLs
        os.environ['PATH'] = vlc.plugin_path + ';' + os.environ['PATH']

    VLCVideo._instance = vlc.Instance(vlc_opts)

    # make VLCvideo the fallback
    VideoOverlay._backends = defaultdict(lambda: VLCVideo, VideoOverlay._backends)
    VideoOverlay._backend_versions.append('VLC {}'.format(vlc.libvlc_get_version().decode('ascii')))
except:
    logger.exception(_("Video support using VLC is disabled."))
