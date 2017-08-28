#       page_number.py
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
:mod:`pympress.page_number` -- Manages the display of page numbers:
------------------------------------

This module contains
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import time

from pympress import ui

class PageNumber(object):
    #: Slide counter :class:`~Gtk.Label` for the current slide.
    label_cur = None
    #: Slide counter :class:`~Gtk.Label` for the last slide.
    label_last = None
    #: :class:`~Gtk.EventBox` associated with the slide counter label in the Presenter window.
    eb_cur = None
    #: :class:`~Gtk.HBox` containing the slide counter label in the Presenter window.
    hb_cur = None
    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur = False
    #: :class:`~Gtk.SpinButton` used to switch to another slide by typing its number.
    spin_cur = None


    def setup(self, builder):
        """ Load all the widgets we need from the spinner.
        """
        builder.load_widgets(self)

        # Initially (from XML) both the spinner and the current page label are visible.
        self.hb_cur.remove(self.spin_cur)


    def set_last(self, num_pages):
        """ Set the max number of pages, both on display and as the range of values for the spinner.
        """
        self.label_last.set_text("/{}".format(num_pages))
        self.spin_cur.set_range(1, num_pages)


    def on_label_event(self, widget = None, event = None, name = None):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked.

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured
            event (:class:`Gdk.Event`):  the event that occured
        """

        if issubclass(type(widget), Gtk.Actionable):
            # A button or menu item, etc. directly connected to this action
            pass

        elif event.type == Gdk.EventType.KEY_PRESS:
            if name is None:
                name = Gdk.keyval_name(event.keyval)
            if name.upper() != 'G':
                return False

        elif event.type == Gdk.EventType.BUTTON_PRESS:
            # If we clicked on the Event Box then don't toggle, just enable.
            if widget is not self.eb_cur or self.editing_cur:
                return False
        else:
            return False

        # Perform the state toggle

        if not self.editing_cur:
            ui.UI.stop_editing_time()

            # Replace label with entry
            self.hb_cur.remove(self.label_cur)
            self.spin_cur.show()
            self.hb_cur.add(self.spin_cur)
            self.hb_cur.reorder_child(self.spin_cur, 0)
            self.spin_cur.grab_focus()
            self.editing_cur = True

            self.spin_cur.set_value(int(self.label_cur.get_text()))
            self.spin_cur.select_region(0, -1)

        else:
            self.restore_current_label()

        return True


    def on_spin_nav(self, widget, event):
        """ Manage key presses for the spinner.

        We check the event for any specific behaviour we want: validating, updating, or cancelling navigation,
        and otherwise fall back to the spin button's normal behaviour.

        Args:
            widget (:class:`Gtk.Widget`):  the widget which has received the key stroke.
            event (:class:`Gdk.Event`):  the GTK event, which contains the ket stroke information.
        """
        if not self.editing_cur or event.type != Gdk.EventType.KEY_PRESS:
            return False

        name = Gdk.keyval_name(event.keyval).lower().replace('kp_', '')

        if name == 'return' or name == 'enter':
            try:
                page_nb = int(self.spin_cur.get_buffer().get_text()) - 1
            except:
                page_nb = int(self.spin_cur.get_value()) - 1
            self.doc.goto(page_nb)
            self.restore_current_label()

        elif name == 'escape':
            GLib.idle_add(ui.UI.notify_page_change, False)
            self.restore_current_label()

        elif name == 'home':
            self.spin_cur.set_value(1)
        elif name == 'end':
            self.spin_cur.set_value(self.doc.pages_number())
        elif name == 'left':
            self.spin_cur.set_value(self.spin_cur.get_value() - 1)
        elif name == 'right':
            self.spin_cur.set_value(self.spin_cur.get_value() + 1)
        else:
            return Gtk.SpinButton.do_key_press_event(self.spin_cur, event)

        return True


    def on_scroll(self, widget = None, event = None):
        """ Scroll event. Pass it on to the spin button if we're currently editing the page number.
        """
        if not self.editing_cur:
            return False
        else:
            return Gtk.SpinButton.do_scroll_event(self.spin_cur, event)


    def restore_current_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        if self.label_cur not in self.hb_cur:
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing_cur = False


    def update_page_numbers(self, cur_nb):
        """ Update the displayed page numbers.
        """
        cur = str(cur_nb+1)

        self.label_cur.set_text(cur)
        self.restore_current_label()


