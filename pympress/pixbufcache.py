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

import Queue
import threading
import time

import pygtk
pygtk.require('2.0')
import gtk

class PixbufCache:
    def __init__(self, doc):
        self.pixbuf_cache = {}
        self.pixbuf_size = {}
        self.locks = {}
        self.threads = {}
        self.jobs = {}
        self.doc = doc
        self.doc_lock = threading.Lock()

    def add_widget(self, widget_name):
        self.pixbuf_cache[widget_name] = {}
        self.pixbuf_size[widget_name] = (-1, -1)
        self.locks[widget_name] = threading.Lock()
        self.threads[widget_name] = threading.Thread(target=self.renderer, args=(widget_name,))
        self.threads[widget_name].daemon = True
        self.jobs[widget_name] = Queue.Queue(0)
        self.threads[widget_name].start()

    def resize_widget(self, widget_name, width, height):
        with self.locks[widget_name]:
            if (width, height) != self.pixbuf_size[widget_name]:
                self.pixbuf_cache[widget_name].clear()
                self.pixbuf_size[widget_name] = (width, height)

    def get(self, widget_name, page_nb):
        with self.locks[widget_name]:
            pc = self.pixbuf_cache[widget_name]
            if page_nb in pc:
                return pc[page_nb]
            else:
                return None

    def set(self, widget_name, page_nb, val):
        with self.locks[widget_name]:
            pc = self.pixbuf_cache[widget_name]
            pc[page_nb] = val

    def prerender(self, page_nb):
        for name in self.jobs:
            self.jobs[name].put(page_nb)

    def renderer(self, widget_name):
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
            with self.doc_lock:
                page = self.doc.page(page_nb)
                pw, ph = page.get_size()

            print "Prerendering page %d for widget %s" % (page_nb+1, widget_name)
            
            # Render
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, ww, wh)
            scale = min(ww/pw, wh/ph)
            page.render_pixbuf(pixbuf, ww, wh, scale)

            # Save if possible and necessary
            with self.locks[widget_name]:
                pc = self.pixbuf_cache[widget_name]
                if (ww, wh) == self.pixbuf_size[widget_name] and not page_nb in pc:
                    pc[page_nb] = pixbuf
