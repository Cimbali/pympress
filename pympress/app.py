# -*- coding: utf-8 -*-
#
#       pympress
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
:mod:`pympress.app` -- The Gtk.Application managing the lifetime and CLI
------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import signal
import platform

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio

from pympress import util, config, extras, document, ui


class Pympress(Gtk.Application):

    gui = None
    config = None
    ett = 0
    log_level = logging.ERROR
    notes_pos = None

    _glib_type_strings = {
        float: 'd',
        bool: 'b',
        int: 's',
        str: 's',
    }

    _glib_type_getters = {
        'd': GLib.Variant.get_double,
        'b': GLib.Variant.get_boolean,
        'x': GLib.Variant.get_int64,
        's': GLib.Variant.get_string,
    }

    options = {
        # long_name: (short_name (int), flags (GLib.OptionFlags), arg (GLib.OptionArg)
        'talk-time': (ord('t'), GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'notes': (ord('n'), GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'log': (0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'version': (ord('v'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
    }

    option_descriptions = {
        #  long_name: (description, arg_description)
        'talk-time': (_('The estimated (intended) talk time in minutes') + ' '
                     + _('(and optionally seconds)'), None),
        'notes': (_('Set the position of notes on the pdf page') + ' ' +
                  _('(none, left, right, top, bottom, or after).') + ' ' +
                  _('Overrides the detection from the file.'), None),
        'log': (_('Set level of verbosity in log file:') + ' ' +
                 _('{}, {}, {}, {}, or {}').format('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'), None),
        'version': (_('Print version and exit'), None),
    }

    version_string = ' '.join([
        'Pympress:', util.get_pympress_meta()['version'],
        '; Python:', platform.python_version(),
        '; OS:', platform.system(), platform.release(), platform.version(),
        '; Gtk {}.{}.{}'.format(Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()),
        '; GLib {}.{}.{}'.format(GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION),
        '; Poppler', document.Poppler.get_version(), document.Poppler.get_backend().value_nick,
        '; Cairo', cairo.cairo_version_string(), ', pycairo', cairo.version,
        '; Media:', extras.Media.backend_version()
    ])


    def __init__(self):
        Gtk.Application.__init__(self, application_id='pympress.presenter', flags=Gio.ApplicationFlags.HANDLES_OPEN)

        self.register(None)

        # Connect proper exit function to interrupt
        signal.signal(signal.SIGINT, self.quit)

        for opt in self.options:
            self.add_main_option(opt, *self.options[opt], *self.option_descriptions[opt])


    def quit(self, *args):
        """ Quit and ignore other arguments e.g. sent by signals.
        """
        Gtk.Application.quit(self)
        return False


    def do_startup(self):
        """ Common start-up tasks for primary and remote instances.

        NB. super(self) causes segfaults, Gtk.Application needs to be used as base.
        """
        self.config = config.Config()

        # prefere X11 on posix systems because Wayland still has some shortcomings for us,
        # specifically libVLC and the ability to disable screensavers
        if util.IS_POSIX:
            Gdk.set_allowed_backends('x11,*')

        logger.info(self.version_string)
        Gtk.Application.do_startup(self)


    def set_action_enabled(self, name, value):
        """ Parse an action name and set its enabled state to True or False.

        Args:
            name (`str`): the name of the stateful action
            value (`bool`): wheether the action should be enabled or disabled
        """
        try:
            self.lookup_action(name).set_enabled(value)
        except:
            pass


    def set_action_state(self, name, value):
        """ Parse an action name and set its state wrapped in a :class:`~GLib.Variant`.

        Args:
            name (`str`): the name of the stateful action
            value (`str`, `int`, `bool` or `float`): the value to set.
        """
        try:
            self.lookup_action(name).change_state(GLib.Variant(self._glib_type_strings[type(value)], value))
        except:
            pass


    def get_action_state(self, name):
        """ Parse an action name and return its unwrapped state from the :class:`~GLib.Variant`.

        Args:
            name (`str`): the name of the stateful action

        Returns:
            `str`, `int`, `bool` or `float`: the value contained in the action
        """
        try:
            state = self.lookup_action(name).get_state()
            return self._glib_type_getters[state.get_type_string()](state)
        except:
            return None


    def activate_action(self, name, parameter=None):
        """ Parse an action name and activate it, with parameter wrapped in a :class:`~GLib.Variant` if it is not None.

        Args:
            name (`str`): the name of the stateful action
        """
        if parameter is not None:
            parameter = GLib.Variant(self._glib_type_strings[type(parameter)], parameter)

        self.lookup_action(name).activate(parameter)


    def do_activate(self, timestamp=GLib.get_current_time()):
        """ Activate: show UI windows.

        Build them if they do not exist, otherwise bring to front.
        """
        Gtk.Application.do_activate(self)
        if self.gui is None:
            self.gui = ui.UI(self, self.config)
            self.gui.activate()

            # pass command line args
            if self.ett:
                self.gui.est_time.set_time(self.ett)

            if self.notes_pos is not None:
                self.gui.change_notes_pos(self.notes_pos, force_change = True)

        self.gui.p_win.present_with_time(timestamp)


    def do_open(self, files, n_files, hint):
        time = GLib.get_current_time()
        if self.gui is None:
            self.do_activate(timestamp=time)

        if n_files:
            self.gui.swap_document(files[-1].get_uri())

        self.do_activate(time)


    def do_shutdown(self):
        if self.gui is not None:
            self.gui.cleanup()

        self.config.save_config()
        Gtk.Application.do_shutdown(self)


    def do_handle_local_options(self, opts_variant_dict):
        """ Parse command line options, returned as a VariantDict

        Returns:
            `tuple`: estimated talk time, log level, notes positions.
        """
        # convert GVariantDict -> GVariant -> dict
        opts = opts_variant_dict.end().unpack()

        for opt, arg in opts.items():
            if opt == "version":
                print(self.version_string)
                return 0

            elif opt == "notes":
                arg = arg.lower()[:1]
                if arg == 'n': self.notes_pos = document.PdfPage.NONE
                if arg == 'l': self.notes_pos = document.PdfPage.LEFT
                if arg == 'r': self.notes_pos = document.PdfPage.RIGHT
                if arg == 't': self.notes_pos = document.PdfPage.TOP
                if arg == 'b': self.notes_pos = document.PdfPage.BOTTOM
                if arg == 'a': self.notes_pos = document.PdfPage.AFTER

            elif opt == "talk-time":
                t = ["0" + n.strip() for n in arg.split(':')]
                try:
                    m = int(t[0])
                    s = int(t[1])
                except ValueError:
                    print(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(arg))
                    usage()
                    return 2
                except IndexError:
                    s = 0
                self.ett = m * 60 + s

            elif opt == "log":
                numeric_level = getattr(logging, arg.upper(), None)
                if isinstance(numeric_level, int):
                    logger.setLevel(numeric_level)
                else:
                    print(_("Invalid log level \"{}\", try one of {}").format(
                        arg, "DEBUG, INFO, WARNING, ERROR, CRITICAL"
                    ))

        return -1
