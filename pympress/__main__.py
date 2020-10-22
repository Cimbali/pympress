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
:mod:`pympress.__main__` -- The entry point of pympress
-------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
import os
import sys
import getopt
import signal
import locale
import gettext
import platform

from pympress import util


# Setup logging, and catch all uncaught exceptions in the log file.
# Load pympress.util early (OS and path-specific things) to load and setup gettext translation asap.
logger = logging.getLogger(__name__)
logging.basicConfig(filename=util.get_log_path(), level=logging.DEBUG)


def uncaught_handler(*exc_info):
    """ Exception handler, to log uncuaght exceptiosn to our log file.
    """
    logger.critical('Uncaught exception:\n{}'.format(logging.Formatter().formatException(exc_info)))
    sys.__excepthook__(*exc_info)


sys.excepthook = uncaught_handler


if util.IS_WINDOWS:
    if os.getenv('LANG') is None:
        lang, enc = locale.getdefaultlocale()
        os.environ['LANG'] = lang

locale.setlocale(locale.LC_ALL, '')
gettext.install('pympress', util.get_locale_dir())


try:
    # python 2.7 does not have this
    ModuleNotFoundError
except NameError:
    ModuleNotFoundError = ImportError


# Load python bindings for gobject introspections, aka pygobject, aka gi, and pycairo.
# These are dependencies that are not specified in the setup.py, so we need to start here.
# They are not specified because:
# - installing those via pip requires compiling (always for pygobject, if no compatible wheels exist for cairo),
# - compiling requires a compiling toolchain, development packages of the libraries, etc.,
# - all of this makes more sense to be handled by the OS package manager,
# - it is hard to make pretty error messages pointing this out at `pip install` time,
#   as they would have to be printed when the dependency resolution happens.
# See https://github.com/Cimbali/pympress/issues/100
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    import cairo
except ModuleNotFoundError:
    logger.critical('Gobject Introspections and/or pycairo module is missing', exc_info = True)
    print('\n' + _('ERROR: Gobject Introspections and/or pycairo module is missing, ' +
                   'make sure Gtk, pygobject and pycairo are installed on your system.') + '\n')
    print(_('Try your operating system’s package manager, or try running: pip install pygobject pycairo'))
    print(_('pip will then download and compile pygobject and pycairo, ' +
            'for which you need the Gtk and cairo headers (or development packages).') + '\n')
    print(_('For instructions, refer to https://github.com/Cimbali/pympress/blob/master/README.md#dependencies'))
    print(_('If using a virtualenv or anaconda, you can also try allowing system site packages.'))
    print()
    exit(1)



# Finally the real deal: load pympress modules, handle command line args, and start up
from pympress import extras, document, ui


def usage():
    """ Display how to use the command line options.
    """
    print('''{usage}

{options}

    -h, --help                       {help}
    -t mm[:ss], --talk-time=mm[:ss]  {talk_time}
                                         {talk_time_secs}
    -n position, --notes=position    {notes}
                                         {notes_position}
                                         {notes_override}
    -m mode, --highlight_mode=mode   {highlight_mode}
    --log=level                      {log_level}
                                         {log_levels_list}
'''.format(
        usage           = _('Usage: {} [options] <presentation_file>').format(sys.argv[0]),
        options         = _('Options:'),
        help            = _('This help'),
        talk_time       = _('The estimated (intended) talk time in minutes'),
        talk_time_secs  = _('(and optionally seconds)'),
        notes           = _('Set the position of notes on the pdf page'),
        notes_position  = _('(none, left, right, top, or bottom).'),
        notes_override  = _('Overrides the detection from the file.'),
        highlight_mode  = _('Select highlighting mode (single, page, or clear)'),
        log_level       = _('Set level of verbosity in log file:'),
        log_levels_list = _('{}, {}, {}, {}, or {}').format('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'),
    ))


def parse_opts(opts):
    """ Parse command line options, returned from getopt.getopt().

    Returns:
        `tuple`: estimated talk time, log level, notes positions.
    """
    ett = 0
    log_level = logging.ERROR
    notes_pos = None
    highlight_mode = "clear"

    for opt, arg in opts.items():
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        if opt in ("-n", "--notes"):
            if arg.lower()[0] == 'n': notes_pos = document.PdfPage.NONE
            if arg.lower()[0] == 'l': notes_pos = document.PdfPage.LEFT
            if arg.lower()[0] == 'r': notes_pos = document.PdfPage.RIGHT
            if arg.lower()[0] == 't': notes_pos = document.PdfPage.TOP
            if arg.lower()[0] == 'b': notes_pos = document.PdfPage.BOTTOM
        elif opt in ("-m", "--mode"):
            if arg.lower()[0] == 'c':
                highlight_mode = 'clear'
            if arg.lower()[0] == 'p':
                highlight_mode = 'page'
            if arg.lower()[0] == 's':
                highlight_mode = 'single'
        elif opt in ("-t", "--talk-time"):
            t = ["0" + n.strip() for n in arg.split(':')]
            try:
                m = int(t[0])
                s = int(t[1])
            except ValueError:
                print(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(arg))
                usage()
                sys.exit(2)
            except IndexError:
                s = 0
            ett = m * 60 + s
        elif opt == "--log":
            numeric_level = getattr(logging, arg.upper(), None)
            if isinstance(numeric_level, int):
                log_level = numeric_level
            else:
                print(_("Invalid log level \"{}\", try one of {}").format(
                    arg, "DEBUG, INFO, WARNING, ERROR, CRITICAL"
                ))

    return ett, log_level, notes_pos, highlight_mode


def main(argv = sys.argv[1:]):
    """ Entry point of pympress. Parse command line arguments, instantiate the UI, and start the main loop.
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # prefere X11 on posix systems because Wayland still has some shortcomings for us,
    # specifically libVLC and the ability to disable screensavers
    if util.IS_POSIX:
        Gdk.set_allowed_backends('x11,*')
    Gtk.init(argv)

    pympress_meta = util.get_pympress_meta()['version']
    logger.info(' '.join([
        'Pympress:', pympress_meta,
        '; Python:', platform.python_version(),
        '; OS:', platform.system(), platform.release(), platform.version(),
        '; Gtk {}.{}.{}'.format(Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()),
        '; GLib {}.{}.{}'.format(GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION),
        '; Poppler', document.Poppler.get_version(), document.Poppler.get_backend().value_nick,
        '; Cairo', cairo.cairo_version_string(), ', pycairo', cairo.version,
        '; Media:', extras.Media.backend_version()
    ]))

    try:
        opts, args = getopt.getopt(argv, "hm:n:t:", ["help", "highlight-mode=", "notes=", "talk-time=", "log="])
        opts = dict(opts)
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    ett, log_level, notes_pos, highlight_mode = parse_opts(opts)
    logger.setLevel(log_level)

    # Create windows
    gui = ui.UI()

    # Connect proper exit function to interrupt
    signal.signal(signal.SIGINT, gui.save_and_quit)

    # pass command line args
    if ett:
        gui.est_time.set_time(ett)

    gui.swap_document(os.path.abspath(args[0])) if args else gui.pick_file()

    if notes_pos is not None:
        gui.change_notes_pos(notes_pos, force_change = True)

    gui.highlight_mode = highlight_mode

    gui.run()


if __name__ == "__main__":
    main()

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
