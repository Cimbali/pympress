#!/usr/bin/env python
#
#       util.py
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
import gtk
import os, os.path, sys
import poppler

def load_icons():
	icons_path = os.path.join(sys.prefix, "share", "pixmaps")

	if not os.path.exists(os.path.join(icons_path, "pympress-16.png")):
		icons_path = "pixmaps"
	
	icons = []
	for size in [16, 32, 48, 64, 128]:
		icon = gtk.gdk.pixbuf_new_from_file(os.path.join(icons_path, "pympress-%d.png" % size))
		icons.append(icon)
	
	return icons


def poppler_links_available():
	"""Check if hyperlink support is enabled in python-poppler.

	@return: C{True} if hyperlink support is avaibable, C{False} otherwise
	@rtype : boolean
	"""

	try:
		type(poppler.ActionGotoDest)
	except AttributeError:
		return False
	else:
		return True
