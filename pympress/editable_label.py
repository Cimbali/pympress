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
:mod:`pympress.editable_label` -- A label that can be swapped out for an editable entry
---------------------------------------------------------------------------------------
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import time


class EditableLabel(object):
    #: single uppercase character `str` containing the key used as a shortcut for editing this button
    shortcut_key = ''
    #: :class:`~Gtk.EventBox` around the label, used to sense clicks
    event_box = None

    #: `bool` tracking whether we are currently editing the label.
    editing = False

    def on_label_event(self, widget, event = None, name = None):
        """ Manage events on the current slide label/entry.

        This function triggers replacing the label with an entry when clicked or otherwise toggled.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gtk.Event` or None):  the event that occured, None if tf we called from a menu item
            name (`str`): name of the key in the casae of a key press

        Returns:
            `bool`: whether the event was consumed
        """

        if issubclass(type(widget), Gtk.Actionable):
            # A button or menu item, etc. directly connected to this action
            pass

        elif event.type == Gdk.EventType.KEY_PRESS:
            if name is None:
                name = Gdk.keyval_name(event.keyval)
            if name.upper() != self.shortcut_key:
                return False

        elif event.type == Gdk.EventType.BUTTON_PRESS:
            # If we clicked on the Event Box then don't toggle, just enable.
            if widget is not self.event_box or self.editing:
                return False
        else:
            return False

        # Perform the state toggle

        if not self.editing:
            self.swap_label_for_entry()
        else:
            self.restore_current_label()

        return True


    def validate(self):
        raise NotImplementedError


    def cancel(self):
        pass


    def more_actions(self, event, name):
        raise NotImplementedError


    def on_keypress(self, widget, event):
        """ Manage key presses for the editable label.

        If we are editing the label, intercept some key presses (to validate or cancel editing or other specific behaviour),
        otherwise pass the key presses on to the button for normal behaviour.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.editing or event.type != Gdk.EventType.KEY_PRESS:
            return False

        name = Gdk.keyval_name(event.keyval).lower().replace('kp_', '')

        if name == 'return' or name == 'enter':
            self.validate()
            self.restore_label()

        elif name == 'escape':
            self.cancel()
            self.restore_label()

        else:
            return self.more_actions(event, name)

        return True


    def swap_label_for_entry(self):
        """ Perform the actual work of starting the editing.
        """
        raise NotImplementedError

    def restore_label(self):
        """ Make sure that the editable label is not in entry mode.
        If it is an entry, then replace it with the label.
        """
        raise NotImplementedError


    def start_editing(self):
        """ Start the editing of the label if it is disabled.
        """
        if not self.editing:
            self.swap_label_for_entry()


    def stop_editing(self):
        """ Disable the editing of the label if it was enabled.
        """
        if self.editing:
            self.restore_label()


class PageNumber(EditableLabel):
    #: Slide counter :class:`~Gtk.Label` for the current slide.
    label_cur = None
    #: Slide counter :class:`~Gtk.Label` for the last slide.
    label_last = None
    #: :class:`~Gtk.EventBox` associated with the slide counter label in the Presenter window.
    eb_cur = None
    #: :class:`~Gtk.HBox` containing the slide counter label in the Presenter window.
    hb_cur = None
    #: :class:`~Gtk.SpinButton` used to switch to another slide by typing its number.
    spin_cur = None

    #: `int` holding the maximum page number in the document
    max_page_number = 1

    #: callback, to be connected to :func:`~pympress.document.Document.goto`
    goto_page = lambda p: None
    #: callback, to be connected to :func:`~pympress.ui.UI.on_page_change`
    page_change = lambda b: None
    #: callback, to be connected to :func:`~pympress.editable_label.EstimatedTalkTime.stop_editing`
    stop_editing_est_time = lambda: None

    def __init__(self, builder):
        """ Load all the widgets we need from the spinner.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(PageNumber, self).__init__()

        builder.load_widgets(self)

        self.goto_page             = builder.get_callback_handler('doc.goto')
        self.page_change           = builder.get_callback_handler('on_page_change')
        self.stop_editing_est_time = builder.get_callback_handler('est_time.stop_editing')

        # Initially (from XML) both the spinner and the current page label are visible.
        self.hb_cur.remove(self.spin_cur)

        self.shortcut_key = 'G'
        self.event_box = self.eb_cur


    def set_last(self, num_pages):
        """ Set the max number of pages, both on display and as the range of values for the spinner.

        Args:
            num_pages (`int`): The maximum page number
        """
        self.max_page_number = num_pages
        self.label_last.set_text("/{}".format(num_pages))
        self.spin_cur.set_range(1, num_pages)


    def validate(self):
        """ Get the page number from the spinner and go to that page
        """
        try:
            page_nb = int(self.spin_cur.get_buffer().get_text()) - 1
        except:
            page_nb = int(self.spin_cur.get_value()) - 1
        self.goto_page(page_nb)


    def cancel(self):
        """ Make the UI re-display the pages from before editing the current page.
        """
        GLib.idle_add(self.page_change, False)


    def more_actions(self, event, name):
        """ Implement directions (left/right/home/end) keystrokes, otherwise pass on to :func:`~Gtk.SpinButton.do_key_press_event()`
        """
        if name == 'home':
            self.spin_cur.set_value(1)
        elif name == 'end':
            self.spin_cur.set_value(self.max_page_number)
        elif name == 'left':
            self.spin_cur.set_value(self.spin_cur.get_value() - 1)
        elif name == 'right':
            self.spin_cur.set_value(self.spin_cur.get_value() + 1)
        else:
            return Gtk.SpinButton.do_key_press_event(self.spin_cur, event)

        return True


    def on_scroll(self, widget, event):
        """ Scroll event. Pass it on to the spin button if we're currently editing the page number.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.editing:
            return False
        else:
            return Gtk.SpinButton.do_scroll_event(self.spin_cur, event)


    def swap_label_for_entry(self):
        """ Perform the actual work of starting the editing.
        """
        self.stop_editing_est_time()

        # Replace label with entry
        self.hb_cur.remove(self.label_cur)
        self.spin_cur.show()
        self.hb_cur.add(self.spin_cur)
        self.hb_cur.reorder_child(self.spin_cur, 0)
        self.spin_cur.grab_focus()

        self.spin_cur.set_value(int(self.label_cur.get_text()))
        self.spin_cur.select_region(0, -1)

        self.editing = True


    def restore_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        if self.label_cur not in self.hb_cur:
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing = False


    def update_page_numbers(self, cur_nb):
        """ Update the displayed page numbers.

        Args:
            cur_nb (`int`): The current page number, in documentation numbering (range [0..max - 1])
        """
        cur = str(cur_nb+1)

        self.label_cur.set_text(cur)
        self.restore_label()


class EstimatedTalkTime(EditableLabel):
    #: Elapsed time :class:`~Gtk.Label`.
    label_time = None
    #: Estimated talk time :class:`~Gtk.Label` for the talk.
    label_ett = None
    #: :class:`~Gtk.EventBox` associated with the estimated talk time.
    eb_ett = None
    #: Estimated talk time, `int` in seconds.
    est_time = 0

    #: :class:`~Gtk.Entry` used to set the estimated talk time.
    entry_ett = Gtk.Entry()

    #: callback, to be connected to :func:`~pympress.editable_label.PageNumber.stop_editing`
    stop_editing_page_number = lambda: None


    def __init__(self, builder, ett):
        """ Setup the talk time.

        Args:
            builder (builder.Builder): The builder from which to load widgets.
            ett (`int`): the estimated time for the talk, in seconds.
        """
        super(EstimatedTalkTime, self).__init__()

        builder.load_widgets(self)

        self.label_ett.set_text("{:02}:{:02}".format(*divmod(ett, 60)))

        self.shortcut_key = 'T'
        self.event_box = self.eb_ett

    def delayed_callback_connection(self, builder):
        """ Connect callbacks later than at init, due to circular dependencies.
        Call this when the page_number module is initialized, but before needing the callback.

        Args:
            builder (builder.Builder): The builder from which to load widgets.
        """
        self.stop_editing_page_number = builder.get_callback_handler('page_number.stop_editing')

    def validate(self):
        """ Update estimated talk time from the input/
        """
        text = self.entry_ett.get_text()

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
        # TODO a callback for timer?


    def more_actions(self, event, name):
        """ Pass on keystrokes to :func:`~Gtk.Entry.do_key_press_event()`
        """
        return Gtk.Entry.do_key_press_event(self.entry_ett, event)


    def swap_label_for_entry(self):
        """ Perform the actual work of starting the editing.
        """
        self.stop_editing_page_number()

        # Set entry text
        self.entry_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
        self.entry_ett.select_region(0, -1)

        # Replace label with entry
        self.eb_ett.remove(self.label_ett)
        self.eb_ett.add(self.entry_ett)
        self.entry_ett.show()
        self.entry_ett.grab_focus()
        self.editing = True


    def restore_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        child = self.eb_ett.get_child()
        if child is not self.label_ett:
            self.eb_ett.remove(child)
            self.eb_ett.add(self.label_ett)

        self.editing = False



