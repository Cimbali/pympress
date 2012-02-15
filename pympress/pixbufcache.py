#       pixbufcache.py
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
:mod:`pympress.pixbufcache` -- pages prerendering and caching
-------------------------------------------------------------

This modules contains stuff needed for caching pages and prerendering them. This
is done by the :class:`~pympress.pixbufcache.PixbufCache` class, using several
dictionaries of :class:`gtk.gdk.Pixbuf` for storing rendered pages.

When used, the prerendering is done asynchronously in another thread.

.. warning:: The prerendering code is currently quite dumb and does exactly what
   it is told to do by the :class:`~pympress.ui.UI` class. So if told to eat all
   the memory by prerendering all the pages in a 1000+ pages PDF document, it
   *will* do so. A future version may however include some mechanism to limit
   the memory consumption. But for now, be careful with the size of your
   documents.
"""

import Queue
import threading
import time

import pygtk
pygtk.require('2.0')
import gtk

class PixbufCache:
    """Pages caching and prerendering made (almost) easy."""

    #: The actual cache. It is a dictionary of dictionaries: its keys are widget
    #: names and its values are dictionaries whose keys are page numbers and
    #: values are instances of :class:`gtk.gdk.Pixbuf`.
    pixbuf_cache = {}

    #: Size of the different managed widgets, as a dictionary of tuples
    pixbuf_size = {}

    #: Type of document handled by each widget. It is a dictionary: its keys are
    #: widget names and its values are document types
    #: (:const:`~pympress.ui.PDF_REGULAR`, :const:`~pympress.ui.PDF_CONTENT_PAGE`
    #: or :const:`~pympress.ui.PDF_NOTES_PAGE`).
    pixbuf_type = {}

    #: Dictionary of :class:`~threading.Lock`\ s used for managing conccurent
    #: accesses to :attr:`pixbuf_cache`, :attr:`pixbuf_size`, and :attr:`jobs`.
    locks = {}

    #: Dictionaries of the prerendering threads.
    threads = {}

    #: Dictionaries of :class:`~Queue.Queue`\ s used to store what has to
    #: be prerendered by each thread.
    jobs = {}

    #: The current :class:`~pympress.document.Document`.
    doc = None

    #: :class:`~threading.Lock` used to manage conccurent accesses to
    #: :attr:`doc`.
    doc_lock = None

    def __init__(self, doc):
        """
        :param doc: the current document
        :type  doc: :class:`pympress.document.Document`
        """
        self.doc = doc
        self.doc_lock = threading.Lock()

    def add_widget(self, widget_name, type):
        """
        Add a widget to the list of widgets that have to be managed (for caching
        and prerendering).

        This creates new entries for ``widget_name`` in the needed internal data
        structures, and creates a new thread for prerendering pages for this
        widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :param type: type of document handled by the widget (see :attr:`pixbuf_type`)
        :type  type: integer
        """
        self.pixbuf_cache[widget_name] = {}
        self.pixbuf_size[widget_name] = (-1, -1)
        self.pixbuf_type[widget_name] = type
        self.locks[widget_name] = threading.Lock()
        self.threads[widget_name] = threading.Thread(target=self.renderer, args=(widget_name,))
        self.threads[widget_name].daemon = True
        self.jobs[widget_name] = Queue.Queue(0)
        self.threads[widget_name].start()

    def set_widget_type(self, widget_name, type):
        """
        Set the document type of a widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :param type: type of document handled by the widget (see :attr:`pixbuf_type`)
        :type  type: integer
        """
        with self.locks[widget_name]:
            if self.pixbuf_type[widget_name] != type :
                self.pixbuf_type[widget_name] = type
                self.pixbuf_cache[widget_name].clear()

    def get_widget_type(self, widget_name):
        """
        Get the document type of a widget.

        :param widget_name: string used to identify a widget
        :type  widget_name: string
        :return: type of document handled by the widget (see :attr:`pixbuf_type`)
        :rtype: integer
        """
        return self.pixbuf_type[widget_name]

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
            if (width, height) != self.pixbuf_size[widget_name]:
                self.pixbuf_cache[widget_name].clear()
                self.pixbuf_size[widget_name] = (width, height)

    def get(self, widget_name, page_nb):
        """
        Fetch a cached, prerendered page for the specified widget.

        :param widget_name: name of the concerned widget
        :type  widget_name: string
        :param page_nb: number of the page to fetch in the cache
        :type  page_nb: integer
        :return: the cached page if available, or ``None`` otherwise
        :rtype: :class:`gtk.gdk.Pixbuf`
        """
        with self.locks[widget_name]:
            pc = self.pixbuf_cache[widget_name]
            if page_nb in pc:
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
        :type  val: :class:`gtk.gdk.Pixbuf`
        """
        with self.locks[widget_name]:
            pc = self.pixbuf_cache[widget_name]
            pc[page_nb] = val

    def prerender(self, page_nb):
        """
        Queue a page for prerendering.

        The specified page will be prerendered for all the registered widgets.

        :param page_nb: number of the page to be prerendered
        :type  page_nb: integer
        """
        for name in self.jobs:
            self.jobs[name].put(page_nb)

    def renderer(self, widget_name):
        """
        Rendering thread.

        This function is meant to be run in the various prerendering threads. It
        only uses safe ways to access attributes of the
        :class:`~pympress.pixbufcache.PixbufCache` class (i.e. synchronization
        with :class:`~threading.Lock`\ s). It runs infinitely (until the program
        ends) and does the following steps:

        - fetch the number of a page to render from the jobs
          :class:`~Queue.Queue`
        - check if it is not already available in the cache
        - render it in a new :class:`~gtk.gdk.Pixbuf` if necessary
        - store it in the cache if it was not added there since the beginning of
          the process

        .. note:: There is a big huge ``print`` in the middle of this function
           which is used to check if everything works fine. It will be removed
           from the code in the next release unless I forget to do it :)

        :param widget_name: name of the widget handled by this thread
        :type  widget_name: string
        """
        # Give the program some time to start
        time.sleep(5)

        while True:
            # Get something to do
            page_nb = self.jobs[widget_name].get()

            # So we have something to do. The main thread may have something to
            # do too: let it acquire this lock first.
            time.sleep(0.1)
            with self.locks[widget_name]:
                if page_nb in self.pixbuf_cache[widget_name]:
                    # Already in cache
                    continue
                ww, wh = self.pixbuf_size[widget_name]
                type = self.pixbuf_type[widget_name]
            with self.doc_lock:
                page = self.doc.page(page_nb)
                pw, ph = page.get_size(type)

            print "Prerendering page %d for widget %s type %d" % (page_nb+1, widget_name, type)

            with gtk.gdk.lock:
                # Render to a pixmap
                pixmap = gtk.gdk.Pixmap(None, ww, wh, 24) # FIXME: 24 or 32?
                cr = pixmap.cairo_create()
                page.render_cairo(cr, ww, wh, type)

                # Convert pixmap to pixbuf
                pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, ww, wh)
                pixbuf.get_from_drawable(pixmap, gtk.gdk.colormap_get_system(),
                                         0, 0, 0, 0, ww, wh)

            # Save if possible and necessary
            with self.locks[widget_name]:
                pc = self.pixbuf_cache[widget_name]
                if (ww, wh) == self.pixbuf_size[widget_name] and not page_nb in pc:
                    pc[page_nb] = pixbuf
