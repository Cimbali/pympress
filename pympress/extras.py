# -*- coding: utf-8 -*-
#
#       extras.py
#
#       Copyright 2017 Cimbali <me@cimba.li>
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
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

"""
:mod:`pympress.extras` -- Manages the display of fancy extras such as annotations, videos and cursors
-----------------------------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import sys
import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

import mimetypes

from pympress import media_overlay
from pympress.ui import PDF_REGULAR, PDF_CONTENT_PAGE, PDF_NOTES_PAGE


class Annotations(object):
    #: The containing widget for the annotations
    scrollable_treelist = None
    #: Making the annotations list scroll if it's too long
    scrolled_window = None

    #: :class:`~Gtk.CellRendererText` Text renderer for the annotations
    annotation_renderer = Gtk.CellRendererText()

    def __init__(self, builder):
        """ Load the widgets and setup for the annotations' display.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Annotations, self).__init__()
        builder.load_widgets(self)

        # wrap text
        self.annotation_renderer.props.wrap_mode = Pango.WrapMode.WORD_CHAR

        column = Gtk.TreeViewColumn(None, self.annotation_renderer, text=0)
        column.props.sizing = Gtk.TreeViewColumnSizing.AUTOSIZE
        column.set_fixed_width(1)

        self.scrollable_treelist.set_model(Gtk.ListStore(str))
        self.scrollable_treelist.append_column(column)

        self.scrolled_window.set_hexpand(True)


    def add_annotations(self, annotations):
        """ Insert text annotations into the tree view that displays them.

        Args:
            annotations (`list`): A list of strings, that are the annotations to be displayed
        """
        list_annot = Gtk.ListStore(str)

        for annot in annotations:
            list_annot.append(('● ' + annot,))

        self.scrollable_treelist.set_model(list_annot)


    def on_configure_annot(self, widget, event):
        """ Adjust wrap width in annotations when they are resized.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which was resized.
            event (:class:`~Gdk.Event`):  the GTK event.
        """
        self.annotation_renderer.props.wrap_width = max(30, widget.get_allocated_width() - 10)
        self.scrolled_window.queue_resize()
        self.scrollable_treelist.get_column(0).queue_resize()


    def on_scroll(self, widget, event):
        """ Try scrolling the annotations window.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        adj = self.scrolled_window.get_vadjustment()
        if event.direction == Gdk.ScrollDirection.UP:
            adj.set_value(adj.get_value() - adj.get_step_increment())
        elif event.direction == Gdk.ScrollDirection.DOWN:
            adj.set_value(adj.get_value() + adj.get_step_increment())
        else:
            return False
        return True


class Media(object):
    #: `dict` of :class:`~pympress.media_overlay.VideoOverlay` ready to be added on top of the slides
    _media_overlays = {}

    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None
    #: :class:`~Gtk.Overlay` for the Presenter window.
    p_overlay = None

    def __init__(self, builder):
        """ Set up the required widgets and queue an initial draw.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Media, self).__init__()
        builder.load_widgets(self)

        self.c_overlay.queue_draw()
        self.p_overlay.queue_draw()


    def remove_media_overlays(self):
        """ Remove current media overlays.
        """
        for media_id in self._media_overlays:
            self.hide(media_id)


    def purge_media_overlays(self):
        """ Remove current media overlays.
        """
        self.remove_media_overlays()
        self._media_overlays.clear()


    def replace_media_overlays(self, current_page, page_type):
        """ Remove current media overlays, add new ones if page contains media.

        Args:
            current_page (:class:`~pympress.document.Page`): The page for twhich to prepare medias
            page_type (`int`): The page type: one of PDF_REGULAR, PDF_CONTENT_PAGE, or PDF_NOTES_PAGE
        """
        if page_type == PDF_NOTES_PAGE:
            return

        self.remove_media_overlays()

        for relative_margins, filename, show_controls in current_page.get_media():
            media_id = hash((relative_margins, filename, show_controls))

            if media_id not in self._media_overlays:
                mime_type, enc = mimetypes.guess_type(filename)
                factory = media_overlay.VideoOverlay.get_factory(mime_type)

                if not factory:
                    continue

                def get_curryfied_callback(name):
                    return lambda *args: media_overlay.VideoOverlay.find_callback_handler(self, name)(media_id, *args)

                v_da_c = factory(self.c_overlay, show_controls, relative_margins, get_curryfied_callback)
                v_da_p = factory(self.p_overlay, True, relative_margins, get_curryfied_callback)

                if page_type == PDF_CONTENT_PAGE:
                    v_da_p.relative_margins.x2 = 2 * v_da_p.relative_margins.x2 - 1
                    v_da_c.relative_margins.x2 = 2 * v_da_c.relative_margins.x2 - 1
                    v_da_p.relative_margins.x1 *= 2
                    v_da_c.relative_margins.x1 *= 2

                v_da_c.set_file(filename)
                v_da_p.set_file(filename)

                v_da_c.mute(True)
                v_da_p.mute(False)

                self._media_overlays[media_id] = (v_da_c, v_da_p)

            for w in self._media_overlays[media_id]:
                if w.autoplay:
                    w.show()


    def resize(self, which = None):
        """ Resize all media overlays that are a child of an overlay
        """
        needs_resizing = (which == 'content', which == 'presenter') if which is not None else (True, True)
        for media_id in self._media_overlays:
            for widget in (w for w, r in zip(self._media_overlays[media_id], needs_resizing) if r and w.is_shown()):
                widget.resize()


    def adjust_margins_for_mode(self, enable_notes):
        """ Adjust the relative margins of child widgets for notes mode update.

        Note that we apply the changes regular -> content and content -> regular without checking the
        initial state, as we do not store it. So take care to call this function appropriately.

        Args:
            enable_notes (`bool`): Whether to enable note, thus transition from PDF_REGULAR to PDF_CONTENT_PAGE, or the opposite
        """
        if enable_notes:
            for media_id in self._media_overlays:
                for widget in self._media_overlays[media_id]:
                    widget.relative_margins.x2 = 2 * widget.relative_margins.x2 - 1
                    widget.relative_margins.x1 *= 2
        else:
            for media_id in self._media_overlays:
                for widget in self._media_overlays[media_id]:
                    widget.relative_margins.x2 = widget.relative_margins.x2 / 2 + 0.5
                    widget.relative_margins.x1 /= 2


    def play(self, media_id, button = None):
        """ Starts playing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        if media_id in self._media_overlays:
            c, p = self._media_overlays[media_id]
            p.show()
            c.show()
            GLib.idle_add(lambda: any(p.do_play() for p in self._media_overlays[media_id]))


    def hide(self, media_id, button = None):
        """ Stops playing a media and hides the player. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        for p in self._media_overlays[media_id]:
            c, p = self._media_overlays[media_id]
            if c.is_shown(): c.do_hide()
            if p.is_shown(): p.do_hide()


    def play_pause(self, media_id, *args):
        """ Toggles playing and pausing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        GLib.idle_add(lambda: any(p.do_play_pause() for p in self._media_overlays[media_id]))


    def set_time(self, media_id, t, *args):
        """ Set the player of a given media at time t. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
            t (`int`): the timestamp, in ms
        """
        GLib.idle_add(lambda: any(p.do_set_time(t) for p in self._media_overlays[media_id]))


    @staticmethod
    def backend_version():
        """ Returns which backend is used.

        Returns:
            `str`: The name and version of the backend.
        """
        return media_overlay.VideoOverlay.backend_version()


class Cursor(object):
    #: a static `dict` of :class:`~Gdk.Cursor`s, ready to use
    _cursors = {
        'parent': None,
        'default': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.LEFT_PTR),
        'pointer': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.HAND1),
        'crosshair': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.CROSSHAIR),
        'invisible': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR),
    }

    @classmethod
    def set_cursor(cls, widget, cursor_name = 'parent'):
        """ Set the cursor named cursor_name'

        Args:
            widget (:class:`~Gtk.Widget`): The widget triggering the cursor change, used to retrieve a Gdk.Window
            cursor_name (`str`): Name of the cursor to be set
        """
        widget.get_window().set_cursor(cls._cursors[cursor_name])


class Zoom(object):
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    zoom_selecting = False
    zoom_points = None
    scale = 1.
    shift = (0, 0)

    #: a callback for the :func:`~Gtk.Button.set_sensitive` function of the zoom-out button in the scribble interface
    set_scribble_zoomout_sensitive = lambda: None
    #: :class:`~Gtk.MenuItem` that is clicked to stop zooming
    menu_zoom_out = None
    #: :class:`~Gtk.Box` in the Presenter window, used to reliably set cursors.
    p_central = None

    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.clear_cache`
    clear_cache = lambda: None

    def __init__(self, builder):
        """ Setup all the necessary for zooming

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Zoom, self).__init__()
        builder.load_widgets(self)

        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.clear_cache = builder.get_callback_handler('clear_zoom_cache')


    def delayed_callback_connection(self, scribble_builder):
        """ Connect callbacks later than at init, due to circular dependencies.
        Call this when the page_number module is initialized, but before needing the callback.

        Args:
            builder (builder.Builder): The builder from which to load widgets for scribble
        """
        self.set_scribble_zoomout_sensitive = scribble_builder.get_callback_handler('zoom_stop_button.set_sensitive')


    def start_zooming(self, *args):
        """ Setup for the user to select the zooming area.

        Returns:
            `bool`: whether the event was consumed
        """
        self.zoom_selecting = True
        Cursor.set_cursor(self.p_central, 'crosshair')

        return True


    def stop_zooming(self, *args):
        """ Cancel the zooming, if it was enabled.

        Returns:
            `bool`: whether the event was consumed
        """
        Cursor.set_cursor(self.p_central)
        self.zoom_selecting = False
        self.zoom_points = None
        self.scale = 1.
        self.shift = (0, 0)
        self.set_scribble_zoomout_sensitive(False)
        self.menu_zoom_out.set_sensitive(False)

        self.redraw_current_slide()
        self.clear_cache()

        return True


    def nav_zoom(self, name, ctrl_pressed):
        """ Handles an key press event: stop trying to select an area to zoom.

        Args:
            name (`str`): The name of the key pressed
            ctrl_pressed (`bool`): whether the ctrl modifier key was pressed

        Returns:
            `bool`: whether the event was consumed
        """
        if name == 'Escape' and self.zoom_selecting:
            Cursor.set_cursor(self.p_central)
            self.zoom_selecting = False
            self.zoom_points = None
            return True

        return False


    def get_slide_point(self, widget, event):
        """ Gets the point on the slide on a scale (0..1, 0..1), from its position in the widget.
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        ex, ey = event.get_coords()

        return ((ex / ww - self.shift[0]) / self.scale, (ey / wh - self.shift[1]) / self.scale)


    def get_matrix(self, ww, wh):
        """ Returns the :class:`~cairo.Matrix` used to perform the zoom for the widget of size ww x wh.

        Args:
            ww (`float`):  widget width
            wh (`float`):  widget height

        Returns:
            :class:`~cairo.Matrix`: the zoom transformation matrix
        """
        return cairo.Matrix(xx = self.scale, x0 = ww * self.shift[0],
                            yy = self.scale, y0 = wh * self.shift[1])


    def track_zoom_target(self, widget, event):
        """ Draw the zoom's target rectangle.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.zoom_selecting and self.zoom_points:
            self.zoom_points[1] = self.get_slide_point(widget, event)

            self.redraw_current_slide()
            return True

        return False


    def toggle_zoom_target(self, widget, event):
        """ Start/stop drawing the zoom's target rectangle.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.zoom_selecting:
            return False

        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            p = self.get_slide_point(widget, event)
            self.zoom_points = [p, p]

            return self.track_zoom_target(widget, event)

        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE and self.zoom_points:
            self.zoom_points[1] = self.get_slide_point(widget, event)

            xmin, xmax = sorted(p[0] for p in self.zoom_points)
            ymin, ymax = sorted(p[1] for p in self.zoom_points)
            self.zoom_points = None

            try:
                # zoom by dimension less zoomed, to fit box while maintaining aspect ratio
                self.scale = 1. / max(ymax - ymin, xmax - xmin)

                # make center of drawn rectangle the center of the zoomed slide
                self.shift = (.5 - self.scale * (xmin + xmax) / 2,
                                    .5 - self.scale * (ymin + ymax) / 2)
            except ZeroDivisionError:
                self.scale = 1.
                self.shift = (0, 0)

            # stop drawing rectangles and reset cursor (NB don't use window, this bugs)
            Cursor.set_cursor(self.p_central)

            self.zoom_selecting = False
            self.clear_cache()
            self.redraw_current_slide()
            self.set_scribble_zoomout_sensitive(True)
            self.menu_zoom_out.set_sensitive(True)

            return True

        return False


    def draw_zoom_target(self, widget, cairo_context):
        """ Perform the drawings by user.

        Args:
            widget (:class:`~Gtk.DrawingArea`): The widget where to draw the scribbles.
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if self.zoom_selecting and self.zoom_points:
            xmin, xmax = sorted(p[0] * ww for p in self.zoom_points)
            ymin, ymax = sorted(p[1] * wh for p in self.zoom_points)

            rect = Gdk.Rectangle()
            rect.x = xmin
            rect.width = xmax - xmin
            rect.y = ymin
            rect.height = ymax - ymin

            cairo_context.set_line_width(3)
            cairo_context.set_line_cap(cairo.LINE_CAP_SQUARE)
            Gdk.cairo_rectangle(cairo_context, rect)
            cairo_context.set_source_rgba(.1, .1, 1, .4)
            cairo_context.stroke()

            Gdk.cairo_rectangle(cairo_context, rect)
            cairo_context.set_source_rgba(.5, .5, 1, .2)
            cairo_context.fill()
