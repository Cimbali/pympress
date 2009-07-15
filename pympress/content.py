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

import pygtk
pygtk.require('2.0')
import gtk, os, sys

import pympress.util

class Content:
	"""
	This class manages the Content window, i.e. the one that displays only the
	current page in full size.

	@ivar fullscreen: indicates if the Content window is currently in fullscreen
	mode
	@type fullscreen: boolean

	@ivar win: GTK widget representing the Content window
	@type win: gtk.Window
	@ivar frame: GTK widget used to display pages with the right size and aspect
	ratio
	@type frame: gtk.AspectFrame
	@ivar da: GTK widget on which pages are rendered
	@type da: gtk.DrawingArea

	@ivar page: page displayed in the Content window
	@type page: L{pympress.Page}

	@ivar dpms_was_enabled: DPMS state the system was before running pympress
	@type dpms_was_enabled: boolean
	"""

	def __init__(self, page, navigation_cb, link_cb):
		"""
		@param page: page to be displayed in the Content window
		@type  page: L{pympress.Page}
		@param navigation_cb: callback function that will be called when the
		user interacts with the window to navigate from page to page (mouse
		scroll, key press, etc.)
		@type  navigation_cb: GTK event handler function
		@param link_cb: callback function that will be called when the user
		moves the mouse over a link or activates one
		@type  link_cb: GTK event handler function
		"""
		black = gtk.gdk.Color(0, 0, 0)

		# Main window
		self.win = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.win.set_title("pympress content")
		self.win.set_default_size(800, 600)
		self.win.modify_bg(gtk.STATE_NORMAL, black)
		self.win.connect("delete-event", gtk.main_quit)

		# Icons
		self.win.set_icon_list(*pympress.util.load_icons())

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

		# Add events
		self.win.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.SCROLL_MASK)
		self.win.connect("key-press-event", navigation_cb)
		self.win.connect("scroll-event", navigation_cb)

		if pympress.util.poppler_links_available():
			self.da.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
			self.da.connect("button-press-event", link_cb, self.get_page)
			self.da.connect("motion-notify-event", link_cb, self.get_page)

		# Don't start in fullscreen mode
		self.fullscreen = False

		# Add the page
		self.set_page(page)

		self.win.show_all()

	def set_page(self, page):
		"""
		Switch to another page and display it.

		@param page: new page to be displayed
		@type  page: L{pympress.Page}
		"""
		self.page = page

		# Page aspect ratio
		pr = self.page.get_aspect_ratio()
		self.frame.set_property("ratio", pr)

		# Don't queue draw event but draw directly (faster)
		self.on_expose(self.da)

	def get_page(self):
		"""
		Return the current page.

		@return: current page
		@rtype: L{pympress.Page}
		"""
		return self.page

	def set_screensaver(self, must_disable):
		"""
		Enable or disable the screensaver.

		@bug: At the moment, this is only supported on POSIX systems where
		xdg-screensaver is installed and working. For now, I{this feature has
		only been tested on Linux}.

		@param must_disable: if C{True}, indicates that the screensaver must be
		disabled; otherwise it will be enabled
		@type  must_disable: boolean
		"""
		if os.name == 'posix':
			# On Linux, set screensaver with xdg-screensaver
			# (compatible with xscreensaver, gnome-screensaver and ksaver or whatever)
			cmd = "suspend" if must_disable else "resume"
			status = os.system("xdg-screensaver %s %s" % (cmd, self.win.window.xid))
			if status != 0:
				print >>sys.stderr, "Warning: Could not set screensaver status: got status %d" % status

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
						print >>sys.stderr, "Warning: Could not disable DPMS screen blanking: got status %d" % status
				else:
					self.dpms_was_enabled = False

			elif self.dpms_was_enabled:
				# Re-enable DPMS
				status = os.system("xset +dpms")
				if status != 0:
					print >>sys.stderr, "Warning: Could not enable DPMS screen blanking: got status %d" % status
		else:
			print >>sys.stderr, "Warning: Unsupported OS: can't enable/disable screensaver"

	def switch_fullscreen(self):
		"""
		Switch the Content window to fullscreen (if in normal mode) or to normal
		mode (if fullscreen).

		Screensaver will be disabled when entering fullscreen mode, and enabled
		when leaving fullscreen mode.
		"""
		if self.fullscreen:
			self.win.unfullscreen()
			self.fullscreen = False
		else:
			self.win.fullscreen()
			self.fullscreen = True

		self.set_screensaver(self.fullscreen)

	def on_expose(self, widget, event=None):
		"""
		Manage expose events by rendering the current page to the Content
		window.

		This function may be called manually to force the Content window to be
		refreshed immediately.

		@param widget: the widget in which the expose event occured
		@type  widget: gtk.Widget
		@param event: the event that occured
		@type  event: gtk.gdk.Event
		"""
		self.page.render_on(widget)
