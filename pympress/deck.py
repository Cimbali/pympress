# -*- coding: utf-8 -*-
#
#       deck.py
#
#       Copyright 2023 Cimbali <me@cimba.li>
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
:mod:`pympress.deck` -- Manage user drawings on the current slide
---------------------------------------------------------------------
"""

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from pympress import builder


class Overview(builder.Builder):
    """ UI that allows to draw free-hand on top of the current slide.

    Args:
        config (:class:`~pympress.config.Config`): A config object containing preferences
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        notes_mode (`bool`): The current notes mode, i.e. whether we display the notes on second slide
    """
    #: Whether we are displaying the deck overview on screen
    deck_mode = False

    #: :class:`~Gtk.Viewport` that replaces normal panes when deck is shown
    deck_viewport = None
    #: :class:`~Gtk.Grid` that displays all the slides of the overview
    deck_grid = None
    #: The :class:`~Gtk.DrawingArea` for the first slide
    deck0 = None

    #: A :class:`~Gtk.OffscreenWindow` where we render the deck interface when it's not shown
    deck_off_render = None
    #: :class:`~Gtk.Box` in the Presenter window, where we insert deck.
    p_central = None

    #: callback, to be connected to :func:`~pympress.ui.UI.compute_frame_grid`
    compute_frame_grid = lambda *args: None

    #: callback, to be connected to :func:`~pympress.ui.UI.load_layout`
    load_layout = lambda *args: None

    #: callback, to be connected to :func:`~pympress.surfacecache.SurfaceCache.resize_widget`
    resize_cache = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.goto_page`
    goto_page = lambda *args: None
    #: :class:`~pympress.surfacecache.SurfaceCache` instance.
    cache = None

    #: `tuple` of rows/columns in the grid
    grid_size = (0, 0)
    #: `bool` whether we show all pages or remove consecutive identically labeled pages, keeping only the last
    all_pages = False
    #: `int` How large (at most) to make rows
    max_row_size = 6

    #: The :class:`~Gtk.DrawingArea` in the content window
    c_da = None

    def __init__(self, config, builder, notes_mode):
        super(Overview, self).__init__()

        self.cache = builder.cache
        self.load_ui('deck')
        builder.load_widgets(self)
        self.deck_da_list = [self.deck0]
        self.get_application().add_window(self.deck_off_render)

        self.load_layout = builder.get_callback_handler('load_layout')
        self.goto_page = builder.get_callback_handler('goto_page')
        self.compute_frame_grid = builder.get_callback_handler('compute_frame_grid')
        self.setup_doc_callbacks(builder.doc)

        self.connect_signals(self)

        self.max_row_size = config.getint('deck-overview', 'max-slides-per-row')
        # Whether to show all pages or only distinctly labeled pages (useful for latex)
        self.all_pages = not config.get('deck-overview', 'distinct-labels-only')

        self.setup_actions({
            'deck-overview': dict(activate=self.switch_deck_overview, state=False),
        })


    def on_deck_hover(self, widget, event):
        """ Track when each deck in the slide is hovered
        """
        ctx = widget.get_style_context()
        ctx.set_state(Gtk.StateFlags.PRELIGHT if event.type == Gdk.EventType.ENTER_NOTIFY else Gtk.StateFlags.NORMAL)
        widget.queue_draw()


    def setup_doc_callbacks(self, doc):
        """ Callbacks that need to be setup again at every new document

        Args:
            doc (:class:`~pympress.document.Document`): The new document that got loaded
        """
        self.pages_number         = doc.pages_number
        self.has_labels           = doc.has_labels
        self.get_last_label_pages = doc.get_last_label_pages

        self.create_drawing_areas()


    def try_cancel(self):
        """ Cancel deck, if it is enabled.

        Returns:
            `bool`: `True` if deck got cancelled, `False` if it was already disabled.
        """
        if not self.deck_mode:
            return False

        self.disable_deck_overview()
        return True


    def create_drawing_areas(self):
        """ Build DrawingArea and AspectFrame elements to display later on
        """
        pages = self.get_last_label_pages() if self.has_labels() else range(self.pages_number())
        self.grid_size = (len(pages), 1)

        # Always keep the first drawing area as it is used to provide surfaces in the cache
        for row in range(1, self.grid_size[0]):
            self.deck_grid.remove_row(row)
        for col in range(1, self.grid_size[1]):
            self.deck_grid.remove_row(col)

        # Set drawing areas
        for num, da in enumerate(self.deck_da_list[1:], 1):
            self.deck_grid.attach(da.get_parent(), 1, num, 1, 1)

        for num in range(len(self.deck_da_list), len(pages)):
            da = Gtk.DrawingArea()
            da.add_events(Gdk.EventMask.TOUCH_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK |
                          Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
            da.connect('draw', self.on_deck_draw)
            da.connect('button-release-event', self.on_deck_click)
            da.connect('touch-event', self.on_deck_click)
            da.connect('enter-notify-event', self.on_deck_hover)
            da.connect('leave-notify-event', self.on_deck_hover)
            self.deck_da_list.append(da)

            frame = Gtk.AspectFrame()
            frame.get_style_context().add_class('grid-frame')
            frame.set_shadow_type(Gtk.ShadowType.NONE)
            frame.add(da)

            self.deck_grid.attach(frame, 1, num, 1, 1)

        ratio = self.c_da.get_allocated_width() / self.c_da.get_allocated_height()
        for page, da in zip(pages, self.deck_da_list):
            da.get_parent().set(.5, .5, ratio, False)
            da.set_name('deck{}'.format(page))


    def reset_grid(self, *args):
        """ Set the slides configuration and size in the grid
        """
        # Gather info about slides to display
        num_pages = self.pages_number() if self.all_pages or not self.has_labels() else len(self.get_last_label_pages())
        ratio = self.c_da.get_allocated_width() / self.c_da.get_allocated_height()

        ww, wh = self.deck_grid.get_allocated_width(), self.deck_grid.get_allocated_height()
        sw, sh = self.deck_grid.get_row_spacing(), self.deck_grid.get_column_spacing()
        rows, cols = self.compute_frame_grid(ww / wh, num_pages)
        window = self.deck_viewport.get_window()
        scale = window.get_scale_factor()

        if not rows or not cols:
            rows, cols = 1, 1

        dw, dh = (ww + sw) / cols - sw, (wh + sh) / rows - sh
        dw, dh = min(dw, dh * ratio), min(dw / ratio, dh)

        if cols > self.max_row_size:
            cols = self.max_row_size
            rows = (num_pages + cols - 1) // cols

            dw = (ww + sw) / cols - sw
            dh = dw / ratio

        self.cache.resize_widget('deck', int(dw * scale), int(dh * scale))

        frames = [da.get_parent() for da in self.deck_da_list]
        for frame in frames:
            frame.set(.5, .5, ratio, False)
            frame.set_size_request(dw / scale, dh / scale)

        if self.grid_size != (rows, cols):
            for frame in frames[1:]:
                self.deck_grid.remove(frame)

            # Always keep the first drawing area as it is used to provide surfaces in the cache
            for row in range(rows, self.grid_size[0]):
                self.deck_grid.remove_row(row)
            for col in range(cols, self.grid_size[1]):
                self.deck_grid.remove_row(col)

            for num, frame in enumerate(frames[1:], 1):
                self.deck_grid.attach(frame, num % cols, num // cols, 1, 1)

            # resize grid and cache
            self.grid_size = rows, cols

        for da in self.deck_da_list:
            GLib.idle_add(self.prerender, da)

        self.deck_grid.show_all()


    def prerender(self, da):
        """ Perform in-cache rendering

        Args:
            da (:class:`~Gtk.DrawingArea`):  the widget for which we’re rendering
        """
        self.cache.renderer('deck', int(da.get_name()[4:]))
        da.queue_draw()
        return GLib.SOURCE_REMOVE


    def on_deck_draw(self, widget, cairo_context):
        """ Actually draw the deck slide -- only do this from cache, to limit overhead

        Args:
            widget (:class:`~Gtk.Widget`):  the widget to update
            cairo_context (:class:`~cairo.Context`):  the Cairo context (or `None` if called directly)
        """
        page_num = int(widget.get_name()[4:])
        pb = self.cache.get('deck', page_num)
        if pb is None:
            # We’ll redraw later
            widget.queue_draw()
            return

        window = widget.get_window()
        scale = window.get_scale_factor()
        cairo_context.scale(1. / scale, 1. / scale)
        cairo_context.set_source_surface(pb, 0, 0)
        cairo_context.paint()

        ctx = widget.get_style_context()
        if ctx.get_state() != Gtk.StateFlags.PRELIGHT:
            return

        # Draw a hover border manually
        color = ctx.get_property('border-color', Gtk.StateFlags.PRELIGHT)
        width = 2
        cairo_context.set_source_rgba(*color)
        cairo_context.set_line_width(width)

        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        cairo_context.move_to(width / 2, width / 2)
        cairo_context.line_to(width / 2, wh - width / 2)
        cairo_context.line_to(ww - width / 2, wh - width / 2)
        cairo_context.line_to(ww - width / 2, width / 2)
        cairo_context.close_path()
        cairo_context.stroke()


    def on_deck_click(self, widget, event):
        """ A slide has been clicked, go to it

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the key stroke
            event (:class:`~Gdk.Event`):  the GTK event, which contains the key stroke details
        """
        page_num = int(widget.get_name()[4:])
        self.goto_page(page_num, False)
        self.disable_deck_overview()


    def switch_deck_overview(self, gaction, target=None):
        """ Starts the mode where one can read on top of the screen.

        Args:

        Returns:
            `bool`: whether the event was consumed
        """
        if target is not None and target == self.deck_mode:
            return False

        # Perform the state toggle
        if self.deck_mode:
            return self.disable_deck_overview()
        else:
            return self.enable_deck_overview()


    def enable_deck_overview(self):
        """ Enable the deck view.

        Returns:
            `bool`: whether it was possible to enable (thus if it was not enabled already)
        """
        if self.deck_mode:
            return False

        self.deck_off_render.remove(self.deck_viewport)
        self.load_layout('deck-overview')

        self.p_central.queue_draw()
        self.deck_viewport.queue_draw()

        GLib.idle_add(self.reset_grid)

        self.deck_mode = True
        self.get_application().lookup_action('deck-overview').change_state(GLib.Variant.new_boolean(self.deck_mode))

        self.p_central.queue_draw()
        return True


    def disable_deck_overview(self):
        """ Disable the deck view.

        Returns:
            `bool`: whether it was possible to disable (thus if it was not disabled already)
        """
        if not self.deck_mode:
            return False

        self.deck_mode = False

        self.load_layout(None)
        self.deck_off_render.add(self.deck_viewport)

        self.get_application().lookup_action('deck-overview').change_state(GLib.Variant.new_boolean(self.deck_mode))

        self.p_central.queue_draw()
        return True
