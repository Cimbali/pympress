#       talk_time.py
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
:mod:`pympress.talk_time` -- Manages the clock of elapsed talk time
-------------------------------------------------------------------
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import time

from pympress import ui

class TalkTime(object):
    #: :class:`~Gdk.RGBA` The default color of the info labels
    label_color_default = None
    #: :class:`~Gdk.RGBA` The color of the elapsed time label if the estimated talk time is reached
    label_color_ett_reached = None
    #: :class:`~Gdk.RGBA` The color of the elapsed time label if the estimated talk time is exceeded by 2:30 minutes
    label_color_ett_info = None
    #: :class:`~Gdk.RGBA` The color of the elapsed time label if the estimated talk time is exceeded by 5 minutes
    label_color_ett_warn = None

    #: Elapsed time :class:`~Gtk.Label`.
    label_time = None
    #: Clock :class:`~Gtk.Label`.
    label_clock = None
    #: Estimated talk time :class:`~gtk.Label` for the talk.
    label_ett = None
    #: :class:`~gtk.EventBox` associated with the estimated talk time.
    eb_ett = None

    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur_ett = False
    #: :class:`~gtk.Entry` used to set the estimated talk time.
    entry_ett = Gtk.Entry()

    #: Time at which the counter was started.
    start_time = 0
    #: Time elapsed since the beginning of the presentation.
    delta = 0
    #: Estimated talk time.
    est_time = 0
    #: Timer paused status.
    paused = True


    def setup(self, builder, ett):
        """ Setup the talk time.

        Args:
            builder (builder.Builder): The builder from which to load widgets.
            ett (`int`): the estimated time for the talk, in seconds.
        """
        self.est_time = ett
        builder.load_widgets(self)

        self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))

        # Load the colors from the CSS
        style_context = self.label_time.get_style_context()

        self.label_color_ett_reached = self.load_color_from_css(style_context, "ett-reached")
        self.label_color_ett_info = self.load_color_from_css(style_context, "ett-info")
        self.label_color_ett_warn = self.load_color_from_css(style_context, "ett-warn")

        self.label_time.show();
        self.label_color_default = style_context.get_color(Gtk.StateType.NORMAL)


    def load_color_from_css(self, style_context, class_name):
        """ Add class class_name to the time label and return its color.

        Args:
            style_context (:class:`~Gtk.StyleContext`): the CSS context managing the color of the label
            class_name (`str`): The name of the class

        Returns:
            :class:`~Gdk.RGBA`: The color of the label with class "class_name"
        """
        style_context.add_class(class_name)
        self.label_time.show();
        color = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class(class_name)

        return color


    def switch_pause(self, *args):
        """ Switch the timer between paused mode and running (normal) mode.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if self.paused:
            self.start_time = time.time() - self.delta
            self.paused = False
        else:
            self.paused = True
        self.update_time()
        return True


    def pause(self):
        """ Pause the timer if it is not paused, otherwise do nothing.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if not self.paused:
            self.switch_pause()
            return True
        else:
            return False


    def unpause(self):
        """ Unpause the timer if it is paused, otherwise do nothing.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if self.paused:
            self.switch_pause()
            return True
        else:
            return False


    def reset_timer(self, *args):
        """ Reset the timer.
        """
        self.start_time = time.time()
        self.delta = 0
        self.update_time()


    def update_time(self):
        """ Update the timer and clock labels.

        Returns:
            `bool`: `True` (to prevent the timer from stopping)
        """
        # Current time
        clock = time.strftime("%X") #"%H:%M:%S"

        # Time elapsed since the beginning of the presentation
        if not self.paused:
            self.delta = time.time() - self.start_time
        elapsed = "{:02}:{:02}".format(*divmod(int(self.delta), 60))
        if self.paused:
            elapsed += " " + _("(paused)")

        self.label_time.set_text(elapsed)
        self.label_clock.set_text(clock)

        self.update_time_color()

        return True


    def calc_color(self, from_color, to_color, position):
        """ Compute the interpolation between two colors.

        Args:
            from_color (:class:`~Gdk.RGBA`):  the color when position = 0
            to_color (:class:`~Gdk.RGBA`):  the color when position = 1
            position (`float`):  A value between 0 and 1 expressing how far from

        Returns:
            :class:`~Gdk.RGBA`: The color that is between from_color and to_color
        """
        color_tuple = lambda color: ( color.red, color.green, color.blue, color.alpha )
        interpolate = lambda start, end: start + (end - start) * position

        return Gdk.RGBA(*map(interpolate, color_tuple(from_color), color_tuple(to_color)))


    def update_time_color(self):
        """ Update the color of the time label based on how much time is remaining.
        """
        if not self.est_time:
            return

        # Set up colors between which to fade, based on how much time remains (<0 has run out of time).
        # Times are given in seconds, in between two of those timestamps the color will interpolated linearly.
        # Outside of the intervals the closest color will be used.
        colors = {
             300:self.label_color_default,
               0:self.label_color_ett_reached,
            -150:self.label_color_ett_info,
            -300:self.label_color_ett_warn
        }
        bounds=list(sorted(colors, reverse=True)[:-1])

        remaining = self.est_time - self.delta
        if remaining >= bounds[0]:
            color = colors[bounds[0]]
        elif remaining <= bounds[-1]:
            color = colors[bounds[-1]]
        else:
            c=1
            while bounds[c] >= remaining:
                c += 1
            position = (remaining - bounds[c-1]) / (bounds[c] - bounds[c-1])
            color = self.calc_color(colors[bounds[c-1]], colors[bounds[c]], position)

        if color:
            self.label_time.override_color(Gtk.StateType.NORMAL, color)

        if (remaining <= 0 and remaining > -5) or (remaining <= -300 and remaining > -310):
            self.label_time.get_style_context().add_class("time-warn")
        else:
            self.label_time.get_style_context().remove_class("time-warn")


    def on_label_ett_event(self, widget, event = None, name = None):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, or otherwise toggled.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gtk.Event` or None):  the event that occured, None if tf we called from a menu item
            name (`str`): The name of the key pressed

        Returns:
            `bool`: whether the event was consumed.
        """

        if issubclass(type(widget), Gtk.Actionable):
            pass

        elif event.type == Gdk.EventType.KEY_PRESS:
            if name is None:
                name = Gdk.keyval_name(event.keyval)
            if name.upper() != 'T':
                return False

        elif event.type == Gdk.EventType.BUTTON_PRESS:
            # If we clicked on the Event Box then don't toggle, just enable.
            if widget is not self.eb_ett or self.editing_cur_ett:
                return False
        else:
            return False


        # Now toggle the state of editing.
        if not self.editing_cur_ett:
            ui.UI.stop_editing_slide()

            # Set entry text
            self.entry_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
            self.entry_ett.select_region(0, -1)

            # Replace label with entry
            self.eb_ett.remove(self.label_ett)
            self.eb_ett.add(self.entry_ett)
            self.entry_ett.show()
            self.entry_ett.grab_focus()
            self.editing_cur_ett = True
        else:
            self.restore_current_label_ett()

        return True


    def on_label_ett_keypress(self, widget, event):
        """ If we are editing the ett, intercept some key presses (to validate or cancel editing),
        otherwise pass the key presses on to the Gtk.Entry.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gdk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed.
        """
        if not self.editing_cur_ett:
            return False

        # Key pressed in the entry
        name = Gdk.keyval_name(event.keyval)

        # Return key --> restore label and goto page
        if name == "Return" or name == "KP_Enter":
            text = self.entry_ett.get_text()
            self.restore_current_label_ett()

            t = ["0" + n.strip() for n in text.split(':')]
            try:
                m = int(t[0])
                s = int(t[1])
            except ValueError:
                logger.error(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(text))
                return True
            except IndexError:
                s = 0

            self.est_time = m * 60 + s;
            self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
            self.label_time.override_color(Gtk.StateType.NORMAL, self.label_color_default)

        # Escape key --> just restore the label
        elif name == "Escape":
            self.restore_current_label_ett()

        else:
            return Gtk.Entry.do_key_press_event(self.entry_ett, event)

        return True


    def restore_current_label_ett(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        child = self.eb_ett.get_child()
        if child is not self.label_ett:
            self.eb_ett.remove(child)
            self.eb_ett.add(self.label_ett)

        self.editing_cur_ett = False


    def stop_editing(self):
        """ Disable the editing of the label if it was enabled.
        """
        if self.editing_cur_ett:
            self.restore_current_label_ett()


