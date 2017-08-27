#       util.py
#
#       Copyright 2009, 2010 Thomas Jost <thomas.jost@gmail.com>
#       Copyright 2015 Cimbali <me@cimba.li>
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
:mod:`pympress.util` -- various utility functions
-------------------------------------------------
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
import locale
import ctypes
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GdkPixbuf
import pkg_resources
import os, os.path, sys


IS_POSIX = os.name == 'posix'
IS_MAC_OS = sys.platform == 'darwin'
IS_WINDOWS = os.name == 'nt'


def __get_resource_path(*path_parts):
    """ Return the resource path based on whether its frozen or not.
    Paths parts given should be relative to the pympress package dir.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), *path_parts)
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_filename(req, os.path.join('pympress', *path_parts))


def __get_resource_list(*path_parts):
    """ Return the list of elements in a directory based on whether its frozen or not.
    Paths parts given should be relative to the pympress package dir.
    """
    if getattr(sys, 'frozen', False):
        return os.listdir(os.path.join(os.path.dirname(sys.executable), *path_parts))
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_listdir(req, os.path.join('pympress', *path_parts))


def get_locale_dir():
    """ Returns the path to the locale directory
    """
    return __get_resource_path('share', 'locale')


def get_style_provider():
    """ Load the css and return corresponding style provider.
    """
    if IS_MAC_OS:
        css_fn = __get_resource_path('share', 'css', 'macos.css')
    else:
        css_fn = __get_resource_path('share', 'css', 'default.css')

    style_provider = Gtk.CssProvider()
    style_provider.load_from_path(css_fn)
    return style_provider


def get_icon_pixbuf(name):
    """ Load an image from pympress' resources in a Gdk Pixbuf.
    """
    return GdkPixbuf.Pixbuf.new_from_file(__get_resource_path('share', 'pixmaps', name))


def get_ui_resource_file(name):
    """ Load an UI definition file from pympress' resources.
    """
    return __get_resource_path('share', 'xml', name + '.glade')


def list_icons():
    """ List the icons from pympress' resources.
    """
    icons = __get_resource_list('share', 'pixmaps')

    return [i for i in icons if os.path.splitext(i)[1].lower() == '.png' and i[:9] == 'pympress-']


def load_icons():
    """ Load pympress icons from the pixmaps directory (usually
    :file:`/usr/share/pixmaps` or something similar).

    Returns:
        list of :class:`GdkPixbuf.Pixbuf`: loaded icons
    """
    icons = []
    for icon_name in list_icons():
        try:
            icon_pixbuf = get_icon_pixbuf(icon_name)
            icons.append(icon_pixbuf)
        except Exception as e:
            logger.exception('Error loading icons')

    return icons


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
