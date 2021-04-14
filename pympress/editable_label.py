# -*- coding: utf-8 -*-
#
#       editable_label.py
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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio


class EditableLabel(object):
    """ A label that can switch between simply displaying a value, and allowing user input to edit this value.
    """
    #: :class:`~Gtk.EventBox` around the label, used to sense clicks
    event_box = None

    #: `bool` tracking whether we are currently editing the label.
    editing = False

    def on_label_event(self, widget_or_action, event=None):
        """ Manage events on the current slide label/entry.

        This function triggers replacing the label with an entry when clicked or otherwise toggled.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred
            event (:class:`~Gtk.Event` or None):  the event that occurred, None if tf we called from a menu item

        Returns:
            `bool`: whether the event was consumed
        """
        hint = None
        if issubclass(type(widget_or_action), Gio.Action):
            hint = widget_or_action.get_name()

        elif event is not None and event.type == Gdk.EventType.BUTTON_PRESS:
            # If we clicked on the Event Box then don't toggle, just enable.
            if widget_or_action is not self.event_box or self.editing:
                return False

        else:
            return False

        # Perform the state toggle
        if not self.editing:
            self.swap_label_for_entry(hint)
        else:
            self.validate()

        return True


    def validate(self):
        """ Validate the input to the label. Needs to be reimplemented by children classes.
        """
        raise NotImplementedError


    def cancel(self):
        """ Cancel editing the label. Needs to be reimplemented by children classes.
        """
        pass


    def on_keypress(self, widget, event):
        """ Manage key presses for the editable label. Needs to be reimplemented by children classes.

        If we are editing the label, intercept some key presses (to validate or cancel editing or other specific
        behaviour), otherwise pass the key presses on to the button for normal behaviour.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.
            name (`str`): the name of the key stroke
            command (`str`): the name of the command in case this function is called by on_navigation

        Returns:
            `bool`: whether the event was consumed
        """
        raise NotImplementedError


    def try_cancel(self):
        """ Cancel editing the label, if it is being edited.

        Returns:
            `bool`: `True` if editing got cancelled, `False` if the label was not being edited.
        """
        if not self.editing:
            return False

        self.cancel()
        self.restore_label()
        return True


    def try_validate(self):
        """ Validate the page choice, if the page label is being edited.

        Returns:
            `bool`: `True` if editing got validated, `False` if the label was not being edited.
        """
        if not self.editing:
            return False

        self.validate()
        self.restore_label()
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
    """ A label that displays "current page / max page", that can be edited to select a page to which to go.

    Args:
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
    """
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
    #: :class:`~Gtk.Entry` used to switch to another slide by typing its label.
    edit_label = None
    #: :class:`~Gtk.Label` separating `~spin_cur` and `~edit_label`
    label_sep = None

    #: `int` holding the maximum page number in the document
    max_page_number = 1
    #: `bool` holding whether we display or ignore page labels
    page_labels = True
    #: `bool` whether to scroll with the pages (True) or with the page numbers (False)
    invert_scroll = True

    #: callback, to be connected to :func:`~pympress.document.Document.goto`
    goto_page = lambda *args: None
    #: callback, to be connected to :func:`~pympress.document.Document.lookup_label`
    find_label = lambda *args: None
    #: callback, to be connected to :func:`~pympress.document.Document.label_after`
    label_before = lambda *args: None
    #: callback, to be connected to :func:`~pympress.document.Document.label_before`
    label_after = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.do_page_change`
    page_change = lambda *args: None

    def __init__(self, builder, page_num_scroll):
        super(PageNumber, self).__init__()

        # The spinner's scroll is with page numbers, invert to scroll with pages
        self.invert_scroll = not page_num_scroll

        builder.load_widgets(self)
        builder.setup_actions({
            'goto-page':          dict(activate=self.on_label_event),
            'jumpto-label':       dict(activate=self.on_label_event),
            'cancel-page-number': dict(activate=self.cancel),
        })

        self.goto_page       = builder.get_callback_handler('goto_page')
        self.page_change     = builder.get_callback_handler('do_page_change')
        self.setup_doc_callbacks(builder.doc)

        # Initially (from XML) both the spinner and the current page label are visible.
        self.hb_cur.remove(self.spin_cur)
        self.hb_cur.remove(self.edit_label)
        self.hb_cur.remove(self.label_sep)

        self.event_box = self.eb_cur


    def setup_doc_callbacks(self, doc):
        """ Callbacks that need to be setup again at every new document

        Args:
            doc (:class:`~pympress.document.Document`): The new document that got loaded
        """
        self.find_label   = doc.lookup_label
        self.label_after  = doc.label_after
        self.label_before = doc.label_before


    def set_last(self, num_pages):
        """ Set the max number of pages, both on display and as the range of values for the spinner.

        Args:
            num_pages (`int`): The maximum page number
        """
        self.max_page_number = num_pages
        self.label_last.set_text(('/{})' if self.page_labels else '/{}').format(num_pages))
        self.spin_cur.set_range(1, num_pages)
        self.spin_cur.set_max_length(len(str(num_pages)) + 1)


    def enable_labels(self, enable):
        """ Allow one to use or ignore labels.

        Args:
            enable (`bool`): Whether to enable labels
        """
        self.page_labels = enable
        self.label_last.set_text(('/{})' if enable else '/{}').format(self.max_page_number))


    def changed_page_label(self, *args):
        """ Get the page number from the spinner and go to that page.
        """
        if not self.page_labels or not self.edit_label.is_focus() or not self.edit_label.get_text():
            return

        page_nb = self.find_label(self.edit_label.get_text(), prefix_unique = True)
        if not page_nb:
            return

        # use the spinner's mechanism
        self.spin_cur.set_value(page_nb + 1)


    def validate(self):
        """ Get the page number from the spinner and go to that page.
        """
        page_nb = None
        if self.page_labels and self.edit_label.is_focus():
            page_nb = self.find_label(self.edit_label.get_text(), prefix_unique = False)

        if page_nb is None:
            page_nb = int(self.spin_cur.get_value() - 1)

        if page_nb is not None:
            self.restore_label()
            self.goto_page(page_nb)
        else:
            self.cancel()


    def cancel(self, gaction=None, param=None):
        """ Make the UI re-display the pages from before editing the current page.
        """
        self.restore_label()
        GLib.idle_add(self.page_change, unpause=False)


    def on_keypress(self, widget, event):
        """ Implement directions (left/right/home/end) keystrokes.

        Otherwise pass on to :func:`~Gtk.SpinButton.do_key_press_event()`.
        """
        if self.page_labels and self.edit_label.is_focus():
            return Gtk.Entry.do_key_press_event(self.edit_label, event)
        else:
            return Gtk.SpinButton.do_key_press_event(self.spin_cur, event)


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
            # flip scroll direction to get scroll down advancing slides
            if self.invert_scroll and event.direction == Gdk.ScrollDirection.DOWN:
                event.direction = Gdk.ScrollDirection.UP
            elif self.invert_scroll and event.direction == Gdk.ScrollDirection.UP:
                event.direction = Gdk.ScrollDirection.DOWN

            # Manually get destination slide if we're editing labels
            if self.edit_label.is_focus():
                cur_page = int(self.spin_cur.get_value()) - 1
                if event.direction == Gdk.ScrollDirection.DOWN:
                    self.spin_cur.set_value(1 + self.label_before(cur_page))
                elif event.direction == Gdk.ScrollDirection.UP:
                    self.spin_cur.set_value(1 + self.label_after(cur_page))

            # Otherwise let the spinner do its job
            else:
                return Gtk.SpinButton.do_scroll_event(self.spin_cur, event)


    def swap_label_for_entry(self, hint=None):
        """ Perform the actual work of starting the editing.
        """
        Gio.Application.get_default().activate_action('cancel-talk-time')

        label, sep, cur = self.label_cur.get_text().rpartition('(')

        # Replace label with entry
        self.spin_cur.show()
        self.hb_cur.pack_start(self.spin_cur, True, True, 0)
        self.hb_cur.reorder_child(self.spin_cur, 1)

        if self.page_labels:
            self.hb_cur.pack_start(self.edit_label, True, True, 0)
            self.hb_cur.reorder_child(self.edit_label, 0)
            self.edit_label.set_text(label.strip())

            self.hb_cur.pack_start(self.label_sep, True, True, 0)
            self.hb_cur.reorder_child(self.label_sep, 1)
            self.label_sep.set_text(' (')

            self.hb_cur.set_homogeneous(False)

        self.hb_cur.remove(self.label_cur)

        try:
            cur_nb = int(cur.strip())
        except ValueError:
            cur_nb = -1
        self.spin_cur.set_value(cur_nb)

        if self.page_labels and (hint == 'jumpto-label' or hint == 'nav_jump'):
            self.edit_label.grab_focus()
            self.edit_label.select_region(0, -1)
        else:
            self.spin_cur.grab_focus()
            self.spin_cur.select_region(0, -1)

        self.editing = True


    def restore_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.

        If it is an entry, then replace it with the label.
        """
        if self.spin_cur in self.hb_cur:
            if self.page_labels:
                self.hb_cur.set_homogeneous(True)
                self.hb_cur.remove(self.edit_label)
                self.hb_cur.remove(self.label_sep)
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing = False


    def update_page_numbers(self, cur_nb, label):
        """ Update the displayed page numbers.

        Args:
            cur_nb (`int`): The current page number, in documentation numbering (range [0..max - 1])
            label (`str`): The current page label
        """
        cur = str(cur_nb + 1)

        if self.page_labels:
            self.label_cur.set_text('{} ({}'.format(str(label), cur))
        else:
            self.label_cur.set_text(cur)

        if self.editing:
            if not self.edit_label.is_focus():
                self.edit_label.set_text(str(label))

            self.spin_cur.set_value(cur_nb + 1)


class EstimatedTalkTime(EditableLabel):
    """ A label that displays the time elapsed since the start of the talk, that can be edited to select talk duration.

    The duration of the talk will cause the label to blink and change colour as the elapsed time gets closer to the
    targeted talk duration.

    Args:
        builder (builder.Builder): The builder from which to load widgets.
    """
    #: Elapsed time :class:`~Gtk.Label`.
    label_time = None
    #: Estimated talk time :class:`~Gtk.Label` for the talk.
    label_ett = None
    #: :class:`~Gtk.EventBox` associated with the estimated talk time.
    eb_ett = None
    #: Estimated talk time, `int` in seconds.
    est_time = 0

    #: :class:`~Gtk.Entry` used to set the estimated talk time.
    entry_ett = None

    #: callback, to be connected to :func:`~pympress.editable_label.PageNumber.stop_editing`
    stop_editing_page_number = lambda *args: None


    def __init__(self, builder):
        super(EstimatedTalkTime, self).__init__()

        self.entry_ett = Gtk.Entry()

        builder.load_widgets(self)
        builder.setup_actions({
            'edit-talk-time':   dict(activate=self.on_label_event),
            'set-talk-time':    dict(activate=self.set_time, parameter_type=int),
            'cancel-talk-time': dict(activate=self.restore_label),
        })

        self.event_box = self.eb_ett


    def validate(self):
        """ Update estimated talk time from the input.
        """
        text = self.entry_ett.get_text()

        t = ["0" + n.strip() for n in text.split(':')]
        try:
            m = int(t[0])
            s = int(t[1])
        except ValueError:
            logger.error(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(text))
            return
        except IndexError:
            s = 0

        self.set_time(None, GLib.Variant.new_int64(m * 60 + s))


    def set_time(self, gaction, param):
        """ Set the talk time.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): The time in seconds, as an int64 variant
        """
        time = param.get_int64()
        self.est_time = time
        self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))


    def on_keypress(self, widget, event):
        """ Pass on keystrokes to :func:`~Gtk.Entry.do_key_press_event()`.
        """
        return Gtk.Entry.do_key_press_event(self.entry_ett, event)


    def swap_label_for_entry(self, *args):
        """ Perform the actual work of starting the editing.
        """
        Gio.Application.get_default().activate_action('cancel-page-number')

        # Set entry text
        self.entry_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
        self.entry_ett.select_region(0, -1)

        # Replace label with entry
        self.eb_ett.remove(self.label_ett)
        self.eb_ett.add(self.entry_ett)
        self.entry_ett.show()
        self.entry_ett.grab_focus()
        self.editing = True


    def restore_label(self, gaction=None, param=None):
        """ Make sure that the current page number is displayed in a label and not in an entry.

        If it is an entry, then replace it with the label.
        """
        child = self.eb_ett.get_child()
        if child is not self.label_ett:
            self.eb_ett.remove(child)
            self.eb_ett.add(self.label_ett)

        self.editing = False
