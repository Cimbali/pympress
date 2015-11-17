#       util.py
#
#       Copyright 2009, 2010 Thomas Jost <thomas.jost@gmail.com>
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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import GdkPixbuf
import pkg_resources
import os, os.path, sys

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

def get_icon_pixbuf(name):
    if getattr(sys, 'frozen', False):
        icon_fn = os.path.join(os.path.dirname(sys.executable), "share", "pixmaps", name)
    else:
        req = pkg_resources.Requirement.parse("pympress")
        icon_fn = pkg_resources.resource_filename(req, os.path.join("share", "pixmaps", name))
    return GdkPixbuf.Pixbuf.new_from_file(icon_fn)

def list_icons():
    if getattr(sys, 'frozen', False):
        icons = os.listdir(os.path.join(os.path.dirname(sys.executable), "share", "pixmaps"))
    else:
        req = pkg_resources.Requirement.parse("pympress")
        icons = pkg_resources.resource_listdir(req, os.path.join("share", "pixmaps"))

    return [i for i in icons if os.path.splitext(i)[1].lower() == ".png" and i[:9] == "pympress-"]

def load_icons():
    """
    Load pympress icons from the pixmaps directory (usually
    :file:`/usr/share/pixmaps` or something similar).

    :return: loaded icons
    :rtype: list of :class:`GdkPixbuf.Pixbuf`
    """

    icons = []
    for icon_name in list_icons():
        try:
            icon_pixbuf = get_icon_pixbuf(icon_name)
            icons.append(icon_pixbuf)
        except Exception:
            print("Error loading icons")

    return icons


def path_to_config():
    if os.name == 'posix':
        conf_dir=os.path.expanduser("~/.config")
        conf_file_nodir=os.path.expanduser("~/.pympress")
        conf_file_indir=os.path.expanduser("~/.config/pympress")

        if os.path.isfile(conf_file_indir):
            return conf_file_indir
        elif os.path.isfile(conf_file_nodir):
            return conf_file_nodir

        elif os.path.isdir(conf_dir):
            return conf_file_indir
        else:
            return conf_file_nodir
    else:
        return os.path.expandvars(os.path.join("%APPDATA%", "pympress.ini"))

def load_config():
    config = configparser.ConfigParser()
    config.add_section('content')
    config.add_section('presenter')
    config.add_section('cache')

    config.read(path_to_config())

    if not config.has_option('cache', 'maxpages'):
        config.set('cache', 'maxpages', '200')

    if not config.has_option('content', 'xalign'):
        config.set('content', 'xalign', '0.50')

    if not config.has_option('content', 'yalign'):
        config.set('content', 'yalign', '0.50')

    if not config.has_option('presenter', 'slide_ratio'):
        config.set('cache', 'maxpages', '0.75')

    return config

def save_config(config):
    with open(path_to_config(), 'w') as configfile:
        config.write(configfile)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
