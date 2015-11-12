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

import os, os.path
import sys
import time

if os.name == 'nt':
    import winreg

import pkg_resources

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkX11
from gi.repository import GdkPixbuf
from gi.repository import Pango

import pympress.surfacecache
import pympress.util
import pympress.slideselector

#: "Regular" PDF file (without notes)
PDF_REGULAR      = 0
#: Content page (left side) of a PDF file with notes
PDF_CONTENT_PAGE = 1
#: Notes page (right side) of a PDF file with notes
PDF_NOTES_PAGE   = 2


class UI:
    """Pympress GUI management."""

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: Content window, as a :class:`Gtk.Window` instance.
    c_win = Gtk.Window(Gtk.WindowType.TOPLEVEL)
    #: :class:`~Gtk.AspectFrame` for the Content window.
    c_frame = Gtk.AspectFrame(yalign=0, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the Content window.
    c_da = Gtk.DrawingArea()

    #: Presentation window, as a :class:`Gtk.Window` instance.
    p_win = Gtk.Window(Gtk.WindowType.TOPLEVEL)
    #: :class:`~Gtk.AspectFrame` for the current slide in the Presenter window.
    p_frame_cur = Gtk.AspectFrame(yalign=0.5, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the current slide in the Presenter window.
    p_da_cur = Gtk.DrawingArea()
    #: Slide counter :class:`~Gtk.Label` for the current slide.
    label_cur = Gtk.Label()
    #: Slide counter :class:`~Gtk.Label` for the last slide.
    label_last = Gtk.Label()
    #: :class:`~Gtk.EventBox` associated with the slide counter label in the Presenter window.
    eb_cur = Gtk.EventBox()
    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur = False
    #: :class:`~Gtk.SpinButton` used to switch to another slide by typing its number.
    spin_cur = None

    #: :class:`~Gtk.AspectFrame` for the next slide in the Presenter window.
    p_frame_next = Gtk.AspectFrame(yalign=0.25, ratio=4./3., obey_child=False)
    #: :class:`~Gtk.DrawingArea` for the next slide in the Presenter window.
    p_da_next = Gtk.DrawingArea()

    #: Elapsed time :class:`~Gtk.Label`.
    label_time = Gtk.Label()
    #: Clock :class:`~Gtk.Label`.
    label_clock = Gtk.Label()

    #: Time at which the counter was started.
    start_time = 0
    #: Time elapsed since the beginning of the presentation.
    delta = 0
    #: Timer paused status.
    paused = True

    #: Fullscreen toggle. By default, don't start in fullscreen mode.
    fullscreen = False

    #: Current :class:`~pympress.document.Document` instance.
    doc = None

    #: Whether to use notes mode or not
    notes_mode = False

    #: number of page currently displayed in Controller window's miniatures
    page_preview_nb = 0

    #: remember screen saver setting before we change it
    screensaver_was_enabled = 0

    #: remember DPMS setting before we change it
    dpms_was_enabled = None

    #: track state of preview window
    p_win_maximized = True

    #: :class:`configparser.RawConfigParser` to remember preferences
    config = None

    def __init__(self, uri):
        """
        :param doc: the current document
        :type  doc: :class:`pympress.document.Document`
        """
        self.config = pympress.util.load_config()

        black = Gdk.Color(0, 0, 0)

        # Common to both windows
        icon_list = pympress.util.load_icons()

        # Document
        if uri is None:
            uri = self.open_file()
        self.doc = pympress.document.Document(self.on_page_change, uri)

        # Pixbuf cache
        self.cache = pympress.surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages', fallback=200))

        # Use notes mode by default if the document has notes
        self.notes_mode = self.doc.has_notes()

        # Content window
        self.c_win.set_title("pympress content")
        self.c_win.set_default_size(800, 600)
        self.c_win.modify_bg(Gtk.StateType.NORMAL, black)
        self.c_win.connect("delete-event", self.save_and_quit)
        self.c_win.set_icon_list(icon_list)

        self.c_frame.modify_bg(Gtk.StateType.NORMAL, black)
        self.c_frame.set_property("yalign", self.config.getfloat('content', 'yalign', fallback=0.5))
        self.c_frame.set_property("xalign", self.config.getfloat('content', 'xalign', fallback=0.5))
        self.c_frame.add(self.c_da)

        self.c_da.connect("draw", self.on_draw)
        self.c_da.set_name("c_da")
        if self.notes_mode:
            self.cache.add_widget("c_da", pympress.document.PDF_CONTENT_PAGE)
        else:
            self.cache.add_widget("c_da", pympress.document.PDF_REGULAR)
        self.c_da.connect("configure-event", self.on_configure_da)

        self.c_frame.set_shadow_type(Gtk.ShadowType.NONE)
        self.c_win.add(self.c_frame)

        self.c_win.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.c_win.connect("key-press-event", self.on_navigation)
        self.c_win.connect("scroll-event", self.on_navigation)

        # Presenter window
        self.p_win.set_title("pympress presenter")
        self.p_win.set_default_size(800, 600)
        self.p_win.set_position(Gtk.WindowPosition.CENTER)
        self.p_win.connect("delete-event", self.save_and_quit)
        self.p_win.set_icon_list(icon_list)

        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            cx, cy, cw, ch = self.c_win.get_position() + self.c_win.get_size()
            c_monitor = screen.get_monitor_at_point(cx + cw / 2, cy + ch / 2)
            p_monitor = 0 if c_monitor > 0 else 1

            p_bounds = screen.get_monitor_geometry(p_monitor)
            self.p_win.move(p_bounds.x, p_bounds.y)
            self.p_win.maximize()

            c_bounds = screen.get_monitor_geometry(c_monitor)
            self.c_win.move(c_bounds.x, c_bounds.y)
            self.c_win.fullscreen()
            self.fullscreen = True

        # Put Menu and Table in VBox
        bigvbox = Gtk.VBox(False, 2)
        self.p_win.add(bigvbox)

        # UI Manager for menu
        ui_manager = Gtk.UIManager()

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
            <menuitem action="Swap screens"/>
            <menuitem action="Notes mode"/>
            <menuitem action="Adjust screen"/>
          </menu>
          <menu action="Navigation">
            <menuitem action="Next"/>
            <menuitem action="Previous"/>
            <menuitem action="First"/>
            <menuitem action="Last"/>
            <menuitem action="Go to..."/>
          </menu>
          <menu action="Help">
            <menuitem action="About"/>
          </menu>
        </menubar>'''
        ui_manager.add_ui_from_string(ui_desc)

        # Accelerator group
        accel_group = ui_manager.get_accel_group()
        self.p_win.add_accel_group(accel_group)

        # Action group
        action_group = Gtk.ActionGroup("MenuBar")
        # Name, stock id, label, accelerator, tooltip, action [, is_active]
        action_group.add_actions([
            ("File",         None,           "_File"),
            ("Presentation", None,           "_Presentation"),
            ("Navigation",   None,           "_Navigation"),
            ("Help",         None,           "_Help"),

            ("Quit",         Gtk.STOCK_QUIT, "_Quit",        "q",     None, self.save_and_quit),
            ("Reset timer",  None,           "_Reset timer", "r",     None, self.reset_timer),
            ("About",        None,           "_About",       None,    None, self.menu_about),
            ("Swap screens", None,           "_Swap screens","s",     None, self.swap_screens),
            ("Adjust screen",None,           "Screen center",None,    None, self.adjust_frame_position),

            ("Next",         None,           "_Next",        "Right", None, self.doc.goto_next),
            ("Previous",     None,           "_Previous",    "Left",  None, self.doc.goto_prev),
            ("First",        None,           "_First",       "Home",  None, self.doc.goto_home),
            ("Last",         None,           "_Last",        "End",   None, self.doc.goto_end),
            ("Go to...",     None,           "_Go to...",    "g",     None, self.on_label_event),
        ])
        action_group.add_toggle_actions([
            ("Pause timer",  None,           "_Pause timer", "p",     None, self.switch_pause,      True),
            ("Fullscreen",   None,           "_Fullscreen",  "f",     None, self.switch_fullscreen, self.fullscreen),
            ("Notes mode",   None,           "_Note mode",   "n",     None, self.switch_mode,       self.notes_mode),
        ])
        ui_manager.insert_action_group(action_group)

        # Add menu bar to the window
        menubar = ui_manager.get_widget('/MenuBar')
        h = ui_manager.get_widget('/MenuBar/Help')
        h.set_right_justified(True)
        bigvbox.pack_start(menubar, False, False, 0)

        # Panes
        hpaned = Gtk.Paned()
        hpaned.set_orientation(Gtk.Orientation.HORIZONTAL)
        if gi.version_info >= (3,16): hpaned.set_wide_handle(True)
        hpaned.set_margin_top(5)
        hpaned.set_margin_bottom(5)
        hpaned.set_margin_left(5)
        hpaned.set_margin_right(5)
        bigvbox.pack_start(hpaned, True, True, 0)

        # "Current slide" frame
        self.p_frame_cur.set_label("Current slide")
        hpaned.pack1(self.p_frame_cur, True, True)
        self.p_da_cur.connect("draw", self.on_draw)
        self.p_da_cur.set_name("p_da_cur")
        if self.notes_mode:
            self.cache.add_widget("p_da_cur", PDF_NOTES_PAGE)
        else:
            self.cache.add_widget("p_da_cur", PDF_REGULAR)
        self.p_da_cur.connect("configure-event", self.on_configure_da)
        self.p_frame_cur.add(self.p_da_cur)

        # "Next slide" frame
        hpaned.pack2(self.p_frame_next, True, True)
        self.p_frame_next.set_label("Next slide")
        self.p_da_next.connect("draw", self.on_draw)
        self.p_da_next.set_name("p_da_next")
        if self.notes_mode:
            self.cache.add_widget("p_da_next", PDF_CONTENT_PAGE)
        else:
            self.cache.add_widget("p_da_next", PDF_REGULAR)
        self.p_da_next.connect("configure-event", self.on_configure_da)
        self.p_frame_next.add(self.p_da_next)

        hbox = Gtk.HBox()

        # "Current slide" label and entry. eb_cur gets all events on the whole,
        # label_cur may be replaced by spin_cur at times, last_cur doesn't move
        self.label_cur.props.halign = Gtk.Align.END
        self.label_cur.set_use_markup(True)
        self.label_last.props.halign = Gtk.Align.START
        self.label_last.set_use_markup(True)
        self.hb_cur=Gtk.HBox()
        self.hb_cur.pack_start(self.label_cur, True, True, 0)
        self.hb_cur.pack_start(self.label_last, True, True, 0)
        self.eb_cur.add(self.hb_cur)
        self.spin_cur = pympress.slideselector.SlideSelector(self, self.doc.pages_number())
        self.spin_cur.set_alignment(0.5)
        self.spin_cur.modify_font(Pango.FontDescription('36'))

        self.eb_cur.set_visible_window(False)
        self.eb_cur.connect("event", self.on_label_event)
        frame = Gtk.Frame()
        frame.set_label("Slide number")
        frame.add(self.eb_cur)
        hbox.pack_start(frame, True, True, 5)

        # "Time elapsed" frame
        frame = Gtk.Frame()
        frame.set_label("Time elapsed")
        hbox.pack_start(frame, True, True, 0)
        frame.add(self.label_time)
        self.label_time.set_use_markup(True)
        self.label_time.set_justify(Gtk.Justification.CENTER)
        self.label_time.set_width_chars(44) # close enough to 13 characters at font size 36

        # "Clock" frame
        frame = Gtk.Frame()
        frame.set_label("Clock")
        hbox.pack_end(frame, True, True, 5)
        frame.add(self.label_clock)
        self.label_clock.set_justify(Gtk.Justification.CENTER)
        self.label_clock.set_use_markup(True)

        bigvbox.pack_end(hbox, False, False, 5)

        self.p_win.connect("destroy", self.save_and_quit)
        self.p_win.show_all()

        pane_size = self.config.getfloat('presenter', 'slide_ratio', fallback=0.75)
        avail_size = self.p_frame_cur.get_allocated_width() + self.p_frame_next.get_allocated_width()
        margins = hpaned.get_allocated_width() - avail_size
        hpaned.set_position(int(round(pane_size * avail_size)))

        # Add events
        self.p_win.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.p_win.connect("key-press-event", self.on_navigation)
        self.p_win.connect("scroll-event", self.on_navigation)
        self.p_win.connect("window-state-event", self.track_pwin_maximized)

        # Hyperlinks if available
        if pympress.util.poppler_links_available():
            self.c_da.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
            self.c_da.connect("button-press-event", self.on_link)
            self.c_da.connect("motion-notify-event", self.on_link)

            self.p_da_cur.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
            self.p_da_cur.connect("button-press-event", self.on_link)
            self.p_da_cur.connect("motion-notify-event", self.on_link)

            self.p_da_next.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
            self.p_da_next.connect("button-press-event", self.on_link)
            self.p_da_next.connect("motion-notify-event", self.on_link)

        # Setup timer
        GObject.timeout_add(250, self.update_time)

        # Show all windows
        self.c_win.show_all()
        self.p_win.show_all()

        # Compute first slides to show
        time.sleep(0.250)
        self.on_page_change(False)


    def run(self):
        """Run the GTK main loop."""
        Gtk.main()


    def save_and_quit(self, *args):
        """Save configuration and exit the main loop"""
        cur_pane_size = self.p_frame_cur.get_allocated_width()
        next_pane_size = self.p_frame_next.get_allocated_width()
        # 5 is handle width
        ratio = float(cur_pane_size) / (cur_pane_size + next_pane_size)
        self.config.set('presenter', 'slide_ratio', "{0:.2f}".format(ratio))

        self.config.set('cache', 'maxpages', str(self.config.getint('cache', 'maxpages', fallback=200)))

        pympress.util.save_config(self.config)
        Gtk.main_quit()


    def open_file(self):
        # Use a GTK file dialog to choose file
        dialog = Gtk.FileChooserDialog("Open...", self.p_win,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        filter = Gtk.FileFilter()
        filter.set_name("PDF files")
        filter.add_mime_type("application/pdf")
        filter.add_pattern("*.pdf")
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        dialog.add_filter(filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            name = dialog.get_filename()
            dialog.destroy()
        else:
            dialog.destroy()

            # Use a GTK dialog to tell we need a file
            msg="""No file selected!\n\nYou can specify the PDF file to open on the command line if you don't want to use the "Open File" dialog."""
            dialog = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format=msg, parent=self.p_win)
            dialog.set_position(Gtk.WindowPosition.CENTER)
            dialog.run()
            sys.exit(1)

        return "file://" + os.path.abspath(name)


    def menu_about(self, widget=None, event=None):
        """Display the "About pympress" dialog."""
        about = Gtk.AboutDialog()
        about.set_program_name("pympress")
        about.set_version(pympress.__version__)
        about.set_copyright("(c) 2009, 2010 Thomas Jost")
        about.set_comments("pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.\nSome preferences are saved in "+pympress.utils.path_to_config())
        about.set_website("http://www.pympress.org/")
        try:
            req = pkg_resources.Requirement.parse("pympress")
            icon_fn = pkg_resources.resource_filename(req, "share/pixmaps/pympress-128.png")
            about.set_logo(GdkPixbuf.Pixbuf.new_from_file(icon_fn))
        except Exception as e:
            print(e)
        about.run()
        about.destroy()


    def page_preview(self, page_nb):
        """
        Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        :param unpause: ``True`` if the page change should unpause the timer,
           ``False`` otherwise
        :type  unpause: boolean
        """
        page_cur = self.doc.page(page_nb)
        page_next = self.doc.page(page_nb+1)

        self.page_preview_nb = page_nb

        # Aspect ratios and queue redraws
        pr = page_cur.get_aspect_ratio(self.notes_mode)
        self.p_frame_cur.set_property("ratio", pr)

        if page_next is not None:
            pr = page_next.get_aspect_ratio(self.notes_mode)
            self.p_frame_next.set_property("ratio", pr)

        # queue redraws
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()


        # Prerender the 4 next pages and the 2 previous ones
        cur = page_cur.number()
        page_max = min(self.doc.pages_number(), cur + 5)
        page_min = max(0, cur - 2)
        for p in list(range(cur+1, page_max)) + list(range(cur, page_min, -1)):
            self.cache.prerender(p)


    def on_page_change(self, unpause=True):
        """
        Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        :param unpause: ``True`` if the page change should unpause the timer,
           ``False`` otherwise
        :type  unpause: boolean
        """
        page_cur = self.doc.current_page()
        page_next = self.doc.next_page()

        # Page change: resynchronize miniatures
        self.page_preview_nb = page_cur.number()

        # Aspect ratios
        pr = page_cur.get_aspect_ratio(self.notes_mode)
        self.c_frame.set_property("ratio", pr)
        self.p_frame_cur.set_property("ratio", pr)

        if page_next is not None:
            pr = page_next.get_aspect_ratio(self.notes_mode)
            self.p_frame_next.set_property("ratio", pr)

        # Queue redraws
        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()


        # Start counter if needed
        if unpause:
            self.paused = False
            if self.start_time == 0:
                self.start_time = time.time()

        # Update display
        self.update_page_numbers()

        # Prerender the 4 next pages and the 2 previous ones
        page_max = min(self.doc.pages_number(), self.page_preview_nb + 5)
        page_min = max(0, self.page_preview_nb - 2)
        for p in list(range(self.page_preview_nb+1, page_max)) + list(range(self.page_preview_nb, page_min, -1)):
            self.cache.prerender(p)


    def on_draw(self, widget, cairo_context):
        """
        Manage draw events for both windows.

        This callback may be called either directly on a page change or as an
        event handler by GTK. In both cases, it determines which widget needs to
        be updated, and updates it, using the
        :class:`~pympress.surfacecache.SurfaceCache` if possible.

        :param widget: the widget to update
        :type  widget: :class:`Gtk.Widget`
        :param cairo_context: the Cairo context (or ``None`` if called directly)
        :type  cairo_context: :class:`cairo.Context`
        """

        if widget is self.c_da:
            # Current page
            page = self.doc.page(self.doc.current_page().number())
        elif widget is self.p_da_cur:
            # Current page 'preview'
            page = self.doc.page(self.page_preview_nb)
        else:
            page = self.doc.page(self.page_preview_nb+1)
            # No next page: just return so we won't draw anything
            if page is None:
                return

        # Instead of rendering the document to a Cairo surface (which is slow),
        # use a surface from the cache if possible.
        name = widget.get_name()
        nb = page.number()
        pb = self.cache.get(name, nb)
        wtype = self.cache.get_widget_type(name)

        if pb is None:
            # Cache miss: render the page, and save it to the cache
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            pb = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, ww, wh)

            cairo_prerender = cairo.Context(pb)
            page.render_cairo(cairo_prerender, ww, wh, wtype)

            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()

            self.cache.set(name, nb, pb)
        else:
            # Cache hit: draw the surface from the cache to the widget
            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()


    def on_configure_da(self, widget, event):
        """
        Manage "configure" events for both windows.

        In the GTK world, this event is triggered when a widget's configuration
        is modified, for example when its size changes. So, when this event is
        triggered, we tell the local :class:`~pympress.surfacecache.SurfaceCache`
        instance about it, so that it can invalidate its internal cache for the
        specified widget and pre-render next pages at a correct size.

        :param widget: the widget which has been resized
        :type  widget: :class:`Gtk.Widget`
        :param event: the GTK event, which contains the new dimensions of the
           widget
        :type  event: :class:`Gdk.Event`
        """
        self.cache.resize_widget(widget.get_name(), event.width, event.height)


    def on_navigation(self, widget, event):
        """
        Manage events as mouse scroll or clicks for both windows.

        :param widget: the widget in which the event occured (ignored)
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
        """
        if event.type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and self.spin_cur.on_keypress(widget, event):
                return True

            if name in ["Right", "Down", "Page_Down", "space"]:
                self.doc.goto_next()
            elif name in ["Left", "Up", "Page_Up", "BackSpace"]:
                self.doc.goto_prev()
            elif name == 'Home':
                self.doc.goto_home()
            elif name == 'End':
                self.doc.goto_end()
            # sic - acceletator recognizes f not F
            elif name.upper() == "F11" or name == "F" \
                or (name == "Return" and event.get_state() & Gdk.ModifierType.MOD1_MASK) \
                or (name.upper() == "L" and event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                self.switch_fullscreen()
            elif name.upper() == "Q":
                self.save_and_quit()
            elif name == "Pause":
                self.switch_pause()
            elif name.upper() == "R":
                self.reset_timer()

            # Some key events are already handled by toggle actions in the
            # presenter window, so we must handle them in the content window
            # only to prevent them from double-firing
            if widget is self.c_win:
                if name.upper() == "P":
                    self.switch_pause()
                elif name.upper() == "N":
                    self.switch_mode()
                elif name.upper() == "S":
                    self.swap_screens()
                elif name.upper() == "F":
                    self.switch_fullscreen()
                elif name.upper() == "G":
                    self.on_label_event(self.eb_cur, True)
                else:
                    return False

                return True
            else:
                return False

            return True

        elif event.type == Gdk.EventType.SCROLL:

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and self.spin_cur.on_keypress(widget, event):
                return True

            if event.direction is Gdk.ScrollDirection.SMOOTH:
                return False
            elif event.direction in [Gdk.ScrollDirection.RIGHT, Gdk.ScrollDirection.DOWN]:
                self.doc.goto_next()
            else:
                self.doc.goto_prev()

            return True

        else:
            print("Unknown event " + str(event.type))

        return False


    def on_link(self, widget, event):
        """
        Manage events related to hyperlinks.

        :param widget: the widget in which the event occured
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
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
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        x2, y2 = x/ww, y/wh
        link = page.get_link_at(x2, y2)

        # Event type?
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if link is not None:
                dest = link.get_destination()
                self.doc.goto(dest)

        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            if link is not None:
                cursor = Gdk.Cursor.new(Gdk.HAND2)
                widget.get_window().set_cursor(cursor)
            else:
                widget.get_window().set_cursor(None)

        else:
            print("Unknown event " + str(event.type))


    def on_label_event(self, *args):
        """
        Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...

        :param widget: the widget in which the event occured
        :type  widget: :class:`Gtk.Widget`
        :param event: the event that occured
        :type  event: :class:`Gdk.Event`
        """

        event=args[-1]

        # Click in label-mode
        if (
            (type(event) == bool and event is True) or # forced manually
            (type(event) == Gtk.Action) or # menu action
            (type(event) == Gdk.Event and event.type == Gdk.EventType.BUTTON_PRESS) # click
        ):
            if self.label_cur in self.hb_cur:
                # Replace label with entry
                self.hb_cur.remove(self.label_cur)
                self.spin_cur.show()
                self.hb_cur.add(self.spin_cur)
                self.hb_cur.reorder_child(self.spin_cur, 0)
                self.spin_cur.grab_focus()
                self.editing_cur = True

                self.spin_cur.set_value(self.doc.current_page().number()+1)
                self.spin_cur.select_region(0, -1)

            elif self.editing_cur:
                self.spin_cur.grab_focus()

        else:
            # Ignored event - propagate further
            return False

        return True


    def restore_current_label(self):
        """
        Make sure that the current page number is displayed in a label and not
        in an entry. If it is an entry, then replace it with the label.
        """
        if self.label_cur not in self.hb_cur:
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing_cur = False


    def update_page_numbers(self):
        """Update the displayed page numbers."""

        text = "<span font='36'>{}</span>"

        cur_nb = self.doc.current_page().number()
        cur = str(cur_nb+1)
        last = "/{}".format(self.doc.pages_number())

        self.label_cur.set_markup(text.format(cur))
        self.label_last.set_markup(text.format(last))
        self.restore_current_label()


    def update_time(self):
        """
        Update the timer and clock labels.

        :return: ``True`` (to prevent the timer from stopping)
        :rtype: boolean
        """

        # Current time
        clock = time.strftime("%H:%M:%S")

        # Time elapsed since the beginning of the presentation
        if not self.paused:
            self.delta = time.time() - self.start_time
        elapsed = "{:02}:{:02}".format(int(self.delta/60), int(self.delta%60))
        if self.paused:
            elapsed += " (pause)"

        self.label_time.set_markup("<span font='36'>{}</span>".format(elapsed))
        self.label_clock.set_markup("<span font='24'>{}</span>".format(clock))

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
        self.delta = 0
        self.update_time()


    def set_screensaver(self, must_disable):
        """
        Enable or disable the screensaver.

        .. warning:: At the moment, this is only supported on POSIX systems
           where :command:`xdg-screensaver` is installed and working. For now,
           this feature has only been tested on **Linux with xscreensaver**.

        :param must_disable: if ``True``, indicates that the screensaver must be
           disabled; otherwise it will be enabled
        :type  must_disable: boolean
        """
        if os.name == 'posix':
            # On Linux, set screensaver with xdg-screensaver
            # (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
            cmd = "suspend" if must_disable else "resume"
            status = os.system("xdg-screensaver {} {}".format(cmd, self.c_win.get_window().get_xid()))
            if status != 0:
                print("Warning: Could not set screensaver status: got status "+str(status), file=sys.stderr)

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
                        print("Warning: Could not disable DPMS screen blanking: got status "+str(status), file=sys.stderr)
                else:
                    self.dpms_was_enabled = False

            elif self.dpms_was_enabled:
                # Re-enable DPMS
                status = os.system("xset +dpms")
                if status != 0:
                    print("Warning: Could not enable DPMS screen blanking: got status "+str(status), file=sys.stderr)
        elif os.name == 'nt':
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Control Panel\Desktop') as key:
                if must_disable:
                    (keytype,self.screensaver_was_enabled) = winreg.QueryValueEx(key, "ScreenSaveActive")
                    winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "0")
                elif self.screensaver_was_enabled != "0":
                    winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, self.screensaver_was_enabled)
        else:
            print("Warning: Unsupported OS: can't enable/disable screensaver", file=sys.stderr)


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


    def track_pwin_maximized(self, widget, event, user_data=None):
        """
        Track whether the preview window is maximized
        """
        self.p_win_maximized = (Gdk.WindowState.MAXIMIZED & event.new_window_state) != 0


    def update_frame_position(self, widget=None, user_data=None):
        if widget and user_data:
            self.c_frame.set_property(user_data, widget.get_value())


    def adjust_frame_position(self, widget=None, event=None):
        """
        Select how to align the frame on screen
        """
        if self.c_frame.get_allocated_width() == self.c_da.get_allocated_width():
            prop = "yalign"
        else:
            prop = "xalign"

        val = self.c_frame.get_property(prop)

        button = Gtk.SpinButton()
        button.set_adjustment(Gtk.Adjustment(lower=0.0, upper=1.0, step_incr=0.01))
        button.set_digits(2)
        button.set_value(val)
        button.connect("value-changed", self.update_frame_position, prop)

        popup = Gtk.Dialog("Adjust alignment of slides in projector screen", self.p_win, 0,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OK, Gtk.ResponseType.OK))

        box = popup.get_content_area()
        box.add(button)
        popup.show_all()
        response = popup.run()
        popup.destroy()

        # revert if we cancelled
        if response == Gtk.ResponseType.CANCEL:
            self.c_frame.set_property(prop, val)
        else:
            self.config.set('content', prop, str(button.get_value()))


    def swap_screens(self, widget=None, event=None):
        """
        Swap the monitors on which each window is displayed (if there are 2 monitors at least)
        """
        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            cx, cy, cw, ch = self.c_win.get_position() + self.c_win.get_size()
            px, py, pw, ph = self.p_win.get_position() + self.p_win.get_size()
            p_monitor = screen.get_monitor_at_point(px + pw / 2, py + ph / 2)
            c_monitor = screen.get_monitor_at_point(cx + cw / 2, cy + ch / 2)

            if p_monitor == c_monitor:
                return

            p_monitor, c_monitor = (c_monitor, p_monitor)

            p_bounds = screen.get_monitor_geometry(p_monitor)
            if self.p_win_maximized:
                self.p_win.unmaximize()
                self.p_win.move(p_bounds.x + (p_bounds.width - pw) / 2, p_bounds.y + (p_bounds.height - ph) / 2)
                self.p_win.maximize()
            else:
                self.p_win.move(p_bounds.x + (p_bounds.width - pw) / 2, p_bounds.y + (p_bounds.height - ph) / 2)

            c_bounds = screen.get_monitor_geometry(c_monitor)
            if self.fullscreen:
                self.c_win.unfullscreen()
                self.c_win.move(c_bounds.x + (c_bounds.width - cw) / 2, c_bounds.y + (c_bounds.height - ch) / 2)
                self.c_win.fullscreen()
            else:
                self.c_win.move(c_bounds.x + (c_bounds.width - cw) / 2, c_bounds.y + (c_bounds.height - ch) / 2)

        self.on_page_change(False)


    def switch_mode(self, widget=None, event=None):
        """
        Switch the display mode to "Notes mode" or "Normal mode" (without notes)
        """
        if self.notes_mode:
            self.notes_mode = False
            self.cache.set_widget_type("c_da", PDF_REGULAR)
            self.cache.set_widget_type("p_da_cur", PDF_REGULAR)
            self.cache.set_widget_type("p_da_next", PDF_REGULAR)
        else:
            self.notes_mode = True
            self.cache.set_widget_type("c_da", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_cur", PDF_NOTES_PAGE)
            self.cache.set_widget_type("p_da_next", PDF_CONTENT_PAGE)

        self.on_page_change(False)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
