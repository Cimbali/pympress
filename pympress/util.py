# -*- coding: utf-8 -*-
#
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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import subprocess
import importlib
import os
import sys

if not getattr(sys, 'frozen', False):
    # doesn’t play too well with cx_Freeze
    import pkg_resources

IS_POSIX = os.name == 'posix'
IS_MAC_OS = sys.platform == 'darwin'
IS_WINDOWS = os.name == 'nt'


if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg

try:
    PermissionError
except NameError:
    PermissionError = OSError



def get_pympress_meta():
    """ Get metadata (version, etc) from pympress' __init__.py or git describe.

    Returns:
        `dict`: metadata properties (version, contributors) mapped to their values
    """
    module = importlib.import_module('pympress.__init__')
    info = {'version': module.__version__, 'contributors': module.__author__}

    if getattr(sys, 'frozen', False):
        return info

    # Try and get a git describe output in case we are on a dirty/editable version
    try:
        path = pkg_resources.get_distribution('pympress').module_path

        command = 'git --git-dir={}/.git describe --tags --long --dirty'.split()
        command[1] = command[1].format(path)  # after spliting in case path has whitespace

        git_version = subprocess.check_output(command, stderr = subprocess.DEVNULL)

        # answer format is: {last tag}-{commit count since tag}-g{commit sha1 hash}[-dirty]
        tag, count, sha, dirty = (git_version + '-').decode('utf-8').strip().split('-', 3)
        if count != '0' or dirty:
            info['version'] = '{}+{}@{}'.format(tag.lstrip('v'), count, sha.lstrip('g'))

    except (pkg_resources.DistributionNotFound, subprocess.CalledProcessError):
        logger.debug('Failed to get git describe output', exc_info = True)

    finally:
        return info


def __get_resource_path(*path_parts):
    """ Return the resource path based on whether its frozen or not.

    Paths parts given should be relative to the pympress package dir.

    Args:
        name (`tuple` of `str`): The directories and filename that constitute the path
        to the resource, relative to the pympress distribution

    Returns:
        `str`: The path to the resource
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), *path_parts)
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_filename(req, '/'.join(('pympress',) + path_parts))


def __get_resource_list(*path_parts):
    """ Return the list of elements in a directory based on whether its frozen or not.

    Paths parts given should be relative to the pympress package dir.

    Args:
        name (`tuple` of `str`): The directories that constitute the path to the resource,
        relative to the pympress distribution

    Returns:
        `list` of `str`: The paths to the resources in the directory
    """
    if getattr(sys, 'frozen', False):
        return os.listdir(os.path.join(os.path.dirname(sys.executable), *path_parts))
    else:
        req = pkg_resources.Requirement.parse('pympress')
        return pkg_resources.resource_listdir(req, '/'.join(('pympress',) + path_parts))


def get_locale_dir():
    """ Returns the path to the locale directory.

    Returns:
        str: The path to the locale directory
    """
    return __get_resource_path('share', 'locale')


def get_portable_config():
    """ Returns the path to the configuration file for a portable install (i.e. in the install root).

    Returns:
        str: The path to the portable configuration file.
    """
    return __get_resource_path('pympress.conf')


def get_default_config():
    """ Returns the path to the configuration file containing the defaults.

    Returns:
        str: The path to the portable configuration file.
    """
    return __get_resource_path('share', 'defaults.conf')


def get_user_config():
    """ Returns the path to the configuration file in the user config directory.

    Returns:
        `str`: path to the user configuration file.
    """
    if IS_WINDOWS:
        base_dir = os.getenv('APPDATA')
    elif IS_MAC_OS:
        base_dir = os.path.expanduser('~/Library/Preferences')
    else:
        base_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        if not os.path.isdir(base_dir):
            os.mkdir(base_dir)

    return os.path.join(base_dir, 'pympress' + ('.ini' if IS_WINDOWS else ''))


def load_style_provider(style_provider):
    """ Load the css and in a style provider.

    Args:
        style_provider (:class:`~Gtk.CssProvider`): The style provider in which to load CSS

    Returns:
        :class:`~Gtk.CssProvider`: The style provider with CSS loaded
    """
    style_provider.load_from_path(__get_resource_path('share', 'css', 'default.css'))
    return style_provider


def get_icon_path(name):
    """ Load an image from pympress' resources in a Gdk Pixbuf.

    Args:
        name (`str`): The name of the icon to load

    Returns:
        :class:`~GdkPixbuf.Pixbuf`: The loaded icon
    """
    return __get_resource_path('share', 'pixmaps', name)


def get_ui_resource_file(name, ext='.glade'):
    """ Load an UI definition file from pympress' resources.

    Args:
        name (`str`): The name of the UI to load
        ext (`str`): The extension of the file

    Returns:
        `str`: The full path to the glade file
    """
    return __get_resource_path('share', 'xml', name + ext)


def list_icons():
    """ List the icons from pympress' resources.

    Returns:
        `list` of `str`: The paths to the icons in the pixmaps directory
    """
    icons = __get_resource_list('share', 'pixmaps')

    return [get_icon_path(i) for i in icons if os.path.splitext(i)[1].lower() == '.png' and i[:9] == 'pympress-']


def get_log_path():
    """ Returns the appropriate path to the log file in the user app dirs.

    Returns:
        `str`: path to the log file.
    """
    if IS_WINDOWS:
        base_dir = os.getenv('LOCALAPPDATA', os.getenv('APPDATA'))
    elif IS_MAC_OS:
        base_dir = os.path.expanduser('~/Library/Logs')
    else:
        base_dir = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))

    if not os.path.isdir(base_dir):
        os.makedirs(base_dir)

    return os.path.join(base_dir, 'pympress.log')


def fileopen(f):
    """ Call the right function to open files, based on the platform.

    Args:
        f (`str`): path to the file to open
    """
    if IS_WINDOWS:
        os.startfile(f)
    elif IS_MAC_OS:
        subprocess.call(['open', f])
    else:
        subprocess.call(['xdg-open', f])


def hard_set_screensaver(disabled):
    """ Enable or disable the screensaver.

    Args:
        disabled (`bool`):  if `True`, indicates that the screensaver must be disabled; otherwise it will be enabled
    """
    if IS_MAC_OS:
        # On Mac OS X we can use caffeinate to prevent the display from sleeping
        if disabled:
            if hard_set_screensaver.caffeinate_process is None or hard_set_screensaver.caffeinate_process.poll():
                hard_set_screensaver.caffeinate_process = subprocess.Popen(['caffeinate', '-d', '-w', str(os.getpid())])
        else:
            if hard_set_screensaver.caffeinate_process and not hard_set_screensaver.caffeinate_process.poll():
                hard_set_screensaver.caffeinate_process.kill()
                hard_set_screensaver.caffeinate_process.poll()
                hard_set_screensaver.caffeinate_process = None

    elif IS_WINDOWS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Control Panel\Desktop', 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                if disabled:
                    value, regtype = winreg.QueryValueEx(key, "ScreenSaveActive")
                    assert(regtype == winreg.REG_SZ)
                    hard_set_screensaver.dpms_was_enabled = (value == "1")
                    if hard_set_screensaver.dpms_was_enabled:
                        winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "0")
                elif hard_set_screensaver.dpms_was_enabled:
                    winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "1")
        except (OSError, PermissionError):
            logger.exception(_("access denied when trying to access screen saver settings in registry!"))

    elif IS_POSIX:
        logger.warning(_("Should not require hard enable/disable screensaver on Linux"))

    else:
        logger.warning(_("Unsupported OS: can't enable/disable screensaver"))


#: remember DPMS setting before we change it
hard_set_screensaver.dpms_was_enabled = None
#: A :class:`~subprocess.Popen` object to track the child caffeinate process
hard_set_screensaver.caffeinate_process = None

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
