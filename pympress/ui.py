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
import importlib

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


from pympress import document, surfacecache, util, pointer, config, builder, talk_time, extras, page_number


class UI(builder.Builder):
    """ Pympress GUI management.
    """
    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: Content window, as a :class:`Gtk.Window` instance.
    c_win = None
    #: :class:`~Gtk.AspectFrame` for the Content window.
    c_frame = None
    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None
    #: :class:`~Gtk.DrawingArea` for the Content window.
    c_da = None

    #: Presenter window, as a :class:`Gtk.Window` instance.
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

    #: Fullscreen toggle for content window. By config value, start in fullscreen mode.
    c_win_fullscreen = False
    #: Fullscreen toggle for presenter window. By config value, start in fullscreen mode.
    p_win_fullscreen = False

    #: Indicates whether we should delay redraws on some drawing areas to fluidify resizing gtk.paned
    resize_panes = False
    #: Tracks return values of GLib.timeout_add to cancel gtk.paned's redraw callbacks
    redraw_timeout = 0

    #: Current :class:`~pympress.document.Document` instance.
    doc = None

    #: Whether to use notes mode or not
    notes_mode = False

    #: Whether to display annotations or not
    show_annotations = True

    #: Whether to display big buttons or not
    show_bigbuttons = True
    #: :class:`Gtk.ToolButton` big button for touch screens, go to previous slide
    prev_button = None
    #: :class:`Gtk.ToolButton` big button for touch screens, go to next slide
    next_button = None
    #: :class:`Gtk.ToolButton` big button for touch screens, go to scribble on screen
    highlight_button = None

    #: number of page currently displayed in Controller window's miniatures
    page_preview_nb = 0

    #: track state of preview window
    p_win_maximized = True

    #: :class:`pympress.config.Config` to remember preferences
    config = config.Config()

    #: track whether we blank the screen
    blanked = False

    #: Dictionary of :class:`Gtk.Widget` from the presenter window that can be dynamically rearranged
    placeable_widgets = {}
    #: Map of :class:`Gtk.Paned` to the relative position (float between 0 and 1) of its handle
    pane_handle_pos = {}

    #: Class :class:`pympress.extras.Annotations` managing the display of annotations
    annotations = extras.Annotations()
    #: Class :class:`pympress.extras.Media` managing keeping track of and callbacks on media overlays
    medias = extras.Media()

    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: list of scribbles to be drawn, as pairs of  :class:`Gdk.RGBA`
    scribble_list = []
    #: Whether the current mouse movements are drawing strokes or should be ignored
    scribble_drawing = False
    #: :class:`Gdk.RGBA` current color of the scribbling tool
    scribble_color = Gdk.RGBA()
    #: `int` current stroke width of the scribbling tool
    scribble_width = 1
    #: :class:`~Gtk.HBox` that is replaces normal panes when scribbling is toggled, contains buttons and scribble drawing area
    scribble_overlay = None
    #: :class:`~Gtk.DrawingArea` for the scribbling in the Presenter window. Actually redraws the slide.
    scribble_c_da = None
    #: :class:`~Gtk.DrawingArea` for the scribbles in the Content window. On top of existing overlays and slide.
    scribble_p_da = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Presenter window, captures freehand drawing
    scribble_c_eb = None
    #: :class:`~Gtk.EventBox` for the scribbling in the Content window, captures freehand drawing
    scribble_p_eb = None
    #: :class:`~Gtk.AspectFrame` for the slide in the Presenter's highlight mode
    scribble_p_frame = None

    #: A :class:`Gtk.OffscreenWindow` where we render the scirbbling interface when it's not shown
    off_render = None

    #: Software-implemented laser pointer, :class:`pympress.pointer.Pointer`
    laser = pointer.Pointer()

    #: Counter diplaying current and max page numbers
    page_number = page_number.PageNumber()

    #: Clock tracking talk time (elapsed, and remaining)
    talk_time = talk_time.TalkTime()

    # The :class:`UI` singleton, since there is only one (as a class variable). Used by classmethods only.
    _instance = None

    def __init__(self, ett = 0, docpath = None):
        """
        Args:
            ett (int):  the estimated (intended) talk time
        """
        super(UI, self).__init__()
        UI._instance = self

        self.blanked = self.config.getboolean('content', 'start_blanked')

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            util.get_style_provider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Use notes mode by default if the document has notes
        self.doc = document.Document.create(docpath)
        self.notes_mode = self.doc.has_notes()
        self.show_annotations = (not self.notes_mode) and self.config.getboolean('presenter', 'show_annotations')
        self.page_preview_nb = self.doc.current_page().number()

        # Surface cache
        self.cache = surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages'))


        # Make and populate windows
        self.load_ui('presenter')
        self.load_ui('content')
        self.load_ui('highlight')

        self.laser.default_pointer(self.config, self)
        self.medias.setup(self)

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
        self.setup_scribbling()

        self.connect_signals(self)

        # Common to both windows
        icon_list = util.load_icons()
        self.c_win.set_icon_list(icon_list)
        self.p_win.set_icon_list(icon_list)

        # Setup timer for clocks
        self.talk_time.setup(self, ett)
        GObject.timeout_add(250, self.talk_time.update_time)

        # Show all windows
        self.c_win.show_all()
        self.p_win.show_all()

        # Add media
        self.medias.replace_media_overlays(self.doc.current_page())

        # Queue some redraws
        self.c_da.queue_draw()
        self.redraw_panes()
        self.on_page_change(False)

        # Adjust default visibility of items
        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)
        self.p_frame_annot.set_visible(self.show_annotations)


    def swap_document(self, docpath):
        """ Replace the currently open document with a new one

        The new document is possibly and EmptyDocument if docpath is None.
        The state of the ui and cache are updated accordingly.

        Args:
            docpath (str): the absolute path to the new document
        """
        self.doc = document.Document.create(docpath)

        # Use notes mode by default if the document has notes
        if self.notes_mode != self.doc.has_notes():
            self.switch_mode()

        # Some things that need updating
        self.cache.swap_document(self.doc)
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


    def rearrange_p_layout(self, layout):
        """ Remix the layout of the presenter window with the layout configuration given (assumed to be valid!).

            Args:
                layout (dict): the json-parsed config string
        """
        # take apart the previous/default layout
        containers = []
        widgets = self.p_central.get_children()
        i = 0
        while i < len(widgets):
            w = widgets[i]
            if issubclass(type(w), Gtk.Box) or issubclass(type(w), Gtk.Paned):
                widgets.extend(w.get_children())
                containers.append(w)
            w.get_parent().remove(w)
            i += 1

        # cleanup widgets
        del widgets[:]
        while containers:
            containers.pop().destroy()

        # iterate over new layout to build it, using a BFS
        widgets_to_add = [(self.p_central, layout)]
        pane_resize = set()

        while widgets_to_add:
            parent, w_desc = widgets_to_add.pop(0)

            if type(w_desc) is str:
                w = self.placeable_widgets[w_desc]

            else:
                # get new container widget, attempt to recycle the containers we removed
                if 'resizeable' in w_desc and w_desc['resizeable']:
                    orientation = getattr(Gtk.Orientation, w_desc['orientation'].upper())
                    w = Gtk.Paned.new(orientation)
                    w.set_wide_handle(True)

                    # Add on resize events
                    w.connect("notify::position", self.on_pane_event)
                    w.connect("button-release-event", self.on_pane_event)

                    # left pane is first child
                    widgets_to_add.append((w, w_desc['children'].pop()))

                    if 'proportions' in w_desc:
                        right_pane = w_desc['proportions'].pop()
                        left_pane  = w_desc['proportions'].pop()
                        w_desc['proportions'].append(left_pane + right_pane)

                        self.pane_handle_pos[w] = float(left_pane) / (left_pane + right_pane)
                        pane_resize.add(w)
                    else:
                        self.pane_handle_pos[w] = 0.5

                    # if more than 2 children are to be added, add the 2+ from the right side in a new child Gtk.Paned
                    widgets_to_add.append((w, w_desc['children'][0] if len(w_desc['children']) == 1 else w_desc))
                else:
                    w = Gtk.Box.new(getattr(Gtk.Orientation, w_desc['orientation'].upper()), 5)
                    w.set_homogeneous(True)
                    w.set_spacing(10)

                    widgets_to_add += [(w, c) for c in w_desc['children']]

            if issubclass(type(parent), Gtk.Box):
                parent.pack_start(w, True, True, 0)
            else: #it's a Gtk.Paned
                if parent.get_child2() is None:
                    parent.pack2(w, True, True)
                    if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                        w.set_margin_start(8)
                    else:
                        w.set_margin_top(8)
                else:
                    parent.pack1(w, True, True)
                    if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                        w.set_margin_end(8)
                    else:
                        w.set_margin_bottom(8)

            # hierarchichally ordered list of widgets
            widgets.append(w)

        for w in widgets:
            w.queue_resize()
            w.show_now()
            w.get_parent().check_resize()

        for p in (w for w in widgets if issubclass(type(w), Gtk.Box) or issubclass(type(w), Gtk.Paned)):
            p.check_resize()
            if p in pane_resize:
                if p.get_orientation() == Gtk.Orientation.HORIZONTAL:
                    pane_pos = int(round(Gtk.Widget.get_allocated_width(p) * self.pane_handle_pos[p]))
                else:
                    pane_pos = int(round(Gtk.Widget.get_allocated_height(p) * self.pane_handle_pos[p]))

                p.set_position(pane_pos)


    def make_pwin(self):
        """ Initializes the presenter window.
        """
        if self.notes_mode:
            self.rearrange_p_layout(self.config.get_notes_layout())
        else:
            self.rearrange_p_layout(self.config.get_plain_layout())

        self.show_bigbuttons = self.config.getboolean('presenter', 'show_bigbuttons')

        init_checkstates = {
            'pres_pause':      True,
            'pres_fullscreen': self.config.getboolean('content', 'start_fullscreen'),
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


        self.annotations.setup(self)
        self.page_number.setup(self)

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


    def on_drag_drop(self, widget, drag_context, x, y, data,info, time):
        """ Receive the drag-drops (as text only). If a file is dropped, open it.
        """
        received = data.get_text()
        if received.startswith('file://'):
            received = received[len('file://'):]

        if os.path.isfile(received) and received.lower().endswith('.pdf'):
            self.swap_document(os.path.abspath(received))


    def run(self):
        """ Run the GTK main loop.
        """
        Gtk.main()


    def save_and_quit(self, *args):
        """ Save configuration and exit the main loop.
        """
        # write the presenter layout in the config file
        if self.scribbling_mode:
            self.switch_scribbling()

        self.doc.cleanup_media_files()

        if self.notes_mode:
            self.config.update_notes_layout(self.p_central.get_children()[0], self.pane_handle_pos)
        else:
            self.config.update_plain_layout(self.p_central.get_children()[0], self.pane_handle_pos)

        self.config.save_config()
        Gtk.main_quit()


    def close_file(self, *args):
        """ Remove the current document.
        """
        self.swap_document(None)


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


    def menu_about(self, widget=None, event=None):
        """ Display the "About pympress" dialog.
        """
        pympress = importlib.import_module('pympress.__init__')
        about = Gtk.AboutDialog()
        about.set_program_name('pympress')
        about.set_version(pympress.__version__)
        about.set_copyright(_('Contributors:') + '\n' + pympress.__copyright__)
        about.set_comments(_('pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.\n')
                         + _('Some preferences are saved in ') + self.config.path_to_config() + '\n\n'
                         + (_('Video support using VLC is enabled.') if vlc_enabled else _('Video support using VLC is disabled.')))
        about.set_website('http://www.pympress.xyz/')
        try:
            about.set_logo(util.get_icon_pixbuf('pympress-128.png'))
        except Exception as e:
            logger.exception(_('Error loading icon for about window'))
        about.run()
        about.destroy()


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
            unpause (boolean):  ``True`` if the page change should unpause the timer, ``False`` otherwise
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

        # Remove scribbling if ongoing
        if self.scribbling_mode:
            self.switch_scribbling()
        del self.scribble_list[:]

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


    @classmethod
    def notify_page_change(cls, unpause = True):
        """ Statically notify the UI of a page change (typically from document)
        """
        cls._instance.on_page_change(unpause)


    def redraw_panes(self):
        """ Callback to redraw gtk.paned's drawing areas, used for delayed drawing events
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


    @classmethod
    def redraw_current_slide(cls):
        """ Static way to queue a redraw of the current slides (in both winows)
        """
        self = cls._instance

        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()


    def on_pane_event(self, widget, evt):
        """ Signal handler for gtk.paned events

        This function allows to delay drawing events when resizing, and to speed up redrawing when
        moving the middle pane is done (which happens at the end of a mouse resize)
        """
        if type(evt) == Gdk.EventButton and evt.type == Gdk.EventType.BUTTON_RELEASE:
            self.redraw_panes()
        elif type(evt) == GObject.GParamSpec and evt.name == "position":
            self.resize_panes = True
            if self.redraw_timeout:
                GLib.Source.remove(self.redraw_timeout)
            self.redraw_timeout = GLib.timeout_add(200, self.redraw_panes)


    def on_draw(self, widget, cairo_context):
        """ Manage draw events for both windows.

        This callback may be called either directly on a page change or as an
        event handler by GTK. In both cases, it determines which widget needs to
        be updated, and updates it, using the
        :class:`~pympress.surfacecache.SurfaceCache` if possible.

        Args:
            widget (:class:`Gtk.Widget`):  the widget to update
            cairo_context (:class:`cairo.Context`):  the Cairo context (or ``None`` if called directly)
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


    def on_configure_da(self, widget, event):
        """ Manage "configure" events for all drawing areas.

        In the GTK world, this event is triggered when a widget's configuration
        is modified, for example when its size changes. So, when this event is
        triggered, we tell the local :class:`~pympress.surfacecache.SurfaceCache`
        instance about it, so that it can invalidate its internal cache for the
        specified widget and pre-render next pages at a correct size.

        Warning: Some not-explicitely sent signals contain wrong values! Just don't resize in that case,
        since these always seem to happen after a correct signal that was sent explicitely.

        Args:
            widget (:class:`Gtk.Widget`):  the widget which has been resized
            event (:class:`Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
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
            widget (:class:`Gtk.Widget`):  the window which has been moved or resized
            event (:class:`Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """

        if widget is self.p_win:
            p_monitor = self.p_win.get_screen().get_monitor_at_window(self.p_frame_cur.get_parent_window())
            self.config.set('presenter', 'monitor', str(p_monitor))
            cw = self.p_central.get_allocated_width()
            ch = self.p_central.get_allocated_height()
            self.off_render.set_size_request(cw, ch)
        elif widget is self.c_win:
            c_monitor = self.c_win.get_screen().get_monitor_at_window(self.c_frame.get_parent_window())
            self.config.set('content', 'monitor', str(c_monitor))


    def on_navigation(self, widget, event):
        """ Manage key presses for both windows

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured (ignored)
            event (:class:`Gdk.Event`):  the event that occured
        """
        if event.type != Gdk.EventType.KEY_PRESS:
            return

        name = Gdk.keyval_name(event.keyval)
        ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

        # Try passing events to spinner or ett if they are enabled
        if self.page_number.on_spin_nav(widget, event):
            return True
        elif self.talk_time.on_label_ett_keypress(widget, event):
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
            or (name.upper() == 'F5' and not self.c_win_fullscreen):
            self.switch_fullscreen(self.c_win)
        elif name.upper() == 'F' and ctrl_pressed:
            self.switch_fullscreen(self.p_win)
        elif name.upper() == 'Q':
            self.save_and_quit()
        elif name == 'Pause':
            self.talk_time.switch_pause()
        elif name.upper() == 'R':
            self.talk_time.reset_timer()

        if self.scribbling_mode:
            if name.upper() == 'Z' and ctrl_pressed:
                self.pop_scribble()
            elif name == 'Escape':
                self.switch_scribbling()

        # Some key events are already handled by toggle actions in the
        # presenter window, so we must handle them in the content window only
        # to prevent them from double-firing
        if widget is self.c_win:
            if self.talk_time.on_label_ett_event(widget, event, name):
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
            elif name.upper() == 'H':
                self.switch_scribbling()
            else:
                return False

            return True
        else:
            return False

        return True


    def on_scroll(self, widget, event):
        """ Manage scroll events

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured (ignored)
            event (:class:`Gdk.Event`):  the event that occured
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


    def track_motions(self, widget = None, event = None):
        """ Track mouse motion events
        """
        if self.track_scribble(widget, event):
            return True
        elif self.laser.track_pointer(widget, event):
            return True
        else:
            return self.hover_link(widget, event)


    def track_clicks(self, widget = None, event = None):
        """ Track mouse press and release events
        """
        if self.toggle_scribble(widget, event):
            return True
        elif self.laser.toggle_pointer(widget, event):
            return True
        else:
            return self.click_link(widget, event)


    def mouse_pos_in_page(self, widget, event, page):
        """ Normalize event coordinates and get link
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

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured
            event (:class:`Gdk.Event`):  the event that occured
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
        """ Manage events related to hyperlinks.

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured
            event (:class:`Gdk.Event`):  the event that occured
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


    @classmethod
    def notify_label_event(cls):
        """ Static way to start the "go to" label editing.

        Typically used as callbacks from document links.
        """
        self = cls._instance
        self.page_number.on_label_event(True)


    @classmethod
    def stop_editing_slide(cls):
        """ Make sure that the current page number is not being edited.
        """
        cls._instance.page_number.restore_current_label()


    @classmethod
    def stop_editing_time(cls):
        """ Make sure that the estiamte talk time is not being edited.
        """
        cls._instance.talk_time.restore_current_label_ett()




    def switch_fullscreen(self, widget=None, event=None):
        """ Switch the Content window to fullscreen (if in normal mode)
        or to normal mode (if fullscreen).

        Screensaver will be disabled when entering fullscreen mode, and enabled
        when leaving fullscreen mode.
        """
        if isinstance(widget, Gtk.CheckMenuItem):
            # Called from menu -> use c_win
            widget = self.c_win
            fullscreen = self.c_win_fullscreen
        elif widget == self.c_win:
            fullscreen = self.c_win_fullscreen
        elif widget == self.p_win:
            fullscreen = self.p_win_fullscreen
        else:
            logger.error(_("Unknow widget {} to be fullscreened, aborting.").format(widget))
            return

        if fullscreen:
            widget.unfullscreen()
        else:
            widget.fullscreen()


    def on_window_state_event(self, widget, event, user_data=None):
        """ Track whether the preview window is maximized.
        """
        if widget.get_name() == self.p_win.get_name():
            self.p_win_maximized = (Gdk.WindowState.MAXIMIZED & event.new_window_state) != 0
            self.p_win_fullscreen = (Gdk.WindowState.FULLSCREEN & event.new_window_state) != 0
        elif widget.get_name() == self.c_win.get_name():
            self.c_win_fullscreen = (Gdk.WindowState.FULLSCREEN & event.new_window_state) != 0
            util.set_screensaver(self.c_win_fullscreen, self.c_win.get_window())


    def update_frame_position(self, widget=None, user_data=None):
        """ Callback to preview the frame alignement, called from the spinbutton.
        """
        if widget and user_data:
            self.c_frame.set_property(user_data, widget.get_value())


    def adjust_frame_position(self, widget=None, event=None):
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


    def swap_screens(self, widget=None, event=None):
        """ Swap the monitors on which each window is displayed (if there are 2 monitors at least).
        """
        c_win_was_fullscreen = self.c_win_fullscreen
        p_win_was_fullscreen = self.p_win_fullscreen
        p_win_was_maximized  = self.p_win_maximized
        if c_win_was_fullscreen:
            self.c_win.unfullscreen()
        if p_win_was_fullscreen:
            self.p_win.unfullscreen()
        if p_win_was_maximized:
            self.p_win.unmaximize()

        screen = self.p_win.get_screen()
        if screen.get_n_monitors() > 1:
            # Though Gtk.Window is a Gtk.Widget get_parent_window() actually returns None on self.{c,p}_win
            p_monitor = screen.get_monitor_at_window(self.p_frame_cur.get_parent_window())
            c_monitor = screen.get_monitor_at_window(self.c_frame.get_parent_window())

            if p_monitor == c_monitor:
                return

            p_monitor, c_monitor = (c_monitor, p_monitor)

            cx, cy, cw, ch = self.c_win.get_position() + self.c_win.get_size()
            px, py, pw, ph = self.p_win.get_position() + self.p_win.get_size()

            c_bounds = screen.get_monitor_geometry(c_monitor)
            p_bounds = screen.get_monitor_geometry(p_monitor)
            self.c_win.move(c_bounds.x + (c_bounds.width - cw) / 2, c_bounds.y + (c_bounds.height - ch) / 2)
            self.p_win.move(p_bounds.x + (p_bounds.width - pw) / 2, p_bounds.y + (p_bounds.height - ph) / 2)

            if p_win_was_fullscreen:
                self.p_win.fullscreen()
            elif p_win_was_maximized:
                self.p_win.maximize()

            if c_win_was_fullscreen:
                self.c_win.fullscreen()


    def switch_blanked(self, widget=None, event=None):
        """ Switch the blanked mode of the content screen.
        """
        self.blanked = not self.blanked
        self.c_da.queue_draw()


    # TODO move config-only switches to  self.config
    def switch_start_blanked(self, widget=None, event=None):
        """ Switch the blanked mode of the content screen at startup.
        """
        if self.config.getboolean('content', 'start_blanked'):
            self.config.set('content', 'start_blanked', 'off')
        else:
            self.config.set('content', 'start_blanked', 'on')


    def switch_start_cwin_full(self, widget=None):
        """ Switch the fullscreen mode of the content screen at startup.
        """

        if self.config.getboolean('content', 'start_fullscreen'):
            self.config.set('content', 'start_fullscreen', 'off')
        else:
            self.config.set('content', 'start_fullscreen', 'on')


    def switch_start_pwin_full(self, widget=None):
        """ Switch the fullscreen mode of the presenter screen at startup.
        """

        if self.config.getboolean('presenter', 'start_fullscreen'):
            self.config.set('presenter', 'start_fullscreen', 'off')
        else:
            self.config.set('presenter', 'start_fullscreen', 'on')


    def switch_mode(self, widget=None, event=None):
        """ Switch the display mode to "Notes mode" or "Normal mode" (without notes).
        """
        if self.scribbling_mode:
            self.switch_scribbling()

        if self.notes_mode:
            self.notes_mode = False
            self.cache.set_widget_type("c_da", PDF_REGULAR)
            self.cache.set_widget_type("p_da_next", PDF_REGULAR)
            self.cache.set_widget_type("p_da_cur", PDF_REGULAR)
            self.cache.set_widget_type("scribble_p_da", PDF_REGULAR)
            self.cache.disable_prerender("p_da_cur")

            self.cache.disable_prerender("p_da_notes")
            self.cache.set_widget_type("p_da_notes", PDF_REGULAR)

            self.config.update_notes_layout(self.p_central.get_children()[0], self.pane_handle_pos)
            self.rearrange_p_layout(self.config.get_plain_layout())
        else:
            self.notes_mode = True
            self.cache.set_widget_type("c_da", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_next", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_cur", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("scribble_p_da", PDF_CONTENT_PAGE)
            self.cache.enable_prerender("p_da_cur")

            self.cache.set_widget_type("p_da_notes", PDF_NOTES_PAGE)
            self.cache.enable_prerender("p_da_notes")

            self.config.update_plain_layout(self.p_central.get_children()[0], self.pane_handle_pos)
            self.rearrange_p_layout(self.config.get_notes_layout())
            # make sure visibility is right
            self.p_frame_annot.set_visible(self.show_annotations)

        self.p_central.show_all()
        self.on_page_change(False)


    def switch_annotations(self, widget=None, event=None):
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


    def switch_bigbuttons(self, widget=None, event=None):
        """ Toggle the display of big buttons (nice for touch screens)
        """
        self.show_bigbuttons = not self.show_bigbuttons

        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)
        self.config.set('presenter', 'show_bigbuttons', 'on' if self.show_bigbuttons else 'off')


    def track_scribble(self, widget, event):
        """ Draw the scribble following the mouse's moves.
        """
        if self.scribble_drawing:
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.scribble_list[-1][2].append((ex / ww, ey / wh))

            self.scribble_c_da.queue_draw()
            self.scribble_p_da.queue_draw()
            return True
        else:
            return False


    def toggle_scribble(self, widget, event):
        """ Start/stop drawing scribbles.
        """
        if not self.scribbling_mode:
            return False

        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            self.scribble_list.append( (self.scribble_color, self.scribble_width, []) )
            self.scribble_drawing = True

            return self.track_scribble(widget, event)
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_drawing = False
            return True

        return False


    def draw_scribble(self, widget, cairo_context):
        """ Drawings by user
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if widget is not self.scribble_c_da:
            page = self.doc.current_page()
            nb = page.number()
            pb = self.cache.get("scribble_p_da", nb)

            if pb is None:
                # Cache miss: render the page, and save it to the cache
                pb = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, ww, wh)
                wtype = PDF_CONTENT_PAGE if self.notes_mode else PDF_REGULAR

                cairo_prerender = cairo.Context(pb)
                page.render_cairo(cairo_prerender, ww, wh, wtype)

                cairo_context.set_source_surface(pb, 0, 0)
                cairo_context.paint()

                self.cache.set("scribble_p_da", nb, pb)
            else:
                # Cache hit: draw the surface from the cache to the widget
                cairo_context.set_source_surface(pb, 0, 0)
                cairo_context.paint()

        cairo_context.set_line_cap(cairo.LINE_CAP_ROUND)

        for color, width, points in self.scribble_list:
            points = [(p[0] * ww, p[1] * wh) for p in points]

            cairo_context.set_source_rgba(*color)
            cairo_context.set_line_width(width)
            cairo_context.move_to(*points[0])

            for p in points[1:]:
                cairo_context.line_to(*p)
            cairo_context.stroke()


    def update_color(self, widget = None):
        """ Callback for the color chooser button, to set scribbling color
        """
        if widget:
            self.scribble_color = widget.get_rgba()
            self.config.set('scribble', 'color', self.scribble_color.to_string())


    def update_width(self, widget = None, event = None, value = None):
        """ Callback for the width chooser slider, to set scribbling width
        """
        if widget:
            self.scribble_width = int(value)
            self.config.set('scribble', 'width', str(self.scribble_width))


    def clear_scribble(self, widget = None):
        """ Callback for the scribble undo button, to undo the last scribble
        """
        del self.scribble_list[:]

        self.scribble_c_da.queue_draw()
        self.scribble_p_da.queue_draw()


    def pop_scribble(self, widget = None):
        """ Callback for the scribble undo button, to undo the last scribble
        """
        if self.scribble_list:
            self.scribble_list.pop()

        self.scribble_c_da.queue_draw()
        self.scribble_p_da.queue_draw()


    def setup_scribbling(self):
        """ Setup all the necessary for scribbling
        """
        self.scribble_color = Gdk.RGBA()
        self.scribble_color.parse(self.config.get('scribble', 'color'))
        self.scribble_width = self.config.getint('scribble', 'width')
        self.cache.add_widget("scribble_p_da", PDF_CONTENT_PAGE if self.notes_mode else PDF_REGULAR, False)

        # Presenter-size setup
        self.get_object("scribble_color").set_rgba(self.scribble_color)
        self.get_object("scribble_width").set_value(self.scribble_width)


    def switch_scribbling(self, widget=None, event=None):
        """ Starts the mode where one can read on top of the screen
        """

        if self.scribbling_mode:
            p_layout = self.off_render.get_child()

            self.p_central.remove(self.scribble_overlay)
            self.off_render.remove(p_layout)

            self.off_render.add(self.scribble_overlay)
            self.p_central.pack_start(p_layout, True, True, 0)
            self.scribbling_mode = False

        else:
            pr = self.doc.current_page().get_aspect_ratio(self.notes_mode)
            self.scribble_p_frame.set_property('ratio', pr)

            p_layout = self.p_central.get_children()[0]

            self.p_central.remove(p_layout)
            self.off_render.remove(self.scribble_overlay)

            self.p_central.pack_start(self.scribble_overlay, True, True, 0)
            self.off_render.add(p_layout)

            self.p_central.queue_draw()

            # Also make sure our overlay on Content window is visible
            self.c_overlay.reorder_overlay(self.scribble_c_eb, 1)
            self.c_overlay.show_all()

            self.scribbling_mode = True



##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
