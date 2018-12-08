# -*- coding: utf-8 -*-
#
#       pointer.py
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
:mod:`pympress.scribble` -- Manage user drawings on the current slide
---------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from pympress import builder, surfacecache, document, extras


class Scribbler(builder.Builder):
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: `list` of scribbles to be drawn, as tuples of color :class:`~Gdk.RGBA`, width `int`, and a `list` of points.
    scribble_list = []
    #: Whether the current mouse movements are drawing strokes or should be ignored
    scribble_drawing = False
    #: :class:`~Gdk.RGBA` current color of the scribbling tool
    scribble_color = Gdk.RGBA()
    #: `int` current stroke width of the scribbling tool
    scribble_width = 1

    #: :class:`~Gtk.HBox` that is replaces normal panes when scribbling is toggled, contains buttons and scribble drawing area
    scribble_overlay = None
    #: :class:`~Gtk.DrawingArea` for the scribbles in the Presenter window. Actually redraws the slide.
    scribble_p_da = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Content window, captures freehand drawing
    scribble_c_eb = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Presenter window, captures freehand drawing
    scribble_p_eb = None
    #: :class:`~Gtk.AspectFrame` for the slide in the Presenter's highlight mode
    scribble_p_frame = None

    #: A :class:`~Gtk.OffscreenWindow` where we render the scribbling interface when it's not shown
    off_render = None
    #: :class:`~Gtk.Box` in the Presenter window, where we insert scribbling.
    p_central = None

    #: :class:`~Gtk.CheckMenuItem` that shows whether the scribbling is toggled
    pres_highlight = None
    #: :class:`~Gtk.Button` that is clicked to stop zooming, unsensitive when there is no zooming
    zoom_stop_button = None

    #: callback, to be connected to :func:`~pympress.surfacecache.SurfaceCache.resize_widget`
    resize_cache = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.on_draw`
    on_draw = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.track_motions`
    track_motions = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.track_clicks`
    track_clicks = lambda: None

    #: callback, to be connected to :func:`~pympress.ui.UI.swap_layout`
    swap_layout = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda: None

    #: callback, to be connected to :func:`~pympress.extras.Zoom.get_slide_point`
    get_slide_point = lambda: None
    #: callback, to be connected to :func:`~pympress.extras.Zoom.start_zooming`
    start_zooming = lambda: None
    #: callback, to be connected to :func:`~pympress.extras.Zoom.stop_zooming`
    stop_zooming = lambda: None

    def __init__(self, config, builder, notes_mode):
        """ Setup all the necessary for scribbling

        Args:
            config (:class:`~pympress.config.Config`): A config object containing preferences
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
            notes_mode (`bool`): The current notes mode, i.e. whether we display the notes on second slide
        """
        super(Scribbler, self).__init__()

        self.load_ui('highlight')
        builder.load_widgets(self)

        self.on_draw = builder.get_callback_handler('on_draw')
        self.track_motions = builder.get_callback_handler('track_motions')
        self.track_clicks = builder.get_callback_handler('track_clicks')
        self.swap_layout = builder.get_callback_handler('swap_layout')
        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.resize_cache = builder.get_callback_handler('cache.resize_widget')
        self.get_slide_point = builder.get_callback_handler('zoom.get_slide_point')
        self.start_zooming = builder.get_callback_handler('zoom.start_zooming')
        self.stop_zooming = builder.get_callback_handler('zoom.stop_zooming')

        self.connect_signals(self)

        self.scribble_color = Gdk.RGBA()
        self.scribble_color.parse(config.get('scribble', 'color'))
        self.scribble_width = config.getint('scribble', 'width')

        self.config = config

        # Presenter-size setup
        self.get_object("scribble_color").set_rgba(self.scribble_color)
        self.get_object("scribble_width").set_value(self.scribble_width)


    def nav_scribble(self, name, ctrl_pressed):
        """ Handles an key press event: undo or disable scribbling.

        Args:
            name (`str`): The name of the key pressed
            ctrl_pressed (`bool`): whether the ctrl modifier key was pressed

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.scribbling_mode:
            return False
        elif name.upper() == 'Z' and ctrl_pressed:
            self.pop_scribble()
        elif name == 'Escape':
            self.disable_scribbling()
        else:
            return False
        return True


    def track_scribble(self, widget, event):
        """ Draw the scribble following the mouse's moves.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.scribble_drawing:
            self.scribble_list[-1][2].append(self.get_slide_point(widget, event))

            self.redraw_current_slide()
            return True
        else:
            return False


    def toggle_scribble(self, widget, event):
        """ Start/stop drawing scribbles.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.scribbling_mode:
            return False

        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            self.scribble_list.append( (self.scribble_color, self.scribble_width, []) )
            self.scribble_drawing = True

            return self.track_scribble(widget, event)
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_drawing = False
            return True

        return False


    def draw_scribble(self, widget, cairo_context):
        """ Perform the drawings by user.

        Args:
            widget (:class:`~Gtk.DrawingArea`): The widget where to draw the scribbles.
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)

        for color, width, points in self.scribble_list:
            points = [(p[0] * ww, p[1] * wh) for p in points]

            cairo_context.set_source_rgba(*color)
            cairo_context.set_line_width(width)
            cairo_context.move_to(*points[0])

            for p in points[1:]:
                cairo_context.line_to(*p)
            cairo_context.stroke()


    def update_color(self, widget):
        """ Callback for the color chooser button, to set scribbling color

        Args:
            widget (:class:`~Gtk.ColorButton`):  the clicked button to trigger this event, if any
        """
        self.scribble_color = widget.get_rgba()
        self.config.set('scribble', 'color', self.scribble_color.to_string())


    def update_width(self, widget, event, value):
        """ Callback for the width chooser slider, to set scribbling width

        Args:
            widget (:class:`~Gtk.Scale`): The slider control used to select the scribble width
            event (:class:`~Gdk.Event`):  the GTK event triggering this update.
            value (`int`): the width of the scribbles to be drawn
        """
        self.scribble_width = int(value)
        self.config.set('scribble', 'width', str(self.scribble_width))


    def clear_scribble(self, *args):
        """ Callback for the scribble clear button, to remove all scribbles
        """
        del self.scribble_list[:]

        self.redraw_current_slide()


    def pop_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble
        """
        if self.scribble_list:
            self.scribble_list.pop()

        self.redraw_current_slide()


    def on_configure_da(self, widget, event):
        """ Transfer configure resize to the cache.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has been resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        # Don't trust those
        if not event.send_event:
            return

        self.resize_cache(widget.get_name(), event.width, event.height)


    def switch_scribbling(self, widget, event = None, name = None):
        """ Starts the mode where one can read on top of the screen

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event` or None):  the GTK event., None when called through a menu item
            name (`str`): The name of the key pressed

        Returns:
            `bool`: whether the event was consumed
        """
        if issubclass(type(widget), Gtk.CheckMenuItem) and widget.get_active() == self.scribbling_mode:
            # Checking the checkbox conforming to current situation: do nothing
            return False

        elif issubclass(type(widget), Gtk.Actionable):
            # A button or menu item, etc. directly connected to this action
            pass

        elif event.type == Gdk.EventType.KEY_PRESS:
            if name is None:
                name = Gdk.keyval_name(event.keyval)
            if name.upper() != 'H':
                return False

        else:
            return False

        # Perform the state toggle
        if self.scribbling_mode:
            return self.disable_scribbling()

        else:
            return self.enable_scribbling()


    def enable_scribbling(self):
        """ Enable the scribbling mode.

        Returns:
            `bool`: whether it was possible to enable (thus if it was not enabled already)
        """
        if self.scribbling_mode:
            return False

        self.off_render.remove(self.scribble_overlay)
        self.swap_layout(None, 'highlight')
        p_layout = self.p_central.get_children()[0]

        self.p_central.queue_draw()
        self.scribble_overlay.queue_draw()

        self.scribbling_mode = True
        self.pres_highlight.set_active(self.scribbling_mode)

        return True


    def disable_scribbling(self):
        """ Disable the scribbling mode.

        Returns:
            `bool`: whether it was possible to disable (thus if it was not disabled already)
        """
        if not self.scribbling_mode:
            return False

        self.swap_layout('highlight', None)
        p_layout = self.p_central.get_children()[0]

        self.off_render.add(self.scribble_overlay)
        self.scribbling_mode = False
        self.pres_highlight.set_active(self.scribbling_mode)

        self.p_central.queue_draw()
        extras.Cursor.set_cursor(self.p_central)

        return True


