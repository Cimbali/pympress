#       widgetcache.py
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

import threading

import pygtk
pygtk.require('2.0')
import gtk

class PixbufCache:
    def __init__(self):
        self.pixbuf_cache = {}
        self.pixbuf_size = {}
        self.locks = {}

    def add_widget(self, widget_name):
        self.pixbuf_cache[widget_name] = {}
        self.pixbuf_size[widget_name] = (-1, -1)
        self.locks[widget_name] = threading.Lock()

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
