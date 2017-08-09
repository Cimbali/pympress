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

import os, os.path, subprocess
import sys
import time
import json

import pkg_resources

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Gtk, Gdk, Pango, GLib, GdkPixbuf

#: "Regular" PDF file (without notes)
PDF_REGULAR      = 0
#: Content page (left side) of a PDF file with notes
PDF_CONTENT_PAGE = 1
#: Notes page (right side) of a PDF file with notes
PDF_NOTES_PAGE   = 2


POINTER_OFF = -1
POINTER_HIDE = 0
POINTER_SHOW = 1

import pympress.document
import pympress.surfacecache
import pympress.util
try:
    import pympress.vlcvideo
    vlc_enabled = True
except Exception as e:
    vlc_enabled = False
    logger.exception(_("video support is disabled"))

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS

if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg
else:
    try:
        gi.require_version('GdkX11', '3.0')
        from gi.repository import GdkX11
    except:
        pass

try:
    PermissionError()
except NameError:
    class PermissionError(Exception):
        pass

class UI:
    """ Pympress GUI management.
    """

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: :class:`~Gtk.Builder` to read XML descriptions of GUIs and load them.
    builder = Gtk.Builder()

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
    #: forward keystrokes to the Content window even if the window manager puts Presenter on top
    editing_cur_ett = False
    #: Estimated talk time :class:`~gtk.Label` for the talk.
    label_ett = None
    #: :class:`~gtk.EventBox` associated with the estimated talk time.
    eb_ett = None
    #: :class:`~gtk.Entry` used to set the estimated talk time.
    entry_ett = Gtk.Entry()

    #: :class:`~GdkPixbuf.Pixbuf` to read XML descriptions of GUIs and load them.
    pointer = GdkPixbuf.Pixbuf()
    #: tuple of position relative to slide, where the pointer should appear
    pointer_pos = (.5, .5)
    #: boolean indicating whether we should show the pointer
    show_pointer = POINTER_OFF
    #: a dict of cursors, ready to use
    cursors = {
        'parent': None,
        'default': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default'),
        'pointer': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'pointer'),
        'invisible': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'none'),
    }

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

    #: Elapsed time :class:`~Gtk.Label`.
    label_time = None
    #: Clock :class:`~Gtk.Label`.
    label_clock = None

    #: Time at which the counter was started.
    start_time = 0
    #: Time elapsed since the beginning of the presentation.
    delta = 0
    #: Estimated talk time.
    est_time = 0
    #: Timer paused status.
    paused = True

    #: Fullscreen toggle. By config value, start in fullscreen mode.
    c_win_fullscreen = False

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

    #: remember DPMS setting before we change it
    dpms_was_enabled = None

    #: track state of preview window
    p_win_maximized = True

    #: :class:`configparser.RawConfigParser` to remember preferences
    config = None

    #: track whether we blank the screen
    blanked = False

    #: Dictionary of :class:`pympress.vlcvideo.VLCVideo` ready to be added on top of the slides
    media_overlays = {}

    #: Dictionary of :class:`Gtk.Widget` from the presenter window that can be dynamically rearranged
    placeable_widgets = {}
    #: Map of :class:`Gtk.Paned` to the relative position (float between 0 and 1) of its handle
    pane_handle_pos = {}
    #: dict-tree of presenter layout for the notes mode
    notes_layout = {}
    #: dict-tree of presenter layout for the non-notes mode
    plain_layout = {}

    #: :class:`Gdk.RGBA` The default color of the info labels
    label_color_default = None
    #: :class:`Gdk.RGBA` The color of the elapsed time label if the estimated talk time is reached
    label_color_ett_reached = None
    #: :class:`Gdk.RGBA` The color of the elapsed time label if the estimated talk time is exceeded by 2:30 minutes
    label_color_ett_info = None
    #: :class:`Gdk.RGBA` The color of the elapsed time label if the estimated talk time is exceeded by 5 minutes
    label_color_ett_warn = None

    #: The containing widget for the annotations
    scrollable_treelist = None
    #: Making the annotations list scroll if it's too long
    scrolled_window = None

    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    scribbling_mode = False
    #: list of scribbles to be drawn, as pairs of  :class:`Gdk.RGBA`
    scribble_list = []
    #: Whether the current mouse movements are drawing strokes or should be ignored
    scribble_drawing = False
    #: :class:`Gdk.RGBA` current color of the scribbling tool
    scribble_color = None
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

    # The :class:`UI` singleton, since there is only one (as a class variable). Used by classmethods only.
    _instance = None

    def __init__(self, ett = 0, docpath = None):
        """
        Args:
            ett (int):  the estimated (intended) talk time
        """
        UI._instance = self

        self.est_time = ett
        self.config = pympress.util.load_config()
        self.blanked = self.config.getboolean('content', 'start_blanked')

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            pympress.util.get_style_provider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Use notes mode by default if the document has notes
        self.doc = pympress.document.Document.create(docpath)
        self.notes_mode = self.doc.has_notes()
        self.show_annotations = (not self.notes_mode) and self.config.getboolean('presenter', 'show_annotations')
        self.page_preview_nb = self.doc.current_page().number()

        # Surface cache
        self.cache = pympress.surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages'))

        # Make and populate windows
        self.builder.add_from_file(pympress.util.get_resource_path('share', 'xml', 'presenter.glade'))
        self.builder.add_from_file(pympress.util.get_resource_path('share', 'xml', 'highlight.glade'))
        self.builder.add_from_file(pympress.util.get_resource_path('share', 'xml', 'content.glade'))

        # Apply translations to top-level widgets from each file
        for top_widget in map(self.builder.get_object, ['p_win', 'c_win', 'off_render']):
            pympress.util.recursive_translate_widgets(top_widget)

        # Introspectively load all missing elements from builder
        # This means that all attributes that are None at this time must exist under the same name in the builder
        for n in (attr for attr in dir(self) if getattr(self, attr) is None and attr[:2] + attr[-2:] != '____'):
            setattr(self, n, self.builder.get_object(n))

        self.placeable_widgets = {
            "notes": self.p_frame_notes,
            "current": self.p_frame_cur,
            "next": self.p_frame_next,
            "annotations": self.p_frame_annot,
        }

        # Initialize windows and screens
        self.setup_screens()
        self.c_win.show_now()
        self.p_win.show_now()

        self.make_cwin()
        self.make_pwin()
        self.setup_scribbling()

        self.builder.connect_signals(self)

        # Common to both windows
        icon_list = pympress.util.load_icons()
        self.c_win.set_icon_list(icon_list)
        self.p_win.set_icon_list(icon_list)

        # Setup timer for clocks
        GObject.timeout_add(250, self.update_time)

        # Show all windows
        self.c_win.show_all()
        self.p_win.show_all()

        # Some final setup steps
        self.load_time_colors()

        # Add media
        self.replace_media_overlays()

        # Queue some redraws
        self.c_overlay.queue_draw()
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
        self.doc = pympress.document.Document.create(docpath)

        # Use notes mode by default if the document has notes
        if self.notes_mode != self.doc.has_notes():
            self.switch_mode()

        # Some things that need updating
        self.cache.swap_document(self.doc)
        self.label_last.set_text("/{}".format(self.doc.pages_number()))

        # Draw the new page(s)
        self.paused = True
        self.reset_timer()
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
            page_type = pympress.document.PDF_CONTENT_PAGE
        else:
            page_type = pympress.document.PDF_REGULAR

        self.cache.add_widget("c_da", page_type)
        self.c_frame.set_property("ratio", self.doc.current_page().get_aspect_ratio(page_type))


    def validate_layout(self, layout, expected_widgets):
        """ Validate layout: check whether the layout of widgets built from the config string is valid.

            Args:
                layout (dict): the json-parsed config string
                expected_widgets (set): strings with the names of widgets for this layout


            Layout must have all self.placeable_widgets (leaves of the tree, as strings) and only allowed properties
            on the nodes of the tree (as dicts).

            Contraints on the only allowed properties of the nodes are:
                resizeable: bool (optional, defaults to no),
                orientation: "vertical" or "horizontal" (mandatory)
                children: list (mandatory), of size >= 2, containing strings or dicts
                proportions: list of floats (optional, only if resizeable) with sum = 1, length == len(children), representing
                    the relative sizes of all the resizeable items.
        """

        next_visits = [layout]
        widget_seen = set()
        while next_visits:
            w_desc = next_visits.pop(0)
            if type(w_desc) is str:
                if w_desc not in expected_widgets:
                    raise ValueError('Unrecognized widget "{}", pick one of: {}'.format(w_desc, ', '.join(expected_widgets)))
                elif w_desc in widget_seen:
                    raise ValueError('Duplicate widget "{}", all expected_widgets can only appear once'.format(w_desc))
                widget_seen.add(w_desc)

            elif type(w_desc) is dict:
                if 'orientation' not in w_desc or w_desc['orientation'] not in ['horizontal', 'vertical']:
                    raise ValueError('"orientation" is mandatory and must be "horizontal" or "vertical" at node {}'.format(w_desc))
                elif 'children' not in w_desc or type(w_desc['children']) is not list or len(w_desc['children']) < 2:
                    raise ValueError('"children" is mandatory and must be a list of 2+ items at node {}'.format(w_desc))
                elif 'resizeable' in w_desc and type(w_desc['resizeable']) is not bool:
                    raise ValueError('"resizeable" must be boolean at node {}'.format(w_desc))

                elif 'proportions' in w_desc:
                    if 'resizeable' not in w_desc or not w_desc['resizeable']:
                        raise ValueError('"proportions" is only valid for resizeable widgets at node {}'.format(w_desc))
                    elif type(w_desc['proportions']) is not list or any(type(n) is not float for n in w_desc['proportions']) or len(w_desc['proportions']) != len(w_desc['children']) or abs(sum(w_desc['proportions']) - 1) > 1e-10:
                        raise ValueError('"proportions" must be a list of floats (one per separator), between 0 and 1, at node {}'.format(w_desc))

                next_visits += w_desc['children']
            else:
                raise ValueError('Unexpected type {}, nodes must be dicts or strings, at node {}'.format(type(w_desc), w_desc))
        widget_missing = expected_widgets - widget_seen
        if widget_missing:
            raise ValueError('Following placeable_widgets were not specified: {}'.format(', '.join(widget_missing)))


    def widget_layout_to_tree(self, widget):
        """ Returns a tree representing a widget hierarchy, leaves are strings and nodes are dicts.

            Args:
                widget (:class:`Gtk.Widget`): the widget where to start

            Recursive function. See validate_layout() for more info on the tree structure.
        """
        orientation_names = {Gtk.Orientation.HORIZONTAL:'horizontal', Gtk.Orientation.VERTICAL:'vertical'}

        if issubclass(type(widget), Gtk.Box):
            node = {'resizeable': False, 'children': [self.widget_layout_to_tree(c) for c in widget.get_children()],
                    'orientation': orientation_names[widget.get_orientation()]}
        elif issubclass(type(widget), Gtk.Paned):
            proportions = [1]
            reverse_children = []
            orientation = widget.get_orientation()

            while issubclass(type(widget), Gtk.Paned) and orientation == widget.get_orientation():
                left_pane = widget.get_child1()
                right_pane = widget.get_child2()

                if not left_pane.get_visible() or not right_pane.get_visible():
                    # reuse number that was in config initially, otherwise gets overwritten with 0
                    ratio = self.pane_handle_pos[widget]
                elif widget.get_orientation() == Gtk.Orientation.HORIZONTAL:
                    ratio = float(widget.get_position()) / Gtk.Widget.get_allocated_width(widget)
                else:
                    ratio = float(widget.get_position()) / Gtk.Widget.get_allocated_height(widget)

                proportions = [ratio] + [(1 - ratio) * p for p in proportions]
                reverse_children.append(right_pane)
                widget = left_pane

            reverse_children.append(left_pane)

            node = {'resizeable': True, 'children': [self.widget_layout_to_tree(c) for c in reversed(reverse_children)],
                    'proportions': proportions, 'orientation': orientation_names[orientation]}

        elif widget in self.placeable_widgets.values():
            for name, placeable_widget in self.placeable_widgets.items():
                if placeable_widget == widget:
                    node = name
                    break
        else:
            raise ValueError('Error serializing layout: widget of type {} is not an expected container or named widget: {}'.format(type(widget), widget))

        return node


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

        default = 'pointer_' + self.config.get('presenter', 'pointer')
        self.load_pointer(default)

        for radio_name in ['pointer_red', 'pointer_blue', 'pointer_green', 'pointer_none']:
            radio = self.builder.get_object(radio_name)
            radio.set_name(radio_name)

            radio.set_active(radio_name == default)


    def make_pwin(self):
        """ Initializes the presenter window.
        """
        default_notes_layout = '{"resizeable":true, "orientation":"horizontal", "children":["notes", {"resizeable":false, "children":["current", "next"], "orientation":"vertical"}], "proportions": [0.60, 0.40]}'
        default_plain_layout = '{"resizeable":true, "orientation":"horizontal", "children":["current", {"resizeable":true, "orientation":"vertical", "children":["next", "annotations"], "proportions":[0.55, 0.45]}], "proportions":[0.67, 0.33]}'

        # Log error and keep default layout
        try:
            self.notes_layout = pympress.util.layout_from_json(self.config.get('layout', 'notes'), default_notes_layout)
            self.validate_layout(self.notes_layout, set(self.placeable_widgets.keys()) - {"annotations"})
        except ValueError as e:
            logger.exception('Invalid layout')
            self.notes_layout = pympress.util.layout_from_json(default_notes_layout)

        try:
            self.plain_layout = pympress.util.layout_from_json(self.config.get('layout', 'plain'), default_plain_layout)
            self.validate_layout(self.plain_layout, set(self.placeable_widgets.keys()) - {"notes"})
        except ValueError as e:
            logger.exception('Invalid layout')
            self.plain_layout = pympress.util.layout_from_json(default_plain_layout)

        self.rearrange_p_layout(self.notes_layout if self.notes_mode else self.plain_layout)

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
            self.builder.get_object(n).set_active(init_checkstates[n])

        self.spin_cur.set_range(1, self.doc.pages_number())
        self.hb_cur.remove(self.spin_cur)

        if self.notes_mode:
            self.cache.add_widget("p_da_cur", PDF_CONTENT_PAGE)
            self.cache.add_widget("p_da_next", PDF_CONTENT_PAGE)
            self.cache.add_widget("p_da_notes", PDF_NOTES_PAGE)
        else:
            self.cache.add_widget("p_da_cur", PDF_REGULAR)
            self.cache.add_widget("p_da_next", PDF_REGULAR)
            self.cache.add_widget("p_da_notes", PDF_REGULAR, False)


        # Annotations
        self.annotation_renderer = Gtk.CellRendererText()
        self.annotation_renderer.props.wrap_mode = Pango.WrapMode.WORD_CHAR

        column = Gtk.TreeViewColumn(None, self.annotation_renderer, text=0)
        column.props.sizing = Gtk.TreeViewColumnSizing.AUTOSIZE
        column.set_fixed_width(1)

        self.scrollable_treelist.set_model(Gtk.ListStore(str))
        self.scrollable_treelist.append_column(column)

        self.scrolled_window.set_hexpand(True)

        # set default values
        self.label_last.set_text("/{}".format(self.doc.pages_number()))
        self.label_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))

        # Enable dropping files onto the window
        self.p_win.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.p_win.drag_dest_add_text_targets()


    def load_time_colors(self):
        # Load color from CSS
        style_context = self.label_time.get_style_context()
        style_context.add_class("ett-reached")
        self.label_time.show();
        self.label_color_ett_reached = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-reached")
        style_context.add_class("ett-info")
        self.label_time.show();
        self.label_color_ett_info = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-info")
        style_context.add_class("ett-warn")
        self.label_time.show();
        self.label_color_ett_warn = style_context.get_color(Gtk.StateType.NORMAL)
        style_context.remove_class("ett-warn")
        self.label_time.show();
        self.label_color_default = style_context.get_color(Gtk.StateType.NORMAL)


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


    def add_annotations(self, annotations):
        """ Insert text annotations into the tree view that displays them.
        """
        list_annot = Gtk.ListStore(str)

        bullet = b'\xe2\x97\x8f '.decode('utf-8') if sys.version_info > (3, 0) else '\xe2\x97\x8f '

        for annot in annotations:
            list_annot.append((bullet + annot,))

        self.scrollable_treelist.set_model(list_annot)


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

        if self.notes_mode:
            self.notes_layout = self.widget_layout_to_tree(self.p_central.get_children()[0])
        else:
            self.plain_layout = self.widget_layout_to_tree(self.p_central.get_children()[0])

        self.config.set('layout', 'notes', json.dumps(self.notes_layout, indent=4))
        self.config.set('layout', 'plain', json.dumps(self.plain_layout, indent=4))

        self.doc.cleanup_media_files()

        pympress.util.save_config(self.config)
        Gtk.main_quit()


    def goto_prev(self, *args):
        """ Wrapper around eponymous function of current document
        """
        self.doc.goto_prev()


    def goto_next(self, *args):
        """ Wrapper around eponymous function of current document
        """
        self.doc.goto_next()


    def goto_home(self, *args):
        """ Wrapper around eponymous function of current document
        """
        self.doc.goto_home()


    def goto_end(self, *args):
        """ Wrapper around eponymous function of current document
        """
        self.doc.goto_end()


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
        about = Gtk.AboutDialog()
        about.set_program_name('pympress')
        about.set_version(pympress.__version__)
        about.set_copyright(_('Contributors:') + '\n' + pympress.__copyright__)
        about.set_comments(_('pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK for the GUI.\n')
                         + _('Some preferences are saved in ') + pympress.util.path_to_config() + '\n\n'
                         + (_('Video support using VLC is enabled.') if vlc_enabled else _('Video support using VLC is disabled.')))
        about.set_website('http://www.pympress.xyz/')
        try:
            about.set_logo(pympress.util.get_icon_pixbuf('pympress-128.png'))
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
            page_type = pympress.document.PDF_REGULAR
        else:
            page_type = pympress.document.PDF_CONTENT_PAGE

            self.p_frame_notes.set_property('ratio', page_cur.get_aspect_ratio(pympress.document.PDF_NOTES_PAGE))
            self.p_da_notes.queue_draw()

        self.p_frame_cur.set_property('ratio', page_cur.get_aspect_ratio(page_type))
        self.p_da_cur.queue_draw()

        if page_next is not None:
            pr = page_next.get_aspect_ratio(page_type)
            self.p_frame_next.set_property('ratio', pr)

        self.p_da_next.queue_draw()

        self.add_annotations(page_cur.get_annotations())


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

        self.add_annotations(page_cur.get_annotations())

        # Page change: resynchronize miniatures
        self.page_preview_nb = page_cur.number()

        # Aspect ratios and queue redraws
        if not self.notes_mode:
            page_type = pympress.document.PDF_REGULAR
        else:
            page_type = pympress.document.PDF_CONTENT_PAGE

            self.p_frame_notes.set_property('ratio', page_cur.get_aspect_ratio(pympress.document.PDF_NOTES_PAGE))
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
        if unpause and self.paused:
            self.switch_pause()

        # Update display
        self.update_page_numbers()

        # Prerender the 4 next pages and the 2 previous ones
        page_max = min(self.doc.pages_number(), self.page_preview_nb + 5)
        page_min = max(0, self.page_preview_nb - 2)
        for p in list(range(self.page_preview_nb+1, page_max)) + list(range(self.page_preview_nb, page_min, -1)):
            self.cache.prerender(p)

        self.replace_media_overlays()


    @classmethod
    def notify_page_change(cls):
        """ Statically notify the UI of a page change (typically from document)
        """
        cls._instance.on_page_change()


    def replace_media_overlays(self):
        """ Remove current media overlays, add new ones if page contains media.
        """
        if not vlc_enabled:
            return

        self.c_overlay.foreach(lambda child, *ignored: child.hide() if child is not self.c_da else None, None)

        page_cur = self.doc.current_page()
        pw, ph = page_cur.get_size()

        for relative_margins, filename, show_controls in page_cur.get_media():
            media_id = hash((relative_margins, filename, show_controls))

            if media_id not in self.media_overlays:
                v_da = pympress.vlcvideo.VLCVideo(self.c_overlay, show_controls, relative_margins)
                v_da.set_file(filename)

                self.media_overlays[media_id] = v_da


    @classmethod
    def play_media(cls, media_id):
        """ Static way of starting (playing) a media. Used by callbacks.
        """
        self = cls._instance
        if media_id in self.media_overlays:
            self.media_overlays[media_id].play()


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

        # Temporarily, while p_frame_annot's configure-event is noto working
        self.on_configure_annot(self.p_frame_annot, None)


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

        if (widget is self.c_da or widget is self.p_da_cur) and self.show_pointer == POINTER_SHOW:
            x = ww * self.pointer_pos[0] - self.pointer.get_width() / 2
            y = wh * self.pointer_pos[1] - self.pointer.get_height() / 2
            Gdk.cairo_set_source_pixbuf(cairo_context, self.pointer, x, y)

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

        if widget is self.c_da and vlc_enabled:
            self.c_overlay.foreach(lambda child, *ignored: child.resize() if type(child) is pympress.vlcvideo.VLCVideo else None, None)


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


    def on_configure_annot(self, widget, event):
        """ Adjust wrap width in annotations when they are resized.
        """
        self.annotation_renderer.props.wrap_width = widget.get_allocated_width() - 10
        self.scrolled_window.queue_resize()
        self.scrollable_treelist.get_column(0).queue_resize()


    def on_navigation(self, widget, event):
        """ Manage events as mouse scroll or clicks for both windows.

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured (ignored)
            event (:class:`Gdk.Event`):  the event that occured
        """
        if event.type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)
            ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and self.on_spin_nav(widget, event):
                return True
            # send all to entry field if it is active to avoid key problems
            if self.editing_cur_ett and self.on_label_ett_event(widget, event):
                return True

            if self.paused and name == 'space':
                self.switch_pause()
            elif name in ['Right', 'Down', 'Page_Down', 'space']:
                self.goto_next()
            elif name in ['Left', 'Up', 'Page_Up', 'BackSpace']:
                self.goto_prev()
            elif name == 'Home':
                self.goto_home()
            elif name == 'End':
                self.goto_end()
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
                self.switch_pause()
            elif name.upper() == 'R':
                self.reset_timer()

            if self.scribbling_mode:
                if name.upper() == 'Z' and ctrl_pressed:
                    self.pop_scribble()
                elif name == 'Escape':
                    self.switch_scribbling()

            # Some key events are already handled by toggle actions in the
            # presenter window, so we must handle them in the content window
            # only to prevent them from double-firing
            if widget is self.c_win:
                if name.upper() == 'P':
                    self.switch_pause()
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
                elif name.upper() == 'G':
                    self.on_label_event(self.eb_cur, True)
                elif name.upper() == 'T':
                    self.on_label_ett_event(self.eb_ett, True)
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

        elif event.type == Gdk.EventType.SCROLL:

            # send all to spinner if it is active to avoid key problems
            if self.editing_cur and Gtk.SpinButton.do_scroll_event(self.spin_cur, event):
                pass

            elif event.direction is Gdk.ScrollDirection.SMOOTH:
                return False
            else:
                adj = self.scrolled_window.get_vadjustment()
                if event.direction == Gdk.ScrollDirection.UP:
                    adj.set_value(adj.get_value() - adj.get_step_increment())
                elif event.direction == Gdk.ScrollDirection.DOWN:
                    adj.set_value(adj.get_value() + adj.get_step_increment())
                else:
                    return False

            return True

        elif event.type == Gdk.EventType.BUTTON_PRESS:
            self.show_pointer = POINTER_SHOW
            # TODO trigger content window redraw
            return True
        elif event.type == Gdk.EventType.BUTTON_RELEASE:
            # TODO trigger content window redraw
            self.show_pointer = POINTER_HIDE

        return False


    def on_spin_nav(self, widget, event):
        """ Manage key presses, for validating or navigating input, or cancelling navigation.

        Args:
            widget (:class:`Gtk.Widget`):  the widget which has received the key stroke.
            event (:class:`Gdk.Event`):  the GTK event, which contains the ket stroke information.
        """
        if event.type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval).lower().replace('kp_', '')

            if name == 'return' or name == 'enter':
                try:
                    page_nb = int(self.spin_cur.get_buffer().get_text()) - 1
                except:
                    page_nb = int(self.spin_cur.get_value()) - 1
                self.doc.goto(page_nb)

            elif name == 'escape':
                GLib.idle_add(self.on_page_change, False)

            if name in ['escape', 'return', 'enter']:
                self.restore_current_label()
            elif name == 'home':
                self.spin_cur.set_value(1)
            elif name == 'end':
                self.spin_cur.set_value(self.doc.pages_number())
            elif name == 'left':
                self.spin_cur.set_value(self.spin_cur.get_value() - 1)
            elif name == 'right':
                self.spin_cur.set_value(self.spin_cur.get_value() + 1)
            elif name in 'a0123456789'  or name in ['up', 'left', 'right', 'down', 'backspace']:
                return Gtk.SpinButton.do_key_press_event(self.spin_cur, event)
            else:
                return False

            return True

        return False


    def on_link(self, widget, event):
        """ Manage events related to hyperlinks.

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
                return
        else:
            page = self.doc.current_page()

        # Normalize event coordinates and get link
        x, y = event.get_coords()
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if not self.notes_mode:
            # PDF_REGULAR page, the allocated size is the page size
            x2, y2 = x/ww, y/wh
        elif widget is self.p_da_notes:
            # PDF_NOTES_PAGE, the allocated size is the right half of the page
            x2, y2 = (ww + x) / (2 * ww), y / wh
        else:
            # PDF_CONTENT_PAGE, the allocated size is left half of the page
            x2, y2 = x / (2 * ww), y / wh

        link = page.get_link_at(x2, y2)

        # Event type?
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if link is not None:
                link.follow()

        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            if self.show_pointer == POINTER_SHOW:
                pass
            elif link is not None:
                widget.get_window().set_cursor(self.cursors['pointer'])
            else:
                widget.get_window().set_cursor(self.cursors['parent'])

        else:
            logger.warning(_("Unknown event {}").format(event.type))

        return True


    def on_label_event(self, *args):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...

        Args:
            widget (:class:`Gtk.Widget`):  the widget in which the event occured
            event (:class:`Gdk.Event`):  the event that occured
        """

        event = args[-1]

        # we can come manually or through a menu action as well
        alt_start_editing = (type(event) == bool and event is True or type(event) == Gtk.MenuItem)
        event_type = None if alt_start_editing else event.type

        # Click in label-mode
        if alt_start_editing or event_type == Gdk.EventType.BUTTON_PRESS: # click
            if self.editing_cur_ett:
                self.restore_current_label_ett()

            if self.label_cur in self.hb_cur:
                # Replace label with entry
                self.hb_cur.remove(self.label_cur)
                self.spin_cur.show()
                self.hb_cur.add(self.spin_cur)
                self.hb_cur.reorder_child(self.spin_cur, 0)
                self.spin_cur.grab_focus()
                self.editing_cur = True

                self.spin_cur.set_range(1, self.doc.pages_number())
                self.spin_cur.set_value(self.doc.current_page().number() + 1)
                self.spin_cur.select_region(0, -1)

            elif self.editing_cur:
                self.spin_cur.grab_focus()

        else:
            # Ignored event - propagate further
            return False

        return True


    @classmethod
    def notify_label_event(cls):
        """ Static way to start the "go to" label editing.

        Typically used as callbacks from document links.
        """
        cls._instance.on_label_event(True)


    def on_label_ett_event(self, *args):
        """ Manage events on the current slide label/entry.

        This function replaces the label with an entry when clicked, replaces
        the entry with a label when needed, etc. The nasty stuff it does is an
        ancient kind of dark magic that should be avoided as much as possible...

        Args:
            widget (:class:`gtk.Widget`):  the widget in which the event occured
            event (:class:`gtk.gdk.Event`):  the event that occured
        """

        widget = self.eb_ett.get_child()
        event = args[-1]

        # we can come manually or through a menu action as well
        alt_start_editing = (type(event) == bool and event is True or type(event) == Gtk.MenuItem)
        event_type = None if alt_start_editing else event.type

        # Click on the label
        if widget is self.label_ett and (alt_start_editing or event_type == Gdk.EventType.BUTTON_PRESS):
            if self.editing_cur:
                self.spin_cur.cancel()

            # Set entry text
            self.entry_ett.set_text("{:02}:{:02}".format(*divmod(self.est_time, 60)))
            self.entry_ett.select_region(0, -1)

            # Replace label with entry
            self.eb_ett.remove(self.label_ett)
            self.eb_ett.add(self.entry_ett)
            self.entry_ett.show()
            self.entry_ett.grab_focus()
            self.editing_cur_ett = True

        # Key pressed in the entry
        elif widget is self.entry_ett and event_type == Gdk.EventType.KEY_PRESS:
            name = Gdk.keyval_name(event.keyval)

            # Return key --> restore label and goto page
            if name == "Return" or name == "KP_Enter":
                text = self.entry_ett.get_text()
                self.restore_current_label_ett()

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
                self.label_time.override_color(Gtk.StateType.NORMAL, self.label_color_default)
                return True

            # Escape key --> just restore the label
            elif name == "Escape":
                self.restore_current_label_ett()
                return True
            else:
                Gtk.Entry.do_key_press_event(widget, event)

        return True


    def restore_current_label(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        if self.label_cur not in self.hb_cur:
            self.hb_cur.remove(self.spin_cur)
            self.hb_cur.pack_start(self.label_cur, True, True, 0)
            self.hb_cur.reorder_child(self.label_cur, 0)

        self.editing_cur = False


    def restore_current_label_ett(self):
        """ Make sure that the current page number is displayed in a label and not in an entry.
        If it is an entry, then replace it with the label.
        """
        child = self.eb_ett.get_child()
        if child is not self.label_ett:
            self.eb_ett.remove(child)
            self.eb_ett.add(self.label_ett)

        self.editing_cur_ett = False


    def update_page_numbers(self):
        """ Update the displayed page numbers.
        """
        cur_nb = self.doc.current_page().number()
        cur = str(cur_nb+1)

        self.label_cur.set_text(cur)
        self.restore_current_label()


    def update_time(self):
        """ Update the timer and clock labels.

        Returns:
            boolean: ``True`` (to prevent the timer from stopping)
        """

        # Current time
        clock = time.strftime("%X") #"%H:%M:%S"

        # Time elapsed since the beginning of the presentation
        if not self.paused:
            self.delta = time.time() - self.start_time
        elapsed = "{:02}:{:02}".format(*divmod(int(self.delta), 60))
        if self.paused:
            elapsed += " " + _("(paused)")

        self.label_time.set_text(elapsed)
        self.label_clock.set_text(clock)

        self.update_time_color()

        return True


    def calc_color(self, from_color, to_color, position):
        """ Compute the interpolation between two colors.

        Args:
            from_color (:class:`Gdk.RGBA`):  the color when position = 0
            to_color (:class:`Gdk.RGBA`):  the color when position = 1
            position (float):  A floating point value in the interval [0.0, 1.0]

        Returns:
            :class:`Gdk.RGBA`: The color that is between from_color and to_color
        """
        color_tuple = lambda color: ( color.red, color.green, color.blue, color.alpha )
        interpolate = lambda start, end: start + (end - start) * position

        return Gdk.RGBA(*map(interpolate, color_tuple(from_color), color_tuple(to_color)))


    def update_time_color(self):
        """ Update the color of the time label based on how much time is remaining.
        """
        if not self.est_time == 0:
            # Set up colors between which to fade, based on how much time remains (<0 has run out of time).
            # Times are given in seconds, in between two of those timestamps the color will interpolated linearly.
            # Outside of the intervals the closest color will be used.
            colors = {
                 300:self.label_color_default,
                   0:self.label_color_ett_reached,
                -150:self.label_color_ett_info,
                -300:self.label_color_ett_warn
            }
            bounds=list(sorted(colors, reverse=True)[:-1])

            remaining = self.est_time - self.delta
            if remaining >= bounds[0]:
                color = colors[bounds[0]]
            elif remaining <= bounds[-1]:
                color = colors[bounds[-1]]
            else:
                c=1
                while bounds[c] >= remaining:
                    c += 1
                position = (remaining - bounds[c-1]) / (bounds[c] - bounds[c-1])
                color = self.calc_color(colors[bounds[c-1]], colors[bounds[c]], position)

            if color:
                self.label_time.override_color(Gtk.StateType.NORMAL, color)

            if (remaining <= 0 and remaining > -5) or (remaining <= -300 and remaining > -310):
                self.label_time.get_style_context().add_class("time-warn")
            else:
                self.label_time.get_style_context().remove_class("time-warn")


    def switch_pause(self, widget=None, event=None):
        """ Switch the timer between paused mode and running (normal) mode.
        """
        if self.paused:
            self.start_time = time.time() - self.delta
            self.paused = False
        else:
            self.paused = True
        self.update_time()


    def reset_timer(self, widget=None, event=None):
        """ Reset the timer.
        """
        self.start_time = time.time()
        self.delta = 0
        self.update_time()


    def set_screensaver(self, must_disable):
        """ Enable or disable the screensaver.

        Args:
            must_disable (boolean):  if ``True``, indicates that the screensaver must be disabled; otherwise it will be enabled
        """
        if IS_MAC_OS:
            # On Mac OS X we can use caffeinate to prevent the display from sleeping
            if must_disable:
                if self.dpms_was_enabled == None or self.dpms_was_enabled.poll():
                    self.dpms_was_enabled = subprocess.Popen(['caffeinate', '-d', '-w', str(os.getpid())])
            else:
                if self.dpms_was_enabled and not self.dpms_was_enabled.poll():
                    self.dpms_was_enabled.kill()
                    self.dpms_was_enabled.poll()
                    self.dpms_was_enabled = None

        elif IS_POSIX:
            # On Linux, set screensaver with xdg-screensaver
            # (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
            cmd = "suspend" if must_disable else "resume"
            status = os.system("xdg-screensaver {} {}".format(cmd, self.c_win.get_window().get_xid()))
            if status != 0:
                logger.warning(_("Could not set screensaver status: got status ")+str(status))

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
                        logger.warning(_("Could not disable DPMS screen blanking: got status ")+str(status))
                else:
                    self.dpms_was_enabled = False

            elif self.dpms_was_enabled:
                # Re-enable DPMS
                status = os.system("xset +dpms")
                if status != 0:
                    logger.warning(_("Could not enable DPMS screen blanking: got status ")+str(status))

        elif IS_WINDOWS:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Control Panel\Desktop', 0, winreg.KEY_QUERY_VALUE|winreg.KEY_SET_VALUE) as key:
                    if must_disable:
                        (value,type) = winreg.QueryValueEx(key, "ScreenSaveActive")
                        assert(type == winreg.REG_SZ)
                        self.dpms_was_enabled = (value == "1")
                        if self.dpms_was_enabled:
                            winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "0")
                    elif self.dpms_was_enabled:
                        winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "1")
            except (OSError, PermissionError):
                logger.exception(_("access denied when trying to access screen saver settings in registry!"))
        else:
            logger.warning(_("Unsupported OS: can't enable/disable screensaver"))


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
            self.set_screensaver(self.c_win_fullscreen)


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
            # temporarily remove the annotations' list size so it won't hinder p_frame_next size adjustment
            self.scrolled_window.set_size_request(-1,  100)

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

            self.notes_layout = self.widget_layout_to_tree(self.p_central.get_children()[0])
            self.rearrange_p_layout(self.plain_layout)
        else:
            self.notes_mode = True
            self.cache.set_widget_type("c_da", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_next", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("p_da_cur", PDF_CONTENT_PAGE)
            self.cache.set_widget_type("scribble_p_da", PDF_CONTENT_PAGE)
            self.cache.enable_prerender("p_da_cur")

            self.cache.set_widget_type("p_da_notes", PDF_NOTES_PAGE)
            self.cache.enable_prerender("p_da_notes")

            self.plain_layout = self.widget_layout_to_tree(self.p_central.get_children()[0])
            self.rearrange_p_layout(self.notes_layout)
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


    def track_scribble(self, widget=None, event=None):
        """ Track events defining drawings by user, on top of current slide
        """
        if not self.scribbling_mode:
            return self.track_pointer(widget, event)

        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            self.scribble_list.append( (self.scribble_color, self.scribble_width, []) )
            self.scribble_drawing = True
        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
            self.scribble_drawing = False

        if self.scribble_drawing:
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.scribble_list[-1][2].append((ex / ww, ey / wh))

            self.scribble_c_da.queue_draw()
            self.scribble_p_da.queue_draw()
        else:
            return self.on_link(widget, event)


    def track_pointer(self, widget=None, event=None):
        """ Track events defining "pointing the laser" by user, on top of current slide
        """
        if self.show_pointer == POINTER_OFF:
            return self.on_link(widget, event)

        ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

        if not ctrl_pressed and event.type == Gdk.EventType.BUTTON_PRESS:
            return self.on_link(widget, event)
        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            self.on_link(widget, event)
        elif event.type == Gdk.EventType.BUTTON_PRESS:
            self.show_pointer = POINTER_SHOW
            self.c_overlay.get_window().set_cursor(self.cursors['invisible'])
            self.p_da_cur.get_window().set_cursor(self.cursors['invisible'])
        elif self.show_pointer == POINTER_SHOW and event.type == Gdk.EventType.BUTTON_RELEASE:
            self.show_pointer = POINTER_HIDE
            self.c_overlay.get_window().set_cursor(self.cursors['parent'])
            self.p_da_cur.get_window().set_cursor(self.cursors['parent'])
            self.c_da.queue_draw()
            self.p_da_cur.queue_draw()

        if self.show_pointer == POINTER_SHOW:
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.pointer_pos = (ex / ww, ey / wh)
            self.c_da.queue_draw()
            self.p_da_cur.queue_draw()

        return True


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
        self.builder.get_object("scribble_color").set_rgba(self.scribble_color)
        self.builder.get_object("scribble_width").set_value(self.scribble_width)


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


    def load_pointer(self, name):
        """ Perform the change of pointer using its name
        """
        if name in ['pointer_red', 'pointer_green', 'pointer_blue']:
            self.show_pointer = POINTER_HIDE
            self.pointer = pympress.util.get_icon_pixbuf(name + '.png')
        else:
            self.show_pointer = POINTER_OFF


    def change_pointer(self, widget):
        """ Callback for a radio item selection as pointer color
        """
        if widget.get_active():
            assert(widget.get_name().startswith('pointer_'))
            self.load_pointer(widget.get_name())
            self.config.set('presenter', 'pointer', widget.get_name()[len('pointer_'):])



##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
