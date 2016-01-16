#       surfacecache.py
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
:mod:`pympress.surfacecache` -- pages prerendering and caching
--------------------------------------------------------------

This modules contains stuff needed for caching pages and prerendering them. This
is done by the :class:`~pympress.surfacecache.SurfaceCache` class, using several
dictionaries of :class:`cairo.ImageSurface` for storing rendered pages.

The problem is, neither Gtk+ nor Poppler are particularly threadsafe.
Hence the prerendering isn't really done in parallel in another thread, but
scheduled on the main thread at idle times using GLib.idle_add().
"""

import threading
import time
import collections

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib


class OrderedDict(collections.OrderedDict):
    """OrderedDict for python2 compatibility, adding move_to_end()."""

    def move_to_end(self, key):
        try:
            collections.OrderedDict.move_to_end(self, key)
        except AttributeError:
            val = self[key]
            del self[key]
            self[key] = val


class SurfaceCache:
    """Pages caching and prerendering made (almost) easy."""

    #: The actual cache. It is a dictionary of :class:`pympress.surfacecache.Cache`:
    #: its keys are widget names and its values are dictionaries whose keys are
    #: page numbers and values are instances of :class:`cairo.ImageSurface`.
    #: In each :class:`pympress.surfacecache.Cache` keys are ordered by Least Recently
    #: Used (get or set), when the size is beyond :attr:`max_pages`, pages are
    #: popped from the start of the cache.
    surface_cache = {}

    #: Size of the different managed widgets, as a dictionary of tuples
    surface_size = {}

    #: Type of document handled by each widget. It is a dictionary: its keys are
    #: widget names and its values are document types
    #: (:const:`~pympress.ui.PDF_REGULAR`, :const:`~pympress.ui.PDF_CONTENT_PAGE`
    #: or :const:`~pympress.ui.PDF_NOTES_PAGE`).
    surface_type = {}

    #: Dictionary of :class:`~threading.Lock`\ s used for managing conccurent
    #: accesses to :attr:`surface_cache`, :attr:`surface_size`, and :attr:`jobs`.
    locks = {}

    #: The current :class:`~pympress.document.Document`.
    doc = None

    #: :class:`~threading.Lock` used to manage conccurent accesses to
    #: :attr:`doc`.
    doc_lock = None

    #: maximum number fo pages we keep in cache
    max_pages = 200

    def __init__(self, doc, max_pages):
        """
        :param doc: the current document
        :type  doc: :class:`pympress.document.Document`
        """
        self.max_pages = max_pages
        self.doc = doc
        self.doc_lock = threading.Lock()

    def add_widget(self, widget_name, wtype):
        """
        Add a widget to the list of widgets that have to be managed (for caching
        and prerendering).

        This creates new entries for ``widget_name`` in the needed internal data
        structures, and creates a new thread for prerendering pages for this
        widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :param wtype: type of document handled by the widget (see :attr:`surface_type`)
        :type  wtype: integer
        """
        self.surface_cache[widget_name] = OrderedDict()
        self.surface_size[widget_name] = (-1, -1)
        self.surface_type[widget_name] = wtype
        self.locks[widget_name] = threading.Lock()

    def set_widget_type(self, widget_name, wtype):
        """
        Set the document type of a widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :param wtype: type of document handled by the widget (see :attr:`surface_type`)
        :type  wtype: integer
        """
        with self.locks[widget_name]:
            if self.surface_type[widget_name] != wtype :
                self.surface_type[widget_name] = wtype
                self.surface_cache[widget_name].clear()

    def get_widget_type(self, widget_name):
        """
        Get the document type of a widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :return: type of document handled by the widget (see :attr:`surface_type`)
        :rtype: integer
        """
        return self.surface_type[widget_name]

    def resize_widget(self, widget_name, width, height):
        """
        Change the size of a registered widget, thus invalidating all the cached pages.

        :param widget_name: name of the widget that is resized
        :type  widget_name: string
        :param width: new width of the widget
        :type  width: integer
        :param height: new height of the widget
        :type  height: integer
        """
        with self.locks[widget_name]:
            if (width, height) != self.surface_size[widget_name]:
                self.surface_cache[widget_name].clear()
                self.surface_size[widget_name] = (width, height)

    def get(self, widget_name, page_nb):
        """
        Fetch a cached, prerendered page for the specified widget.

        :param widget_name: name of the concerned widget
        :type  widget_name: string
        :param page_nb: number of the page to fetch in the cache
        :type  page_nb: integer
        :return: the cached page if available, or ``None`` otherwise
        :rtype: :class:`cairo.ImageSurface`
        """
        with self.locks[widget_name]:
            pc = self.surface_cache[widget_name]
            if page_nb in pc:
                pc.move_to_end(page_nb)
                return pc[page_nb]
            else:
                return None

    def set(self, widget_name, page_nb, val):
        """
        Store a rendered page in the cache.

        :param widget_name: name of the concerned widget
        :type  wdiget_name: string
        :param page_nb: number of the page to store in the cache
        :type  page_nb: integer
        :param val: content to store in the cache
        :type  val: :class:`cairo.ImageSurface`
        """
        with self.locks[widget_name]:
            pc = self.surface_cache[widget_name]
            pc[page_nb] = val
            pc.move_to_end(page_nb)

            while len(pc) > self.max_pages:
                pc.popitem(False)

    def prerender(self, page_nb):
        """
        Queue a page for prerendering.

        The specified page will be prerendered for all the registered widgets.

        :param page_nb: number of the page to be prerendered
        :type  page_nb: integer
        """
        for name in self.locks:
            GLib.idle_add(self.renderer, name, page_nb)

    def renderer(self, widget_name, page_nb):
        """
        Rendering thread.

        This function is meant to be run in the prerendering thread. It runs
        infinitely (until the program ends) and does the following steps:

        - check if the job's result is not already available in the cache
        - render it in a new :class:`~cairo.ImageSurface` if necessary
        - store it in the cache if it was not added there since the beginning of
          the process

        :param widget_name: name of the concerned widget
        :type  wdiget_name: string
        :param page_nb: number of the page to store in the cache
        :type  page_nb: integer
        """

        with self.locks[widget_name]:
            if page_nb in self.surface_cache[widget_name]:
                # Already in cache
                return False
            ww, wh = self.surface_size[widget_name]
            wtype = self.surface_type[widget_name]

        with self.doc_lock:
            page = self.doc.page(page_nb)
            pw, ph = page.get_size(wtype)

        # Render to a ImageSurface
        # 32 to support alpha (needed with premultiplied values?)
        # Anyway 24 uses 32-bit values with 8 unused
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, ww, wh)
        context = cairo.Context(surface)
        page.render_cairo(context, ww, wh, wtype)
        del context

        # Save if possible and necessary
        with self.locks[widget_name]:
            pc = self.surface_cache[widget_name]
            if (ww, wh) == self.surface_size[widget_name] and not page_nb in pc:
                pc[page_nb] = surface
                pc.move_to_end(page_nb)

            while len(pc) > self.max_pages:
                pc.popitem(False)

        return False

