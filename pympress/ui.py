# -*- coding: utf-8 -*-
#
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

import logging
logger = logging.getLogger(__name__)

import pathlib
import math
import sys
import gc
from urllib.request import url2pathname
from urllib.parse import urlsplit

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Gtk, Gdk, GLib, GdkPixbuf, Gio


from pympress import (
    document, surfacecache, util, pointer, scribble, deck, builder, talk_time, dialog, extras, editable_label
)


class UI(builder.Builder):
    """ Pympress GUI management.
    """
    #: The :class:`~pympress.app.Pympress` instance
    app = None
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

    #: :class:`~Gtk.Grid` for the next slide(s) in the Presenter window.
    grid_next = None
    #: `list` of :class:`~Gtk.AspectFrame` for the next slide in the Presenter window.
    p_frames_next = None
    #: :class:`~Gtk.DrawingArea` for the next slide in the Presenter window.
    p_das_next = None
    #: `int` the number of next slides currently on display in the “Next slides” pane, initialized to the maximal number
    next_frames_count = 16
    #: `list` of :class:`~Gtk.AspectFrame` for the current slide copy in the Presenter window.
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
    notes_mode = document.PdfPage.NONE
    #: Current choice of mode to toggle notes
    chosen_notes_mode = document.PdfPage.RIGHT

    #: Whether to display annotations or not
    show_annotations = True
    #: Whether to display big buttons or not
    show_bigbuttons = True
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to previous slide
    prev_button = None
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to next slide
    next_button = None
    #: :class:`~Gtk.ToolButton` big button for touch screens, go toggle the pointer
    laser_button = None
    #: :class:`~Gtk.ToolButton` big button for touch screens, go to scribble on screen
    highlight_button = None

    #: number of page currently displayed in Content window's miniatures
    current_page = -1
    #: number of page currently displayed in Presenter window's miniatures
    preview_page = -1

    #: track whether we blank the screen
    blanked = False

    #: Dictionary of :class:`~Gtk.Widget` from the presenter window that can be dynamically rearranged
    placeable_widgets = {}
    #: Map of :class:`~Gtk.Paned` to the relative position (`float` between 0 and 1) of its handle
    pane_handle_pos = {}

    #: :class:`~pympress.config.Config` to remember preferences
    config = None

    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: Current :class:`~pympress.document.Document` instance.
    doc = document.EmptyDocument()

    #: Class :class:`~pympress.scribble.Scribble` managing drawing by the user on top of the current slide.
    scribbler = None
    #: Class :class:`~pympress.deck.Overview` displaying a view of all slides
    deck = None
    #: Class :class:`~pympress.extras.Annotations` managing the display of annotations
    annotations = None
    #: Class :class:`~pympress.extras.Media` managing keeping track of and callbacks on media overlays
    medias = None
    #: Class :class:`~pympress.extras.Zoom` managing the zoom level of the current slide.
    zoom = None

    #: Software-implemented laser pointer, :class:`~pympress.pointer.Pointer`
    laser = None

    #: :class:`~pympress.editable_label.PageNumber` displaying and setting current page numbers
    page_number = None

    #: :class:`~pympress.editable_label.EstimatedTalkTime` to set estimated/remaining talk time
    est_time = None
    #: :class:`~pympress.dialog.TimingReport` popup to show how much time was spent on which part
    timing = None
    #: :class:`~pympress.talk_time.TimeCounter` clock tracking talk time (elapsed, and remaining)
    talk_time = None

    #: A :class:`~Gtk.ShortcutsWindow` to show the shortcuts
    shortcuts_window = None
    #: :class:`~pympress.dialog.LayoutEditor` popup to configure the layouts of the presenter window
    layout_editor = None
    #: :class:`~pympress.dialog.AutoPlay` popup to configure automatic playing
    autoplay = None

    #: A :class:`~Gtk.AccelGroup` to store the shortcuts
    accel_group = None
    #: A :class:`~Gio.Menu` to display the recent files to open
    recent_menu = None

    #: A :class:`~pympress.extras.FileWatcher` object to reload modified files
    file_watcher = None

    #: `int` or `None`, may keep track of the Gtk.Application inhibit request
    inhibit_cookie = None

    ##############################################################################
    #############################      UI setup      #############################
    ##############################################################################

    def __init__(self, app, config):
        super(UI, self).__init__()
        self.app = app
        self.config = config

        self.blanked = self.config.getboolean('content', 'start_blanked')

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            util.load_style_provider(Gtk.CssProvider()),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # We may want some additional CSS changes
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.show_annotations = self.config.getboolean('presenter', 'show_annotations')
        self.chosen_notes_mode = document.PdfPage[self.config.get('notes position', 'horizontal').upper()]
        self.show_bigbuttons = self.config.getboolean('presenter', 'show_bigbuttons')

        # Surface cache
        self.cache = surfacecache.SurfaceCache(self.doc, self.config.getint('cache', 'maxpages'))

        # Make and populate windows
        self.load_ui('presenter')
        self.load_ui('content')
        self.app.add_window(self.p_win)
        self.app.add_window(self.c_win)

        self.load_ui('menu_bar', ext='.xml')
        self.app.set_menubar(self.get_object('menu_bar'))
        self.recent_menu = self.get_object('recent_menu')

        c_full = self.config.getboolean('content', 'start_fullscreen')
        p_full = self.config.getboolean('presenter', 'start_fullscreen')
        self.setup_actions({
            'quit':                  dict(activate=self.app.quit),
            'about':                 dict(activate=self.menu_about),
            'big-buttons':           dict(activate=self.switch_bigbuttons, state=self.show_bigbuttons),
            'show-shortcuts':        dict(activate=self.show_shortcuts),
            'content-fullscreen':    dict(activate=self.switch_fullscreen, state=c_full),
            'presenter-fullscreen':  dict(activate=self.switch_fullscreen, state=p_full),
            'swap-screens':          dict(activate=self.swap_screens),
            'blank-screen':          dict(activate=self.switch_blanked, state=self.blanked),
            'notes-mode':            dict(activate=self.switch_mode, state=False),
            'notes-pos':             dict(activate=self.change_notes_pos, parameter_type=str,
                                          state=self.chosen_notes_mode.name.lower()),
            'annotations':           dict(activate=self.switch_annotations, state=self.show_annotations),
            'validate-input':        dict(activate=self.validate_current_input),
            'cancel-input':          dict(activate=self.cancel_current_input),
            'align-content':         dict(activate=self.adjust_frame_position),
            'next-frames':           dict(activate=self.reconfigure_next_frames, parameter_type=int,
                                          state=self.next_frames_count),
        })

        self.setup_actions({
            'open-file':         dict(activate=self.open_file, parameter_type=str),
            'close-file':        dict(activate=self.close_file),
            'save-file':         dict(activate=self.save_file),
            'save-file-as':      dict(activate=self.save_file_as),
            'pick-file':         dict(activate=self.pick_file),
            'list-recent-files': dict(change_state=self.populate_recent_menu, state=False),
            'page':              dict(activate=lambda gaction, param: self.goto_page(param.get_int64()),
                                      parameter_type=int, state=self.current_page),
            'next-page':         dict(activate=self.doc_goto_next),
            'next-label':        dict(activate=self.doc_label_next),
            'prev-page':         dict(activate=self.doc_goto_prev),
            'prev-label':        dict(activate=self.doc_label_prev),
            'hist-back':         dict(activate=self.doc_hist_prev),
            'hist-forward':      dict(activate=self.doc_hist_next),
            'first-page':        dict(activate=self.doc_goto_home),
            'last-page':         dict(activate=self.doc_goto_end),
        })

        self.zoom = extras.Zoom(self)
        self.scribbler = scribble.Scribbler(self.config, self, self.notes_mode)
        self.deck = deck.Overview(self.config, self, self.notes_mode)
        self.annotations = extras.Annotations(self)
        self.medias = extras.Media(self, self.config)
        self.laser = pointer.Pointer(self.config, self)
        self.est_time = editable_label.EstimatedTalkTime(self)
        self.page_number = editable_label.PageNumber(self, self.config.getboolean('presenter', 'scroll_number'))
        self.timing = dialog.TimingReport(self)
        self.autoplay = dialog.AutoPlay(self)
        self.talk_time = talk_time.TimeCounter(self, self.est_time, self.timing, self.autoplay)
        self.layout_editor = dialog.LayoutEditor(self, self.config)
        self.file_watcher = extras.FileWatcher()
        self.config.register_actions(self)

        # Get placeable widgets. NB, get the highlight one manually from the scribbler class
        self.placeable_widgets = {
            name: self.get_object(widget_name) for name, widget_name in self.config.placeable_widgets.items()
        }
        self.placeable_widgets['highlight'] = self.scribbler.scribble_overlay
        self.placeable_widgets['deck'] = self.deck.deck_viewport

        # Initialize windows
        self.make_cwin()
        self.make_pwin()

        self.connect_signals(self)

        for action, shortcut_list in self.config.shortcuts.items():
            if action == 'highlight-hold-to-erase':
                continue  # Not really an action but we define a shortcut for it
            self.app.set_accels_for_action('app.' + action, shortcut_list)

        # Common to both windows
        self.load_icons()

        # Adjust default visibility of items
        self.prev_button.set_no_show_all(True)
        self.next_button.set_no_show_all(True)
        self.laser_button.set_no_show_all(True)
        self.highlight_button.set_no_show_all(True)
        self.p_frame_annot.set_no_show_all(True)

        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.laser_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)
        self.p_frame_annot.set_visible(self.show_annotations)
        self.laser.activate_pointermode()

        # Setup screens and show all windows
        self.p_win.parse_geometry(self.config.get('presenter', 'geometry'))
        self.c_win.parse_geometry(self.config.get('content', 'geometry'))

        screen = self.p_win.get_screen()
        if type(screen).__name__ != 'GdkWaylandScreen':
            self.setup_screens(screen, 'at startup')
        else:
            self.app.lookup_action('swap-screens').set_enabled(False)

        screen.connect('monitors-changed', self.screens_changed)

        self.c_win.show_all()
        self.p_win.show_all()

        # Queue some redraws
        self.c_da.queue_draw()
        self.redraw_panes()
        self.do_page_change(unpause=False)

        if type(screen).__name__ == 'GdkWaylandScreen':
            GLib.timeout_add(100, self.setup_screens, screen, 'delayed startup')


    def load_icons(self):
        """ Set the icon list for both windows.
        """
        try:
            icon_list = [GdkPixbuf.Pixbuf.new_from_file(i) for i in util.list_icons()]
        except Exception:
            logger.exception('Error loading icons')
            return

        self.c_win.set_icon_list(icon_list)
        self.p_win.set_icon_list(icon_list)


    def make_cwin(self):
        """ Initializes the content window.
        """
        self.c_frame.set_property('yalign', self.config.getfloat('content', 'yalign'))
        self.c_frame.set_property('xalign', self.config.getfloat('content', 'xalign'))

        page_type = self.notes_mode.complement()

        self.cache.add_widget(self.c_da, page_type)
        self.cache.add_widget(self.c_da, page_type, zoomed = True)
        self.c_frame.set_property("ratio", self.doc.page(self.current_page).get_aspect_ratio(page_type))

        colourclass = 'white' if self.config.getboolean('content', 'white_blanking') else 'black'
        self.c_da.get_style_context().add_class(colourclass)
        self.c_win.get_style_context().add_class(colourclass)

        self.c_win.insert_action_group('content', self.c_win.get_action_group('win'))
        self.c_win.insert_action_group('win', None)


    def make_pwin(self):
        """ Initializes the presenter window.
        """
        layout = self.config.get_layout('notes' if self.notes_mode else 'plain')
        pane_handles = self.replace_layout(layout, self.p_central, self.placeable_widgets, self.on_pane_event)
        self.pane_handle_pos.update(pane_handles)

        self.p_frames_next = [self.get_object('p_frame_next{}'.format(n)) for n in range(16)]
        self.p_das_next = [self.get_object('p_da_next{}'.format(n)) for n in range(16)]
        self.reconfigure_next_frames(None, GLib.Variant.new_int64(self.config.getint('presenter', 'next_slide_count')))

        slide_type = self.notes_mode.complement()
        self.cache.add_widget(self.p_da_cur, slide_type)
        self.cache.add_widget(self.p_da_cur, slide_type, zoomed = True)
        # A single cache for all next slides
        self.cache.add_widget(self.p_das_next[0], slide_type)
        self.cache.add_widget(self.p_da_notes, self.notes_mode, prerender_enabled = bool(self.notes_mode))
        self.cache.add_widget(self.scribbler.scribble_p_da, slide_type, prerender_enabled = False)
        self.cache.add_widget(self.scribbler.scribble_p_da, slide_type, zoomed = True)
        self.cache.add_widget(self.deck.deck0, slide_type, prerender_enabled = False, ignore_max = True)

        # set default value
        self.page_number.set_last(self.doc.pages_number())

        # Enable dropping files onto the window
        self.p_win.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.p_win.drag_dest_add_text_targets()

        self.p_win.insert_action_group('presenter', self.c_win.get_action_group('win'))
        self.p_win.insert_action_group('win', None)


    def reconfigure_next_frames(self, gaction, param):
        """ Callback to set the number of next frames to preview the the “next slides” panel

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the number of slides as a GVariant
        """
        n_frames = param.get_int64()
        if n_frames < 1:
            n_frames = 1
        if n_frames > 16:
            n_frames = 16

        self.reflow_next_frames(n_frames)
        self.next_frames_count = n_frames
        self.app.set_action_state('next-frames', n_frames)
        self.config.set('presenter', 'next_slide_count', str(n_frames))


    def reflow_next_frames(self, n_frames=None):
        """ Set the number of next frames to preview the the “next slides” panel

        Args:
            n_frames (`int`): the number of frames
        """
        for n in range(self.next_frames_count):
            self.grid_next.remove(self.p_frames_next[n])

        for n in range(4):
            self.grid_next.remove_row(n)
            self.grid_next.remove_column(n)

        if n_frames is None:
            n_frames = self.next_frames_count

        ww, wh = self.grid_next.get_allocated_width(), self.grid_next.get_allocated_height()
        rows, cols = self.compute_frame_grid(ww / wh, n_frames)

        for n in range(n_frames):
            self.grid_next.attach(self.p_frames_next[n], n % cols, n // cols, 1, 1)


    def compute_frame_grid(self, grid_ar, n_frames):
        """ Determine the arragement of frames in a grid to maximise their size given respective aspect ratios

        Args:
            grid_ar (`float`): aspect ratio of grid containing the slides
            n_frames (`int`): the number of frames
        """
        if not n_frames:
            return 0, 0

        page_ratio = self.doc.page(self.preview_page).get_aspect_ratio(self.notes_mode.complement())
        grid_ar /= page_ratio

        # works best when n_frames = rows * cols * grid_ar
        rows = math.sqrt(n_frames / grid_ar)

        # If rows < 1 always ceil
        if rows < 1:
            return 1, n_frames

        # Check which of ceiling or flooring rows is better
        rows = math.floor(rows)
        f_cols, c_cols = (n_frames + rows - 1) // rows, (n_frames + rows) // (rows + 1)

        if min(f_cols, grid_ar * rows) > min(c_cols, grid_ar * (rows + 1)):
            return rows, f_cols
        else:
            return rows + 1, c_cols


    def screens_changed(self, screen):
        """ Handle ::monitors-changed events

        Args:
            screen (:class:`~Gdk.Screen`):  the screen
        """
        self.setup_screens(screen, 'at monitors-changed event')
        GLib.timeout_add(1000, self.setup_screens, screen, 'delayed after monitors-changed event')


    def setup_screens(self, screen, event_name=''):
        """ If multiple monitors, fullscreen windows on monitors according to config.

        Args:
            screen (:class:`~Gdk.Screen`):  the screen
            event_name (`str`):  a description of what caused the screen setup event, for debugging
        """
        display = Gdk.Display.get_default()
        try:
            c_monitor, p_monitor, primary, non_primary = util.Monitor.lookup_monitors(display, self.c_win, self.p_win)
        except util.NoMonitorPositions:
            return

        # Noisy, but just for debug level
        logger.debug('Detecting monitor layout ' + event_name + ': ' + ', '.join([
            'Content window is at monitor ' + c_monitor.name,
            'Presenter window is at monitor ' + p_monitor.name,
            'Primary monitor is (or overlapped with) ' + primary.name,
            'No non-primary monitor available' if primary.equal(non_primary)
            else 'A non-primary monitor is (or overlapped with) ' + non_primary.name
        ]))

        c_full = self.config.getboolean('content', 'start_fullscreen')
        p_full = self.config.getboolean('presenter', 'start_fullscreen')
        wayland = type(display).__name__ == 'GdkWaylandDisplay'

        if not c_full and not p_full or c_monitor is None or p_monitor is None:
            return

        if primary.equal(non_primary):
            logger.warning(_('Not starting content or presenter window full screen ' +
                             'because there is only one monitor'))

            c_full, p_full = False, False

        else:
            # To start fullscreen, we need to ensure windows are on individual monitors
            if not c_monitor.equal(p_monitor):
                pass
            elif wayland:
                # On Wayland, we can’t move windows, and they happen to be on the same monitor.
                # So if we are to fullscreen one, just do it on another monitor
                if c_full:
                    c_monitor = p_monitor.least_intersection([primary, non_primary])
                elif p_full:
                    p_monitor = c_monitor.least_intersection([primary, non_primary])
            elif c_monitor.equal(primary):
                self.move_window(self.c_win, c_monitor, non_primary)
                c_monitor = non_primary
            else:  # not p_monitor.equal(primary)
                self.move_window(self.p_win, p_monitor, primary)
                p_monitor = primary

        if p_full:
            self.p_win.fullscreen_on_monitor(self.p_win.get_screen(), p_monitor.monitor_number)
        elif not wayland:
            self.p_win.unfullscreen()

        if c_full:
            self.c_win.fullscreen_on_monitor(self.c_win.get_screen(), c_monitor.monitor_number)
            self.set_screensaver(True)
        else:
            # Let Wayland do its own un-fullscreening as we can’t move the windows afterwards and messing with it
            # results in a non-fullscreen window that is out of bounds of the remaining monitors.
            if not wayland:
                self.c_win.unfullscreen()
            self.set_screensaver(False)

        self.app.set_action_state('content-fullscreen', c_full)
        self.app.set_action_state('presenter-fullscreen', p_full)


    def move_window(self, win, from_bounds, to_bounds):
        """ Move window from monitor number from_monitor to monitor to_monitor.
        """
        x, y, w, h = win.get_position() + win.get_size()
        win_state = win.get_window().get_state() if win.get_window() is not None else 0

        logger.debug('Moving {} window from screen {} to screen {}'.format(
            'Content' if win is self.c_win else 'Presenter', from_bounds.name, to_bounds.name
        ))

        if (win_state & Gdk.WindowState.FULLSCREEN) != 0:
            win.unfullscreen()
        if (win_state & Gdk.WindowState.MAXIMIZED) != 0:
            win.unmaximize()

        to_w = min(w, to_bounds.width)
        to_h = min(h, to_bounds.height)

        # Get fraction of free space that is left or top of window
        x = (max(0, x - from_bounds.x) / (from_bounds.width - w)) if w < from_bounds.width else 0
        y = (max(0, y - from_bounds.y) / (from_bounds.height - h)) if h < from_bounds.height else 0

        win.resize(to_w, to_h)
        win.move(to_bounds.x + x * (to_bounds.width - to_w), to_bounds.y + y * (to_bounds.height - to_h))

        if (win_state & Gdk.WindowState.MAXIMIZED) != 0:
            win.maximize()
        if (win_state & Gdk.WindowState.FULLSCREEN) != 0:
            win.fullscreen()


    def show_shortcuts(self, *args):
        """ Display the shortcuts window.
        """
        # Use a different builder to load and be able to release the shortcuts window
        shortcuts_builder = builder.Builder()
        shortcuts_builder.load_ui('shortcuts')
        self.shortcuts_window = shortcuts_builder.get_object('shortcuts_window')

        for command, shortcut_list in self.config.items('shortcuts'):
            display_shortcut = shortcuts_builder.get_object('shortcut_' + command.replace('-', '_').replace('::', '_'))
            if display_shortcut is not None:
                display_shortcut.props.accelerator = shortcut_list

        self.shortcuts_window.set_transient_for(self.p_win)
        self.shortcuts_window.show_all()
        self.shortcuts_window.present()


    def close_shortcuts(self, *args):
        """ Destroy the shortcuts window once it is hidden.
        """
        self.shortcuts_window.destroy()
        self.shortcuts_window = None


    ##############################################################################
    ############################   Dynamic resize   ##############################
    ##############################################################################

    def on_configure_da(self, widget, event):
        """ Manage "configure" events for all drawing areas, e.g. resizes.

        We tell the local :class:`~pympress.surfacecache.SurfaceCache` cache about it, so that it can
        invalidate its internal cache for the specified widget and pre-render next pages at a correct size.

        Warning: Some not-explicitly sent signals contain wrong values! Just don't resize in that case,
        since these always seem to happen after a correct signal that was sent explicitly.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has been resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        # Don't trust those
        if not event.send_event:
            return

        self.cache.resize_widget(widget.get_name().rstrip('0123456789'), event.width, event.height)

        if widget is self.c_da:
            self.medias.resize('content')
            self.scribbler.reset_scribble_cache()
            self.scribbler.prerender()
        elif widget is self.p_da_cur:
            self.medias.resize('presenter')

        widget.queue_draw()


    def on_configure_win(self, widget, event):
        """ Manage "configure" events for both window widgets.

        Args:
            widget (:class:`~Gtk.Widget`):  the window which has been moved or resized
            event (:class:`~Gdk.Event`):  the GTK event, which contains the new dimensions of the widget
        """
        geom = '{}x{}{:+}{:+}'.format(*widget.get_size(), *widget.get_position())
        win_state = widget.get_window().get_state() if widget.get_window() is not None else 0
        win_state &= Gdk.WindowState.FULLSCREEN | Gdk.WindowState.MAXIMIZED

        if widget is self.p_win:
            if win_state == 0:
                self.config.set('presenter', 'geometry', geom)
            cw = self.p_central.get_allocated_width()
            ch = self.p_central.get_allocated_height()
            self.scribbler.scribble_off_render.set_size_request(cw, ch)
            self.deck.deck_off_render.set_size_request(cw, ch)

            if self.deck.deck_mode:
                self.deck.reset_grid()

            self.adjust_bottom_bar_font()

        elif widget is self.c_win and win_state == 0:
            self.config.set('content', 'geometry', geom)


    def adjust_bottom_bar_font(self):
        """ Scale baseline font size of bottom bar, clipped to 6px..13px. Fonts are then scaled by CSS em indications.
        """
        ww, wh = self.p_win.get_size()
        font_size = max(6, min(13, ww / 120 if self.show_bigbuttons else ww / 75))
        self.css_provider.load_from_data('#bottom {{ font-size: {:.1f}px; }}'.format(font_size).encode())


    def redraw_panes(self):
        """ Handler for :class:`~Gtk.Paned`'s resizing signal.

        Used for delayed drawing events of drawing areas inside the panes.

        This is very useful on windows where resizing gets sluggish if we try to redraw while resizing.
        """
        self.resize_panes = False
        self.reflow_next_frames()
        self.p_da_cur.queue_draw()
        for da in self.p_das_next:
            da.queue_draw()
        if self.notes_mode:
            self.p_da_notes.queue_draw()
        if self.redraw_timeout:
            self.redraw_timeout = 0

        self.config.update_layout_from_widgets(self.layout_name(self.notes_mode), self.p_central.get_children()[0],
                                               self.pane_handle_pos)


    def on_pane_event(self, widget, evt):
        """ Signal handler for gtk.paned events.

        This function allows one to delay drawing events when resizing, and to speed up redrawing when
        moving the middle pane is done (which happens at the end of a mouse resize)

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred (ignored)
            evt (:class:`~Gdk.Event`):  the event that occurred
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

    def cleanup(self, *args):
        """ Save configuration and exit the main loop.
        """
        self.scribbler.disable_scribbling()
        self.medias.hide_all()

        self.doc.cleanup_media_files()

        if self.app.get_action_state('content-fullscreen'):
            # In case we used hard-disabling
            self.set_screensaver(disabled=False)


    def menu_about(self, *args):
        """ Display the "About pympress" dialog.

        Handles clicks on the "about" menu.
        """
        about = Gtk.AboutDialog(transient_for = self.p_win)
        pympress = util.get_pympress_meta()
        about.set_program_name('pympress')
        about.set_version(pympress['version'])
        about.set_copyright(_('Contributors:') + '\n' + pympress['contributors'])
        about.set_comments(_('pympress is a little PDF reader written in Python ' +
                             'using Poppler for PDF rendering and GTK for the GUI.\n') +
                           _('Some preferences are saved in ') + str(self.config.path_to_config()) + '\n' +
                           _('Resources are loaded from ') + str(util.get_locale_dir().parent) + '\n' +
                           _('The log is written to ') + str(util.get_log_path()) + '\n\n' +
                           _('Media support uses {}.').format(self.medias.backend_version) + '\n' +
                           _('Python version {}').format(sys.version))
        about.set_website('https://github.com/Cimbali/pympress')
        try:
            about.set_logo(GdkPixbuf.Pixbuf.new_from_file(util.get_icon_path('pympress.png')))
        except Exception:
            logger.exception(_('Error loading icon for about window'))
        about.run()
        about.destroy()


    ##############################################################################
    ############################ Document manangement ############################
    ##############################################################################

    def swap_document(self, doc_uri, page=0, reloading=False):
        """ Replace the currently open document with a new one.

        The new document is possibly and EmptyDocument if doc_uri is None.
        The state of the ui and cache are updated accordingly.

        Args:
            doc_uri (`str`): the URI to the new document
            page (`int`): the page at which to start the presentation
            reloading (`bool`): whether we are reloading or detecting stuff from the document
        """
        if self.unsaved_changes(reloading):
            # If we keep the unsaved changes and were prompted by automatic file change,
            # stop watching for file changes in the future.
            if reloading:
                self.file_watcher.stop_watching()
            return

        run_gc = self.doc.doc is not None
        try:
            self.doc = document.Document.create(self, doc_uri)

            if not reloading and doc_uri:
                Gtk.RecentManager.get_default().add_item(doc_uri)
                self.file_watcher.watch_file(doc_uri, self.reload_document)

            elif not reloading:
                self.file_watcher.stop_watching()

        except GLib.Error:
            if reloading:
                return

            self.doc = document.Document.create(self, None)
            self.error_opening_file(doc_uri)
            self.file_watcher.stop_watching()

        self.current_page = self.preview_page = self.doc.goto(page)

        # Guess notes mode by default if the document has notes
        if not reloading:
            hpref = self.config.get('notes position', 'horizontal')
            vpref = self.config.get('notes position', 'vertical')
            target_mode = self.doc.guess_notes(hpref, vpref, self.current_page)

            if self.notes_mode != target_mode:
                self.switch_mode('notes-mode', target_mode=target_mode)

            # don't toggle from NONE to NONE
            if target_mode:
                self.app.activate_action('notes-pos', target_mode.name.lower())
        else:
            self.doc.set_notes_pos(self.notes_mode.direction())

        # Some things that need updating
        self.cache.swap_document(self.doc)
        self.page_number.set_last(self.doc.pages_number())
        self.page_number.enable_labels(self.doc.has_labels())
        self.autoplay.set_doc_pages(self.doc.pages_number())
        self.medias.purge_media_overlays()
        self.timing.set_document_metadata(self.doc.get_structure().copy(), self.doc.page_labels[:])

        # A new document, restart at time 0, paused
        if not reloading:
            self.talk_time.pause()
            self.talk_time.reset_timer()
            self.page_number.setup_doc_callbacks(self.doc)
            self.deck.setup_doc_callbacks(self.doc)

        self.do_page_change(unpause=False)

        # Now that all references to the old document have been replaced or removed, manually
        # collect garbage to delete objects and release file handles / close file descriptors
        if run_gc:
            gc.collect(1)


    def reload_document(self):
        """ Reload the current document.
        """
        self.swap_document(self.doc.get_uri(), page=self.current_page, reloading=True)


    def populate_recent_menu(self, gaction, is_opening=None):
        """ Callback for the recent document menu.

        Gets the URI and requests the document swap.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            is_opening (:class:`~GLib.Variant`): a wrapped boolean indicating whether the menu is opening or closing.
        """
        if not is_opening.get_boolean():
            self.recent_menu.remove_all()
            return

        for file in Gtk.RecentManager.get_default().get_items():
            if not file.exists() or not file.get_mime_type() == 'application/pdf':
                continue

            item = Gio.MenuItem.new(file.get_display_name(), 'app.open-file')
            item.set_action_and_target_value('app.open-file', GLib.Variant.new_string(file.get_uri()))
            item.set_icon(file.get_gicon())

            self.recent_menu.append_item(item)

            if self.recent_menu.get_n_items() >= 10:
                break


    def on_drag_drop(self, widget, drag_context, x, y, data, info, time):
        """ Receive the drag-drops (as text only). If a file is dropped, open it.

        Args:
            widget (:class:`~Gtk.Widget`): The widget on which the dragged item was dropped
            drag_context (:class:`~Gdk.DragContext`): Context object of the dragging
            x (`float`): position of the drop
            y (`float`):  position of the drop
            data (:class:`~Gtk.SelectionData`): container for the dropped data
            info (`int`): info on the target
            time (`int`): time of the drop
        """
        uri_parts = urlsplit(data.get_text())
        path = pathlib.Path(url2pathname(uri_parts.path) if uri_parts.scheme else uri_parts.path)

        if path.is_file() and path.suffix.lower() == '.pdf':
            self.swap_document(path.as_uri())


    def unsaved_changes(self, reload=False):
        """ Prompt the user about what to do with changes in the document: save, discard, or cancel action

        Args:
            reload (`bool`): The unsaved changes is prompted by reloading the file

        Returns:
            `bool`: `True` iff we need to cancel the current action
        """
        if not self.doc.has_changes():
            return False

        dialog = Gtk.MessageDialog(title=_('Unsaved changes'), transient_for=self.p_win, type=Gtk.MessageType.WARNING)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        if not reload:
            dialog.set_markup(_('Save changes before closing?'))
            dialog.format_secondary_markup(_('Unsaved changes will be lost'))

            dialog.add_button(Gtk.STOCK_SAVE, Gtk.ResponseType.YES)
            dialog.add_button(_('_Discard'), Gtk.ResponseType.NO).set_image(
                Gtk.Button.new_from_icon_name('edit-delete', Gtk.IconSize.BUTTON).get_image()
            )
            dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
            dialog.set_default_response(Gtk.ResponseType.YES)
        else:
            dialog.set_markup(_('The open file was modified outside of pympress but you have made unsaved changes.') +
                              '\n<b>' + _('Overwrite changes instead of reloading?') + '</b>')
            dialog.format_secondary_markup(_('Saving changes will overwrite the changed file!') + '\n' +
                                           _('Unsaved changes will be lost.'))

            dialog.add_button(_('Overwrite'), Gtk.ResponseType.YES).set_image(
                Gtk.Button.new_from_icon_name('document-save', Gtk.IconSize.BUTTON).get_image()
            )
            dialog.add_button(_('Reload'), Gtk.ResponseType.NO).set_image(
                Gtk.Button.new_from_icon_name('view-refresh', Gtk.IconSize.BUTTON).get_image()
            )
            dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
            dialog.set_default_response(Gtk.ResponseType.YES)

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.doc.save_changes()

        return response == Gtk.ResponseType.CANCEL or (reload and Gtk.ResponseType == Gtk.ResponseType.YES)


    def save_file_as(self, *args):
        """ Remove the current document.
        """
        # Use a GTK file dialog to choose file
        dialog = Gtk.FileChooserDialog(title = _('Save as...'), transient_for = self.p_win,
                                       action = Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(Gtk.STOCK_SAVE_AS, Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        file_filter = Gtk.FileFilter()
        file_filter.set_name(_('PDF files'))
        file_filter.add_mime_type('application/pdf')
        file_filter.add_pattern('*.pdf')
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.set_name(_('All files'))
        file_filter.add_pattern('*')
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.doc.save_changes(dialog.get_uri())

        dialog.destroy()


    def pick_file(self, *args):
        """ Ask the user which file he means to open.
        """
        # Use a GTK file dialog to choose file
        dialog = Gtk.FileChooserDialog(title = _('Open...'), transient_for = self.p_win,
                                       action = Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        file_filter = Gtk.FileFilter()
        file_filter.set_name(_('PDF files'))
        file_filter.add_mime_type('application/pdf')
        file_filter.add_pattern('*.pdf')
        dialog.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.set_name(_('All files'))
        file_filter.add_pattern('*')
        dialog.add_filter(file_filter)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.swap_document(dialog.get_uri())

        dialog.destroy()


    def error_opening_file(self, uri):
        """ Remove the current document.

        Args:
            uri (`str`): the URI of the document
        """
        # Check if the path is valid
        uri_parts = urlsplit(uri)
        filename = pathlib.Path(url2pathname(uri_parts.path))
        if uri_parts.scheme == 'file' and not filename.exists():
            msg = _('Could not find the file "{}"').format(filename)
        else:
            msg = _('Error opening the file "{}"').format(uri)
        dialog = Gtk.MessageDialog(transient_for=self.p_win, flags=Gtk.DialogFlags.MODAL,
                                   message_type=Gtk.MessageType.ERROR, message_format=msg)
        dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.run()
        dialog.destroy()


    def close_file(self, *args):
        """ Remove the current document.
        """
        self.swap_document(None)


    def save_file(self, *args):
        """ Remove the current document.
        """
        self.doc.save_changes()


    def open_file(self, gaction, target):
        """ Open a document.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target (:class:`~GLib.Variant`): the file to open as a string variant
        """
        self.swap_document(target.get_string())


    def get_notes_mode(self):
        """ Simple getter.

        Returns:
             :class:`~pympress.document.PdfPage`: Truthy when we split slides in content + notes
        """
        return self.notes_mode


    ##############################################################################
    ############################  Displaying content  ############################
    ##############################################################################

    def on_page_change(self, widget, event=None):
        """ Signal handler for current page editing.

        Args:
            widget (:class:`~Gtk.Widget`):  the editable widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.
        """
        widget_text = widget.get_buffer().get_text()
        try:
            display_page_num = int(widget_text)
        except ValueError:
            return
        else:
            self.goto_page(display_page_num - 1)


    def goto_page(self, page, autoplay=False):
        """ Handle going to the page passed as argument

        Args:
            page (`int`): the page to which to go. Will be clipped to document pages.
            autoplay (`bool`): whether this page change was triggered automatically
        """
        self.preview_page = self.doc.goto(page)

        if not self.page_number.editing:
            self.current_page = self.preview_page

        self.do_page_change(autoplay=autoplay)


    def doc_goto_prev(self, gaction=None, param=None):
        """ Handle going to the next page.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        self.goto_page(self.preview_page - 1)


    def doc_goto_next(self, gaction=None, param=None):
        """ Handle going to the previous page.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        if not self.page_number.editing and self.talk_time.paused:
            self.talk_time.unpause()
        else:
            self.goto_page(self.preview_page + 1)


    def doc_label_next(self, gaction=None, param=None):
        """ Handle going to the next page with a different label.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        self.goto_page(self.doc.label_after(self.preview_page))


    def doc_label_prev(self, gaction=None, param=None):
        """ Handle going to the previous page with a different label.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        self.goto_page(self.doc.label_before(self.preview_page))


    def doc_hist_prev(self, gaction=None, param=None):
        """ Handle going to the previous page in the history of visited pages

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        dest = self.doc.hist_prev()
        if dest is not None:
            self.goto_page(dest)


    def doc_hist_next(self, gaction=None, param=None):
        """ Handle going to the next page in the history of visited pages

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        dest = self.doc.hist_next()
        if dest is not None:
            self.goto_page(dest)


    def doc_goto_home(self, gaction=None, param=None):
        """ Handle going to the start of the document

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        self.goto_page(0)


    def doc_goto_end(self, gaction=None, param=None):
        """ Handle going to the end of the document

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        self.goto_page(self.doc.pages_number())


    def do_page_change(self, unpause=True, autoplay=False):
        """ Switch to another page and display it.

        This is a kind of event which is supposed to be called only from the
        :class:`~pympress.document.Document` class.

        Args:
            is_preview (`bool`):  `True` if the page change should not update the content
            unpause (`bool`):  `True` if the page change should unpause the timer, `False` otherwise
            autoplay (`bool`):  `True` if the page change is triggered automatically, otherwise cancel auto play
        """
        is_preview = self.page_number.editing
        if not is_preview:
            self.preview_page = self.current_page
            self.app.set_action_state('page', self.current_page + 1)

        draw_notes = self.notes_mode
        draw_page = draw_notes.complement()

        page_content = self.doc.page(self.current_page)
        page_preview = self.doc.page(self.preview_page)
        pages_next = [self.doc.page(self.preview_page + n + 1) for n in range(self.next_frames_count)]
        page_notes = self.doc.notes_page(self.preview_page)

        # Aspect ratios and queue redraws
        if draw_notes and page_notes is not None:
            note_pr = page_notes.get_aspect_ratio(draw_notes)
            self.p_frame_notes.set_property('ratio', note_pr)
        self.p_da_notes.queue_draw()

        preview_pr = page_preview.get_aspect_ratio(draw_page)

        self.p_frame_cur.set_property('ratio', preview_pr)
        self.p_da_cur.queue_draw()

        if not is_preview:
            content_pr = page_content.get_aspect_ratio(draw_page)
            self.c_frame.set_property('ratio', content_pr)
            self.c_da.queue_draw()

            self.scribbler.scribble_p_frame.set_property('ratio', content_pr)
            self.scribbler.scribble_p_frame.queue_draw()

        next_pr = preview_pr  # A default page ratio
        for page, frame, da in zip(pages_next, self.p_frames_next, self.p_das_next):
            if page is not None:
                next_pr = page.get_aspect_ratio(draw_page)
            frame.set_property('ratio', next_pr)
            da.queue_draw()

        self.annotations.load_annotations(page_preview)

        # Update display -- needs to be different ?
        self.page_number.update_page_numbers(self.preview_page, page_preview.label())

        # Prerender the 4 next pages and the 2 previous ones
        page_max = min(self.doc.pages_number(), self.preview_page + self.next_frames_count + 4)
        page_min = max(0, self.preview_page - 2)
        for p in list(range(self.preview_page + 1, page_max)) + list(range(self.preview_page, page_min, -1)):
            self.cache.prerender(p)

        if is_preview:
            return

        # Remove scribbles and scribbling/zooming modes
        if self.scribbler.page_change_exits:
            self.scribbler.disable_scribbling()
        self.scribbler.page_change(self.preview_page, page_preview.label())
        self.zoom.stop_zooming()

        # Update medias
        self.medias.replace_media_overlays(self.doc.page(self.current_page), draw_page)

        # Start counter if needed
        if unpause:
            self.talk_time.unpause()
        if not autoplay:
            self.autoplay.stop_looping()

        self.timing.transition(self.preview_page, self.talk_time.current_time())


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
            page = self.doc.page(self.current_page)
        elif widget is self.p_da_cur or widget is self.scribbler.scribble_p_da:
            # Current page 'preview'
            page = self.doc.page(self.preview_page)
        elif widget is self.p_da_notes:
            # Notes page, aligned with preview
            page = self.doc.notes_page(self.preview_page)
        elif widget in self.p_das_next:
            offset = 1 + int(widget.get_name()[len('p_da_next'):])
            page = self.doc.page(self.preview_page + offset)
            # No next page: just return so we won't draw anything
            if page is None:
                return
        else:
            logger.warning(_('Unknown widget "{}" to draw'.format(widget.get_name())))

        if page is None:
            if widget is not self.p_da_notes or self.notes_mode.direction() != 'page mapping':
                logger.warning(_('Unexpected missing page to draw for widget "{}"'.format(widget.get_name())))
            return

        if not page.can_render():
            return

        name = widget.get_name().rstrip('0123456789')
        nb = page.number()  # Use PDF page numbering for the cache
        wtype = self.cache.get_widget_type(name)
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        window = widget.get_window()
        scale = window.get_scale_factor()

        if self.zoom.scale != 1. and (widget is self.p_da_cur or widget is self.c_da or
                                      widget is self.scribbler.scribble_p_da):
            zoom_matrix = self.zoom.get_matrix(ww, wh)
            name += '_zoomed'
        else:
            zoom_matrix = cairo.Matrix()

        pb = self.cache.get(name, nb)
        if pb is None:
            if self.resize_panes and widget in self.p_das_next + [self.p_da_cur, self.p_da_notes]:
                # too slow to render here when resize_panes things
                return

            # Cache miss: render the page, and save it to the cache
            try:
                pb = window.create_similar_image_surface(cairo.Format.RGB24, ww * scale, wh * scale, scale)
            except cairo.Error:
                logger.warning('Failed creating an RGB24 surface sized {}x{} scale {} for widget {}'
                               .format(ww * scale, wh * scale, scale, name), exc_info=True)
                if widget is self.c_da:
                    cairo_context.save()
                    cairo_context.set_source_rgb(0, 0, 0)
                    cairo_context.fill()
                    cairo_context.paint()
                    cairo_context.restore()
                return

            cairo_prerender = cairo.Context(pb)
            cairo_prerender.transform(zoom_matrix)
            page.render_cairo(cairo_prerender, ww, wh, wtype)

            self.cache.put(name, nb, pb)

            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()
        else:
            # Cache hit: draw the surface from the cache to the widget
            cairo_context.set_source_surface(pb, 0, 0)
            cairo_context.paint()

        if widget is self.c_da or widget is self.p_da_cur or widget is self.scribbler.scribble_p_da:
            cairo_context.save()
            cairo_context.transform(zoom_matrix)

            self.scribbler.draw_scribble(widget, cairo_context)
            self.zoom.draw_zoom_target(widget, cairo_context)

            cairo_context.restore()

        if widget is self.c_da or widget is self.p_da_cur or widget is self.scribbler.scribble_p_da:
            # do not use the zoom matrix for the pointer, it is relative to the screen not the slide
            self.laser.render_pointer(cairo_context, ww, wh)


    def clear_zoom_cache(self):
        """ Callback to clear the cache of zoomed widgets.
        """
        self.cache.clear_cache(self.c_da.get_name() + '_zoomed')
        self.cache.clear_cache(self.p_da_cur.get_name() + '_zoomed')
        self.cache.clear_cache(self.scribbler.scribble_p_da.get_name() + '_zoomed')


    def redraw_current_slide(self):
        """ Callback to queue a redraw of the current slides (in both winows).
        """
        self.c_da.queue_draw()
        self.p_da_cur.queue_draw()
        self.scribbler.scribble_p_da.queue_draw()


    ##############################################################################
    ############################     User inputs      ############################
    ##############################################################################

    def validate_current_input(self, gaction, param=None):
        """ Handle the action validating the input, if applicable.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        if self.page_number.try_validate():
            return True
        elif self.est_time.try_validate():
            return True

        return False


    def on_key_input(self, widget, event):
        """ Handle key strokes at top level, only for when editing needs to bypass action accelerators

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the key stroke
            event (:class:`~Gdk.Event`):  the GTK event, which contains the key stroke details
        """
        if self.annotations.key_event(widget, event):
            return True
        elif self.scribbler.key_event(widget, event):
            return True

        return False


    def cancel_current_input(self, gaction, param=None):
        """ Handle the action cancelling the input, if applicable.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        if self.page_number.try_cancel():
            return True
        elif self.est_time.try_cancel():
            return True
        elif self.zoom.try_cancel():
            return True
        elif self.scribbler.try_cancel():
            return True
        elif self.deck.try_cancel():
            return True
        elif self.annotations.try_cancel():
            return True
        elif self.autoplay.stop_looping():
            return True

        return False


    def on_scroll(self, widget, event):
        """ Manage scroll events.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred (ignored)
            event (:class:`~Gdk.Event`):  the event that occurred

        Returns:
            `bool`: whether the event was consumed
        """
        if event.type != Gdk.EventType.SCROLL:
            return False

        # send to spinner if it is active
        elif self.page_number.on_scroll(widget, event):
            return True
        else:
            return False


    def track_motions(self, widget, event):
        """ Track mouse motion events.

        Handles mouse motions on the "about" menu.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget that received the mouse motion
            event (:class:`~Gdk.Event`):  the GTK event containing the mouse position

        Returns:
            `bool`: whether the event was consumed
        """
        if self.zoom.track_zoom_target(widget, event):
            return True
        elif self.scribbler.track_scribble(widget, event):
            return True
        elif self.laser.track_pointer(widget, event):
            return True
        else:
            return self.hover_link(widget, event)


    def track_clicks(self, widget, event):
        """ Track mouse press and release events.

        Handles clicks on the slides.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget that received the click
            event (:class:`~Gdk.Event`):  the GTK event containing the click position

        Returns:
            `bool`: whether the event was consumed
        """
        if self.zoom.toggle_zoom_target(widget, event):
            return True
        elif self.scribbler.toggle_scribble(widget, event):
            return True
        elif self.laser.toggle_pointer(widget, event):
            return True
        else:
            return self.click_link(widget, event)


    def click_link(self, widget, event):
        """ Check whether a link was clicked and follow it.

        Handles a click on a slide.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred
            event (:class:`~Gdk.Event`):  the event that occurred

        Returns:
            `bool`: whether the event was consumed
        """
        if event.type == Gdk.EventType.BUTTON_RELEASE:
            return False

        # Where did the event occur?
        if widget in self.p_das_next:
            offset = 1 + int(widget.get_name()[len('p_da_next'):])
            page = self.doc.page(self.preview_page + offset)
        elif widget is self.p_da_notes:
            page = self.doc.notes_page(self.preview_page)
        elif widget is self.p_da_cur:
            page = self.doc.page(self.preview_page)
        else:
            page = self.doc.page(self.current_page)

        if page is None:
            return False

        x, y = self.zoom.get_slide_point(widget, event)
        page_mode = self.notes_mode if widget is self.p_da_notes else self.notes_mode.complement()

        link = page.get_link_at(x, y, page_mode)

        if event.type == Gdk.EventType.BUTTON_PRESS and link is not None:
            link.follow()
            return True
        else:
            return False


    def hover_link(self, widget, event):
        """ Manage events related to hyperlinks, setting the cursor to a pointer if the hovered region is clickable.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred
            event (:class:`~Gdk.Event`):  the event that occurred

        Returns:
            `bool`: whether the event was consumed
        """
        if event.type != Gdk.EventType.MOTION_NOTIFY:
            return False

        # Where did the event occur?
        if widget in self.p_das_next:
            offset = 1 + int(widget.get_name()[len('p_da_next'):])
            page = self.doc.page(self.preview_page + offset)
        elif widget is self.p_da_notes:
            page = self.doc.notes_page(self.preview_page)
        elif widget is self.p_da_cur:
            page = self.doc.page(self.preview_page)
        else:
            page = self.doc.page(self.current_page)

        if page is None:
            return False

        x, y = self.zoom.get_slide_point(widget, event)
        page_mode = self.notes_mode if widget is self.p_da_notes else self.notes_mode.complement()

        if page.get_link_at(x, y, page_mode):
            extras.Cursor.set_cursor(widget, 'pointer')
            return False
        else:
            extras.Cursor.set_cursor(widget, 'parent')
            return True


    def switch_fullscreen(self, gaction, target):
        """ Switch the Content window to fullscreen (if in normal mode) or to normal mode (if fullscreen).

        Screensaver will be disabled when entering fullscreen mode, and enabled
        when leaving fullscreen mode.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget in which the event occurred

        Returns:
            `bool`: whether some window's full screen status got toggled
        """
        if gaction.get_name() == 'content-fullscreen':
            widget = self.c_win
        elif gaction.get_name() == 'presenter-fullscreen':
            widget = self.p_win
        else:
            raise ValueError('Do not know which widget to put full screen')

        if widget != self.c_win and widget != self.p_win:
            logger.error(_("Unknow widget {} to be fullscreened, aborting.").format(widget))
            return False

        toggle_to = not gaction.get_state().get_boolean()
        window = widget.get_window()
        cur_state = (window.get_state() & Gdk.WindowState.FULLSCREEN) if window is not None else False

        if cur_state:
            widget.unfullscreen()
        else:
            widget.fullscreen()

        if gaction.get_name() == 'content-fullscreen':
            self.set_screensaver(disabled=toggle_to)

        gaction.change_state(GLib.Variant.new_boolean(toggle_to))
        return True


    def set_screensaver(self, disabled):
        """ Disable or re-enable the screensaver.

        Args:
            disabled (`bool`): `True` iff the screensaver should be disabled, otherwise enabled.
        """
        if not disabled:
            if self.inhibit_cookie:
                self.app.uninhibit(self.inhibit_cookie)
            elif self.inhibit_cookie is not None:
                util.hard_set_screensaver(disabled=False)
            self.inhibit_cookie = None

        else:
            flags = (Gtk.ApplicationInhibitFlags.LOGOUT | Gtk.ApplicationInhibitFlags.SWITCH |
                     Gtk.ApplicationInhibitFlags.SUSPEND | Gtk.ApplicationInhibitFlags.IDLE)

            self.inhibit_cookie = self.app.inhibit(self.c_win, flags, _("Fullscreen Presentation running"))

            if not self.inhibit_cookie:
                logger.warning(_('Gtk.Application.inhibit failed preventing screensaver, trying hard disabling'))
                util.hard_set_screensaver(disabled=True)


    def update_frame_position(self, widget, user_data):
        """ Callback to preview the frame alignment, called from the Gtk.SpinButton.

        Args:
            widget (:class:`~Gtk.SpinButton`): The button updating the slide alignment in the drawing area widget
            user_data (`str`): The property being set, either the x or y alignment (resp. xalign and yalign).
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
        button.set_adjustment(Gtk.Adjustment(lower=0.0, upper=1.0, step_increment=0.01))
        button.set_digits(2)
        button.set_value(val)
        button.connect("value-changed", self.update_frame_position, prop)

        popup = Gtk.Dialog(title = _("Adjust alignment of slides in projector screen"), transient_for = self.p_win)
        popup.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

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
        display = Gdk.Display.get_default()
        try:
            c_monitor, p_monitor, primary, non_primary = util.Monitor.lookup_monitors(display, self.c_win, self.p_win)
        except util.NoMonitorPositions:
            return

        if primary.equal(non_primary) == 1 or p_monitor.equal(c_monitor):
            return

        logger.debug('Swapping screens:')
        self.move_window(self.c_win, c_monitor, p_monitor)
        self.move_window(self.p_win, p_monitor, c_monitor)


    def switch_blanked(self, gaction, param):
        """ Switch the blanked mode of the content screen.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None

        Returns:
            `bool`: whether the notes blanking has been toggled.
        """
        self.blanked = not self.blanked
        self.c_da.queue_draw()
        gaction.change_state(GLib.Variant.new_boolean(self.blanked))

        return True


    def layout_name(self, notes_mode):
        """ Return the layout made for the selected notes_mode

        Args:
            notes_mode (:class:`~pympress.document.PdfPage`): the mode/positioning of notes

        Returns:
            `str`: a string representing the appropriate layout
        """
        if self.scribbler.scribbling_mode:
            return 'highlight'
        elif self.deck.deck_mode:
            return 'deck'
        elif notes_mode.direction() == 'page number':
            return 'note_pages'
        elif notes_mode:
            return 'notes'
        else:
            return 'plain'


    def load_layout(self, new):
        """ Replace the current layout

        Args:
            new (`str`): the name of the layout to load, `None` to use current layout automatically
        """
        if new is None:
            new = self.layout_name(self.notes_mode)
        else:
            self.layout_editor.set_current_layout(new)

        pane_handles = self.replace_layout(self.config.get_layout(new), self.p_central,
                                           self.placeable_widgets, self.on_pane_event)
        self.scribbler.adjust_tools_orientation()
        self.pane_handle_pos.update(pane_handles)

        # queue visibility of all newly added widgets, make sure visibility is right
        self.p_central.show_all()
        self.p_frame_annot.set_visible(self.show_annotations)


    def change_notes_pos(self, gaction, target, force=False):
        """ Switch the position of the nodes in the slide.

        Returns:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target (:class:`~GLib.Variant`): the notes position as a string variant
            force (`bool`): Whether to force the notes switch even if it’s already enabled

        Returns:
            `bool`: whether the notes position has been toggled
        """
        target_mode = document.PdfPage[target.get_string().upper()]

        # Redundant toggle, do nothing
        if target_mode == self.chosen_notes_mode:
            return False

        # Update the choice, except for NONE or BEFORE/AFTER or EVEN/ODD
        if target_mode:
            self.chosen_notes_mode = target_mode
            gaction.change_state(target)
            self.config.set('notes position', target_mode.direction(), target_mode.name.lower())

        # Change the notes arrangement if they are enabled or if we are forced to
        if self.notes_mode or force:
            self.switch_mode(self.app.lookup_action('notes-mode'), target_mode=target_mode, force=True)

        return True


    def switch_mode(self, gaction, target_mode=None, force=False):
        """ Switch the display mode to "Notes mode" or "Normal mode" (without notes).

        Returns:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target_mode (:class:`~pympress.document.PdfPage`): the mode to which we should switch
            force (`bool`): Whether to force the mode switch even if it’s already enabled

        Returns:
            `bool`: whether the notes mode has been toggled
        """
        if target_mode is None:
            target_mode = document.PdfPage.NONE if self.notes_mode else self.chosen_notes_mode

        if target_mode == self.notes_mode and not force:
            return False

        self.scribbler.disable_scribbling()
        self.doc.set_notes_pos(target_mode.direction())

        self.load_layout(self.layout_name(target_mode))

        # Transform or clip page number appropriately
        renumber_page = (target_mode.direction() == 'page parity') - (self.notes_mode.direction() == 'page parity')
        if renumber_page < 0:
            self.preview_page *= 2
            self.current_page *= 2
        elif renumber_page > 0:
            self.preview_page //= 2
            self.current_page //= 2
        elif target_mode.direction() == 'page number':
            self.preview_page = min(self.preview_page, self.doc.pages_number())
            self.current_page = min(self.current_page, self.doc.pages_number())

        self.notes_mode = target_mode
        page_type = self.notes_mode.complement()

        self.cache.set_widget_type('c_da', page_type)
        self.cache.set_widget_type('c_da_zoomed', page_type)
        self.cache.set_widget_type('p_da_next', page_type)
        self.cache.set_widget_type('p_da_cur', page_type)
        self.cache.set_widget_type('p_da_cur_zoomed', page_type)
        self.cache.set_widget_type('scribble_p_da', page_type)
        self.cache.set_widget_type('p_da_notes', self.notes_mode)

        if self.notes_mode:
            self.cache.enable_prerender('p_da_notes')
            self.cache.disable_prerender('p_da_cur')
        else:
            self.cache.disable_prerender('p_da_notes')
            self.cache.enable_prerender('p_da_cur')

        self.medias.adjust_margins_for_mode(page_type)
        self.do_page_change(unpause=False)
        self.page_number.set_last(self.doc.pages_number())
        self.app.set_action_state('notes-mode', bool(self.notes_mode))

        return True


    def switch_annotations(self, gaction, target):
        """ Switch the display to show annotations or to hide them.

        Returns:
            gaction (:class:`~Gio.Action`): the action triggering the call
            target (:class:`~GLib.Variant`): the parameter as a variant, or None

        Returns:
            `bool`: whether the mode has been toggled.
        """
        self.show_annotations = not self.show_annotations

        self.p_frame_annot.set_visible(self.show_annotations)
        self.config.set('presenter', 'show_annotations', 'on' if self.show_annotations else 'off')

        if self.show_annotations:
            parent = self.p_frame_annot.get_parent()
            if issubclass(type(parent), Gtk.Paned):
                if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                    size = parent.get_allocated_width()
                else:
                    size = parent.get_allocated_height()
                parent.set_position(self.pane_handle_pos[parent] * size)

        GLib.idle_add(self.redraw_panes)

        self.annotations.load_annotations(self.doc.page(self.preview_page))
        gaction.change_state(GLib.Variant.new_boolean(self.show_annotations))

        return True


    def switch_bigbuttons(self, *args):
        """ Toggle the display of big buttons (nice for touch screens).
        """
        self.show_bigbuttons = not self.show_bigbuttons
        if self.show_bigbuttons:
            # potentially reduce font
            self.adjust_bottom_bar_font()

        self.prev_button.set_visible(self.show_bigbuttons)
        self.next_button.set_visible(self.show_bigbuttons)
        self.laser_button.set_visible(self.show_bigbuttons)
        self.highlight_button.set_visible(self.show_bigbuttons)

        if not self.show_bigbuttons:
            # potentially increase font
            self.adjust_bottom_bar_font()

        self.config.set('presenter', 'show_bigbuttons', 'on' if self.show_bigbuttons else 'off')
        self.app.set_action_state('big-buttons', self.show_bigbuttons)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
