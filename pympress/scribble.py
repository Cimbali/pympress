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
from gi.repository import Gtk, Gdk, GLib

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
    #: The :class:`~Gtk.DrawingArea` in the content window
    c_da = None

    #: The :class:`~Gtk.ColorButton` selecting the color of the pen
    scribble_color_selector = None
    #: The :class:`~Gtk.Scale` selecting the size of the pen
    scribble_width_selector = None
    #: The `list` containing the radio buttons :class:`~Gtk.ModelButton`
    scribble_preset_buttons = []

    #: The position of the mouse on the slide as `tuple` of `float`s
    mouse_pos = None
    #: A :class:`~cairo.Surface` to hold drawn highlights
    scribble_cache = None
    #: The next scribble to render (i.e. that is not rendered in cache)
    next_render = 0

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

    #: :class:`~Gtk.Button` that is clicked to stop zooming, unsensitive when there is no zooming
    zoom_stop_button = None

    #: callback, to be connected to :func:`~pympress.surfacecache.SurfaceCache.resize_widget`
    resize_cache = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.on_draw`
    on_draw = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.track_motions`
    track_motions = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.track_clicks`
    track_clicks = lambda *args: None

    #: callback, to be connected to :func:`~pympress.ui.UI.load_layout`
    load_layout = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda *args: None

    #: callback, to be connected to :func:`~pympress.extras.Zoom.get_slide_point`
    get_slide_point = lambda *args: None
    #: callback, to be connected to :func:`~pympress.extras.Zoom.start_zooming`
    start_zooming = lambda *args: None
    #: callback, to be connected to :func:`~pympress.extras.Zoom.stop_zooming`
    stop_zooming = lambda *args: None

    #: `int` that is the currently selected element
    active_preset = -1

    #: The :class:`~Gio.Action` that contains the currently selected pen
    pen_action = None

    #: `str` which is the mode for scribbling, one of 3 possile values:
    # global means one set of scribbles for the whole document
    # single-page means we manage a single page of scribbles, and clear everything on page change (historical behaviour)
    # per-page means we manage a set of scribbles per document page, and clear or restore them on page change
    # per-label means we manage a set of scribbles per document page, but defined by label and not page number
    highlight_mode = 'single-page'

    #: `dict` of scribbles per page
    remembered_scribbles = {}
    #: `tuple` of (`int`, `str`) indicating the current page number and label
    current_page = (None, None)

    #: `str` indicating the current layout of the highlight toolbar
    tools_orientation = 'vertical'
    #: :class:`~Gtk.Box` containing the presets
    preset_toolbar = None
    #: :class:`~Gtk.Box` containing the scribble buttons
    scribble_toolbar = None
    #: :class:`~Gtk.Box` containing the scribble color and width selectors
    scribble_color_toolbox = None


    def __init__(self, config, builder, notes_mode):
        super(Scribbler, self).__init__()

        self.load_ui('highlight')
        builder.load_widgets(self)
        self.get_application().add_window(self.off_render)

        self.on_draw = builder.get_callback_handler('on_draw')
        self.track_motions = builder.get_callback_handler('track_motions')
        self.track_clicks = builder.get_callback_handler('track_clicks')
        self.load_layout = builder.get_callback_handler('load_layout')
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

        # Load color and active pen preferences. Pen 0 is the eraser.
        self.color_width = [(Gdk.RGBA(0, 0, 0, 0), 150)] + list(zip(
            [self.parse_color(config.get('highlight', 'color_{}'.format(pen))) for pen in range(1, 10)],
            [config.getint('highlight', 'width_{}'.format(pen)) for pen in range(1, 10)],
        ))

        self.scribble_preset_buttons = [
            self.get_object('pen_preset_{}'.format(pen) if pen else 'eraser') for pen in range(10)
        ]

        self.tools_orientation = self.config.get('layout', 'highlight_tools')
        self.adjust_tools_orientation()

        active_pen = config.get('highlight', 'active_pen')
        self.setup_actions({
            'highlight':         dict(activate=self.switch_scribbling, state=False),
            'highlight-use-pen': dict(activate=self.load_preset, state=active_pen, parameter_type=str, enabled=False),
            'highlight-clear':   dict(activate=self.clear_scribble),
            'highlight-redo':    dict(activate=self.redo_scribble),
            'highlight-undo':    dict(activate=self.pop_scribble),
            'highlight-mode':    dict(activate=self.set_mode, state=self.highlight_mode, parameter_type=str),
            'highlight-tools-orientation': dict(activate=self.set_tools_orientation, state=self.tools_orientation,
                                                parameter_type=str),
        })


        self.pen_action = self.get_application().lookup_action('highlight-use-pen')
        self.load_preset(self.pen_action, int(active_pen) if active_pen.isnumeric() else 0)
        self.set_mode(None, GLib.Variant.new_string(config.get('highlight', 'mode')))


    def set_mode(self, gaction, param):
        """ Change the mode of clearing and restoring highlights

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the new mode as a string wrapped in a GLib.Variant
        """
        new_mode = param.get_string()
        if new_mode not in {'single-page', 'global', 'per-page', 'per-label'}:
            return False

        self.get_application().lookup_action('highlight-mode').change_state(GLib.Variant.new_string(new_mode))
        self.highlight_mode = new_mode
        self.config.set('highlight', 'mode', self.highlight_mode)
        self.remembered_scribbles.clear()

        return True


    def try_cancel(self):
        """ Cancel scribbling, if it is enabled.

        Returns:
            `bool`: `True` if scribbling got cancelled, `False` if it was already disabled.
        """
        if not self.scribbling_mode:
            return False

        self.disable_scribbling()
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
        """ Transform a list of points from scribbles to bezier curves

        Returns:
            `list`: control points of a bezier curves to draw
        """
        curves = []

        if len(points) <= 2:
            return curves

        c1 = points[1]
        for c2, pt in zip(points[2:-1:2], points[3:-1:2]):
            half_c2pt = (pt[0] - c2[0]) / 2, (pt[1] - c2[1]) / 2

            curves.append((*c1, c2[0] + half_c2pt[0], c2[1] + half_c2pt[1], *pt))
            c1 = (pt[0] + half_c2pt[0], pt[1] + half_c2pt[1])

        if len(points) % 2 == 0:
            curves.append((*c1, *points[-2], *points[-1]))

        return curves


    def track_scribble(self, widget, event):
        """ Draw the scribble following the mouse's moves.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        pos = self.get_slide_point(widget, event)
        if self.scribble_drawing:
            self.scribble_list[-1][-1].append(pos)
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
            self.scribble_list.append((self.scribble_color, self.scribble_width, []))
            self.scribble_drawing = True

            return self.track_scribble(widget, event)
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_drawing = False
            self.prerender()
            return True

        return False


    def reset_scribble_cache(self):
        """ Clear the cached scribbles.
        """
        window = self.c_da.get_window()

        if window is None:
            return ValueError('Cannot initialize scribble acche without drawing area window')

        scale = window.get_scale_factor()
        ww, wh = self.c_da.get_allocated_width() * scale, self.c_da.get_allocated_height() * scale
        try:
            self.scribble_cache = window.create_similar_image_surface(cairo.Format.ARGB32, ww, wh, scale)
        except ValueError:
            logger.exception('Error creating highlight cache')
        self.next_render = 0


    def prerender(self):
        """ Clear scribbles to cached.
        """
        if self.scribble_cache is None:
            try:
                self.reset_scribble_cache()
            except ValueError as e:
                logger.info(e)
                return

        if self.scribble_cache is None:
            self.next_render = 0
            return

        ww, wh = self.scribble_cache.get_width(), self.scribble_cache.get_height()

        monitor = self.c_da.get_display().get_monitor_at_window(self.c_da.get_parent_window()).get_geometry()
        pen_scale_factor = max(ww / monitor.width, wh / monitor.height)  # or sqrt of product

        cairo_context = cairo.Context(self.scribble_cache)
        cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)

        draw = slice(self.next_render, -1 if self.scribble_drawing else None)

        for color, width, points in self.scribble_list[draw]:
            self.render_scribble(cairo_context, color, width * pen_scale_factor, [(x * ww, y * wh) for x, y in points])

        del cairo_context

        self.next_render = len(self.scribble_list) + (draw.stop if draw.stop else 0)


    def render_scribble(self, cairo_context, color, width, points):
        """ Draw a single scribble, i.e. a bezier curve, on the cairo context

        Args:
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
            color (:class:`~Gdk.RGBA`): The color of the scribble
            width (`float`): The width of the curve
            points (`list`): The control points of the curve, scaled to the surface.

        Returns:
            :class:`~cairo.Path`: A copy of the path that was drawn
        """
        if not points:
            return

        # alpha == 0 -> Eraser mode
        cairo_context.set_operator(cairo.OPERATOR_OVER if color.alpha else cairo.OPERATOR_CLEAR)
        cairo_context.set_source_rgba(*color)
        cairo_context.set_line_width(width)

        cairo_context.move_to(*points[0])

        for curve in self.points_to_curves(points):
            cairo_context.curve_to(*curve)

        path = cairo_context.copy_path()

        cairo_context.line_to(*points[-1])
        cairo_context.stroke()

        return path


    def draw_scribble(self, widget, cairo_context):
        """ Perform the drawings by user.

        Args:
            widget (:class:`~Gtk.DrawingArea`): The widget where to draw the scribbles.
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        cw, ch = self.scribble_cache.get_width(), self.scribble_cache.get_height()

        cairo_context.push_group()

        cairo_context.save()

        cairo_context.scale(ww / cw, wh / ch)
        cairo_context.set_source_surface(self.scribble_cache)
        cairo_context.paint()

        cairo_context.restore()

        monitor = widget.get_display().get_monitor_at_window(widget.get_parent_window()).get_geometry()
        pen_scale_factor = max(ww / monitor.width, wh / monitor.height)  # or sqrt of product

        if self.scribble_drawing:
            cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)
            color, width, points = self.scribble_list[-1]
            self.render_scribble(cairo_context, color, width * pen_scale_factor, [(x * ww, y * wh) for x, y in points])

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
        if not self.active_preset:
            return

        self.color_width[self.active_preset] = self.scribble_color, self.scribble_width
        self.scribble_preset_buttons[self.active_preset].queue_draw()

        pen = self.active_preset
        self.config.set('highlight', 'color_{}'.format(pen), self.scribble_color.to_string())
        self.config.set('highlight', 'width_{}'.format(pen), str(self.scribble_width))


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

        self.reset_scribble_cache()
        self.redraw_current_slide()
        self.adjust_buttons()


    def page_change(self, page_number, page_label):
        """ Called when we change pages, to clear or restore scribbles

        Args:
            page_number (`int`): The number of the new page
            page_label (`str`): The label of the new page
        """
        if self.highlight_mode == 'per-page':
            current_page = self.current_page[0]
            new_page = page_number
        elif self.highlight_mode == 'per-label':
            current_page = self.current_page[1]
            new_page = page_label

        # Remember whatever the current mode, to facilitate switching modes
        self.current_page = (page_number, page_label)

        if self.highlight_mode == 'global':
            return
        elif self.highlight_mode == 'single-page':
            return self.clear_scribble()
        else:
            # Now optionally save the current scribbles
            if current_page is not None and self.scribble_list:
                self.remembered_scribbles[current_page] = self.scribble_list.copy()

            self.scribble_list = self.remembered_scribbles.pop(new_page, [])

            self.reset_scribble_cache()
            self.adjust_buttons()
            self.prerender()
            self.redraw_current_slide()


    def pop_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_list:
            self.scribble_redo_list.append(self.scribble_list.pop())

        self.adjust_buttons()
        self.reset_scribble_cache()
        self.prerender()
        self.redraw_current_slide()


    def redo_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_redo_list:
            self.scribble_list.append(self.scribble_redo_list.pop())

        self.adjust_buttons()
        self.prerender()
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


    def set_tools_orientation(self, gaction, target):
        """ Changes the orientation of the highlighting tool box.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target (:class:`~GLib.Variant`): the new orientation to set, as a string wrapped in a GLib.Variant

        Returns:
            `bool`: whether the preset was loaded
        """
        orientation = target.get_string()
        if orientation == self.tools_orientation:
            return False
        elif orientation not in ['horizontal', 'vertical']:
            logger.error('Unexpected highlight-tools orientation {}'.format(orientation))
            return False

        self.tools_orientation = orientation
        self.adjust_tools_orientation()

        gaction.change_state(target)
        self.config.set('layout', 'highlight_tools', self.tools_orientation)


    def adjust_tools_orientation(self):
        """ Actually change the highlight tool elements orientations according to self.tools_orientation
        """
        orientation = Gtk.Orientation.VERTICAL if self.tools_orientation == 'vertical' else Gtk.Orientation.HORIZONTAL
        self.preset_toolbar.set_orientation(orientation)
        self.scribble_toolbar.set_orientation(orientation)
        self.scribble_color_toolbox.set_orientation(orientation)
        self.scribble_width_selector.set_orientation(orientation)

        w, h = sorted(self.scribble_width_selector.get_size_request(), reverse=self.tools_orientation != 'vertical')
        self.scribble_width_selector.set_size_request(w, h)

        # NB the parent container is layed out perpendicularly to its contents
        self.scribble_overlay.set_orientation(Gtk.Orientation.HORIZONTAL if self.tools_orientation == 'vertical' else
                                              Gtk.Orientation.VERTICAL)


    def switch_scribbling(self, gaction, target=None):
        """ Starts the mode where one can read on top of the screen.

        Args:

        Returns:
            `bool`: whether the event was consumed
        """
        if target is not None and target == self.scribbling_mode:
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
        self.load_layout('highlight')

        self.p_central.queue_draw()
        self.scribble_overlay.queue_draw()

        self.scribbling_mode = True
        self.get_application().lookup_action('highlight').change_state(GLib.Variant.new_boolean(self.scribbling_mode))
        self.pen_action.set_enabled(self.scribbling_mode)

        self.p_central.queue_draw()
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
        self.load_layout(None)
        self.off_render.add(self.scribble_overlay)

        self.scribbling_mode = False
        self.get_application().lookup_action('highlight').change_state(GLib.Variant.new_boolean(self.scribbling_mode))
        self.pen_action.set_enabled(self.scribbling_mode)

        self.p_central.queue_draw()
        extras.Cursor.set_cursor(self.p_central)
        self.mouse_pos = None

        return True


    def load_preset(self, gaction=None, target=None):
        """ Loads the preset color of a given number or designed by a given widget, as an event handler.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target (:class:`~GLib.Variant`): the new preset to load, as a string wrapped in a GLib.Variant

        Returns:
            `bool`: whether the preset was loaded
        """
        if type(target) == int:
            self.active_preset = target
        else:
            self.active_preset = int(target.get_string()) if target.get_string() != 'eraser' else 0

        target = str(self.active_preset) if self.active_preset else 'eraser'

        self.config.set('highlight', 'active_pen', target)
        self.pen_action.change_state(GLib.Variant.new_string(target))
        self.scribble_color, self.scribble_width = self.color_width[self.active_preset]

        # Presenter-side setup
        self.scribble_color_selector.set_rgba(self.scribble_color)
        self.scribble_width_selector.set_value(self.scribble_width)
        self.scribble_color_selector.set_sensitive(target != 'eraser')
        self.scribble_width_selector.set_sensitive(target != 'eraser')

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
        color, width = self.color_width[button_number]
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
