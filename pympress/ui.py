#       ui.py
#
#       Copyright 2010 Thomas Jost <thomas.jost@gmail.com>
#       Copyright 2015 Cimbali <me@cimba.li>
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

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import os.path

import pkg_resources

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Gtk, Gdk, GLib

#: "Regular" PDF file (without notes)
PDF_REGULAR      = 0
#: Content page (left side) of a PDF file with notes
PDF_CONTENT_PAGE = 1
#: Notes page (right side) of a PDF file with notes
PDF_NOTES_PAGE   = 2


from pympress import __main__, document, surfacecache, util, pointer, scribble, config, builder, talk_time, extras, editable_label


class UI(builder.Builder):
    """ Pympress GUI management.

    Args:
        ett (`int`):  the estimated (intended) talk time
        docpath (`str`): path to the file passed on the command line
    """
    #: Content window, as a :class:`~Gtk.Window` instance.
    c_win = None
    #: :class:`~Gtk.AspectFrame` for the Content window.
    c_frame = None
    #: :class:`~Gtk.DrawingArea` for the Content window.
    c_da = None

    #: Presenter window, as a :class:`~Gtk.Window` instance.
    p_win = None
    #: :class:`~Gtk.Box` for the Presenter window.
    p_central = None
    #: :class:`~Gtk.AspectFrame` for the current slide in the Presenter window.
    p_frame_notes = None
    #: :class:`~Gtk.DrawingArea` for the current slide in the Presenter window.
    p_da_notes = None

    #: :class:`~Gtk.AspectFrame` for the next slide in the Presenter window.
    p_frame_next = None
    #: :class:`~Gtk.DrawingArea` for the next slide in the Presenter window.
    p_da_next = None
    #: :class:`~Gtk.AspectFrame` for the current slide copy in the Presenter window.
    p_frame_cur = None
    #: :class:`~Gtk.DrawingArea` for the current slide copy in the Presenter window.
    p_da_cur = None

    #: :class:`~Gtk.Frame` for the annotations in the Presenter window.
    p_frame_annot = None

    #: Indicates whether we should delay redraws on some drawing areas to fluidify resizing gtk.paned
    resize_panes = False
    #: Tracks return values of GLib.timeout_add to cancel gtk.paned's redraw callbacks
    redraw_timeout = 0

    #: Whether to use notes mode or not
    notes_mode = False

    #: Whether to display annotations or not
    show_annotations = True
    #: Whether to display big buttons or not
    show_bigbuttons = True
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to previous slide
    prev_button = None
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to next slide
    next_button = None
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to scribble on screen
    highlight_button = None

    #: number of page currently displayed in Controller window's miniatures
    page_preview_nb = -1

    #: track whether we blank the screen
    blanked = False

    #: Dictionary of :class:`~Gtk.Widget` from the presenter window that can be dynamically rearranged
    placeable_widgets = {}
    #: Map of :class:`~Gtk.Paned` to the relative position (`float` between 0 and 1) of its handle
    pane_handle_pos = {}

    #: :class:`~pympress.config.Config` to remember preferences
    config = config.Config()

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: Current :class:`~pympress.document.Document` instance.
    doc = document.EmptyDocument()

    #: Class :class:`~pympress.scribble.Scribble` managing drawing by the user on top of the current slide.
    scribbler = None
    #: Class :class:`~pympress.extras.Annotations` managing the display of annotations
    annotations = None
    #: Class :class:`~pympress.extras.Media` managing keeping track of and callbacks on media overlays
    medias = None

    #: Software-implemented laser pointer, :class:`~pympress.pointer.Pointer`
    laser = None

    #: :class:`~pympress.editable_label.PageNumber` displaying current and max page numbers and setting current page number
    page_number = None

    #: :class:`~pympress.editable_label.EstimatedTalkTime` to set estimated/remaining talk time
    est_time = None
    #: :class:`~pympress.talk_time.TalkTime` clock tracking talk time (elapsed, and remaining)
    talk_time = None


    ##############################################################################
    #############################      UI setup      #############################
    ##############################################################################

    def __init__(self, ett = 0, docpath = None):
        super(UI, self).__init__()
        self.blanked = self.config.getboolean('content', 'start_blanked')

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            util.get_style_provider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.show_annotations = self.config.getboolean('presenter', 'show_annotations')

        # Surface cache
        self.cache = surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages'))

        # Make and populate windows
        self.load_ui('presenter')
        self.load_ui('content')

        self.scribbler = scribble.Scribbler(self.config, self, self.notes_mode)
        self.annotations = extras.Annotations(self)
        self.medias = extras.Media(self)
        self.laser = pointer.Pointer(self.config, self)
        self.est_time = editable_label.EstimatedTalkTime(self, ett)
        self.page_number = editable_label.PageNumber(self)
        self.talk_time = talk_time.TimeCounter(self, self.est_time)

        # solve circular creation-time dependency
        self.est_time.delayed_callback_connection(self)

        # Get placeable widgets. NB, ids are slightly shorter than names.
        self.placeable_widgets = {
            name: self.get_object('p_frame_' + ('cur' if name == 'current' else name[:5])) for name in self.config.placeable_widgets
        }

        # Initialize windows and screens
        self.setup_screens()
        self.c_win.show_now()
        self.p_win.show_now()

        self.make_cwin()
        self.make_pwin()

        self.connect_signals(self)

        # Common to both windows
        icon_list = util.load_icons()
        self.c_win.set_icon_list(icon_list)
        self.p_win.set_icon_list(icon_list)

        # Show all windows
        self.c_win.show_all()
        self.p_win.show_all()

        # Initialize doc last. Use notes mode by default if the document has notes
        if docpath:
            self.swap_document(docpath)
            self.scribbler.cache.swap_document(docpath)
        else:
            GLib.idle_add(self.pick_file)

        # Queue some redraws
        self.c_da.queue_draw()
        self.redraw_panes()
        self.on_page_change(False)

        # Adjust default visibility of items
        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)
        self.p_frame_annot.set_visible(self.show_annotations)


    def make_cwin(self):
        """ Initializes the content window.
        """
        self.c_frame.set_property("yalign", self.config.getfloat('content', 'yalign'))
        self.c_frame.set_property("xalign", self.config.getfloat('content', 'xalign'))
        if self.notes_mode:
            page_type = document.PDF_CONTENT_PAGE
        else:
            page_type = document.PDF_REGULAR

        self.cache.add_widget("c_da", page_type)
        self.c_frame.set_property("ratio", self.doc.current_page().get_aspect_ratio(page_type))


    def make_pwin(self):
        """ Initializes the presenter window.
        """
        if self.notes_mode:
            layout = self.config.get_notes_layout()
        else:
            layout = self.config.get_plain_layout()

        pane_handles = self.replace_layout(layout, self.p_central, self.placeable_widgets, self.on_pane_event)
        self.pane_handle_pos.update(pane_handles)

        self.show_bigbuttons = self.config.getboolean('presenter', 'show_bigbuttons')

        init_checkstates = {
            'pres_pause':      True,
            'pres_fullscreen': bool(self.c_win.get_window().get_state() & Gdk.WindowState.FULLSCREEN),
            'pres_notes':      self.notes_mode,
            'pres_blank':      self.blanked,
            'pres_annot':      self.show_annotations,
            'pres_buttons':    self.show_bigbuttons,
            'pres_highlight':  False,

            'start_blanked':   self.config.getboolean('content', 'start_blanked'),
            'start_cwin_full': self.config.getboolean('content', 'start_fullscreen'),
            'start_pwin_full': self.config.getboolean('presenter', 'start_fullscreen'),
        }

        for n in init_checkstates:
            self.get_object(n).set_active(init_checkstates[n])

        if self.notes_mode:
            self.cache.add_widget("p_da_cur", PDF_CONTENT_PAGE)
            self.cache.add_widget("p_da_next", PDF_CONTENT_PAGE)
            self.cache.add_widget("p_da_notes", PDF_NOTES_PAGE)
        else:
            self.cache.add_widget("p_da_cur", PDF_REGULAR)
            self.cache.add_widget("p_da_next", PDF_REGULAR)
            self.cache.add_widget("p_da_notes", PDF_REGULAR, False)


        # set default value
        self.page_number.set_last(self.doc.pages_number())

        # Enable dropping files onto the window
        self.p_win.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.p_win.drag_dest_add_text_targets()


    def setup_screens(self):
        """ Sets up the position of the windows
        """
        # If multiple monitors, apply windows to monitors according to config
        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            c_monitor = self.config.getint('content', 'monitor')
            p_monitor = self.config.getint('presenter', 'monitor')
            p_full = self.config.getboolean('presenter', 'start_fullscreen')
            c_full = self.config.getboolean('content', 'start_fullscreen')

            if c_monitor == p_monitor and (c_full or p_full):
                logger.warning(_("Content and presenter window must not be on the same monitor if you start full screen!"))
                p_monitor = 0 if c_monitor > 0 else 1
        else:
            c_monitor = 0
            p_monitor = 0
            c_full = False
            p_full = False

            if self.config.getboolean('presenter', 'start_fullscreen') or self.config.getboolean('content', 'start_fullscreen'):
                logger.warning(_("Not starting content or presenter window full screen because there is only one monitor"))

        p_bounds = screen.get_monitor_geometry(p_monitor)
        self.p_win.move(p_bounds.x, p_bounds.y)
        self.p_win.resize(p_bounds.width, p_bounds.height)
        if p_full:
            self.p_win.fullscreen()
        else:
            self.p_win.maximize()

        c_bounds = screen.get_monitor_geometry(c_monitor)
        self.c_win.move(c_bounds.x, c_bounds.y)
        self.c_win.resize(c_bounds.width, c_bounds.height)
        if c_full:
            self.c_win.fullscreen()


    ##############################################################################
    ############################   Dynamic resize   ##############################
    ##############################################################################

    def on_configure_da(self, widget, event):
        """ Manage "configure" events for all drawing areas, e.g. resizes.

        We tell the local :class:`~pympress.surfacecache.SurfaceCache` cache about it, so that it can
        invalidate its internal cache for the specified widget and pre-render next pages at a correct size.

        Warning: Some not-explicitely sent signals contain wrong values! Just don't resize in that case,
        since these always seem to happen after a correct signal that was sent explicitely.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has been resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """

        # Don't trust those
        if not event.send_event:
            return

        self.cache.resize_widget(widget.get_name(), event.width, event.height)

        if widget is self.c_da:
            self.medias.resize()


    def on_configure_win(self, widget, event):
        """ Manage "configure" events for both window widgets.

        Args:
            widget (:class:`~Gtk.Widget`):  the window which has been moved or resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        if widget is self.p_win:
            p_monitor = self.p_win.get_screen().get_monitor_at_window(self.p_frame_cur.get_parent_window())
            self.config.set('presenter', 'monitor', str(p_monitor))
            cw = self.p_central.get_allocated_width()
            ch = self.p_central.get_allocated_height()
            self.scribbler.off_render.set_size_request(cw, ch)

        elif widget is self.c_win:
            c_monitor = self.c_win.get_screen().get_monitor_at_window(self.c_frame.get_parent_window())
            self.config.set('content', 'monitor', str(c_monitor))


    def redraw_panes(self):
        """ Handler for :class:`~Gtk.Paned`'s resizing signal, used for delayed drawing events of drawing areas inside the panes.
        This is very useful on windows where resizing gets sluggish if we try to redraw while resizing.
        """
        self.resize_panes = False
        self.p_da_cur.queue_draw()
        self.p_da_next.queue_draw()
        if self.notes_mode:
            self.p_da_notes.queue_draw()
        if self.redraw_timeout:
            self.redraw_timeout = 0

        # Temporarily, while p_frame_annot's configure-event is not working
        self.annotations.on_configure_annot(self.p_frame_annot, None)


    def on_pane_event(self, widget, evt):
        """ Signal handler for gtk.paned events

        This function allows to delay drawing events when resizing, and to speed up redrawing when
        moving the middle pane is done (which happens at the end of a mouse resize)

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured (ignored)
            evt (:class:`~Gdk.Event`):  the event that occured
        """
        if type(evt) == Gdk.EventButton and evt.type == Gdk.EventType.BUTTON_RELEASE:
            self.redraw_panes()
        elif type(evt) == GObject.GParamSpec and evt.name == "position":
            self.resize_panes = True
            if self.redraw_timeout:
                GLib.Source.remove(self.redraw_timeout)
            self.redraw_timeout = GLib.timeout_add(200, self.redraw_panes)


    ############################################################################
    ############################  Program lifetime  ############################
    ############################################################################

    def run(self):
        """ Run the GTK main loop.
        """
        Gtk.main()


    def save_and_quit(self, *args):
        """ Save configuration and exit the main loop.
        """
        self.scribbler.disable_scribbling()

        self.doc.cleanup_media_files()

        if self.notes_mode:
            self.config.update_notes_layout(self.p_central.get_children()[0], self.pane_handle_pos)
        else:
            self.config.update_plain_layout(self.p_central.get_children()[0], self.pane_handle_pos)

        self.config.save_config()
        Gtk.main_quit()


    def menu_about(self, *args):
        """ Display the "About pympress" dialog.

        Handles clicks on the "about" menu.
        """
        about = Gtk.AboutDialog()
        about.set_program_name('pympress')
        about.set_version(pympress.__version__)
        about.set_copyright(_('Contributors:') + '\n' + pympress.__copyright__)
        about.set_comments(_('pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.\n')
                         + _('Some preferences are saved in ') + util.Config.path_to_config() + '\n\n'
                         + (_('Video support using VLC is enabled.') if vlc_enabled else _('Video support using VLC is disabled.')))
        about.set_website('http://www.pympress.xyz/')
        try:
            about.set_logo(util.get_icon_pixbuf('pympress-128.png'))
        except Exception as e:
            logger.exception(_('Error loading icon for about window'))
        about.run()
        about.destroy()


    ##############################################################################
    ############################ Document manangement ############################
    ##############################################################################

    def swap_document(self, docpath):
        """ Replace the currently open document with a new one

        The new document is possibly and EmptyDocument if docpath is None.
        The state of the ui and cache are updated accordingly.

        Args:
            docpath (`str`): the absolute path to the new document
        """
        try:
            self.doc = document.Document.create(self, docpath)
        except GLib.Error:
            self.doc = document.Document.create(self, None)
            self.error_opening_file(docpath)

        # Use notes mode by default if the document has notes
        if self.notes_mode != self.doc.has_notes():
            self.switch_mode()

        # Some things that need updating
        self.cache.swap_document(self.doc)
        self.scribbler.cache.swap_document(self.doc)
        self.page_number.set_last(self.doc.pages_number())

        # Draw the new page(s)
        self.talk_time.pause()
        self.talk_time.reset_timer()
        self.on_page_change(False)


    def recent_document(self, recent_menu):
        """ Callback for the recent document menu.

        Gets the URI and requests the document swap.

        Args:
            recent_menu (:class:`~Gtk.RecentChooserMenu`): the recent docs menu
        """
        self.swap_document(recent_menu.get_current_uri())


    def on_drag_drop(self, widget, drag_context, x, y, data, info, time):
        """ Receive the drag-drops (as text only). If a file is dropped, open it.

        Args:
            widget (:class:`~Gtk.Widget`): The widget on which the dragged item was dropped
            drag_context (:class:`~Gdk.DragContext`):
            x (`float`):
            y (`float`):
            data (:class:`~Gtk.SelectionData`): container for the dropped data
            info (`int`):
            time (`int`):
        """
        received = data.get_text()
        if received.startswith('file://'):
            received = received[len('file://'):]

        if os.path.isfile(received) and received.lower().endswith('.pdf'):
            self.swap_document(os.path.abspath(received))


    def pick_file(self, *args):
        """ Ask the user which file he means to open.
        """
        # Use a GTK file dialog to choose file
        dialog = Gtk.FileChooserDialog(_('Open...'), self.p_win,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        filter = Gtk.FileFilter()
        filter.set_name(_('PDF files'))
        filter.add_mime_type('application/pdf')
        filter.add_pattern('*.pdf')
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name(_('All files'))
        filter.add_pattern('*')
        dialog.add_filter(filter)

        response = dialog.run()

        path = None
        if response == Gtk.ResponseType.OK:
            self.swap_document(os.path.abspath(dialog.get_filename()))

        dialog.destroy()


    def error_opening_file(self, filename):
        """ Remove the current document.
        """
        # Check if the path is valid
        if not os.path.exists(filename):
            msg=_('Could not find the file "{}"').format(filename)
        else:
            msg=_('Error opening the file "{}"').format(filename)
        dialog = Gtk.MessageDialog(self.p_win, Gtk.DialogFlags.MODAL,
                                    Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, msg)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.run()
        dialog.destroy()


    def close_file(self, *args):
        """ Remove the current document.
        """
        self.swap_document(None)


    def get_notes_mode(self):
        """ Simple getter.

        Returns (bool):
            Whether we split slides in content + notes
        """
        return self.notes_mode


    ##############################################################################
    ############################  Displaying content  ############################
    ##############################################################################

    def page_preview(self, widget, *args):
        """ Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the spin_cur spinner as a callback

        Args:
            widget (:class:`~Gtk.SpinButton`): The spinner button widget calling page_preview
        """
        try:
            page_nb = int(widget.get_buffer().get_text()) - 1
        except:
            return

        if page_nb >= self.doc.pages_number() or page_nb < 0:
            return

        page_cur = self.doc.page(page_nb)
        page_next = self.doc.page(page_nb + 1)

        self.page_preview_nb = page_nb

        # Aspect ratios and queue redraws
        if not self.notes_mode:
            page_type = document.PDF_REGULAR
        else:
            page_type = document.PDF_CONTENT_PAGE

            self.p_frame_notes.set_property('ratio', page_cur.get_aspect_ratio(document.PDF_NOTES_PAGE))
            self.p_da_notes.queue_draw()

        self.p_frame_cur.set_property('ratio', page_cur.get_aspect_ratio(page_type))
        self.p_da_cur.queue_draw()

        if page_next is not None:
            pr = page_next.get_aspect_ratio(page_type)
            self.p_frame_next.set_property('ratio', pr)

        self.p_da_next.queue_draw()

        self.annotations.add_annotations(page_cur.get_annotations())


        # Prerender the 4 next pages and the 2 previous ones
        cur = page_cur.number()
        page_max = min(self.doc.pages_number(), cur + 5)
        page_min = max(0, cur - 2)
        for p in list(range(cur+1, page_max)) + list(range(cur, page_min, -1)):
            self.cache.prerender(p)


    def on_page_change(self, unpause=True):
        """ Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        Args:
            unpause (`bool`):  `True` if the page change should unpause the timer, `False` otherwise
        """
        page_cur = self.doc.current_page()
        page_next = self.doc.next_page()

        self.annotations.add_annotations(page_cur.get_annotations())

        # Page change: resynchronize miniatures
        self.page_preview_nb = page_cur.number()

        # Aspect ratios and queue redraws
        if not self.notes_mode:
            page_type = document.PDF_REGULAR
        else:
            page_type = document.PDF_CONTENT_PAGE

            self.p_frame_notes.set_property('ratio', page_cur.get_aspect_ratio(document.PDF_NOTES_PAGE))
            self.p_da_notes.queue_draw()

        self.c_frame.set_property('ratio', page_cur.get_aspect_ratio(page_type))
        self.c_da.queue_draw()

        self.p_frame_cur.set_property('ratio', page_cur.get_aspect_ratio(page_type))
        self.p_da_cur.queue_draw()

        if page_next is not None:
            pr = page_next.get_aspect_ratio(page_type)
            self.p_frame_next.set_property('ratio', pr)

        self.p_da_next.queue_draw()

        # Remove scribbles and scribbling mode
        self.scribbler.disable_scribbling()
        self.scribbler.clear_scribble()

        # Start counter if needed
        if unpause:
            self.talk_time.unpause()

        # Update display
        self.page_number.update_page_numbers(self.doc.current_page().number())

        # Prerender the 4 next pages and the 2 previous ones
        page_max = min(self.doc.pages_number(), self.page_preview_nb + 5)
        page_min = max(0, self.page_preview_nb - 2)
        for p in list(range(self.page_preview_nb+1, page_max)) + list(range(self.page_preview_nb, page_min, -1)):
            self.cache.prerender(p)

        self.medias.replace_media_overlays(self.doc.current_page())


    def on_draw(self, widget, cairo_context):
        """ Manage draw events for both windows.

        This callback may be called either directly on a page change or as an
        event handler by GTK. In both cases, it determines which widget needs to
        be updated, and updates it, using the
        :class:`~pympress.surfacecache.SurfaceCache` if possible.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget to update
            cairo_context (:class:`~cairo.Context`):  the Cairo context (or `None` if called directly)
        """

        if widget is self.c_da:
            # Current page
            if self.blanked:
                return
            page = self.doc.page(self.doc.current_page().number())
        elif widget is self.p_da_notes or widget is self.p_da_cur:
            # Current page 'preview'
            page = self.doc.page(self.page_preview_nb)
        else:
            page = self.doc.page(self.page_preview_nb + 1)
            # No next page: just return so we won't draw anything
            if page is None:
                return

        if not page.can_render():
            return

        # Instead of rendering the document to a Cairo surface (which is slow),
        # use a surface from the cache if possible.
        name = widget.get_name()
        nb = page.number()
        pb = self.cache.get(name, nb)
        wtype = self.cache.get_widget_type(name)
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if pb is None:
            if self.resize_panes and widget in [self.p_da_next, self.p_da_cur, self.p_da_notes]:
                # too slow to render here when resize_panes things
                return

            # Cache miss: render the page, and save it to the cache
            pb = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, ww, wh)

            cairo_prerender = cairo.Context(pb)
            page.render_cairo(cairo_prerender, ww, wh, wtype)

            self.cache.set(name, nb, pb)

            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()
        else:
            # Cache hit: draw the surface from the cache to the widget
            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()

        if widget is self.c_da or widget is self.p_da_cur:
            self.laser.render_pointer(cairo_context, ww, wh)

        cairo_context.paint()


    def redraw_current_slide(self):
        """ Callback to queue a redraw of the current slides (in both winows)
        """
        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()


    ##############################################################################
    ############################     User inputs      ############################
    ##############################################################################

    def on_navigation(self, widget, event):
        """ Manage key presses for both windows

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured (ignored)
            event (:class:`~Gdk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed
        """
        if event.type != Gdk.EventType.KEY_PRESS:
            return

        name = Gdk.keyval_name(event.keyval)
        ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

        # Try passing events to spinner or ett if they are enabled
        if self.page_number.on_keypress(widget, event):
            return True
        elif self.est_time.on_keypress(widget, event):
            return True
        elif self.scribbler.nav_scribble(name, ctrl_pressed):
            return True

        if name == 'space' and self.talk_time.unpause():
            # first space unpauses, next space(s) advance by one page
            pass
        elif name in ['Right', 'Down', 'Page_Down', 'space']:
            self.doc.goto_next()
        elif name in ['Left', 'Up', 'Page_Up', 'BackSpace']:
            self.doc.goto_prev()
        elif name == 'Home':
            self.doc.goto_home()
        elif name == 'End':
            self.doc.goto_end()
        # sic - accelerator recognizes f not F
        elif name.upper() == 'F11' or name == 'F' \
            or (name == 'Return' and event.get_state() & Gdk.ModifierType.MOD1_MASK) \
            or (name.upper() == 'L' and ctrl_pressed) \
            or (name.upper() == 'F5' and (self.c_win.get_window().get_state() & Gdk.WindowState.FULLSCREEN) == 0):
            self.switch_fullscreen(self.c_win)
        elif name.upper() == 'F' and ctrl_pressed:
            self.switch_fullscreen(self.p_win)
        elif name.upper() == 'Q':
            self.save_and_quit()
        elif name == 'Pause':
            self.talk_time.switch_pause()
        elif name.upper() == 'R':
            self.talk_time.reset_timer()

        # Some key events are already handled by toggle actions in the
        # presenter window, so we must handle them in the content window only
        # to prevent them from double-firing
        elif widget is self.c_win:
            if self.scribbler.switch_scribbling(widget, event, name):
                return True
            elif self.est_time.on_label_event(widget, event, name):
                return True
            elif self.page_number.on_label_event(widget, event, name):
                return True
            elif name.upper() == 'P':
                self.talk_time.switch_pause()
            elif name.upper() == 'N':
                self.switch_mode()
            elif name.upper() == 'A':
                self.switch_annotations()
            elif name.upper() == 'S':
                self.swap_screens()
            elif name.upper() == 'F':
                if ctrl_pressed:
                    self.switch_fullscreen(self.p_win)
                else:
                    self.switch_fullscreen(self.c_win)
            elif name.upper() == 'B':
                self.switch_blanked()
            elif ctrl_pressed and name.upper() == 'W':
                self.close_file()
            else:
                return False

            return True
        else:
            return False

        return True


    def on_scroll(self, widget, event):
        """ Manage scroll events

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured (ignored)
            event (:class:`~Gdk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed
        """
        if event.type != Gdk.EventType.SCROLL:
            return False

        # send to spinner if it is active
        elif self.page_number.on_scroll(widget, event):
            return True
        elif self.annotations.on_scroll(widget, event):
            return True
        else:
            return False


    def track_motions(self, widget, event):
        """ Track mouse motion events

        Handles mouse motions on the "about" menu.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget that received the mouse motion
            event (:class:`~Gdk.Event`):  the GTK event containing the mouse position

        Returns:
            `bool`: whether the event was consumed
        """
        if self.scribbler.track_scribble(widget, event):
            return True
        elif self.laser.track_pointer(widget, event):
            return True
        else:
            return self.hover_link(widget, event)


    def track_clicks(self, widget, event):
        """ Track mouse press and release events

        Handles clicks on the slides.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget that received the click
            event (:class:`~Gdk.Event`):  the GTK event containing the click position

        Returns:
            `bool`: whether the event was consumed
        """
        if self.scribbler.toggle_scribble(widget, event):
            return True
        elif self.laser.toggle_pointer(widget, event):
            return True
        else:
            return self.click_link(widget, event)


    def mouse_pos_in_page(self, widget, event, page):
        """ Normalize event coordinates from widget size and notes mode

        Args:
            widget (:class:`~Gtk.Widget`):  the widget that received the click
            event (:class:`~Gdk.Event`):  the GTK event containing the click position
            page (:class:`~pympress.document.Page`): The page that was clicked

        Returns:
            `(float, float)`: the relative position in the full slide
        """
        x, y = event.get_coords()
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if not self.notes_mode:
            # PDF_REGULAR page, the allocated size is the page size
            return x/ww, y/wh
        elif widget is self.p_da_notes:
            # PDF_NOTES_PAGE, the allocated size is the right half of the page
            return (ww + x) / (2 * ww), y / wh
        else:
            # PDF_CONTENT_PAGE, the allocated size is left half of the page
            return x / (2 * ww), y / wh


    def click_link(self, widget, event):
        """ Check whether a link was clicked and follow it.
        Handles a click on a slide.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gdk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed
        """

        if event.type == Gdk.EventType.BUTTON_RELEASE:
            return False

        # Where did the event occur?
        if widget is self.p_da_next:
            page = self.doc.next_page()
            if page is None:
                return False
        else:
            page = self.doc.current_page()

        x, y = self.mouse_pos_in_page(widget, event, page)
        link = page.get_link_at(x, y)

        if event.type == Gdk.EventType.BUTTON_PRESS and link is not None:
            link.follow()
            return True
        else:
            return False


    def hover_link(self, widget, event):
        """ Manage events related to hyperlinks, setting the cursor to a pointer if
        the hovered region is clickable.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gdk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed
        """

        if event.type != Gdk.EventType.MOTION_NOTIFY:
            return False

        # Where did the event occur?
        if widget is self.p_da_next:
            page = self.doc.next_page()
            if page is None:
                return
        else:
            page = self.doc.current_page()

        x, y = self.mouse_pos_in_page(widget, event, page)

        if page.get_link_at(x, y):
            extras.Cursor.set_cursor(widget, 'pointer')
            return False
        else:
            extras.Cursor.set_cursor(widget, 'parent')
            return True


    def switch_fullscreen(self, widget):
        """ Switch the Content window to fullscreen (if in normal mode)
        or to normal mode (if fullscreen).

        Screensaver will be disabled when entering fullscreen mode, and enabled
        when leaving fullscreen mode.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured

        Returns:
            `bool`: whether some window's full screen status got toggled
        """
        if isinstance(widget, Gtk.CheckMenuItem):
            # Called from menu -> use c_win
            widget = self.c_win

        if widget != self.c_win and widget != self.p_win:
            logger.error(_("Unknow widget {} to be fullscreened, aborting.").format(widget))
            return False

        if (widget.get_window().get_state() & Gdk.WindowState.FULLSCREEN) != 0:
            widget.unfullscreen()
        else:
            widget.fullscreen()

        return True


    def on_window_state_event(self, widget, event):
        """ Track whether the preview window is maximized.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occured
            event (:class:`~Gtk.Event`):  the event that occured

        Returns:
            `bool`: whether the event was consumed.
        """
        if widget.get_name() == self.c_win.get_name():
            fullscreen = (Gdk.WindowState.FULLSCREEN & event.new_window_state) != 0
            util.set_screensaver(fullscreen, self.c_win.get_window())
        return False


    def update_frame_position(self, widget, user_data):
        """ Callback to preview the frame alignement, called from the Gtk.SpinButton.

        Args:
            widget (:class:`~Gtk.SpinButton`): The button updating the slide alignement in the drawing area widget
            user_data (`str`): The property being set, either the x or y alignement (resp. xalign and yalign).
        """
        self.c_frame.set_property(user_data, widget.get_value())


    def adjust_frame_position(self, *args):
        """ Select how to align the frame on screen.
        """
        win_aspect_ratio = float(self.c_win.get_allocated_width()) / self.c_win.get_allocated_height()

        if win_aspect_ratio <= float(self.c_frame.get_property("ratio")):
            prop = "yalign"
        else:
            prop = "xalign"

        val = self.c_frame.get_property(prop)

        button = Gtk.SpinButton()
        button.set_adjustment(Gtk.Adjustment(lower=0.0, upper=1.0, step_incr=0.01))
        button.set_digits(2)
        button.set_value(val)
        button.connect("value-changed", self.update_frame_position, prop)

        popup = Gtk.Dialog(_("Adjust alignment of slides in projector screen"), self.p_win, 0,
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


    ##############################################################################
    ############################    Option toggles    ############################
    ##############################################################################

    def swap_screens(self, *args):
        """ Swap the monitors on which each window is displayed (if there are 2 monitors at least).
        """
        screen = self.p_win.get_screen()

        # Though Gtk.Window is a Gtk.Widget get_parent_window() actually returns None on self.{c,p}_win
        p_monitor = screen.get_monitor_at_window(self.p_frame_cur.get_parent_window())
        c_monitor = screen.get_monitor_at_window(self.c_frame.get_parent_window())

        if screen.get_n_monitors() == 1 or p_monitor == c_monitor:
            return

        p_win_state = self.p_win.get_window().get_state()
        c_win_state = self.c_win.get_window().get_state()
        if (c_win_state & Gdk.WindowState.FULLSCREEN) != 0:
            self.c_win.unfullscreen()
        if (p_win_state & Gdk.WindowState.FULLSCREEN) != 0:
            self.p_win.unfullscreen()
        if (c_win_state & Gdk.WindowState.MAXIMIZED) != 0:
            self.c_win.unmaximize()
        if (p_win_state & Gdk.WindowState.MAXIMIZED) != 0:
            self.p_win.unmaximize()

        p_monitor, c_monitor = (c_monitor, p_monitor)

        cx, cy, cw, ch = self.c_win.get_position() + self.c_win.get_size()
        px, py, pw, ph = self.p_win.get_position() + self.p_win.get_size()

        c_bounds = screen.get_monitor_geometry(c_monitor)
        p_bounds = screen.get_monitor_geometry(p_monitor)
        self.c_win.move(c_bounds.x + (c_bounds.width - cw) / 2, c_bounds.y + (c_bounds.height - ch) / 2)
        self.p_win.move(p_bounds.x + (p_bounds.width - pw) / 2, p_bounds.y + (p_bounds.height - ph) / 2)

        if (c_win_state & Gdk.WindowState.MAXIMIZED) != 0:
            self.c_win.maximize()
        if (p_win_state & Gdk.WindowState.MAXIMIZED) != 0:
            self.p_win.maximize()
        if (c_win_state & Gdk.WindowState.FULLSCREEN) != 0:
            self.c_win.fullscreen()
        if (p_win_state & Gdk.WindowState.FULLSCREEN) != 0:
            self.p_win.fullscreen()


    def switch_blanked(self, *args):
        """ Switch the blanked mode of the content screen.
        """
        self.blanked = not self.blanked
        self.c_da.queue_draw()


    def switch_mode(self, *args):
        """ Switch the display mode to "Notes mode" or "Normal mode" (without notes).
        """
        self.scribbler.disable_scribbling()

        if self.notes_mode:
            self.notes_mode = False
            self.cache.set_widget_type("c_da", PDF_REGULAR)
            self.cache.set_widget_type("p_da_next", PDF_REGULAR)
            self.cache.set_widget_type("p_da_cur", PDF_REGULAR)
            self.scribbler.cache.set_widget_type("scribble_p_da", PDF_REGULAR)
            self.cache.disable_prerender("p_da_cur")

            self.cache.disable_prerender("p_da_notes")
            self.cache.set_widget_type("p_da_notes", PDF_REGULAR)

            self.config.update_notes_layout(self.p_central.get_children()[0], self.pane_handle_pos)
            pane_handles = self.replace_layout(self.config.get_plain_layout(), self.p_central, self.placeable_widgets, self.on_pane_event)
        else:
            self.notes_mode = True
            self.cache.set_widget_type("c_da", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_next", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_cur", PDF_CONTENT_PAGE)
            self.scribbler.cache.set_widget_type("scribble_p_da", PDF_CONTENT_PAGE)
            self.cache.enable_prerender("p_da_cur")

            self.cache.set_widget_type("p_da_notes", PDF_NOTES_PAGE)
            self.cache.enable_prerender("p_da_notes")

            self.config.update_plain_layout(self.p_central.get_children()[0], self.pane_handle_pos)
            pane_handles = self.replace_layout(self.config.get_notes_layout(), self.p_central, self.placeable_widgets, self.on_pane_event)
            # make sure visibility is right
            self.p_frame_annot.set_visible(self.show_annotations)

        self.pane_handle_pos.update(pane_handles)
        self.p_central.show_all()
        self.on_page_change(False)


    def switch_annotations(self, *args):
        """ Switch the display to show annotations or to hide them.
        """
        self.show_annotations = not self.show_annotations

        self.p_frame_annot.set_visible(self.show_annotations)
        self.config.set('presenter', 'show_annotations', 'on' if self.show_annotations else 'off')

        if self.show_annotations:
            parent = self.p_frame_annot.get_parent()
            if issubclass(type(parent), Gtk.Paned):
                if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                    size = parent.get_parent().get_allocated_width()
                else:
                    size = parent.get_parent().get_allocated_height()
                parent.set_position(self.pane_handle_pos[parent] * size)

        self.on_page_change(False)


    def switch_bigbuttons(self, *args):
        """ Toggle the display of big buttons (nice for touch screens)
        """
        self.show_bigbuttons = not self.show_bigbuttons

        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)
        self.config.set('presenter', 'show_bigbuttons', 'on' if self.show_bigbuttons else 'off')


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
