#!/usr/bin/env python
#
#       document.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
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

import gtk
import poppler

import pympress.content, pympress.presenter

class Document:
	def __init__(self, uri, page=0):
		# Open PDF file
		self.doc = poppler.document_new_from_file(uri, None)

		# Pages number
		self.nb_pages = self.doc.get_n_pages()

		# Open first two pages
		self.current, first, second = self.get_current_and_next(page)

		# Create windows
		self.presenter = pympress.presenter.Presenter(first, second, self.current, self.nb_pages, self.event_callback)
		self.content = pympress.content.Content(first, self.event_callback)

	def get_current_and_next(self, page):
		if page >= self.nb_pages:
			page = self.nb_pages-1
		elif page < 0:
			page = 0
		current = self.doc.get_page(page)

		next = None
		if page+1 < self.nb_pages:
			next = self.doc.get_page(page+1)

		return (page, current, next)

	def run(self):
		gtk.main()

	def next(self):
		page, current, next = self.get_current_and_next(self.current + 1)
		self.content.set_page(current)
		self.presenter.set_page(current, next, page)
		self.current = page

	def prev(self):
		page, current, next = self.get_current_and_next(self.current - 1)
		self.content.set_page(current)
		self.presenter.set_page(current, next, page)
		self.current = page

	def fullscreen(self):
		self.content.switch_fullscreen()

	def event_callback(self, widget, event):
		if event.type == gtk.gdk.KEY_PRESS:
			name = gtk.gdk.keyval_name(event.keyval)

			if name in ["Right", "Down", "Page_Down", "space"]:
				self.next()
			elif name in ["Left", "Up", "Page_Up", "BackSpace"]:
				self.prev()
			elif (name.upper() in ["F", "F11"]) \
				or (name == "Return" and event.state & gtk.gdk.MOD1_MASK) \
				or (name.upper() == "L" and event.state & gtk.gdk.CONTROL_MASK):
				self.fullscreen()
			elif name.upper() == "Q":
				gtk.main_quit()

		elif event.type == gtk.gdk.BUTTON_PRESS:
			if event.button == 1:
				self.next()
			else:
				self.prev()

		elif event.type == gtk.gdk.SCROLL:
			if event.direction in [gtk.gdk.SCROLL_RIGHT, gtk.gdk.SCROLL_DOWN]:
				self.next()
			else:
				self.prev()

		else:
			print "Unknown event %s" % event.type
