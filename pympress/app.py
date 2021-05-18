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

from pympress import util, config, document, ui, builder


class Pympress(Gtk.Application):
    """ Class representing the single pympress Gtk application.
    """
    #: The :class:`~pympress.ui.UI` object that is the interface of pympress
    gui = None
    #: The :class:`~pympress.config.Config` object that holds pympress conferences
    config = None
    #: `list` of actions to be passsed to the GUI that were queued before GUI was created
    action_startup_queue = []
    #: `bool` to automatically upgrade log level (DEBUG / INFO at init, then ERROR), False if user set log level
    auto_log_level = True

    options = {
        # long_name:  (short_name (int), flags (GLib.OptionFlags), arg (GLib.OptionArg)
        'talk-time':  (ord('t'), GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'notes':      (ord('N'), GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'log':        (0,        GLib.OptionFlags.NONE, GLib.OptionArg.STRING),
        'version':    (ord('v'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'pause':      (ord('P'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'reset':      (ord('r'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'next':       (ord('n'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'prev':       (ord('p'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'first':      (ord('f'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'last':       (ord('l'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'blank':      (ord('b'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
        'quit':       (ord('q'), GLib.OptionFlags.NONE, GLib.OptionArg.NONE),
    }

    option_descriptions = {
        #  long_name: (description, arg_description)
        'talk-time': (_('The estimated (intended) talk time in minutes') + ' ' +
                      _('(and optionally seconds)'), 'mm[:ss]'),
        'notes':     (_('Set the position of notes on the pdf page') + ' ' +
                      _('(none, left, right, top, bottom, or after).') + ' ' +
                      _('Overrides the detection from the file.'), '<position>'),
        'log':       (_('Set level of verbosity in log file:') + ' ' +
                      _('{}, {}, {}, {}, or {}').format('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'), '<level>'),
        'version':   (_('Print version and exit'), None),
        'pause':     (_('Toggle pause of talk timer'), None),
        'reset':     (_('Reset talk timer'), None),
        'next':      (_('Next slide'), None),
        'prev':      (_('Previous slide'), None),
        'first':     (_('First slide'), None),
        'last':      (_('Last slide'), None),
        'blank':     (_('Blank/unblank content screen'), None),
        'quit':      (_('Close opened pympress instance'), None),
    }

    version_string = ' '.join([
        'Pympress:', util.get_pympress_meta()['version'],
        '; Python:', platform.python_version(),
        '; OS:', platform.system(), platform.release(), platform.version(),
        '; Gtk {}.{}.{}'.format(Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()),
        '; GLib {}.{}.{}'.format(GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION),
        '; Poppler', document.Poppler.get_version(), document.Poppler.get_backend().value_nick,
        '; Cairo', cairo.cairo_version_string(), ', pycairo', cairo.version,
    ])


    def __init__(self):
        GLib.set_application_name('pympress')
        Gtk.Application.__init__(self, application_id='io.github.pympress',
                                 flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.CAN_OVERRIDE_APP_ID)

        self.register(None)

        if not self.get_is_remote():
            builder.Builder.setup_actions({
                'log-level': dict(activate=self.set_log_level, state=logger.getEffectiveLevel(), parameter_type=int),
            }, action_map=self)

        # Connect proper exit function to interrupt
        signal.signal(signal.SIGINT, self.quit)

        for opt in self.options:
            self.add_main_option(opt, *self.options[opt], *self.option_descriptions.get(opt, ['', None]))


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


    def do_activate(self, timestamp=GLib.get_current_time()):
        """ Activate: show UI windows.

        Build them if they do not exist, otherwise bring to front.
        """
        if self.gui is None:
            if self.auto_log_level:
                self.activate_action('log-level', logging.INFO)
                self.action_startup_queue.append(('log-level', logging.ERROR))

            # Build the UI and windows
            self.gui = ui.UI(self, self.config)

            while self.action_startup_queue:
                self.activate_action(*self.action_startup_queue.pop(0))

        Gtk.Application.do_activate(self)
        self.gui.p_win.present_with_time(timestamp)


    def set_action_enabled(self, name, value):
        """ Parse an action name and set its enabled state to True or False.

        Args:
            name (`str`): the name of the stateful action
            value (`bool`): wheether the action should be enabled or disabled
        """
        self.lookup_action(name).set_enabled(value)


    def set_action_state(self, name, value):
        """ Parse an action name and set its state wrapped in a :class:`~GLib.Variant`.

        Args:
            name (`str`): the name of the stateful action
            value (`str`, `int`, `bool` or `float`): the value to set.
        """
        self.lookup_action(name).change_state(GLib.Variant(builder.Builder._glib_type_strings[type(value)], value))


    def get_action_state(self, name):
        """ Parse an action name and return its unwrapped state from the :class:`~GLib.Variant`.

        Args:
            name (`str`): the name of the stateful action

        Returns:
            `str`, `int`, `bool` or `float`: the value contained in the action
        """
        state = self.lookup_action(name).get_state()
        return builder.Builder._glib_type_getters[state.get_type_string()](state)


    def activate_action(self, name, parameter=None):
        """ Parse an action name and activate it, with parameter wrapped in a :class:`~GLib.Variant` if it is not None.

        Args:
            name (`str`): the name of the stateful action
            parameter: an object or None to pass as a parameter to the action, wrapped in a GLib.Variant
        """
        if not self.get_is_remote() and self.gui is None and name not in ['log-level']:
            self.action_startup_queue.append((name, parameter))
            return

        if parameter is not None:
            parameter = GLib.Variant(builder.Builder._glib_type_strings[type(parameter)], parameter)

        Gio.ActionGroup.activate_action(self, name, parameter)


    def do_open(self, files, n_files, hint):
        """ Handle opening files. In practice we only open once, the last one.

        Args:
            files (`list` of :class:`~Gio.File`s): representing an array of files to open
            n_files (`int`): the number of files passed.
            hint (`str`): a hint, such as view, edit, etc. Should always be the empty string.
        """
        if not n_files:
            return

        self.do_activate(timestamp=GLib.get_current_time())
        self.gui.swap_document(files[-1].get_uri())


    def do_shutdown(self):
        """ Perform various cleanups and save preferences.
        """
        if self.gui is not None:
            self.gui.cleanup()

        self.config.save_config()
        Gtk.Application.do_shutdown(self)


    def set_log_level(self, action, param):
        """ Action that sets the logging level (on the root logger of the active instance)

        Args:
            action (:class:`~Gio.Action`): The action activatd
            param (:class:~`GLib.Variant`): The desired level as an int wrapped in a GLib.Variant
        """
        logging.getLogger(None).setLevel(param.get_int64())
        action.change_state(param)


    def do_handle_local_options(self, opts_variant_dict):
        """ Parse command line options, returned as a VariantDict

        Returns:
            `tuple`: estimated talk time, log level, notes positions.
        """
        # convert GVariantDict -> GVariant -> dict
        opts = opts_variant_dict.end().unpack()

        simple_actions = {
            'pause': 'pause-timer',
            'reset': 'reset-timer',
            'next': 'next-page',
            'prev': 'prev-page',
            'blank': 'blank-screen',
            'quit': 'quit',
            'first': 'first-page',
            'last': 'last-page',
        }

        for opt, arg in opts.items():
            if opt == "version":
                print(self.version_string)
                return 0

            elif opt == "log":
                numeric_level = getattr(logging, arg.upper(), None)
                if isinstance(numeric_level, int):
                    self.auto_log_level = False
                    self.activate_action('log-level', numeric_level)
                else:
                    print(_("Invalid log level \"{}\", try one of {}").format(
                        arg, "DEBUG, INFO, WARNING, ERROR, CRITICAL"
                    ))

            elif opt == "notes":
                arg = arg.lower()[:1]
                if arg == 'n': self.activate_action('notes-pos', 'none')
                if arg == 'l': self.activate_action('notes-pos', 'left')
                if arg == 'r': self.activate_action('notes-pos', 'right')
                if arg == 't': self.activate_action('notes-pos', 'top')
                if arg == 'b': self.activate_action('notes-pos', 'bottom')
                if arg == 'a': self.activate_action('notes-pos', 'after')

            elif opt == "talk-time":
                t = ["0" + n.strip() for n in arg.split(':')]
                try:
                    m = int(t[0])
                    s = int(t[1])
                except ValueError:
                    print(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(arg))
                    return 2
                except IndexError:
                    s = 0
                self.activate_action('set-talk-time', m * 60 + s)

            elif opt in simple_actions:
                self.activate_action(simple_actions[opt])

        return -1
