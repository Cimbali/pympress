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
:mod:`pympress.pointer` -- Manage when and where to draw a software-emulated laser pointer on screen
----------------------------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import enum

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GdkPixbuf, GLib

from pympress import util, extras


class PointerMode(enum.Enum):
    """ Possible values for the pointer.
    """
    #: Pointer switched on continuously
    CONTINUOUS = 2
    #: Pointer switched on only manual
    MANUAL = 1
    #: Pointer never switched on
    DISABLED = 0


class Pointer(object):
    """ Manage and draw the software “laser pointer” to point at the slide.

    Displays a pointer of chosen color on the current slide (in both windows), either on all the time or only when
    clicking while ctrl pressed.

    Args:
        config (:class:`~pympress.config.Config`): A config object containing preferences
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
    """
    #: :class:`~GdkPixbuf.Pixbuf` to read XML descriptions of GUIs and load them.
    pointer = GdkPixbuf.Pixbuf()
    #: `(float, float)` of position relative to slide, where the pointer should appear
    pointer_pos = (.5, .5)
    #: `bool` indicating whether we should show the pointer
    show_pointer = False
    #: :class:`~pympress.pointer.PointerMode` indicating the pointer mode
    pointer_mode = PointerMode.MANUAL
    #: The :class:`~pympress.pointer.PointerMode` to which we toggle back
    old_pointer_mode = PointerMode.CONTINUOUS
    #: A reference to the UI's :class:`~pympress.config.Config`, to update the pointer preference
    config = None
    #: :class:`~Gtk.DrawingArea` Slide in the Presenter window, used to reliably set cursors.
    p_da_cur = None
    #: :class:`~Gtk.DrawingArea` Slide in the Contents window, used to reliably set cursors.
    c_da     = None
    #: :class:`~Gtk.AspectFrame` Frame of the Contents window, used to reliably set cursors.
    c_frame  = None
    #: a `dict` of the :class:`~Gtk.RadioMenuItem` selecting the pointer mode
    pointermode_radios = {}

    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda *args: None
    #: callback, to be connected to :meth:`~pympress.app.Pympress.set_action_state`
    set_action_state = None

    def __init__(self, config, builder):
        super(Pointer, self).__init__()
        self.config = config

        builder.load_widgets(self)

        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.set_action_state = builder.get_callback_handler('app.set_action_state')

        default_mode = config.get('presenter', 'pointer_mode')
        default_color = config.get('presenter', 'pointer')

        try:
            default_mode = PointerMode[default_mode.upper()]
        except KeyError:
            default_mode = PointerMode.MANUAL

        self.activate_pointermode(default_mode)
        self.load_pointer(default_color)

        self.action_map = builder.setup_actions({
            'pointer-color': dict(activate=self.change_pointercolor, state=default_color, parameter_type=str),
            'pointer-mode': dict(activate=self.change_pointermode, state=default_mode.name.lower(), parameter_type=str),
        })


    def load_pointer(self, name):
        """ Perform the change of pointer using its color name.

        Args:
            name (`str`): Name of the pointer to load
        """
        if name in ['red', 'green', 'blue']:
            self.pointer = GdkPixbuf.Pixbuf.new_from_file(util.get_icon_path('pointer_' + name + '.png'))
        else:
            raise ValueError('Wrong color name')


    def change_pointercolor(self, action, target):
        """ Callback for a radio item selection as pointer mode (continuous, manual, none).

        Args:
            action (:class:`~Gio.Action`): The action activatd
            target (:class:`~GLib.Variant`): The selected mode
        """
        color = target.get_string()
        self.load_pointer(color)
        self.config.set('presenter', 'pointer', color)
        action.change_state(target)


    def activate_pointermode(self, mode=None):
        """ Activate the pointer as given by mode.

        Depending on the given mode, shows or hides the laser pointer and the normal mouse pointer.

        Args:
            mode (:class:`~pympress.pointer.PointerMode`): The mode to activate
        """
        # Set internal variables, unless called without mode (from ui, after windows have been mapped)
        if mode == self.pointer_mode:
            return
        elif mode is not None:
            self.old_pointer_mode, self.pointer_mode = self.pointer_mode, mode
            self.config.set('presenter', 'pointer_mode', self.pointer_mode.name.lower())


        # Set mouse pointer and cursors on/off, if windows are already mapped
        self.show_pointer = False
        for slide_widget in [self.p_da_cur, self.c_da]:
            ww, wh = slide_widget.get_allocated_width(), slide_widget.get_allocated_height()
            if max(ww, wh) == 1:
                continue

            window = slide_widget.get_window()
            pointer_coordinates = window.get_pointer() if window is not None else (-1, -1)

            if 0 < pointer_coordinates.x < ww and 0 < pointer_coordinates.y < wh \
                    and self.pointer_mode == PointerMode.CONTINUOUS:
                # Laser activated right away
                self.pointer_pos = (pointer_coordinates.x / ww, pointer_coordinates.y / wh)
                self.show_pointer = True
                extras.Cursor.set_cursor(slide_widget, 'invisible')
            else:
                extras.Cursor.set_cursor(slide_widget, 'parent')

        self.redraw_current_slide()


    def change_pointermode(self, action, target):
        """ Callback for a radio item selection as pointer mode (continuous, manual, none).

        Args:
            action (:class:`~Gio.Action`): The action activatd
            target (:class:`~GLib.Variant`): The selected mode
        """
        if target is None or target.get_string() == 'toggle':
            mode = self.old_pointer_mode if self.pointer_mode == PointerMode.CONTINUOUS else PointerMode.CONTINUOUS
        else:
            mode = PointerMode[target.get_string().upper()]
        self.activate_pointermode(mode)

        action.change_state(GLib.Variant.new_string(mode.name.lower()))


    def render_pointer(self, cairo_context, ww, wh):
        """ Draw the laser pointer on screen.

        Args:
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the pointer
            ww (`int`): The widget width
            wh (`int`): The widget height
        """
        if self.show_pointer:
            x = ww * self.pointer_pos[0] - self.pointer.get_width() / 2
            y = wh * self.pointer_pos[1] - self.pointer.get_height() / 2
            Gdk.cairo_set_source_pixbuf(cairo_context, self.pointer, x, y)
            cairo_context.paint()


    def track_pointer(self, widget, event):
        """ Move the laser pointer at the mouse location.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.show_pointer:
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.pointer_pos = (ex / ww, ey / wh)
            self.redraw_current_slide()
            return True

        else:
            return False


    def track_enter_leave(self, widget, event):
        """ Switches laser off/on in continuous mode on leave/enter slides.

        In continuous mode, the laser pointer is switched off when the mouse leaves the slide
        (otherwise the laser pointer "sticks" to the edge of the slide).
        It is switched on again when the mouse reenters the slide.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        # Only handle enter/leave events on one of the current slides
        if self.pointer_mode != PointerMode.CONTINUOUS or widget not in [self.c_da, self.p_da_cur]:
            return False

        if event.type == Gdk.EventType.ENTER_NOTIFY:
            self.show_pointer = True
            extras.Cursor.set_cursor(widget, 'invisible')

        elif event.type == Gdk.EventType.LEAVE_NOTIFY:
            self.show_pointer = False
            extras.Cursor.set_cursor(widget, 'parent')

        self.redraw_current_slide()
        return True


    def toggle_pointer(self, widget, event):
        """ Track events defining when the laser is pointing.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.pointer_mode in {PointerMode.DISABLED, PointerMode.CONTINUOUS}:
            return False

        ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

        if ctrl_pressed and event.type == Gdk.EventType.BUTTON_PRESS:
            self.show_pointer = True
            extras.Cursor.set_cursor(widget, 'invisible')

            # Immediately place & draw the pointer
            return self.track_pointer(widget, event)

        elif self.show_pointer and event.type == Gdk.EventType.BUTTON_RELEASE:
            self.show_pointer = False
            extras.Cursor.set_cursor(widget, 'parent')
            self.redraw_current_slide()
            return True

        else:
            return False
