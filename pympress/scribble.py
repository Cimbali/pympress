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

import math

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from pympress import builder, extras, util


class Scribbler(builder.Builder):
    """ UI that allows to draw free-hand on top of the current slide.

    Args:
        config (:class:`~pympress.config.Config`): A config object containing preferences
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        notes_mode (`bool`): The current notes mode, i.e. whether we display the notes on second slide
    """
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: `list` of scribbles to be drawn, as tuples of color :class:`~Gdk.RGBA`, width `int`, and a `list` of points.
    scribble_list = []
    #: `list` of undone scribbles to possibly redo
    scribble_redo_list = []
    #: Whether the current mouse movements are drawing strokes or should be ignored
    scribble_drawing = False
    #: :class:`~Gdk.RGBA` current color of the scribbling tool
    scribble_color = Gdk.RGBA()
    #: `int` current stroke width of the scribbling tool
    scribble_width = 1

    #: :class:`~Gtk.HBox` that replaces normal panes when scribbling is on, contains buttons and scribble drawing area.
    scribble_overlay = None
    #: :class:`~Gtk.DrawingArea` for the scribbles in the Presenter window. Actually redraws the slide.
    scribble_p_da = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Content window, captures freehand drawing
    scribble_c_eb = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Presenter window, captures freehand drawing
    scribble_p_eb = None
    #: :class:`~Gtk.AspectFrame` for the slide in the Presenter's highlight mode
    scribble_p_frame = None

    #:
    scribble_color_selector = None
    #:
    scribble_width_selector = None
    #:
    scribble_preset_buttons = []

    #:
    mouse_pos = None
    #:
    current_scribble_points = []

    #: :class:`~Gtk.Button` for removing the last drawn scribble
    scribble_undo = None
    #: :class:`~Gtk.Button` for drawing the last removed scribble
    scribble_redo = None
    #: :class:`~Gtk.Button` for removing all drawn scribbles
    scribble_clear = None

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
        self.config = config

        # Prepare cairo surfaces for markers, with 3 different marker sizes, and for eraser
        ms = [1, 2, 3]
        icons = [cairo.ImageSurface.create_from_png(util.get_icon_path('marker_{}.png'.format(n))) for n in ms]
        masks = [cairo.ImageSurface.create_from_png(util.get_icon_path('marker_fill_{}.png'.format(n))) for n in ms]

        self.marker_surfaces = list(zip(icons, masks))
        self.eraser_surface = cairo.ImageSurface.create_from_png(util.get_icon_path('eraser.png'))

        # Load color and active pen preferences
        self.color_width = list(zip(
            [self.parse_color(config.get('scribble', 'color_{}'.format(pen))) for pen in range(1, 10)],
            [config.getint('scribble', 'width_{}'.format(pen)) for pen in range(1, 10)],
        ))
        self.scribble_preset_buttons = [self.get_object('pen_preset_{}'.format(pen)) for pen in range(1, 10)]
        self.load_preset(config.getint('scribble', 'active_pen') - 1)


    def nav_scribble(self, name, ctrl_pressed, command = None):
        """ Handles a key press event: undo or disable scribbling.

        Args:
            name (`str`): The name of the key pressed
            ctrl_pressed (`bool`): whether the ctrl modifier key was pressed
            command (`str`): the name of the command in case this function is called by on_navigation

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.scribbling_mode:
            return False
        elif command == 'undo_scribble':
            self.pop_scribble()
        elif command == 'redo_scribble':
            self.pop_scribble()
        elif command == 'cancel':
            self.disable_scribbling()
        elif command and command[:-1] == 'scribble_preset_' and command[-1] in list('0123456789'):
            self.load_preset(int(command[-1]) - 1)
        else:
            return False
        return True


    @staticmethod
    def parse_color(text):
        """ Transform a string to a Gdk object in a single function call

        Args:
            text (`str`): A string describing a color

        Returns:
            :class:`~Gdk.RGBA`: A new color object parsed from the string
        """
        color = Gdk.RGBA()
        color.parse(text)
        return color


    def points_to_curves(self, points):
        if len(points) <= 2:
            return points

        curves = []
        curves.append(points[0])

        c1 = points[1]
        for c2, pt in zip(points[2:-1:2], points[3:-1:2]):
            half_c2pt = (pt[0] - c2[0]) / 2, (pt[1] - c2[1]) / 2

            curves.append((*c1, c2[0] + half_c2pt[0], c2[1] + half_c2pt[1], *pt))
            c1 = (pt[0] + half_c2pt[0], pt[1] + half_c2pt[1])

        if len(points) % 2 == 0:
            curves.append((*c1, *points[-2], *points[-1]))
        else:
            curves.append(points[-1])

        return curves


    def get_current_scribble(self):
        return (self.scribble_color, self.scribble_width, self.points_to_curves(self.current_scribble_points))


    def track_scribble(self, widget, event):
        """ Draw the scribble following the mouse's moves.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        last = getattr(self, 'last_time', None)
        self.last_time = event.get_time()
        print(self.last_time - last)

        pos = self.get_slide_point(widget, event)
        if self.scribble_drawing:
            self.current_scribble_points.append(pos)
            self.scribble_list[-1] = self.get_current_scribble()
            self.scribble_redo_list.clear()

            self.adjust_buttons()

        self.mouse_pos = pos
        self.redraw_current_slide()
        return self.scribble_drawing


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
            self.current_scribble_points.clear()
            self.scribble_list.append(self.get_current_scribble())
            self.scribble_drawing = True

            return self.track_scribble(widget, event)
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_list[-1] = self.get_current_scribble()
            self.current_scribble_points.clear()
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

        monitor = widget.get_display().get_monitor_at_window(widget.get_parent_window()).get_geometry()
        pen_scale_factor = max(ww / monitor.width, wh / monitor.height) # or sqrt of product

        cairo_context.push_group()
        cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)

        for color, width, curves in self.scribble_list:
            curves = [[coord * size for coord, size in zip(curve, [ww, wh] * (len(curve) // 2))] for curve in curves]

            # alpha == 0 -> Eraser mode
            cairo_context.set_operator(cairo.OPERATOR_OVER if color.alpha else cairo.OPERATOR_CLEAR)
            cairo_context.set_source_rgba(*color)
            cairo_context.set_line_width(width * pen_scale_factor)

            cairo_context.move_to(*curves[0])
            for curve in curves[1:]:
                if len(curve) == 2:
                    cairo_context.line_to(*curve)
                else:
                    cairo_context.curve_to(*curve)

            cairo_context.stroke()

        cairo_context.pop_group_to_source()
        cairo_context.paint()

        if widget.get_name() == 'scribble_p_da' and self.mouse_pos is not None:
            cairo_context.set_source_rgba(0, 0, 0, 1)
            cairo_context.set_line_width(1)

            mx, my = self.mouse_pos
            cairo_context.arc(mx * ww, my * wh, self.scribble_width * pen_scale_factor / 2, 0, 2 * math.pi)

            cairo_context.stroke_preserve()

            cairo_context.set_source_rgba(*list(self.scribble_color)[:3], self.scribble_color.alpha * .5)
            cairo_context.close_path()
            cairo_context.fill()


    def update_color(self, widget):
        """ Callback for the color chooser button, to set scribbling color.

        Args:
            widget (:class:`~Gtk.ColorButton`):  the clicked button to trigger this event, if any
        """
        self.scribble_color = widget.get_rgba()
        self.update_active_color_width()


    def update_width(self, widget, event, value):
        """ Callback for the width chooser slider, to set scribbling width.

        Args:
            widget (:class:`~Gtk.Scale`): The slider control used to select the scribble width
            event (:class:`~Gdk.Event`):  the GTK event triggering this update.
            value (`int`): the width of the scribbles to be drawn
        """
        self.scribble_width = max(5, min(90, int(value)))
        self.update_active_color_width()


    def update_active_color_width(self):
        """ Update modifications to the active scribble color and width, on the pen button and config object
        """
        self.color_width[self.active_preset] = self.scribble_color, self.scribble_width
        self.scribble_preset_buttons[self.active_preset].queue_draw()

        pen = self.active_preset + 1
        self.config.set('scribble', 'color_{}'.format(pen), self.scribble_color.to_string())
        self.config.set('scribble', 'width_{}'.format(pen), str(self.scribble_width))


    def adjust_buttons(self):
        """ Properly enable and disable buttons based on scribblings lists.
        """
        self.scribble_undo.set_sensitive(bool(self.scribble_list))
        self.scribble_clear.set_sensitive(bool(self.scribble_list))
        self.scribble_redo.set_sensitive(bool(self.scribble_redo_list))


    def clear_scribble(self, *args):
        """ Callback for the scribble clear button, to remove all scribbles.
        """
        self.scribble_list.clear()

        self.redraw_current_slide()
        self.adjust_buttons()


    def pop_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_list:
            self.scribble_redo_list.append(self.scribble_list.pop())

        self.adjust_buttons()
        self.redraw_current_slide()


    def redo_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_redo_list:
            self.scribble_list.append(self.scribble_redo_list.pop())

        self.adjust_buttons()
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


    def switch_scribbling(self, widget, event = None):
        """ Starts the mode where one can read on top of the screen.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event` or None):  the GTK event., None when called through a menu item

        Returns:
            `bool`: whether the event was consumed
        """
        if issubclass(type(widget), Gtk.CheckMenuItem) and widget.get_active() == self.scribbling_mode:
            # Checking the checkbox conforming to current situation: do nothing
            return False

        elif issubclass(type(widget), Gtk.Actionable):
            # A button or menu item, etc. directly connected to this action
            pass

        elif event.type != Gdk.EventType.KEY_PRESS:
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

        self.p_central.queue_draw()
        self.scribble_overlay.queue_draw()

        self.scribbling_mode = True
        self.pres_highlight.set_active(self.scribbling_mode)

        extras.Cursor.set_cursor(self.scribble_p_da, 'invisible')
        return True


    def disable_scribbling(self):
        """ Disable the scribbling mode.

        Returns:
            `bool`: whether it was possible to disable (thus if it was not disabled already)
        """
        if not self.scribbling_mode:
            return False

        extras.Cursor.set_cursor(self.scribble_p_da, 'default')
        self.swap_layout('highlight', None)

        self.off_render.add(self.scribble_overlay)
        self.scribbling_mode = False
        self.pres_highlight.set_active(self.scribbling_mode)

        self.p_central.queue_draw()
        extras.Cursor.set_cursor(self.p_central)
        self.mouse_pos = None

        return True


    def load_preset(self, widget, event=None):
        """ Loads the preset color of a given number or designed by a given widget, as an event handler.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event, or an `int` for the selected preset
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the preset was loaded
        """
        if isinstance(widget, Gtk.RadioButton):
            if not widget.get_active():
                return False
            elif widget.get_name() == 'eraser':
                preset_number = -1
            else:
                preset_number = int(widget.get_name().split('_')[-1]) - 1
        elif type(widget) is int:
            preset_number = widget
        else:
            return False

        self.active_preset = preset_number
        self.config.set('scribble', 'active_pen', str(self.active_preset + 1))

        if preset_number < 0:
            self.scribble_color, self.scribble_width = Gdk.RGBA(0, 0, 0, 0), 150
            self.get_object('eraser').set_active(True)
        else:
            self.scribble_color, self.scribble_width = self.color_width[preset_number]
            self.get_object('pen_preset_{}'.format(preset_number + 1)).set_active(True)

        # Presenter-side setup
        self.scribble_color_selector.set_rgba(self.scribble_color)
        self.scribble_width_selector.set_value(self.scribble_width)
        self.scribble_color_selector.set_sensitive(preset_number >= 0)
        self.scribble_width_selector.set_sensitive(preset_number >= 0)

        return True


    def on_eraser_button_draw(self, widget, cairo_context):
        """ Handle drawing the eraser button.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget to update
            cairo_context (:class:`~cairo.Context`):  the Cairo context (or `None` if called directly)
        """
        cairo_context.push_group()
        scale = widget.get_allocated_height() / self.eraser_surface.get_height()
        cairo_context.scale(scale, scale)

        cairo_context.set_source_surface(self.eraser_surface)
        cairo_context.paint()

        cairo_context.pop_group_to_source()
        cairo_context.paint()


    def on_preset_button_draw(self, widget, cairo_context):
        """ Handle drawing the marker/pencil buttons, with appropriate thickness and color.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget to update
            cairo_context (:class:`~cairo.Context`):  the Cairo context (or `None` if called directly)
        """
        button_number = int(widget.get_name().split('_')[-1])
        color, width = self.color_width[button_number - 1]
        icon, mask = self.marker_surfaces[int((width - 1) / 30)]

        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        scale = wh / icon.get_height()

        dw, dh = self.scribble_p_da.get_allocated_width(), self.scribble_p_da.get_allocated_height()
        monitor = widget.get_display().get_monitor_at_window(widget.get_parent_window()).get_geometry()
        pen_scale_factor = max(dw / monitor.width, dh / monitor.height)
        width *= pen_scale_factor

        cairo_context.push_group()

        # A line demonstrating the scribble style
        cairo_context.set_source_rgba(*color)
        cairo_context.set_line_width(width)
        cairo_context.move_to(0, wh - width / 2)
        cairo_context.line_to(ww, wh - width / 2)
        cairo_context.stroke()

        cairo_context.set_operator(cairo.OPERATOR_DEST_OUT)

        # Clip the line to the lower triangle
        cairo_context.set_source_rgba(0, 0, 0, 1)
        cairo_context.set_line_width(0)
        cairo_context.move_to(0, 0)
        cairo_context.line_to(0, wh)
        cairo_context.line_to(ww, 0)
        cairo_context.close_path()
        cairo_context.fill()

        # Also clip the colored part of the marker
        cairo_context.scale(scale, scale)
        cairo_context.set_source_surface(mask)
        cairo_context.paint()

        cairo_context.pop_group_to_source()
        cairo_context.paint()


        cairo_context.push_group()

        # Fill with desired color
        cairo_context.set_source_rgba(*color)
        cairo_context.rectangle(0, 0, ww, wh)
        cairo_context.fill()

        # Transform for surfaces
        cairo_context.scale(scale, scale)

        # Clip color to the mask
        cairo_context.set_operator(cairo.OPERATOR_DEST_IN)
        cairo_context.set_source_surface(mask)
        cairo_context.paint()

        # Add the rest of the marker
        cairo_context.set_operator(cairo.OPERATOR_OVER)
        cairo_context.set_source_surface(icon)
        cairo_context.paint()

        cairo_context.pop_group_to_source()
        cairo_context.paint()
