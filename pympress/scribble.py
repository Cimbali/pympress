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

import logging
logger = logging.getLogger(__name__)

import math
import json
import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from pympress import builder, document, extras, util


def clone_strokes(strokes):
    """ Deep-copy stroke tuples - remembered pages do not share point lists with 'scribble_list'.  """
    out = []
    for item in strokes:
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        color, width, points, pressure = item[0], item[1], item[2], item[3]
        c = Gdk.RGBA()
        try:
            c.red, c.green, c.blue, c.alpha = color.red, color.green, color.blue, color.alpha
        except AttributeError:
            continue
        pts = [(float(x), float(y)) for x, y in points] if points else []
        pr = [float(p) for p in pressure] if pressure else []
        out.append((c, width, pts, pr))
    return out


def serialize_strokes(strokes):
    """ Serialize strokes for JSON (coordinates are relative to the slide). 'strokes' must be a list of (Gdk.RGBA, width, points, pressure)"""
    data = []
    for color, width, points, pressure in strokes:
        if not points:
            continue
        pr = list(pressure)
        while len(pr) < len(points):
            pr.append(1.0)
        try:
            cs = color.to_string()
        except Exception:
            logger.warning('Could not serialize highlight color, using black', exc_info=True)
            cs = 'rgb(0,0,0)'
        data.append({
            'c': cs,
            'w': width,
            'p': [[float(x), float(y)] for x, y in points],
            'P': [float(p) for p in pr[:len(points)]],
        })
    return data


def deserialize_strokes(data):
    """ Restore strokes from output. """
    strokes = []
    for item in data:
        try:
            color = Gdk.RGBA()
            if not color.parse(item['c']):
                continue
            width = int(round(float(item['w'])))
            points = [(float(x), float(y)) for x, y in item['p']]
            pressure = [float(p) for p in item['P']]
        except (KeyError, TypeError, ValueError):
            logger.warning('Skipping invalid entry when loading highlights file', exc_info=True)
            continue
        strokes.append((color, width, points, pressure))
    return strokes


class Scribbler(builder.Builder):
    """ UI that allows to draw free-hand on top of the current slide.

    Args:
        config (:class:`~pympress.config.Config`): A config object containing preferences
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        notes_mode (`bool`): The current notes mode, i.e. whether we display the notes on second slide
    """
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: `list` of scribbles to be drawn, as tuples of color :class:`~Gdk.RGBA`, width `int`, a `list` of points,
    #: and a `list` of pressure values.
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

    #: The position of the mouse on the slide as `tuple` of `float`
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
    scribble_off_render = None
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
    #: callback return current preview page index 
    get_preview_page_number = lambda *args: 0
    #: callback return current preview page label string
    get_preview_page_label = lambda *args: ''

    #: `int` that is the currently selected element
    active_preset = -1
    #: `int` to remember the previously selected element, before holding “eraser”
    previous_preset = -1
    #: `list` that contains the modifiers which, when held on scribble start, toggle the eraser
    toggle_erase_modifiers = []
    #: `list` that contains the non-modifier shortcuts which, when held on scribble start, toggle the eraser
    toggle_erase_shortcuts = []
    #: `str` or `None` that indicates whether a modifier + click or a held shortcut is toggling the eraser
    toggle_erase_source = None

    #: The :class:`~Gio.Action` that contains the currently selected pen
    pen_action = None

    #: `str` which is the mode for scribbling, one of 4 possible values:
    # global and per-page: per_page[int slide_index] holds strokes for that slide; active slide also uses scribble_list
    # single-page clears scribble_list on page change (per_page still updated for export of current slide)
    # per-label uses per_page[str label] as key instead of slide index
    highlight_mode = 'per-page'
    #: `bool` indicating whether we exit highlighting mode on page change
    page_change_exits = True

    #: All slides strokes: keys are slide index (int) or label ('str' in per-label mode); values match scribble_list shape.
    per_page = {}
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
        self.get_application().add_window(self.scribble_off_render)

        self.on_draw = builder.get_callback_handler('on_draw')
        self.track_motions = builder.get_callback_handler('track_motions')
        self.track_clicks = builder.get_callback_handler('track_clicks')
        self.load_layout = builder.get_callback_handler('load_layout')
        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.resize_cache = builder.get_callback_handler('cache.resize_widget')
        gsp = builder.get_callback_handler('zoom.get_slide_point')
        self.get_slide_point = gsp if callable(gsp) else self.fallback_slide_point
        if not callable(gsp):
            logger.error('.get_slide_point is not available; using widget-normalized coordinates only')
        self.start_zooming = builder.get_callback_handler('zoom.start_zooming')
        self.stop_zooming = builder.get_callback_handler('zoom.stop_zooming')
        gpn = builder.get_callback_handler('get_preview_page_number')
        self.get_preview_page_number = gpn if callable(gpn) else (lambda: 0)
        gpl = builder.get_callback_handler('get_preview_page_label')
        self.get_preview_page_label = gpl if callable(gpl) else (lambda: '')

        self.connect_signals(self)
        self.config = config

        # Prepare cairo surfaces for markers, with 3 different marker sizes, and for eraser
        ms = [1, 2, 3]
        icons = [cairo.ImageSurface.create_from_png(util.get_icon_path('marker_{}.png'.format(n))) for n in ms]
        masks = [cairo.ImageSurface.create_from_png(util.get_icon_path('marker_fill_{}.png'.format(n))) for n in ms]

        self.marker_surfaces = list(zip(icons, masks))
        self.eraser_surface = cairo.ImageSurface.create_from_png(str(util.get_icon_path('eraser.png')))

        # Load color and active pen preferences. Pen 0 is the eraser.
        self.color_width = [(Gdk.RGBA(0, 0, 0, 0), config.getfloat('highlight', 'width_eraser'))] + list(zip(
            [self.parse_color(config.get('highlight', 'color_{}'.format(pen))) for pen in range(1, 10)],
            [config.getfloat('highlight', 'width_{}'.format(pen)) for pen in range(1, 10)],
        ))

        self.scribble_preset_buttons = [
            self.get_object('pen_preset_{}'.format(pen) if pen else 'eraser') for pen in range(10)
        ]

        self.tools_orientation = self.config.get('layout', 'highlight_tools')
        self.adjust_tools_orientation()

        active_pen = config.get('highlight', 'active_pen')
        self.page_change_exits = config.getboolean('highlight', 'page_change_exits')
        self.setup_actions({
            'highlight':         dict(activate=self.switch_scribbling, state=False),
            'highlight-use-pen': dict(activate=self.load_preset, state=active_pen, parameter_type=str, enabled=False),
            'highlight-clear':   dict(activate=self.clear_scribble),
            'highlight-redo':    dict(activate=self.redo_scribble),
            'highlight-undo':    dict(activate=self.pop_scribble),
            'highlight-mode':    dict(activate=self.set_mode, state=self.highlight_mode, parameter_type=str),
            'highlight-page-exit': dict(activate=self.page_change_action, state=self.page_change_exits),
            'highlight-tools-orientation': dict(activate=self.set_tools_orientation, state=self.tools_orientation,
                                                parameter_type=str),
        })

        hold_erase = [Gtk.accelerator_parse(keys) for keys in config.shortcuts.get('highlight-hold-to-erase', [])]
        self.toggle_erase_modifiers = [mod for keycode, mod in hold_erase if not keycode]
        self.toggle_erase_shortcuts = [(keycode, mod) for keycode, mod in hold_erase if keycode]

        self.pen_action = self.get_application().lookup_action('highlight-use-pen')
        self.load_preset(self.pen_action, int(active_pen) if active_pen.isnumeric() else 0)
        self.set_mode(None, GLib.Variant.new_string(config.get('highlight', 'mode')))


    def page_change_action(self, gaction, param):
        """ Change whether we exit or stay in highlighting mode on page changes

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the new mode as a string wrapped in a GLib.Variant
        """
        self.page_change_exits = not gaction.get_state().get_boolean()
        self.config.set('highlight', 'page_change_exits', 'on' if self.page_change_exits else 'off')
        gaction.change_state(GLib.Variant.new_boolean(self.page_change_exits))

        return True


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
        self.per_page.clear()

        return True


    def storage_key_for_active_slide(self):
        """ Key into 'per_page' for the slide being drawn (int index or str label). """
        if self.highlight_mode == 'per-label':
            if self.current_page[0] is not None:
                return self.current_page[1] or ''
            fn = self.get_preview_page_label
            if callable(fn):
                try:
                    return (fn() or '')
                except TypeError:
                    pass
            return ''
        idx = self.current_page[0]
        if idx is not None:
            return int(idx)
        fn = self.get_preview_page_number
        if callable(fn):
            try:
                return int(fn())
            except (TypeError, ValueError):
                pass
        return 0


    def fallback_slide_point(self, widget, event):
        """ If 'get_slide_point' is missing, use pointer size only (no zoom correction). """
        ww = max(widget.get_allocated_width(), 1)
        wh = max(widget.get_allocated_height(), 1)
        ex, ey = event.get_coords()
        return ex / ww, ey / wh


    def event_to_slide_coordinates(self, widget, event):
        """ Normalized slide coordinates from pointer position; uses widget w/h and zoom (not Cairo pixels). """
        ww = widget.get_allocated_width()
        wh = widget.get_allocated_height()
        if ww < 1 or wh < 1:
            logger.warning('highlight: widget size %sx%s too small for coordinates', ww, wh)
            return 0.0, 0.0
        fn = self.get_slide_point
        if not callable(fn):
            logger.error('highlight: get_slide_point is not callable')
            return self.fallback_slide_point(widget, event)
        try:
            pt = fn(widget, event)
        except Exception:
            logger.exception('highlight: get_slide_point failed')
            return self.fallback_slide_point(widget, event)
        if pt is None:
            logger.warning('highlight: get_slide_point returned None, using fallback')
            return self.fallback_slide_point(widget, event)
        try:
            x, y = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            logger.warning('highlight: get_slide_point returned invalid %r, using fallback', pt)
            return self.fallback_slide_point(widget, event)
        if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
            logger.warning('highlight: non-finite coordinates (%s, %s), clamping to 0', x, y)
            return 0.0, 0.0
        logger.debug('highlight: slide coords (%s, %s) widget=%s', x, y, widget.get_name())
        return x, y


    def sync_per_page_from_list(self):
        """ Deep-copy 'scribble_list' into 'per_page' for the active slide."""
        if not self.scribble_list:
            return
        key = self.storage_key_for_active_slide()
        snapshot = clone_strokes(self.scribble_list)
        self.per_page[key] = snapshot
        points = [p for s in self.scribble_list
                  if isinstance(s, (list, tuple)) and len(s) >= 4 and isinstance(s[2], list)
                  for p in s[2]]
        

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

        for (ax, ay), (bx, by), (cx, cy), (dx, dy) in zip(
                [points[0], *points[:-2]], points[:-1], points[1:], [*points[2:], points[-1]]
        ):
            curves.append((bx, by,
                           bx + (cx - ax) / 4, by + (cy - ay) / 4,
                           cx + (bx - dx) / 4, cy + (by - dy) / 4,
                           cx, cy))

        return curves


    def ensure_active_stroke(self):
        """ Ensure 'scribble_list' ends with a valid stroke (color, width, points, pressures)."""
        need_new = False
        if not self.scribble_list:
            need_new = True
        else:
            stroke = self.scribble_list[-1]
            if not isinstance(stroke, (list, tuple)) or len(stroke) < 4:
                need_new = True
            elif not isinstance(stroke[2], list) or not isinstance(stroke[3], list):
                need_new = True
        if need_new:
            self.scribble_list.append((self.scribble_color, self.scribble_width, [], []))


    def track_scribble(self, widget, event):
        """ Draw the scribble following the mouse's moves.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        pos = self.event_to_slide_coordinates(widget, event) + ()

        if self.scribble_drawing:
            self.ensure_active_stroke()
            stroke = self.scribble_list[-1]
            points = stroke[2]
            pressures = stroke[3]
            points.append(pos)
            pressure = event.get_axis(Gdk.AxisUse.PRESSURE)
            pressures.append(1. if pressure is None else pressure)
            self.scribble_redo_list.clear()

            self.adjust_buttons()
            self.sync_per_page_from_list()
            key = self.storage_key_for_active_slide()
        self.mouse_pos = pos
        self.redraw_current_slide()
        return self.scribble_drawing


    def key_event(self, widget, event):
        """ Handle key events to activate the eraser while the shortcut is held

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.scribbling_mode:
            return False
        elif event.type != Gdk.EventType.KEY_PRESS and event.type != Gdk.EventType.KEY_RELEASE:
            return False
        elif not (*event.get_keyval()[1:], event.get_state()) in self.toggle_erase_shortcuts:
            return False

        if event.type == Gdk.EventType.KEY_PRESS and self.active_preset and self.toggle_erase_source is None:
            self.previous_preset = self.active_preset
            self.toggle_erase_source = 'shortcut'
            self.load_preset(target=0)
        elif event.type == Gdk.EventType.KEY_RELEASE and self.toggle_erase_source == 'shortcut' \
                and self.previous_preset and not self.active_preset:
            self.load_preset(target=self.previous_preset)
            self.previous_preset = 0
            self.toggle_erase_source = None
        else:
            return False
        return True


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
            eraser_button = event.get_source_device().get_source() == Gdk.InputSource.ERASER
            eraser_modifier = any(mod & event.get_state() == mod for mod in self.toggle_erase_modifiers)
            if (eraser_button or eraser_modifier) and self.active_preset and self.toggle_erase_source is None:
                self.previous_preset = self.active_preset
                self.toggle_erase_source = 'modifier'
                self.load_preset(target=0)

            self.scribble_list.append((self.scribble_color, self.scribble_width, [], []))
            self.scribble_drawing = True

            return self.track_scribble(widget, event)
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_drawing = False
            last = self.scribble_list[-1] if self.scribble_list else None
            if last is not None and isinstance(last, (list, tuple)) and len(last) >= 4 \
                    and isinstance(last[2], list) and not last[2]:
                self.scribble_list.pop()
            self.sync_per_page_from_list()
            self.prerender()

            if not self.active_preset and self.previous_preset and self.toggle_erase_source == 'modifier':
                self.load_preset(target=self.previous_preset)
                self.previous_preset = 0
                self.toggle_erase_source = None

            return True

        return False


    def reset_scribble_cache(self):
        """ Highlights are drawn from vector data. This function is called when the cache needs to be cleared, on page change or mode change. """
        self.scribble_cache = None
        self.next_render = 0


    def queue_draw(self):
        """ Queue GTK redraw on drawing areas that show highlights. """
        if self.c_da is not None:
            self.c_da.queue_draw()
        if self.scribble_p_da is not None:
            self.scribble_p_da.queue_draw()


    def prerender(self):
        """ Keep 'per_page' in sync after a stroke ends (drawing is vector-based)."""
        self.sync_per_page_from_list()


    def render_scribble(self, cairo_context, color, width, points, pressures):
        """ Draw a single scribble, i.e. a bezier curve, on the cairo context

        Args:
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
            color (:class:`~Gdk.RGBA`): The color of the scribble
            width (`float`): The width of the curve
            points (`list`): The control points of the curve, scaled to the surface.
            pressures (`list`): The relative line width at each point as `float` values in 0..1
        """
        if not points:
            return

        pressures = list(pressures)
        while len(pressures) < len(points):
            pressures.append(1.0)

        # Draw every stroke on a separate surface, then merge them all into the scribble cache
        # Erasers do not have their own group as they are meant to interfere with strokes below
        if color.alpha:
            cairo_context.push_group()
            cairo_context.set_operator(cairo.OPERATOR_SOURCE)
        else:
            # alpha == 0 -> Eraser mode
            cairo_context.set_operator(cairo.OPERATOR_CLEAR)
        cairo_context.set_source_rgba(*color)

        curves = self.points_to_curves(points)
        curve_widths = [(a + b) / 2 for a, b in zip(pressures[:-1], pressures[1:])]
        for curve, relwidth in zip(curves, curve_widths):
            cairo_context.move_to(*curve[:2])
            cairo_context.set_line_width(width * relwidth)
            cairo_context.curve_to(*curve[2:])
            cairo_context.stroke()

        # Draw from last uneven-indexed point to last point
        cairo_context.move_to(*points[-2 if len(points) % 2 and len(points) > 1 else -1])
        cairo_context.set_line_width(width * (curve_widths[-1] if curve_widths else pressures[-1]))
        cairo_context.line_to(*points[-1])
        cairo_context.stroke()

        if color.alpha:
            cairo_context.pop_group_to_source()
            cairo_context.paint()


    def draw_scribble(self, widget, cairo_context):
        """ Perform the drawings by user.

        Args:
            widget (:class:`~Gtk.DrawingArea`): The widget where to draw the scribbles.
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
        """
        window = widget.get_window()
        if window is None:
            return
        if self.scribble_list:
            self.sync_per_page_from_list()
        key = self.storage_key_for_active_slide()
        strokes = self.scribble_list if self.scribble_list else self.per_page.get(key, [])

        ww = max(widget.get_allocated_width(), 1)
        wh = max(widget.get_allocated_height(), 1)
        pen_scale_factor = max(ww / 900, wh / 900)

        cairo_context.push_group()
        cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)

        for color, width, points, pressure in strokes:
            if not points:
                continue
            self.render_scribble(cairo_context, color, width * pen_scale_factor,
                                 [(x * ww, y * wh) for x, y in points], pressure)

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
        self.scribble_width = max(1, min(100, 10 ** value if value < 1 else 10 + (value - 1) * 90))
        self.update_active_color_width()


    def update_active_color_width(self):
        """ Update modifications to the active scribble color and width, on the pen button and config object
        """
        self.color_width[self.active_preset] = self.scribble_color, self.scribble_width
        if self.active_preset:
            self.scribble_preset_buttons[self.active_preset].queue_draw()

        pen = self.active_preset if self.active_preset else 'eraser'
        if self.active_preset:
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
        self.per_page[self.storage_key_for_active_slide()] = []

        self.reset_scribble_cache()
        self.redraw_current_slide()
        self.adjust_buttons()


    def build_scribbles_save_payload(self, page_number, page_label):
        """ Build JSON-ready data for the active highlight mode, including the current slide."""
        key = self.storage_key_for_active_slide()
        current_json = serialize_strokes(clone_strokes(self.scribble_list))
        if self.highlight_mode == 'per-label':
            out = {str(k): serialize_strokes(v) for k, v in self.per_page.items()}
            out[str(key)] = current_json
            return {'per_label': out}
        out = {str(k): serialize_strokes(v) for k, v in self.per_page.items()}
        out[str(key)] = current_json
        return {'per_page': out}


    def save_scribbles_data(self, uri, page_number, page_label):
        """ Write scribbles for 'uri' to '.pdf.json' next to the PDF. """
        path = document.Document.scribble_data_path(uri)
        if path is None:
            return

        self.sync_per_page_from_list()

        existing = {}
        if path.is_file():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except (OSError, ValueError, json.JSONDecodeError):
                logger.warning('Could not read existing highlights file {}, overwriting'.format(path), exc_info=True)

        self.sync_per_page_from_list()

        payload = {'version': 1}
        payload.update(self.build_scribbles_save_payload(page_number, page_label))

        existing['version'] = 1
        for key in ('global', 'per_page', 'per_label'):
            if key not in payload:
                continue
            if key in existing and isinstance(existing[key], dict) and isinstance(payload[key], dict):
                merged = dict(existing[key])
                merged.update(payload[key])
                existing[key] = merged
            else:
                existing[key] = payload[key]

        tmp_path = path.parent / (path.name + '~')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.sync_per_page_from_list()
            payload_final = self.build_scribbles_save_payload(page_number, page_label)
            for mkey in ('per_page', 'per_label'):
                if mkey not in payload_final:
                    continue
                if mkey in existing and isinstance(existing[mkey], dict) and isinstance(payload_final[mkey], dict):
                    existing[mkey].update(payload_final[mkey])
                else:
                    existing[mkey] = payload_final[mkey]
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
                f.flush()
            tmp_path.replace(path)
            sec = payload_final.get('per_page') or payload_final.get('per_label') or {}
            n_strokes = sum(len(v) for v in sec.values() if isinstance(v, list))
        except OSError:
            logger.exception('Failed to write highlights file {}'.format(path))
            if tmp_path.is_file():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


    def load_scribbles_data(self, uri, page_number, page_label):
        """ Load scribbles from the JSON. """
        path = document.Document.scribble_data_path(uri)

        if path is None:
            self.scribble_redo_list.clear()
            self.per_page.clear() 
            self.scribble_list.clear() 
            self.reset_scribble_cache() 
            self.adjust_buttons() 
            self.redraw_current_slide() 
            return
        
        self.scribble_redo_list.clear()
        self.current_page = (None, None)
        page_label = page_label or ''

        self.per_page.clear()
        self.scribble_list.clear()

        if path is None or not path.is_file():
            self.reset_scribble_cache()
            self.adjust_buttons()
            self.redraw_current_slide()
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning('Invalid highlights file {}, ignoring'.format(path), exc_info=True)
            self.reset_scribble_cache()
            self.adjust_buttons()
            self.redraw_current_slide()
            return

        if self.highlight_mode in ('global', 'per-page'):
            per = data.get('per_page', {})
            if not per and data.get('global'):
                self.per_page[page_number] = deserialize_strokes(data['global'])
            else:
                for k, v in per.items():
                    try:
                        ki = int(k)
                    except (TypeError, ValueError):
                        continue
                    self.per_page[ki] = deserialize_strokes(v)
        elif self.highlight_mode == 'per-label':
            for k, v in data.get('per_label', {}).items():
                self.per_page[k] = deserialize_strokes(v)
        else:
            per = data.get('per_page', {})
            self.scribble_list[:] = deserialize_strokes(per.get(str(page_number), []))

        self.reset_scribble_cache()
        self.adjust_buttons()
        if self.scribble_list or self.per_page:
            self.prerender()
        self.redraw_current_slide()


    def page_change(self, page_number, page_label):
        """ Called when we change pages, to clear or restore scribbles

        Args:
            page_number (`int`): The number of the new page
            page_label (`str`): The label of the new page
        """
        page_label = page_label or ''
        prev_idx, prev_lbl = self.current_page

        if self.highlight_mode == 'single-page':
            if prev_idx is not None:
                self.clear_scribble()
            self.current_page = (page_number, page_label)
            return

        if self.highlight_mode == 'per-label':
            if prev_idx is not None:
                self.sync_per_page_from_list()
            stored = self.per_page.pop(page_label, [])
            self.scribble_list.clear()
            self.scribble_list.extend(clone_strokes(stored))
            self.current_page = (page_number, page_label)
            self.reset_scribble_cache()
            self.queue_draw()
            self.adjust_buttons()
            self.prerender()
            self.redraw_current_slide()
            return

        if prev_idx is not None:
            self.sync_per_page_from_list()
        stored = self.per_page.pop(page_number, [])
        self.scribble_list.clear()
        self.scribble_list.extend(clone_strokes(stored))
        self.current_page = (page_number, page_label)

        self.reset_scribble_cache()
        self.queue_draw()
        self.adjust_buttons()
        self.prerender()
        self.redraw_current_slide()


    def pop_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_list:
            self.scribble_redo_list.append(self.scribble_list.pop())

        self.adjust_buttons()
        self.sync_per_page_from_list()
        self.reset_scribble_cache()
        self.prerender()
        self.redraw_current_slide()


    def redo_scribble(self, *args):
        """ Callback for the scribble undo button, to undo the last scribble.
        """
        if self.scribble_redo_list:
            self.scribble_list.append(self.scribble_redo_list.pop())

        self.adjust_buttons()
        self.sync_per_page_from_list()
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

        # NB the parent container is laid out perpendicularly to its contents
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

        self.scribble_off_render.remove(self.scribble_overlay)
        self.load_layout('highlight')

        self.p_central.queue_draw()
        self.scribble_overlay.queue_draw()

        # Get frequent events for smooth drawing
        self.p_central.get_window().set_event_compression(False)

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

        self.scribbling_mode = False

        extras.Cursor.set_cursor(self.scribble_p_da, 'default')
        self.load_layout(None)
        self.scribble_off_render.add(self.scribble_overlay)
        window = self.p_central.get_window()
        if window:
            window.set_event_compression(True)

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
        if isinstance(target, int):
            self.active_preset = target
        else:
            self.active_preset = int(target.get_string()) if target.get_string() != 'eraser' else 0

        target = str(self.active_preset) if self.active_preset else 'eraser'

        self.config.set('highlight', 'active_pen', target)
        self.pen_action.change_state(GLib.Variant.new_string(target))
        self.scribble_color, self.scribble_width = self.color_width[self.active_preset]

        # Presenter-side setup
        self.scribble_color_selector.set_rgba(self.scribble_color)
        self.scribble_width_selector.set_value(math.log10(self.scribble_width) if self.scribble_width < 10
                                               else 1 + (self.scribble_width - 10) / 90)
        self.scribble_color_selector.set_sensitive(target != 'eraser')

        # Re-draw the eraser
        self.scribble_p_da.queue_draw()
        self.c_da.queue_draw()

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
        icon, mask = self.marker_surfaces[int(width >= 2) + int(width >= 40)]

        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        scale = wh / icon.get_height()

        dw, dh = self.scribble_p_da.get_allocated_width(), self.scribble_p_da.get_allocated_height()
        pen_scale_factor = max(dw / 900, dh / 900)  # or sqrt of product
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
