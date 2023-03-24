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

import logging
logger = logging.getLogger(__name__)

import contextlib
import subprocess
import importlib
import os
import sys
import pathlib

try:
    # Introduced in 3.7
    import importlib.resources as importlib_resources
except ImportError:
    # Backport dependency
    import importlib_resources


IS_POSIX = os.name == 'posix'
IS_MAC_OS = sys.platform == 'darwin'
IS_WINDOWS = os.name == 'nt'


if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg


#: A :class:`~contextlib.ExitStack` containing all entered importlib context managers for used resources
_opened_resources = contextlib.ExitStack()


def get_pympress_meta():
    """ Get metadata (version, etc) from pympress' __init__.py or git describe.

    Returns:
        `dict`: metadata properties (version, contributors) mapped to their values
    """
    module = importlib.import_module('pympress.__init__')
    info = {'version': module.__version__, 'contributors': module.__author__}

    if getattr(sys, 'frozen', False) or not getattr(module, '__file__', None):
        return info

    git_dir = pathlib.Path(module.__file__).parents[1] / '.git'
    if not git_dir.exists():
        return info

    # Try and get a git describe output in case we are on a dirty/editable version
    try:
        command = 'git --git-dir={} describe --tags --long --dirty'.split()
        command[1] = command[1].format(git_dir)  # after spliting in case path has whitespace

        git_version = subprocess.check_output(command, stderr = subprocess.DEVNULL)

        # answer format is: {last tag}-{commit count since tag}-g{commit sha1 hash}[-dirty]
        tag, count, sha, dirty = (git_version.decode('utf-8') + '-').strip().split('-', 3)
        if count != '0' or dirty:
            info['version'] = '{}+{}@{}'.format(tag.lstrip('v'), count, sha.lstrip('g'))

    except subprocess.CalledProcessError:
        logger.debug('Failed to get git describe output', exc_info = True)

    finally:
        return info


def __get_resource_path(*path_parts):
    """ Return the path to a resource, ensuring it was made available as a file for the duration of the program.

    Args:
        name (`tuple` of `str`): The directories and filename that constitute the path
        to the resource, relative to the pympress distribution

    Returns:
        :class:`~pathlib.Path`: The path to the resource
    """
    try:
        # Introduced in 3.9
        resource = importlib_resources.asfile(importlib_resources.files('pympress').joinpath(*path_parts))
    except AttributeError:
        # Deprecated in 3.11
        resource = importlib_resources.path('.'.join(('pympress', *path_parts[:-1])), path_parts[-1])
    return _opened_resources.enter_context(resource)


def close_opened_resources():
    """ Close all importlib context managers for resources that we needed over the program lifetime. """
    _opened_resources.close()


def get_locale_dir():
    """ Returns the path to the locale directory.

    Returns:
        :class:`~pathlib.Path`: The path to the locale directory
    """
    return __get_resource_path('share', 'locale')


def get_portable_config():
    """ Returns the path to the configuration file for a portable install (i.e. in the install root).

    Returns:
        :class:`~pathlib.Path`: The path to the portable configuration file.
    """
    return __get_resource_path('pympress.conf')


def get_default_config():
    """ Returns the path to the configuration file containing the defaults.

    Returns:
        :class:`~pathlib.Path`: The path to the portable configuration file.
    """
    return __get_resource_path('share', 'defaults.conf')


def get_user_config():
    """ Returns the path to the configuration file in the user config directory

    Returns:
        :class:`~pathlib.Path`: path to the user configuration file.
    """
    if IS_WINDOWS:
        base_dir = pathlib.Path(os.getenv('APPDATA'))
    elif IS_MAC_OS:
        base_dir = pathlib.Path('~/Library/Preferences').expanduser()
    else:
        base_dir = pathlib.Path(os.getenv('XDG_CONFIG_HOME', '~/.config')).expanduser()
        if not base_dir.exists():
            base_dir.mkdir(parents=True)

    return base_dir.joinpath('pympress' + ('.ini' if IS_WINDOWS else ''))


def load_style_provider(style_provider):
    """ Load the css and in a style provider

    Args:
        style_provider (:class:`~Gtk.CssProvider`): The style provider in which to load CSS

    Returns:
        :class:`~Gtk.CssProvider`: The style provider with CSS loaded
    """
    style_provider.load_from_path(str(__get_resource_path('share', 'css', 'default.css')))
    return style_provider


def get_icon_path(name):
    """ Get the path for an image from pympress' resources

    Args:
        name (`str`): The name of the icon to load

    Returns:
        `str`: The path to the icon to load
    """
    return str(__get_resource_path('share', 'pixmaps', name))


def get_ui_resource_file(name, ext='.glade'):
    """ Load an UI definition file from pympress' resources

    Args:
        name (`str`): The name of the UI to load
        ext (`str`): The extension of the file

    Returns:
        `str`: The full path to the glade file
    """
    return str(__get_resource_path('share', 'xml', name + ext))


def list_icons():
    """ List the icons from pympress' resources.

    Returns:
        `list` of `str`: The paths to the icons in the pixmaps directory
    """
    return [get_icon_path('pympress-{}.png'.format(size)) for size in (16, 22, 24, 32, 48, 64)]


def get_log_path():
    """ Returns the appropriate path to the log file in the user app dirs.

    Returns:
        :class:`~pathlib.Path`: path to the log file.
    """
    if IS_WINDOWS:
        base_dir = pathlib.Path(os.getenv('LOCALAPPDATA', os.getenv('APPDATA')))
    elif IS_MAC_OS:
        base_dir = pathlib.Path('~/Library/Logs').expanduser()
    else:
        base_dir = pathlib.Path(os.getenv('XDG_CACHE_HOME', '~/.cache')).expanduser()

    if not base_dir.exists():
        base_dir.mkdir(parents=True)

    return base_dir.joinpath('pympress.log')


def fileopen(f):
    """ Call the right function to open files, based on the platform.

    Args:
        f (path-like): path to the file to open
    """
    if IS_WINDOWS:
        os.startfile(f)
    elif IS_MAC_OS:
        subprocess.call(['open', str(f)])
    else:
        subprocess.call(['xdg-open', str(f)])


def introspect_flag_value(flags_class, nick, fallback):
    """ Get the value of a flag from its class, given a value’s name (or nick)

    Introspection technique (in particular __flags_values__ dict) inspired from pygtkcompat.
    This is needed because there is no typelib for libgstplayback.

    Args:
        flags_class (a `~type` inheriting from :class:`~Gobject.GFlags`): the flags class to introspect
        nick (`str`): a name or nick of the flag value that should be returned
        fallback (`int`): the documented flag value, if lookup fails
    """
    try:
        flag_values = flags_class.__flags_values__
    except AttributeError:
        return fallback

    for value, flag in flag_values.items():
        if nick in flag.value_nicks or nick in flag.value_names:
            return value
    else:
        return fallback


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
                    assert regtype == winreg.REG_SZ, 'Unexpected RegType when modifying ScreenSaveActive'
                    hard_set_screensaver.dpms_was_enabled = (value == "1")
                    if hard_set_screensaver.dpms_was_enabled:
                        winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "0")
                elif hard_set_screensaver.dpms_was_enabled:
                    winreg.SetValueEx(key, "ScreenSaveActive", 0, winreg.REG_SZ, "1")
        except (OSError, PermissionError, AssertionError):
            logger.exception(_("access denied when trying to access screen saver settings in registry!"))

    elif IS_POSIX:
        logger.warning(_("Should not require hard enable/disable screensaver on Linux"))

    else:
        logger.warning(_("Unsupported OS: can't enable/disable screensaver"))


#: remember DPMS setting before we change it
hard_set_screensaver.dpms_was_enabled = None
#: A :class:`~subprocess.Popen` object to track the child caffeinate process
hard_set_screensaver.caffeinate_process = None


class NoMonitorPositions(Exception):
    """ The Exception we raise when there is no way of figuring out the monitor position of windows """
    pass


class ScreenArea(object):
    """ Convenience class to represent monitors or windows in terms of the area (position and size) they use on screen

    This is similar to :class:`~Gdk.Monitor`, but necessary as we want to handle “mirrored” monitors as if they were a
    single monitor, and only use “extended” monitors as target for content window position and/or fullscreening.
    """
    def most_intersection(self, candidates):
        """ Find the rectangle that intersects most with `~rect` in `~candidates`

        Args:
            candidates (iterable of `ScreenArea`s): The monitor areas to check for intersection

        Returns:
            `ScreenArea`: The best candidate screen area, i.e. that has the largest intersection
        """
        areas = []
        for geom in candidates:
            intersection = geom.intersection(self)
            if intersection is None:
                areas.append(-1)  # Not even 0 for a common bound
            elif intersection.equal(self):
                return geom
            else:
                areas.append(intersection.width * intersection.height)
        else:
            return candidates[areas.index(max(areas))]


    def least_intersection(self, candidates):
        """ Find the rectangle that intersects least with `~rect` in `~candidates`

        Args:
            candidates (iterable of `ScreenArea`s): The monitor areas to check for intersection

        Returns:
            `ScreenArea`: The best candidate screen area, i.e. that has the smallest intersection
        """
        areas = []
        for geom in candidates:
            intersection = self.intersection(geom)
            if intersection is None:
                return geom
            else:
                areas.append(intersection.width * intersection.height)
        else:
            return candidates[areas.index(min(areas))]


    def __init__(self, obj):
        if isinstance(obj, tuple):
            self.x, self.y, self.width, self.height = obj
        else:
            self.x, self.y, self.width, self.height = obj.x, obj.y, obj.width, obj.height


    def __repr__(self):
        """ Return a complete representation of the object """
        return 'ScreenArea(at {} size {})'.format((self.x, self.y), (self.width, self.height))


    def intersection(self, other):
        """ Compute the intersection of 2 screen areas

        Args:
            other (`ScreenArea`): The screen area to compare with

        Returns:
            `ScreenArea` or `None`: An area representing the intersection, or `None` if there is no intersection
        """
        if self.x + self.width < other.x or self.x > other.x + other.width:
            return None
        if self.y + self.height < other.y or self.y > other.y + other.height:
            return None

        x = max(self.x, other.x)
        w = min(self.x + self.width, other.x + other.width) - x
        y = max(self.y, other.y)
        h = min(self.y + self.height, other.y + other.height) - y
        return ScreenArea((x, y, w, h))


    def equal(self, other):
        """ Check whether 2 areas cover the exact same space

        Args:
            other (`ScreenArea`): The screen area to compare with

        Returns:
            `bool`: `True` iff the areas are identical
        """
        return (self.x, self.y, self.width, self.height) == (other.x, other.y, other.width, other.height)


    def contains(self, other):
        """ Check whether this area contains `~other`

        Args:
            other (`ScreenArea`): The screen area to compare with

        Returns:
            `bool`: `True` iff the area is contained
        """
        intersection = self.intersection(other)
        return intersection is not None and intersection.equal(self)


    def intersects(self, other):
        """ Check whether this area intersects `~other`

        Args:
            other (`ScreenArea`): The screen area to compare with

        Returns:
            `bool`: `True` iff the areas have an intersection
        """
        return self.intersection(other) is None


class Monitor(ScreenArea):
    """ A specialised `~ScreenArea` representing a monitor, with an descriptive string and a monitor number """
    #: A `str` to represent a user-friendly name for the monitor
    name = ''

    #: An `int` that identifies the monitor in :class:`~Gdk.Display`
    monitor_number = -1

    def __init__(self, obj, id_=None, num=None):
        super(Monitor, self).__init__(obj)
        self.name = id_
        self.monitor_number = num


    def __repr__(self):
        """ Return a complete representation of the object """
        return 'Monitor({} at {} size {})'.format(self.name, (self.x, self.y), (self.width, self.height))


    @staticmethod
    def lookup_monitors(display, *windows):
        """ Get the info on the monitors

        Args:
            display (:class:`~Gdk.Display`):  the current screen
            *windows (`tuple` of :class:`~Gtk.Window`):  windows for wich to look up the monitor position

        Returns:
            `tuple` of `Monitor`: The monitors for each window, followed by the best monitors for presenter and content
        """
        # Helpful for debugging
        monitors = [display.get_monitor(n) for n in range(display.get_n_monitors())]
        mon_names = ['{} {}'.format(mon.get_manufacturer() or 'Unknown manufacturer',
                                    mon.get_model() or 'Unknown model') for mon in monitors]

        all_geom = [Monitor(mon.get_geometry(), name, n) for n, (mon, name) in enumerate(zip(monitors, mon_names))]

        # Remove duplicate monitors (“mirrored”)
        all_geom = [rect for n, rect in enumerate(all_geom) if not any(rect.equal(other) for other in all_geom[:n])]
        # Remove monitors whose area is entirely contained in that of another monitor. NB: union() computes intersection
        all_geom = [rect for n, rect in enumerate(all_geom)
                    if all(not other.contains(rect) for other in all_geom[:n] + all_geom[n + 1:])]

        # We have a global positioning system
        if any(win.get_position() != (0, 0) for win in windows):
            pos = [ScreenArea(win.get_position() + win.get_size()).most_intersection(all_geom) for win in windows]
        # We have access to Gdk Windows
        elif all(win.get_window() is not None for win in windows):
            pos = [ScreenArea(mon.get_geometry()).most_intersection(all_geom) for mon in (
                display.get_monitor_at_window(win.get_window()) for win in windows
            )]
        else:
            raise NoMonitorPositions()

        # Figure out which monitor is best for presenter view: embedded panel on laptops, primary, or just first in list
        prim_area = all_geom[0]
        for mon in monitors:
            if mon.get_model() is None:
                continue
            model = mon.get_model().upper()
            if any(model.startswith(embedded) for embedded in {'LVDS', 'IDP', 'EDP', 'LCD', 'DSI'}):
                prim_area = ScreenArea(mon.get_geometry())
                break
            elif mon.is_primary():
                # NB. there may be 0 primaries. Don’t break as we prefer to identify an embedded screen.
                prim_area = ScreenArea(mon.get_geometry())

        return (*pos, prim_area.most_intersection(all_geom), prim_area.least_intersection(all_geom))

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
