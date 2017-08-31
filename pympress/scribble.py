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
:mod:`pympress.pointer` -- Manage when and where to draw a pointer on screen
------------------------------------

This module contains
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from pympress import ui, util, builder, surfacecache, document
from pympress.ui import PDF_REGULAR, PDF_CONTENT_PAGE, PDF_NOTES_PAGE


class Scribbler(builder.Builder):
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: list of scribbles to be drawn, as pairs of  :class:`Gdk.RGBA`
    scribble_list = []
    #: Whether the current mouse movements are drawing strokes or should be ignored
    scribble_drawing = False
    #: :class:`Gdk.RGBA` current color of the scribbling tool
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
    #: A :class:`Gtk.OffscreenWindow` where we render the scribbling interface when it's not shown
    off_render = None
    #: :class:`~Gtk.Box` in the Presenter window, where we insert scribbling.
    p_central = None

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    def __init__(self):
        super(Scribbler, self).__init__()

        self.load_ui('highlight')
        self.connect_signals(self)


    def nav_scribble(self, name, ctrl_pressed):
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
        """ Drawings by user
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if widget is not self.scribble_c_da:
            page, wtype = ui.UI.get_current_page()
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


    def update_color(self, widget = None):
        """ Callback for the color chooser button, to set scribbling color
        """
        if widget:
            self.scribble_color = widget.get_rgba()
            self.config.set('scribble', 'color', self.scribble_color.to_string())


    def update_width(self, widget = None, event = None, value = None):
        """ Callback for the width chooser slider, to set scribbling width
        """
        if widget:
            self.scribble_width = int(value)
            self.config.set('scribble', 'width', str(self.scribble_width))


    def clear_scribble(self, widget = None):
        """ Callback for the scribble clear button, to remove all scribbles
        """
        del self.scribble_list[:]

        ui.UI.redraw_current_slide()


    def pop_scribble(self, widget = None):
        """ Callback for the scribble undo button, to undo the last scribble
        """
        if self.scribble_list:
            self.scribble_list.pop()

        ui.UI.redraw_current_slide()
        self.scribble_p_da.queue_draw()


    def setup_scribbling(self, config, builder, notes_mode):
        """ Setup all the necessary for scribbling
        """
        # Surface cache
        self.cache = surfacecache.SurfaceCache(document.EmptyDocument(), config.getint('cache', 'maxpages'))

        self.scribble_color = Gdk.RGBA()
        self.scribble_color.parse(config.get('scribble', 'color'))
        self.scribble_width = config.getint('scribble', 'width')
        self.cache.add_widget("scribble_p_da", PDF_CONTENT_PAGE if notes_mode else PDF_REGULAR, False)

        self.config = config
        builder.load_widgets(self)

        # Presenter-size setup
        self.get_object("scribble_color").set_rgba(self.scribble_color)
        self.get_object("scribble_width").set_value(self.scribble_width)


    def on_configure_da(self, widget, event):
        """ Transfer configure resize to the cache.

        Args:
            widget (:class:`Gtk.Widget`):  the widget which has been resized
            event (:class:`Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        # Don't trust those
        if not event.send_event:
            return

        self.cache.resize_widget(widget.get_name(), event.width, event.height)


    def switch_scribbling(self, widget = None, event = None, name = None):
        """ Starts the mode where one can read on top of the screen
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
        if self.scribbling_mode:
            return False

        page, wtype = ui.UI.get_current_page()
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
        if not self.scribbling_mode:
            return False

        p_layout = self.off_render.get_child()

        self.p_central.remove(self.scribble_overlay)
        self.off_render.remove(p_layout)

        self.off_render.add(self.scribble_overlay)
        self.p_central.pack_start(p_layout, True, True, 0)
        self.scribbling_mode = False

        return True


