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

import os
import sys
import time

import pygtk
pygtk.require('2.0')
import gobject
import gtk
import pango

import pympress.pixbufcache
import pympress.util

class UI:
    """
    This class manages the GUI of pympress, which is made of two separate
    windows: the Content window, which displays only the current page in full
    size, and the Presenter window, which displays both the current and the next
    page, as well as a time counter and a clock.
    """

    def __init__(self, doc):
        black = gtk.gdk.Color(0, 0, 0)

        # Common to both windows
        icon_list = pympress.util.load_icons()

        # Pixbuf cache
        self.cache = pympress.pixbufcache.PixbufCache()

        # Content window
        self.c_win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.c_win.set_title("pympress content")
        self.c_win.set_default_size(800, 600)
        self.c_win.modify_bg(gtk.STATE_NORMAL, black)
        self.c_win.connect("delete-event", gtk.main_quit)
        self.c_win.set_icon_list(*icon_list)

        self.c_frame = gtk.AspectFrame(ratio=4./3., obey_child=False)
        self.c_frame.modify_bg(gtk.STATE_NORMAL, black)

        self.c_da = gtk.DrawingArea()
        self.c_da.modify_bg(gtk.STATE_NORMAL, black)
        self.c_da.connect("expose-event", self.on_expose)
        self.c_da.set_name("c_da")
        self.cache.add_widget("c_da")
        self.c_da.connect("configure-event", self.on_configure)

        self.c_frame.add(self.c_da)
        self.c_win.add(self.c_frame)

        self.c_win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.SCROLL_MASK)
        self.c_win.connect("key-press-event", self.on_navigation)
        self.c_win.connect("scroll-event", self.on_navigation)

        # Presenter window
        self.start_time = 0
        self.delta = 0
        self.paused = True

        p_win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        p_win.set_title("pympress presenter")
        p_win.set_default_size(800, 600)
        p_win.set_position(gtk.WIN_POS_CENTER)
        p_win.connect("delete-event", gtk.main_quit)
        p_win.set_icon_list(*icon_list)

        # Put Menu and Table in VBox
        bigvbox = gtk.VBox(False, 2)
        p_win.add(bigvbox)

        # A little space around everything in the window
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(20, 20, 20, 20)
        bigvbox.pack_end(align)

        # UI Manager for menu
        ui_manager = gtk.UIManager()

        # UI description
        ui_desc = '''
        <menubar name="MenuBar">
          <menu action="File">
            <menuitem action="Quit"/>
          </menu>
          <menu action="Presentation">
            <menuitem action="Pause timer"/>
            <menuitem action="Reset timer"/>
            <menuitem action="Fullscreen"/>
          </menu>
          <menu action="Help">
            <menuitem action="About"/>
          </menu>
        </menubar>'''
        ui_manager.add_ui_from_string(ui_desc)

        # Accelerator group
        accel_group = ui_manager.get_accel_group()
        p_win.add_accel_group(accel_group)

        # Action group
        action_group = gtk.ActionGroup("MenuBar")
        # Name, stock id, label, accelerator, tooltip, action [, is_active]
        action_group.add_actions([
            ("File",         None,           "_File"),
            ("Presentation", None,           "_Presentation"),
            ("Help",         None,           "_Help"),

            ("Quit",         gtk.STOCK_QUIT, "_Quit",        "q",  None, gtk.main_quit),
            ("Reset timer",  None,           "_Reset timer", "r",  None, self.reset_timer),
            ("About",        None,           "_About",       None, None, self.menu_about),
        ])
        action_group.add_toggle_actions([
            ("Pause timer",  None,           "_Pause timer", "p",  None, self.switch_pause,      True),
            ("Fullscreen",   None,           "_Fullscreen",  "f",  None, self.switch_fullscreen, False),
        ])
        ui_manager.insert_action_group(action_group)

        # Add menu bar to the window
        menubar = ui_manager.get_widget('/MenuBar')
        h = ui_manager.get_widget('/MenuBar/Help')
        h.set_right_justified(True)
        bigvbox.pack_start(menubar, False, True)
        
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
        self.p_frame_cur = gtk.AspectFrame(yalign=1, ratio=4./3., obey_child=False)
        vbox.pack_start(self.p_frame_cur)
        self.eb_cur = gtk.EventBox()
        self.eb_cur.set_visible_window(False)
        self.eb_cur.connect("event", self.on_label_event)
        vbox.pack_start(self.eb_cur, False, False, 10)
        self.p_da_cur = gtk.DrawingArea()
        self.p_da_cur.modify_bg(gtk.STATE_NORMAL, black)
        self.p_da_cur.connect("expose-event", self.on_expose)
        self.p_da_cur.set_name("p_da_cur")
        self.cache.add_widget("p_da_cur")
        self.p_da_cur.connect("configure-event", self.on_configure)
        self.p_frame_cur.add(self.p_da_cur)

        # "Current slide" label and entry
        self.label_cur = gtk.Label()
        self.label_cur.set_justify(gtk.JUSTIFY_CENTER)
        self.label_cur.set_use_markup(True)
        self.eb_cur.add(self.label_cur)
        self.entry_cur = gtk.Entry()
        self.entry_cur.set_alignment(0.5)
        self.entry_cur.modify_font(pango.FontDescription('36'))

        # "Next slide" frame
        frame = gtk.Frame("Next slide")
        table.attach(frame, 6, 10, 0, 1)
        align = gtk.Alignment(0.5, 0.5, 1, 1)
        align.set_padding(0, 0, 12, 0)
        frame.add(align)
        vbox = gtk.VBox()
        align.add(vbox)
        self.p_frame_next = gtk.AspectFrame(yalign=1, ratio=4./3., obey_child=False)
        vbox.pack_start(self.p_frame_next)
        self.label_next = gtk.Label()
        self.label_next.set_justify(gtk.JUSTIFY_CENTER)
        self.label_next.set_use_markup(True)
        vbox.pack_start(self.label_next, False, False, 10)
        self.p_da_next = gtk.DrawingArea()
        self.p_da_next.modify_bg(gtk.STATE_NORMAL, black)
        self.p_da_next.connect("expose-event", self.on_expose)
        self.p_da_next.set_name("p_da_next")
        self.cache.add_widget("p_da_next")
        self.p_da_next.connect("configure-event", self.on_configure)
        self.p_frame_next.add(self.p_da_next)

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

        bigvbox.pack_end(table, True, True, 0)
        p_win.connect("destroy", gtk.main_quit)
        p_win.show_all()


        # Add events
        p_win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.SCROLL_MASK)
        p_win.connect("key-press-event", self.on_navigation)
        p_win.connect("scroll-event", self.on_navigation)

        # Hyperlinks if available
        if pympress.util.poppler_links_available():
            self.c_da.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
            self.c_da.connect("button-press-event", self.on_link)
            self.c_da.connect("motion-notify-event", self.on_link)

            self.p_da_cur.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
            self.p_da_cur.connect("button-press-event", self.on_link)
            self.p_da_cur.connect("motion-notify-event", self.on_link)

            self.p_da_next.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
            self.p_da_next.connect("button-press-event", self.on_link)
            self.p_da_next.connect("motion-notify-event", self.on_link)

        # Don't start in fullscreen mode
        self.fullscreen = False

        # Setup timer
        gobject.timeout_add(250, self.update_time)
        
        # Document
        self.doc = doc

        # Show all windows
        self.c_win.show_all()
        p_win.show_all()


    def run(self):
        """Run the GTK main loop."""
        gtk.main()


    def menu_about(self, widget=None, event=None):
        about = gtk.AboutDialog()
        about.set_program_name("pympress")
        about.set_version("0.3")
        about.set_copyright("(c) 2009, 2010 Thomas Jost")
        about.set_comments("pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.")
        about.set_website("http://www.pympress.org/")
        #about.set_logo(gtk.gdk.pixbuf_new_from_file("pympress-128.png"))
        about.run()
        about.destroy()


    def on_page_change(self, unpause=True):
        """
        Switch to another page and display it.
        """
        page_cur = self.doc.current_page()
        page_next = self.doc.next_page()

        # Aspect ratios
        pr = page_cur.get_aspect_ratio()
        self.c_frame.set_property("ratio", pr)
        self.p_frame_cur.set_property("ratio", pr)

        if page_next is not None:
            pr = page_next.get_aspect_ratio()
            self.p_frame_next.set_property("ratio", pr)

        # Start counter if needed
        if unpause:
            self.paused = False
            if self.start_time == 0:
                self.start_time = time.time()

        # Update display
        self.update_page_numbers()

        # Don't queue draw event but draw directly (faster)
        self.on_expose(self.c_da)
        self.on_expose(self.p_da_cur)
        self.on_expose(self.p_da_next)


    def on_expose(self, widget, event=None):
        """
        Manage expose events by rendering the current page to the Content
        window.
        """

        if widget in [self.c_da, self.p_da_cur]:
            # Current page
            page = self.doc.current_page()
        else:
            # Next page: it can be None
            page = self.doc.next_page()
            if page is None:
                widget.hide_all()
                widget.parent.set_shadow_type(gtk.SHADOW_NONE)
                return
            else:
                widget.show_all()
                widget.parent.set_shadow_type(gtk.SHADOW_IN)

        # Instead of rendering the document to a Cairo surface (which is slow),
        # use a pixbuf from the cache if possible.
        name = widget.get_name()
        nb = page.number()
        pb = self.cache.get(name, nb)

        if pb is None:
            # Cache miss: render the page, and save it to the cache
            self.render_page(page, widget)
            ww, wh = widget.window.get_size()
            pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, ww, wh)
            pb.get_from_drawable(widget.window, widget.window.get_colormap(), 0, 0, 0, 0, ww, wh)
            self.cache.set(name, nb, pb)
        else:
            # Cache hit: draw the pixbuf from the cache to the widget
            gc = widget.window.new_gc()
            widget.window.draw_pixbuf(gc, pb, 0, 0, 0, 0)


    def on_configure(self, widget, event):
        self.cache.resize_widget(widget.get_name(), event.width, event.height)
        

    def on_navigation(self, widget, event):
        """
        Manage events as mouse scroll or clicks.
        """
        if event.type == gtk.gdk.KEY_PRESS:
            name = gtk.gdk.keyval_name(event.keyval)

            if name in ["Right", "Down", "Page_Down", "space"]:
                self.doc.goto_next()
            elif name in ["Left", "Up", "Page_Up", "BackSpace"]:
                self.doc.goto_prev()
            elif (name.upper() in ["F", "F11"]) \
                or (name == "Return" and event.state & gtk.gdk.MOD1_MASK) \
                or (name.upper() == "L" and event.state & gtk.gdk.CONTROL_MASK):
                self.switch_fullscreen()
            elif name.upper() == "Q":
                gtk.main_quit()
            elif name in ["p", "P", "Pause"]:
                self.switch_pause()
            elif name.upper() == "R":
                self.reset_timer()

        elif event.type == gtk.gdk.SCROLL:
            if event.direction in [gtk.gdk.SCROLL_RIGHT, gtk.gdk.SCROLL_DOWN]:
                self.doc.goto_next()
            else:
                self.doc.goto_prev()

        else:
            print "Unknown event %s" % event.type        


    def on_link(self, widget, event):
        """
        Manage events related to hyperlinks.

        @param widget: the widget in which the event occured
        @type  widget: gtk.Widget
        @param event: the event that occured
        @type  event: gtk.gdk.Event
        @param get_page: method returning the L{pympress.Page} on which the
        event occured
        @type  get_page: callable returning a L{pympress.Page} (or C{None})
        """

        # Where did the event occur?
        if widget is self.p_da_next:
            page = self.doc.next_page()
            if page is None:
                return
        else:
            page = self.doc.current_page()
            
        # Normalize event coordinates and get link
        x, y = event.get_coords()
        ww, wh = widget.window.get_size()
        x2, y2 = x/ww, y/wh
        link = page.get_link_at(x2, y2)

        # Event type?
        if event.type == gtk.gdk.BUTTON_PRESS:
            if link is not None:
                dest = link.get_destination()
                self.doc.goto(dest)

        elif event.type == gtk.gdk.MOTION_NOTIFY:
            if link is not None:
                cursor = gtk.gdk.Cursor(gtk.gdk.HAND2)
                widget.window.set_cursor(cursor)
            else:
                widget.window.set_cursor(None)

        else:
            print "Unknown event %s" % event.type
            

    def on_label_event(self, widget, event):
        """
        Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...
        """

        widget = self.eb_cur.get_child()

        # Click on the label
        if widget is self.label_cur and event.type == gtk.gdk.BUTTON_PRESS:
            # Set entry text
            self.entry_cur.set_text("%d/%d" % (self.doc.current_page().number()+1, self.doc.pages_number()))
            self.entry_cur.select_region(0, -1)

            # Replace label with entry
            self.eb_cur.remove(self.label_cur)
            self.eb_cur.add(self.entry_cur)
            self.entry_cur.show()
            self.entry_cur.grab_focus()

        # Key pressed in the entry
        elif widget is self.entry_cur and event.type == gtk.gdk.KEY_RELEASE:
            name = gtk.gdk.keyval_name(event.keyval)

            # Return key --> restore label and goto page
            if name == "Return" or name == "KP_Return":
                text = self.entry_cur.get_text()
                self.restore_current_label()

                # Deal with the text
                n = self.doc.current_page().number() + 1
                try:
                    s = text.split('/')[0]
                    n = int(s)
                except ValueError:
                    print "Invalid number: %s" % text

                n -= 1
                if n != self.doc.current_page().number():
                    if n <= 0:
                        n = 0
                    elif n >= self.doc.pages_number():
                        n = self.doc.pages_number() - 1
                    self.doc.goto(n)

            # Escape key --> just restore the label
            elif name == "Escape":
                self.restore_current_label()

        # Propagate the event further
        return False



    def render_page(self, page, widget):
        """Render the page on the specified widget."""

        # Make sure the widget is initialized
        if widget.window is None:
            return

        # Widget size
        ww, wh = widget.window.get_size()

        # Page size
        pw, ph = page.get_size()

        # Manual double buffering (since we use direct drawing instead of
        # calling queue_draw() on the widget)
        widget.window.begin_paint_rect(gtk.gdk.Rectangle(0, 0, ww, wh))

        cr = widget.window.cairo_create()
        cr.set_source_rgb(1, 1, 1)

        # Scale
        scale = min(ww/pw, wh/ph)
        cr.scale(scale, scale)

        cr.rectangle(0, 0, pw, ph)
        cr.fill()
        page.render_cairo(cr)

        # Blit off-screen buffer to screen
        widget.window.end_paint()
    

    def restore_current_label(self):
        """
        Make sure that the current page number is displayed in a label and not
        in an entry. If it is an entry, then replace it with the label.
        """
        child = self.eb_cur.get_child()
        if child is not self.label_cur:
            self.eb_cur.remove(child)
            self.eb_cur.add(self.label_cur)


    def update_page_numbers(self):
        """Update the displayed page numbers."""

        text = "<span font='36'>%s</span>"

        cur_nb = self.doc.current_page().number()
        cur = "%d/%d" % (cur_nb+1, self.doc.pages_number())
        next = "--"
        if cur_nb+2 <= self.doc.pages_number():
            next = "%d/%d" % (cur_nb+2, self.doc.pages_number())

        self.label_cur.set_markup(text % cur)
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
        elapsed = "%02d:%02d" % (int(self.delta/60), int(self.delta%60))
        if self.paused:
            elapsed += " (pause)"

        self.label_time.set_markup(text % elapsed)
        self.label_clock.set_markup(text % clock)

        return True


    def switch_pause(self, widget=None, event=None):
        """Switch the timer between paused mode and running (normal) mode."""

        if self.paused:
            self.start_time = time.time() - self.delta
            self.paused = False
        else:
            self.paused = True
        self.update_time()


    def reset_timer(self, widget=None, event=None):
        """Reset the timer."""
        self.start_time = time.time()
        self.update_time()


    def set_screensaver(self, must_disable):
        """
        Enable or disable the screensaver.

        @bug: At the moment, this is only supported on POSIX systems where
        xdg-screensaver is installed and working. For now, I{this feature has
        only been tested on Linux}.

        @param must_disable: if C{True}, indicates that the screensaver must be
        disabled; otherwise it will be enabled
        @type  must_disable: boolean
        """
        if os.name == 'posix':
            # On Linux, set screensaver with xdg-screensaver
            # (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
            cmd = "suspend" if must_disable else "resume"
            status = os.system("xdg-screensaver %s %s" % (cmd, self.c_win.window.xid))
            if status != 0:
                print >>sys.stderr, "Warning: Could not set screensaver status: got status %d" % status

            # Also manage screen blanking via DPMS
            if must_disable:
                # Get current DPMS status
                pipe = os.popen("xset q") # TODO: check if this works on all locales
                dpms_status = "Disabled"
                for line in pipe.readlines():
                    if line.count("DPMS is") > 0:
                        dpms_status = line.split()[-1]
                        break
                pipe.close()

                # Set the new value correctly
                if dpms_status == "Enabled":
                    self.dpms_was_enabled = True
                    status = os.system("xset -dpms")
                    if status != 0:
                        print >>sys.stderr, "Warning: Could not disable DPMS screen blanking: got status %d" % status
                else:
                    self.dpms_was_enabled = False

            elif self.dpms_was_enabled:
                # Re-enable DPMS
                status = os.system("xset +dpms")
                if status != 0:
                    print >>sys.stderr, "Warning: Could not enable DPMS screen blanking: got status %d" % status
        else:
            print >>sys.stderr, "Warning: Unsupported OS: can't enable/disable screensaver"


    def switch_fullscreen(self, widget=None, event=None):
        """
        Switch the Content window to fullscreen (if in normal mode) or to normal
        mode (if fullscreen).

        Screensaver will be disabled when entering fullscreen mode, and enabled
        when leaving fullscreen mode.
        """
        if self.fullscreen:
            self.c_win.unfullscreen()
            self.fullscreen = False
        else:
            self.c_win.fullscreen()
            self.fullscreen = True

        self.set_screensaver(self.fullscreen)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
