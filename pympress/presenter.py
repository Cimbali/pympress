#!/usr/bin/env python
#
#       presenter.py
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

import gobject, gtk
import time

class Presenter:
	def __init__(self, current, next, number, total, event_callback):
		black = gtk.gdk.Color(0, 0, 0)

		self.start_time = 0
		self.number_total = total

		# Window
		win = gtk.Window(gtk.WINDOW_TOPLEVEL)
		win.set_title("pympress presenter")
		win.set_default_size(800, 600)
		#~ win.modify_bg(gtk.STATE_NORMAL, black)
		win.connect("delete-event", gtk.main_quit)

		# Horizontal box
		hbox = gtk.HBox(True)
		win.add(hbox)

		# Aspect frame for current page
		self.frame_current = gtk.AspectFrame(ratio=4./3., obey_child=False)
		#~ self.frame_current.modify_bg(gtk.STATE_NORMAL, black)
		hbox.pack_start(self.frame_current)

		# Drawing area for current page
		self.da_current = gtk.DrawingArea()
		self.da_current.modify_bg(gtk.STATE_NORMAL, black)
		self.da_current.connect("expose-event", self.on_expose)
		self.frame_current.add(self.da_current)

		# Vertical box
		vbox = gtk.VBox(False)
		hbox.pack_start(vbox)

		# Text label
		self.label = gtk.Label()
		self.label.set_justify(gtk.JUSTIFY_CENTER)
		self.label.set_use_markup(True)
		vbox.pack_start(self.label, False, False)

		# Aspect frame for next page
		self.frame_next = gtk.AspectFrame(ratio=4./3., obey_child=False)
		#~ self.frame_next.modify_bg(gtk.STATE_NORMAL, black)
		vbox.pack_start(self.frame_next)

		# Drawing area for next page
		self.da_next = gtk.DrawingArea()
		self.da_next.modify_bg(gtk.STATE_NORMAL, black)
		self.da_next.connect("expose-event", self.on_expose)
		self.frame_next.add(self.da_next)

		# Add events
		win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.SCROLL_MASK)
		win.connect("key-press-event", event_callback)
		win.connect("button-press-event", event_callback)
		win.connect("scroll-event", event_callback)

		# Set page
		self.set_page(current, next, number, False)

		# Setup timer
		gobject.timeout_add(1000, self.update_text)

		win.show_all()

	def on_expose(self, widget, event):
		cr = widget.window.cairo_create()
		cr.set_source_rgb(1, 1, 1)

		# Widget size
		ww, wh = widget.window.get_size()

		# Page-specific stuff (dirty)
		page = self.page_current
		pw, ph = self.pw_cur, self.ph_cur
		if widget == self.da_next:
			page = self.page_next
			pw, ph = self.pw_next, self.ph_next

		# Scale
		scale = min(ww/pw, wh/ph)
		cr.scale(scale, scale)

		cr.rectangle(0, 0, ww, wh)
		cr.fill()

		if page is not None:
			page.render(cr)

	def set_page(self, current, next, number, start = True):
		self.page_current = current
		self.page_next = next
		self.number_current = number

		# Page sizes
		self.pw_cur, self.ph_cur = self.page_current.get_size()

		# Aspect ratios
		pr = self.pw_cur / self.ph_cur
		self.frame_current.set_property("ratio", pr)

		# Same thing for next page if it's set
		if self.page_next is not None:
			self.pw_next, self.ph_next = self.page_next.get_size()
			pr = self.pw_next / self.ph_next
			self.frame_next.set_property("ratio", pr)

		# Start counter if needed
		if start and self.start_time == 0:
			self.start_time = time.time()

		# Update display
		self.update_text()

		self.da_current.queue_draw()
		self.da_next.queue_draw()

	def update_text(self):
		text = "%s\n\n%s\nSlide %d/%d"

		# Current time
		cur_time = time.strftime("%H:%M:%S")

		# Time elapsed since the beginning of the presentation
		delta = time.time() - self.start_time
		if self.start_time == 0:
			delta = 0
		elapsed = "%02d:%02d" % (int(delta/60), int(delta%60))

		text = text % (cur_time, elapsed, self.number_current+1, self.number_total)
		text = "<span font='36'>%s</span>" % text
		self.label.set_markup(text)
		return True
