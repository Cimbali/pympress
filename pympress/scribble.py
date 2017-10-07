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

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from pympress import builder, surfacecache, document
from pympress.ui import PDF_REGULAR, PDF_CONTENT_PAGE, PDF_NOTES_PAGE


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
    #: :class:`~Gtk.DrawingArea` for the scribbling in the Presenter window. Actually redraws the slide.
    scribble_c_da = None
    #: :class:`~Gtk.DrawingArea` for the scribbles in the Content window. On top of existing overlays and slide.
    scribble_p_da = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Presenter window, captures freehand drawing
    scribble_c_eb = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Content window, captures freehand drawing
    scribble_p_eb = None
    #: :class:`~Gtk.AspectFrame` for the slide in the Presenter's highlight mode
    scribble_p_frame = None

    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None
    #: A :class:`~Gtk.OffscreenWindow` where we render the scribbling interface when it's not shown
    off_render = None
    #: :class:`~Gtk.Box` in the Presenter window, where we insert scribbling.
    p_central = None

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: callback, to be connected to :func:`~pympress.document.Document.current_page`
    get_current_page = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.notes_mode`
    get_notes_mode = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda: None

    def __init__(self, config, builder, notes_mode):
        """ Setup all the necessary for scribbling

        Args:
            config (:class:`~pympress.config.Config`): A config object containing preferences
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
            notes_mode (`bool`): The current notes mode, i.e. whether we display the notes on second slide
        """
        super(Scribbler, self).__init__()

        self.load_ui('highlight')
        self.connect_signals(self)
        builder.load_widgets(self)

        self.get_notes_mode = builder.get_callback_handler('get_notes_mode')
        self.get_current_page = builder.get_callback_handler('doc.current_page')
        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')

        # Surface cache
        self.cache = surfacecache.SurfaceCache(document.EmptyDocument(), config.getint('cache', 'maxpages'))

        self.scribble_color = Gdk.RGBA()
        self.scribble_color.parse(config.get('scribble', 'color'))
        self.scribble_width = config.getint('scribble', 'width')
        self.cache.add_widget("scribble_p_da", PDF_CONTENT_PAGE if notes_mode else PDF_REGULAR, False)

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
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.scribble_list[-1][2].append((ex / ww, ey / wh))

            self.scribble_c_da.queue_draw()
            self.scribble_p_da.queue_draw()
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

        if widget is not self.scribble_c_da:
            page = self.get_current_page()
            wtype = PDF_CONTENT_PAGE if self.get_notes_mode() else PDF_REGULAR
            nb = page.number()
            pb = self.cache.get("scribble_p_da", nb)

            if pb is None:
                # Cache miss: render the page, and save it to the cache
                pb = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, ww, wh)

                cairo_prerender = cairo.Context(pb)
                page.render_cairo(cairo_prerender, ww, wh, wtype)

                cairo_context.set_source_surface(pb, 0, 0)
                cairo_context.paint()

                self.cache.set("scribble_p_da", nb, pb)
            else:
                # Cache hit: draw the surface from the cache to the widget
                cairo_context.set_source_surface(pb, 0, 0)
                cairo_context.paint()

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
        self.scribble_p_da.queue_draw()


    def pop_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble
        """
        if self.scribble_list:
            self.scribble_list.pop()

        self.redraw_current_slide()
        self.scribble_p_da.queue_draw()


    def on_configure_da(self, widget, event):
        """ Transfer configure resize to the cache.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has been resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        # Don't trust those
        if not event.send_event:
            return

        self.cache.resize_widget(widget.get_name(), event.width, event.height)


    def switch_scribbling(self, widget, event = None, name = None):
        """ Starts the mode where one can read on top of the screen

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event` or None):  the GTK event., None when called through a menu item
            name (`str`): The name of the key pressed

        Returns:
            `bool`: whether the event was consumed
        """
        if issubclass(type(widget), Gtk.Actionable):
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

        page = self.get_current_page()
        wtype = PDF_CONTENT_PAGE if self.get_notes_mode() else PDF_REGULAR
        pr = page.get_aspect_ratio(wtype)
        self.scribble_p_frame.set_property('ratio', pr)

        p_layout = self.p_central.get_children()[0]

        self.p_central.remove(p_layout)
        self.off_render.remove(self.scribble_overlay)

        self.p_central.pack_start(self.scribble_overlay, True, True, 0)
        self.off_render.add(p_layout)

        self.p_central.queue_draw()

        # Also make sure our overlay on Content window is visible
        self.c_overlay.reorder_overlay(self.scribble_c_eb, 1)
        self.c_overlay.show_all()

        self.scribbling_mode = True

        return True


    def disable_scribbling(self):
        """ Disable the scribbling mode.

        Returns:
            `bool`: whether it was possible to disable (thus if it was not disabled already)
        """
        if not self.scribbling_mode:
            return False

        p_layout = self.off_render.get_child()

        self.p_central.remove(self.scribble_overlay)
        self.off_render.remove(p_layout)

        self.off_render.add(self.scribble_overlay)
        self.p_central.pack_start(p_layout, True, True, 0)
        self.scribbling_mode = False

        return True


