#!/usr/bin/env python
#
#       content.py
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

import gtk, os, sys

class Content:
	def __init__(self, page, event_callback):
		black = gtk.gdk.Color(0, 0, 0)

		# Main window
		self.win = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.win.set_title("pympress content")
		self.win.set_default_size(800, 600)
		self.win.modify_bg(gtk.STATE_NORMAL, black)
		self.win.connect("delete-event", gtk.main_quit)

		# Aspect frame
		self.frame = gtk.AspectFrame(ratio=4./3., obey_child=False)
		self.frame.modify_bg(gtk.STATE_NORMAL, black)

		# Drawing area
		self.da = gtk.DrawingArea()
		self.da.modify_bg(gtk.STATE_NORMAL, black)
		self.da.connect("expose-event", self.on_expose)

		# Prepare the window
		self.frame.add(self.da)
		self.win.add(self.frame)
		self.win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.SCROLL_MASK)
		self.win.connect("key-press-event", event_callback)
		self.win.connect("button-press-event", event_callback)
		self.win.connect("scroll-event", event_callback)

		# Don't start in fullscreen mode
		self.fullscreen = False

		# Add the page
		self.set_page(page)

		self.win.show_all()

	def set_page(self, page):
		self.page = page

		# Page size
		self.pw, self.ph = self.page.get_size()

		# Page aspect ratio
		pr = self.pw / self.ph
		self.frame.set_property("ratio", pr)

		# Don't queue draw event but draw directly (faster)
		self.on_expose(self.da)

	def set_screensaver(self, enabled):
		if os.name == 'posix':
			# On Linux, set screensaver with xdg-screensaver
			# (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
			cmd = "resume" if enabled else "suspend"
			status = os.system("xdg-screensaver %s %s" % (cmd, self.win.window.xid))
			if status != 0:
				print >>sys.stderr, "Warning: Could not disable screensaver: got status %d" % status

			# Also manage screen blanking via DPMS
			if enabled:
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
						print >>sys.stderr, "Warning: Could not disable DPMS screen blanking: got status %d" % status
				else:
					self.dpms_was_enabled = False

			elif self.dpms_was_enabled:
				# Re-enable DPMS
				status = os.system("xset -dpms")
				if status != 0:
					print >>sys.stderr, "Warning: Could not disable DPMS screen blanking: got status %d" % status
		else:
			print >>sys.stderr, "Warning: Unsupported OS: can't enable/disable screensaver"

	def switch_fullscreen(self):
		if self.fullscreen:
			self.win.unfullscreen()
			self.fullscreen = False
		else:
			self.win.fullscreen()
			self.fullscreen = True

		self.set_screensaver(self.fullscreen)

	def on_expose(self, widget, event=None):
		# Make sure the object is initialized
		if widget.window is None:
			return

		# Widget size
		ww, wh = widget.window.get_size()

		# Manual double buffering (since we use direct drawing instead of
		# calling self.da.queue_draw())
		widget.window.begin_paint_rect(gtk.gdk.Rectangle(0, 0, ww, wh))

		cr = widget.window.cairo_create()
		cr.set_source_rgb(1, 1, 1)

		# Scale
		scale = min(ww/self.pw, wh/self.ph)
		cr.scale(scale, scale)

		cr.rectangle(0, 0, self.pw, self.ph)
		cr.fill()
		self.page.render(cr)

		# Blit off-screen buffer to screen
		widget.window.end_paint()
