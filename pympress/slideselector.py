#       ui.py
#
#       Copyright 2010 Thomas Jost <thomas.jost@gmail.com>
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
:mod:`pympress.ui` -- GUI management
------------------------------------

This module contains the whole graphical user interface of pympress, which is
made of two separate windows: the Content window, which displays only the
current page in full size, and the Presenter window, which displays both the
current and the next page, as well as a time counter and a clock.

Both windows are managed by the :class:`~pympress.ui.UI` class.
"""

import os
import sys
import time

import pkg_resources

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

class SlideSelector(Gtk.SpinButton):
    ui = None
    maxpage = -1
    timer = -1
    def __init__(self, parent, maxpage):
        GObject.GObject.__init__(self)

        self.ui = parent
        self.maxpage = maxpage

        self.set_adjustment(Gtk.Adjustment(lower=1, upper=maxpage, step_incr=1))
        self.set_update_policy(Gtk.SpinButtonUpdatePolicy.ALWAYS)
        self.set_numeric(True)

        self.connect('changed', self.on_changed)
        self.connect("key-press-event", self.on_keypress)
        self.connect("key-release-event", self.on_keyup)
        self.connect("editing-done", self.done)
        self.connect("insert-text", self.on_changed)

    def on_keyup(self, widget, event):
        if event.type == Gdk.EventType.KEY_PRESS and Gdk.keyval_name(event.keyval).upper() == "G":
            return False
        return Gtk.SpinButton.do_key_release_event(self, event)

    def done(self, *args):
        self.ui.restore_current_label()
        self.ui.doc.goto(self.get_page())

    def cancel(self, *args):
        self.ui.restore_current_label()
        self.ui.on_page_change()

    def on_changed(self, *args):
        self.ui.page_preview(self.get_page())

    def force_update(self, *args):
        self.timer = -1
        self.set_value(float(self.get_buffer().get_text()))
        self.on_changed()
        return False

    def get_page(self):
        return max(1, min(self.maxpage, self.get_value_as_int()))-1

    def on_keypress(self, widget, event):
        if event.type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)

            # Return key --> restore label and goto page
            if name == "Return" or name == "KP_Enter":
                self.done()
            # Escape key --> just restore the label
            elif name == "Escape":
                self.cancel()
            elif name == 'Home':
                self.set_value(1)
            elif name == 'End':
                self.set_value(self.maxpage)

            elif name in map(str, range(10)):
                if self.timer >= 0:
                    GObject.source_remove(self.timer)
                self.timer = GObject.timeout_add(250, self.force_update)
                return Gtk.SpinButton.do_key_press_event(self, event)

            elif name.upper() in ['A', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'BACKSPACE']:
                return Gtk.SpinButton.do_key_press_event(self, event)
            else:
                return False

            if self.timer >= 0:
                GObject.source_remove(self.timer)

            return True

        elif event.type == Gdk.EventType.SCROLL:
            page=self.get_value_as_int()
            if event.direction is Gdk.ScrollDirection.SMOOTH:
                return False
            elif event.direction in [Gdk.ScrollDirection.RIGHT, Gdk.ScrollDirection.DOWN]:
                self.set_value(self.get_value_as_int() + 1)
            else:
                self.set_value(self.get_value_as_int() - 1)

            return True

        return False


