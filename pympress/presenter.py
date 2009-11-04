#!/usr/bin/env python
#
#       presenter.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
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

import time

import pygtk
pygtk.require('2.0')
import gobject
import gtk
import pango

import pympress.util

class Presenter:
    """
    This class manages the Presenter window, i.e. the one that displays both the
    current and the next page, as well as a time counter and a clock.

    @ivar start_time: timestamp at which the timer was started (0 if it was not
    started)
    @type start_time: float
    @ivar delta: time elapsed since the timer was started
    @type delta: float
    @ivar paused: indicates if the timer is on pause or not
    @type paused: boolean
    @ivar label_time: timer label
    @type label_time: gtk.Label
    @ivar label_clock: clock label
    @type label_clock: gtk.Label

    @ivar doc: current document
    @type doc: L{pympress.Document}
    @ivar page_current: current page
    @type page_current: L{pympress.Page}
    @ivar page_next: next page
    @type page_next: L{pympress.Page}

    @ivar frame_current: GTK widget used to display current pages with the right
    size and aspect ratio
    @type frame_current: gtk.AspectFrame
    @ivar frame_next: GTK widget used to display next pages with the right size
    and aspect ratio
    @type frame_next: gtk.AspectFrame
    @ivar label_current: label indicating the current page number
    @type label_current: gtk.Label
    @ivar label_next: label indicating the next page number
    @type label_next: gtk.Label
    @ivar da_current: GTK widget on which current pages are rendered
    @type da_current: gtk.DrawingArea
    @ivar da_next: GTK widget on which next pages are rendered
    @type da_next: gtk.DrawingArea
    """

    def __init__(self, doc):
        """
        @param doc: current document
        @type  doc: L{pympress.Document}
        """
        black = gtk.gdk.Color(0, 0, 0)

        self.start_time = 0
        self.delta = 0
        self.paused = False

        self.doc = doc

        # Window
        win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        win.set_title("pympress presenter")
        win.set_default_size(800, 600)
        win.set_position(gtk.WIN_POS_CENTER)
        win.connect("delete-event", gtk.main_quit)

        # Icons
        win.set_icon_list(*pympress.util.load_icons())

        # A little space around everything in the window
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(20, 20, 20, 20)
        win.add(align)

        # Table
        table = gtk.Table(2, 10, False)
        table.set_col_spacings(25)
        table.set_row_spacings(25)
        align.add(table)

        # "Current slide" frame
        frame = gtk.Frame("Current slide")
        table.attach(frame, 0, 6, 0, 1)
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(0, 0, 12, 0)
        frame.add(align)
        vbox = gtk.VBox()
        align.add(vbox)
        self.frame_current = gtk.AspectFrame(yalign=1, ratio=4./3., obey_child=False)
        vbox.pack_start(self.frame_current)
        self.eb_current = gtk.EventBox()
        self.eb_current.set_visible_window(False)
        self.eb_current.connect("event", self.on_label_event)
        vbox.pack_start(self.eb_current, False, False, 10)
        self.da_current = gtk.DrawingArea()
        self.da_current.modify_bg(gtk.STATE_NORMAL, black)
        self.da_current.connect("expose-event", self.on_expose)
        self.frame_current.add(self.da_current)

        # "Current slide" label and entry
        self.label_current = gtk.Label()
        self.label_current.set_justify(gtk.JUSTIFY_CENTER)
        self.label_current.set_use_markup(True)
        self.eb_current.add(self.label_current)
        self.entry_current = gtk.Entry()        
        self.entry_current.set_alignment(0.5)
        self.entry_current.modify_font(pango.FontDescription('36'))

        # "Next slide" frame
        frame = gtk.Frame("Next slide")
        table.attach(frame, 6, 10, 0, 1)
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(0, 0, 12, 0)
        frame.add(align)
        vbox = gtk.VBox()
        align.add(vbox)
        self.frame_next = gtk.AspectFrame(yalign=1, ratio=4./3., obey_child=False)
        vbox.pack_start(self.frame_next)
        self.label_next = gtk.Label()
        self.label_next.set_justify(gtk.JUSTIFY_CENTER)
        self.label_next.set_use_markup(True)
        vbox.pack_start(self.label_next, False, False, 10)
        self.da_next = gtk.DrawingArea()
        self.da_next.modify_bg(gtk.STATE_NORMAL, black)
        self.da_next.connect("expose-event", self.on_expose)
        self.frame_next.add(self.da_next)

        # "Time elapsed" frame
        frame = gtk.Frame("Time elapsed")
        table.attach(frame, 0, 5, 1, 2, yoptions=gtk.FILL)
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(10, 10, 12, 0)
        frame.add(align)
        self.label_time = gtk.Label()
        self.label_time.set_justify(gtk.JUSTIFY_CENTER)
        self.label_time.set_use_markup(True)
        align.add(self.label_time)

        # "Clock" frame
        frame = gtk.Frame("Clock")
        table.attach(frame, 5, 10, 1, 2, yoptions=gtk.FILL)
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(10, 10, 12, 0)
        frame.add(align)
        self.label_clock = gtk.Label()
        self.label_clock.set_justify(gtk.JUSTIFY_CENTER)
        self.label_clock.set_use_markup(True)
        align.add(self.label_clock)

        # Add events
        win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.SCROLL_MASK)
        win.connect("key-press-event", self.doc.navigation_cb)
        win.connect("scroll-event", self.doc.navigation_cb)

        if pympress.util.poppler_links_available():
            self.da_current.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
            self.da_current.connect("button-press-event", self.doc.link_cb, self.get_current_page)
            self.da_current.connect("motion-notify-event", self.doc.link_cb, self.get_current_page)

            self.da_next.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
            self.da_next.connect("button-press-event", self.doc.link_cb, self.get_next_page)
            self.da_next.connect("motion-notify-event", self.doc.link_cb, self.get_next_page)

        # Set page
        number, current, next = doc.get_two_pages(doc.nb_current)
        self.set_page(current, next, number, False)

        # Setup timer
        gobject.timeout_add(1000, self.update_time)

        win.show_all()

    def on_expose(self, widget, event):
        """
        Manage expose events by rendering the current page and the next page to
        the Presenter window.

        This function may be called manually to force the Presenter window to be
        refreshed immediately.

        @param widget: the widget in which the expose event occured
        @type  widget: gtk.Widget
        @param event: the event that occured
        @type  event: gtk.gdk.Event
        """
        if widget == self.da_current:
            self.page_current.render_on(widget)
        else:
            # Next page: it can be None
            if self.page_next is not None:
                self.page_next.render_on(widget)
            else:
                # Blank the widget
                cr = widget.window.cairo_create()
                cr.set_source_rgb(1, 1, 1)
                cr.scale(1, 1)
                ww, wh = widget.window.get_size()
                cr.rectangle(0, 0, ww, wh)
                cr.fill()

    def restore_current_label(self):
        """
        Make sure that the current page number is displayed in a label and not
        in an entry. If it is an entry, then replace it with the label.
        """
        child = self.eb_current.get_child()
        if child is not self.label_current:
            self.eb_current.remove(child)
            self.eb_current.add(self.label_current)

    def on_label_event(self, widget, event):
        """
        Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...
        
        @param widget: the widget in which the event occured
        @type  widget: gtk.Widget
        @param event: the event that occured
        @type  event: gtk.gdk.Event
        """

        widget = self.eb_current.get_child()

        # Click on the label
        if widget is self.label_current and event.type == gtk.gdk.BUTTON_PRESS:
            # Set entry text
            self.entry_current.set_text("%d/%d" % (self.doc.nb_current+1, self.doc.nb_pages))
            self.entry_current.select_region(0, -1)
            
            # Replace label with entry
            self.eb_current.remove(self.label_current)
            self.eb_current.add(self.entry_current)
            self.entry_current.show()
            self.entry_current.grab_focus()

        # Key pressed in the entry
        elif widget is self.entry_current and event.type == gtk.gdk.KEY_RELEASE:
            name = gtk.gdk.keyval_name(event.keyval)

            # Return key --> restore label and goto page
            if name == "Return" or name == "KP_Return":
                text = self.entry_current.get_text()
                self.restore_current_label()

                # Deal with the text
                n = self.doc.nb_current + 1
                try:
                    s = text.split('/')[0]
                    n = int(s)
                except ValueError:
                    print "Invalid number: %s" % text

                n -= 1
                if n != self.doc.nb_current and n >= 0 and n < self.doc.nb_pages:
                    self.doc.goto(n)

            # Escape key --> just restore the label
            elif name == "Escape":
                self.restore_current_label()                

        # Propagate the event further
        return False

    def set_page(self, current, next, number, start = True):
        """
        Switch to another page and display it.

        @param current: new current page to be displayed
        @type  current: L{pympress.Page}
        @param next: new next page to be displayed
        @type  next: L{pympress.Page}
        @param number: number of the new current page
        @type  number: integer
        @param start: specify whether this page change should start the timer or
        not
        @type  start: boolean
        """
        self.page_current = current
        self.page_next = next

        # Aspect ratios
        pr = self.page_current.get_aspect_ratio()
        self.frame_current.set_property("ratio", pr)

        # Same thing for next page if it's set
        if self.page_next is not None:
            pr = self.page_next.get_aspect_ratio()
            self.frame_next.set_property("ratio", pr)

        # Start counter if needed
        if start and self.start_time == 0:
            self.start_time = time.time()

        # Update display
        self.update_numbers()

        self.da_current.queue_draw()
        self.da_next.queue_draw()

    def get_current_page(self):
        """
        Return the current page.

        @return: current page
        @rtype: L{pympress.Page}
        """
        return self.page_current

    def get_next_page(self):
        """
        Return the next page.

        @return: next page
        @rtype: L{pympress.Page}
        """
        return self.page_next

    def update_numbers(self):
        """Update the displayed page numbers."""

        text = "<span font='36'>%s</span>"

        cur = "%d/%d" % (self.doc.nb_current+1, self.doc.nb_pages)
        next = "--"
        if self.doc.nb_current+2 <= self.doc.nb_pages:
            next = "%d/%d" % (self.doc.nb_current+2, self.doc.nb_pages)

        self.label_current.set_markup(text % cur)
        self.label_next.set_markup(text % next)
        self.restore_current_label()

    def update_time(self):
        """Update the timer and clock labels."""

        text = "<span font='36'>%s</span>"

        # Current time
        clock = time.strftime("%H:%M:%S")

        # Time elapsed since the beginning of the presentation
        if not self.paused:
            self.delta = time.time() - self.start_time
        if self.start_time == 0:
            self.delta = 0
        elapsed = "%02d:%02d" % (int(self.delta/60), int(self.delta%60))
        if self.paused:
            elapsed += " (pause)"

        self.label_time.set_markup(text % elapsed)
        self.label_clock.set_markup(text % clock)

        return True

    def switch_pause(self):
        """Switch the timer between paused mode and running (normal) mode."""

        if self.paused:
            self.start_time = time.time() - self.delta
            self.paused = False
        else:
            self.paused = True

    def reset_timer(self):
        """Reset the timer."""
        self.start_time = 0

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
