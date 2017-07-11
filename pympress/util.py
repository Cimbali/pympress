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
import json
import locale
import ctypes
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GdkPixbuf
import pkg_resources
import os, os.path, sys

IS_POSIX = os.name == 'posix'
IS_MAC_OS = sys.platform == 'darwin'
IS_WINDOWS = os.name == 'nt'

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


def recursive_translate_widgets(a_widget):
    ''' Calls gettext on all strings we can find in widgets, recursively.
    '''
    for str_prop in (prop.name for prop in a_widget.props if prop.value_type == GObject.TYPE_STRING):
        try:
            setattr(a_widget.props, str_prop, _(getattr(a_widget.props, str_prop)))
        except TypeError:
            # Thrown when a string property is not readable
            pass

    if issubclass(type(a_widget), Gtk.Container):
        #NB: Parent-loop in widgets would cause infinite loop here, but that's absurd (right?)
        #NB2: maybe forall instead of foreach if we miss some strings?
        a_widget.foreach(recursive_translate_widgets)

    if issubclass(type(a_widget), Gtk.MenuItem) and a_widget.get_submenu() is not None:
        recursive_translate_widgets(a_widget.get_submenu())


def get_resource_path(*path_parts):
    ''' Return the resource path based on whether its frozen or not.
    Paths parts given should be relative to the pympress package dir.
    '''
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), *path_parts)
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_filename(req, os.path.join('pympress', *path_parts))


def get_resource_list(*path_parts):
    ''' Return the list of elements in a directory based on whether its frozen or not.
    Paths parts given should be relative to the pympress package dir.
    '''
    if getattr(sys, 'frozen', False):
        return os.listdir(os.path.join(os.path.dirname(sys.executable), *path_parts))
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_listdir(req, os.path.join('pympress', *path_parts))


def get_style_provider():
    ''' Load the css and return corresponding style provider.
    '''
    if IS_MAC_OS:
        css_fn = get_resource_path('share', 'css', 'macos.css')
    else:
        css_fn = get_resource_path('share', 'css', 'default.css')

    style_provider = Gtk.CssProvider()
    style_provider.load_from_path(css_fn)
    return style_provider


def get_icon_pixbuf(name):
    ''' Load an image from pympress' resources in a Gdk Pixbuf.
    '''
    return GdkPixbuf.Pixbuf.new_from_file(get_resource_path('share', 'pixmaps', name))


def list_icons():
    ''' List the icons from pympress' resources.
    '''
    icons = get_resource_list('share', 'pixmaps')

    return [i for i in icons if os.path.splitext(i)[1].lower() == '.png' and i[:9] == 'pympress-']


def load_icons():
    ''' Load pympress icons from the pixmaps directory (usually
    :file:`/usr/share/pixmaps` or something similar).

    Returns:
        list of :class:`GdkPixbuf.Pixbuf`: loaded icons
    '''
    icons = []
    for icon_name in list_icons():
        try:
            icon_pixbuf = get_icon_pixbuf(icon_name)
            icons.append(icon_pixbuf)
        except Exception as e:
            logger.exception('Error loading icons')

    return icons


def path_to_config():
    ''' Return the OS-specific path to the configuration file.
    '''
    if IS_POSIX:
        conf_dir=os.path.expanduser('~/.config')
        conf_file_nodir=os.path.expanduser('~/.pympress')
        conf_file_indir=os.path.expanduser('~/.config/pympress')

        if os.path.isfile(conf_file_indir):
            return conf_file_indir
        elif os.path.isfile(conf_file_nodir):
            return conf_file_nodir

        elif os.path.isdir(conf_dir):
            return conf_file_indir
        else:
            return conf_file_nodir
    else:
        return os.path.join(os.environ['APPDATA'], 'pympress.ini')


def load_config():
    ''' Get the configuration from its file.
    '''
    config = configparser.ConfigParser()
    config.add_section('content')
    config.add_section('presenter')
    config.add_section('layout')
    config.add_section('cache')
    config.add_section('scribble')

    config.read(path_to_config())

    if not config.has_option('cache', 'maxpages'):
        config.set('cache', 'maxpages', '200')

    if not config.has_option('content', 'xalign'):
        config.set('content', 'xalign', '0.50')

    if not config.has_option('content', 'yalign'):
        config.set('content', 'yalign', '0.50')

    if not config.has_option('content', 'monitor'):
        config.set('content', 'monitor', '0')

    if not config.has_option('content', 'start_blanked'):
        config.set('content', 'start_blanked', 'off')

    if not config.has_option('content', 'start_fullscreen'):
        config.set('content', 'start_fullscreen', 'on')

    if not config.has_option('presenter', 'monitor'):
        config.set('presenter', 'monitor', '1')

    if not config.has_option('presenter', 'start_fullscreen'):
        config.set('presenter', 'start_fullscreen', 'off')

    if not config.has_option('presenter', 'pointer'):
        config.set('presenter', 'pointer', 'red')

    if not config.has_option('presenter', 'show_bigbuttons'):
        config.set('presenter', 'show_bigbuttons', 'off')

    if not config.has_option('presenter', 'show_annotations'):
        config.set('presenter', 'show_annotations', 'off')

    if not config.has_option('layout', 'notes'):
        config.set('layout', 'notes', '')

    if not config.has_option('layout', 'plain'):
        config.set('layout', 'plain', '')

    if not config.has_option('scribble', 'color'):
        config.set('scribble', 'color', Gdk.RGBA(1., 0., 0., 1.).to_string())

    if not config.has_option('scribble', 'width'):
        config.set('scribble', 'width', '8')

    return config


def recursive_unicode_to_str(obj):
    ''' Recursively convert unicode to str (for python2)
        Raises NameError in python3 as 'unicode' is undefined
    '''
    if isinstance(obj, unicode):
        return str(obj)
    elif isinstance(obj, dict):
        return {recursive_unicode_to_str(k):recursive_unicode_to_str(obj[k]) for k in obj}
    elif isinstance(obj, list):
        return [recursive_unicode_to_str(i) for i in obj]
    else:
        return obj


def layout_from_json(layout_string, default_string):
    ''' Load the layout from config, with all strings cast to type 'str' (even on python2 where they default to 'unicode')
        Raises ValueError until python 3.4, json.decoder.JSONDecodeError afterwards, on invalid input.
    '''

    if not layout_string:
        layout_string = default_string

    layout = json.loads(layout_string)

    try:
        layout = recursive_unicode_to_str(layout)
    except NameError:
        pass

    return layout


def save_config(config):
    ''' Save the configuration to its file.
    '''
    with open(path_to_config(), 'w') as configfile:
        config.write(configfile)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
