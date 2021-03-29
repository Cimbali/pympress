# -*- coding: utf-8 -*-
#
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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import time


class TimeLabelColorer(object):
    """ Manage the colors of a label with a set of colors between which to fade, based on how much time remains.

    Times are given in seconds (<0 has run out of time). In between timestamps the color will interpolated linearly,
    outside of the intervals the closest color will be used.

    Args:
        label_time (:class:`Gtk.Label`): the label where the talk time is displayed
    """

    #: The :class:`Gtk.Label` whose colors need updating
    label_time = None

    #: :class:`~Gdk.RGBA` The default color of the info labels
    label_color_default = None

    #: :class:`~Gtk.CssProvider` affecting the style context of the labels
    color_override = None

    #: `list` of tuples (`int`, :class:`~Gdk.RGBA`), which are the desired colors at the corresponding timestamps.
    #: Sorted on the timestamps.
    color_map = []

    def __init__(self, label_time):
        self.label_time = label_time

        style_context = self.label_time.get_style_context()
        self.color_override = Gtk.CssProvider()
        style_context.add_provider(self.color_override, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        self.label_color_default = self.load_color_from_css(style_context)
        label_color_ett_reached = self.load_color_from_css(style_context, "ett-reached")
        label_color_ett_info = self.load_color_from_css(style_context, "ett-info")
        label_color_ett_warn = self.load_color_from_css(style_context, "ett-warn")

        self.color_map = [
            ( 300, self.label_color_default),
            (   0, label_color_ett_reached),
            (-150, label_color_ett_info),
            (-300, label_color_ett_warn)
        ]


    def load_color_from_css(self, style_context, class_name = None):
        """ Add class class_name to the time label and return its color.

        Args:
            label_time (:class:`Gtk.Label`): the label where the talk time is displayed
            style_context (:class:`~Gtk.StyleContext`): the CSS context managing the color of the label
            class_name (`str` or `None`): The name of the class, if any

        Returns:
            :class:`~Gdk.RGBA`: The color of the label with class "class_name"
        """
        if class_name:
            style_context.add_class(class_name)

        self.label_time.show()
        color = style_context.get_color(Gtk.StateType.NORMAL)

        if class_name:
            style_context.remove_class(class_name)

        return color


    def default_color(self):
        """ Forces to reset the default colors on the label.
        """
        self.color_override.load_from_data(''.encode('ascii'))


    def update_time_color(self, remaining):
        """ Update the color of the time label based on how much time is remaining.

        Args:
            remaining (`int`): Remaining time until estimated talk time is reached, in seconds.
        """
        if (remaining <= 0 and remaining > -5) or (remaining <= -300 and remaining > -310):
            self.label_time.get_style_context().add_class("time-warn")
        else:
            self.label_time.get_style_context().remove_class("time-warn")

        prev_time, prev_color = None, None

        for timestamp, color in self.color_map:
            if remaining >= timestamp:
                break
            prev_time, prev_color = (timestamp, color)

        else:
            # if remaining < all timestamps, use only last color
            prev_color = None

        if prev_color:
            position = (remaining - prev_time) / (timestamp - prev_time)
            color_spec = '* {{color: mix({}, {}, {})}}'.format(prev_color.to_string(), color.to_string(), position)
        else:
            color_spec = '* {{color: {}}}'.format(color.to_string())

        self.color_override.load_from_data(color_spec.encode('ascii'))


class TimeCounter(object):
    """ A double counter, that displays the time elapsed in the talk and a clock.

    Args:
        builder (builder.Builder): The builder from which to load widgets.
        ett (`int`): the estimated time for the talk, in seconds.
    """
    #: Elapsed time :class:`~Gtk.Label`
    label_time = None
    #: Clock :class:`~Gtk.Label`
    label_clock = None

    #: Time at which the counter was started, `int` in seconds as returned by :func:`~time.time()`
    restart_time = 0
    #: Time elapsed since the beginning of the presentation, `int` in seconds
    elapsed_time = 0
    #: Timer paused status, `bool`
    paused = True

    #: :class:`~TimeLabelColorer` that handles setting the colors of :attr:`label_time`
    label_colorer = None

    #: :class:`~pympress.editable_label.EstimatedTalkTime` that handles changing the ett
    ett = None

    #: The pause-timer :class:`~Gio.Action`
    pause_action = None

    #: The :class:`~pympress.extras.TimingReport`, needs to know when the slides change
    timing_tracker = None

    def __init__(self, builder, ett, timing_tracker):
        super(TimeCounter, self).__init__()

        self.label_colorer = TimeLabelColorer(builder.get_object('label_time'))
        self.ett = ett
        self.timing_tracker = timing_tracker

        builder.load_widgets(self)

        builder.setup_actions({
            'pause-timer':    dict(activate=self.switch_pause, state=self.paused),
            'reset-timer':    dict(activate=self.reset_timer),
        })
        self.pause_action = builder.get_application().lookup_action('pause-timer')

        # Setup timer for clocks
        GLib.timeout_add(250, self.update_time)


    def switch_pause(self, gaction, param=None):
        """ Switch the timer between paused mode and running (normal) mode.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if self.paused:
            self.unpause()
        else:
            self.pause()
        return None


    def pause(self):
        """ Pause the timer if it is not paused, otherwise do nothing.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if self.paused:
            return False

        self.paused = True
        self.pause_action.change_state(GLib.Variant.new_boolean(self.paused))

        self.elapsed_time += time.time() - self.restart_time
        self.timing_tracker.end_time = self.elapsed_time

        self.update_time()
        return True


    def unpause(self):
        """ Unpause the timer if it is paused, otherwise do nothing.

        Returns:
            `bool`: whether the clock's pause was toggled.
        """
        if not self.paused:
            return False

        self.restart_time = time.time()

        self.paused = False
        self.pause_action.change_state(GLib.Variant.new_boolean(self.paused))

        self.update_time()
        return True


    def reset_timer(self, *args):
        """ Reset the timer.
        """
        self.timing_tracker.reset(self.current_time())

        self.restart_time = time.time()
        self.elapsed_time = 0
        self.update_time()


    def current_time(self):
        """ Returns the time elapsed in the presentation.

        Returns:
            `int`: the time since the presentation started in seconds.
        """
        # Time elapsed since the beginning of the presentation
        if self.paused:
            return self.elapsed_time
        else:
            return self.elapsed_time + (time.time() - self.restart_time)


    def update_time(self):
        """ Update the timer and clock labels.

        Returns:
            `bool`: `True` (to prevent the timer from stopping)
        """
        # Current time
        clock = time.strftime("%X")  # "%H:%M:%S"

        # Time elapsed since the beginning of the presentation
        elapsed = self.current_time()
        display_time = "{:02}:{:02}".format(*divmod(int(elapsed), 60))

        if self.paused:
            display_time += " " + _("(paused)")

        self.label_time.set_text(display_time)
        self.label_clock.set_text(clock)
        if not self.paused:
            self.timing_tracker.end_time = elapsed

        if self.ett.est_time:
            self.label_colorer.update_time_color(self.ett.est_time - elapsed)
        else:
            self.label_colorer.default_color()

        return True
