# -*- coding: utf-8 -*-
#
#!/usr/bin/env python
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

from __future__ import print_function, unicode_literals

import logging
import os.path
import sys
import getopt
import signal
import locale
import gettext
import ctypes
import tempfile
import platform


# Setup logging, and catch all uncaught exceptions in the log file.
# Load pympress.util early (OS and path-specific things) to load and setup gettext translation asap.
logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.path.join(tempfile.gettempdir(), 'pympress.log'), level=logging.DEBUG)


def uncaught_handler(*exc_info):
    logger.critical('Uncaught exception:\n{}'.format(logging.Formatter().formatException(exc_info)))
    sys.__excepthook__(*exc_info)

sys.excepthook = uncaught_handler


from pympress import util

if util.IS_WINDOWS:
    if os.getenv('LANG') is None:
        lang, enc = locale.getdefaultlocale()
        os.environ['LANG'] = lang

locale.setlocale(locale.LC_ALL, '')
gettext.install('pympress', util.get_locale_dir())



# Load python bindings for gobject introspections, aka pygobject, aka gi.
# This is a dependency that is not specified in the setup.py, so we need to start here
# see https://github.com/Cimbali/pympress/issues/100
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
except ModuleNotFoundError:
    logger.critical('Gobject Introspections module is missing', exc_info = True)
    print('\n' + _('ERROR: Gobject Introspections module is missing, make Gtk and pygobject are installed on your system.'))
    print('\n' + _('For instructions, refer to https://github.com/Cimbali/pympress/blob/master/README.md#dependencies'))
    print(_('If using a virtualenv or anaconda, you can either allow system site packages, or run: pip install pygobject'))
    print(_('pip will then download and compile pygobject, for which you need the Gtk headers (or development package).') + '\n')
    exit(1)




# Finally the real deal: load pympress modules, handle command line args, and start up
from pympress import media_overlay, document, ui


def usage():
    print(_("Usage: {} [options] <presentation_file>").format(sys.argv[0]))
    print("")
    print(_("Options:"))
    print("    -h, --help                       " + _("This help"))
    print("    -t mm[:ss], --talk-time=mm[:ss]  " + _("The estimated (intended) talk time in minutes"))
    print("                                       " + _("(and optionally seconds)"))
    print("    -n position, --notes=position    " + _("Set the position of notes on the pdf page (none, left, right, top, or bottom)."))
    print("                                       " + _("Overrides the detection from the file."))
    print("    --log=level                      " + _("Set level of verbosity in log file:"))
    print("                                       " + _("{}, {}, {}, {}, or {}").format("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
    print("")


def main(argv = sys.argv[1:]):
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # prefere X11 on posix systems because Wayland still has some shortcomings for us,
    # specifically libVLC and the ability to disable screensavers
    if util.IS_POSIX:
        Gdk.set_allowed_backends('x11,*')
    Gtk.init(argv)

    try:
        opts, args = getopt.getopt(argv, "hn:t:", ["help", "notes=", "talk-time=", "log="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    ett = 0
    log_level = logging.ERROR
    notes_pos = None

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        if opt in ("-n", "--notes"):
            if arg.lower()[0] == 'n': notes_pos = document.PdfPage.NONE
            if arg.lower()[0] == 'l': notes_pos = document.PdfPage.LEFT
            if arg.lower()[0] == 'r': notes_pos = document.PdfPage.RIGHT
            if arg.lower()[0] == 't': notes_pos = document.PdfPage.TOP
            if arg.lower()[0] == 'b': notes_pos = document.PdfPage.BOTTOM
        elif opt in ("-t", "--talk-time"):
            t = ["0" + n.strip() for n in arg.split(':')]
            try:
                m = int(t[0])
                s = int(t[1])
            except ValueError:
                print(_("Invalid time (mm or mm:ss expected), got \"{}\"").format(text))
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


    pympress_meta = util.get_pympress_meta().__version__
    logger.info(' '.join(['Pympress:', pympress_meta,
            '; Python:', platform.python_version(),
            '; OS:', platform.system(), platform.release(), #platform.version(),
            '; Gtk {}.{}.{}'.format(Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()),
            '; GLib {}.{}.{}'.format(GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION),
            '; Poppler', document.Poppler.get_version(), document.Poppler.get_backend().value_nick,
            '; Cairo', ui.cairo.cairo_version_string(), ', pycairo', ui.cairo.version,
            '; Media:', media_overlay.VideoOverlay.backend_version()
        ]))

    logger.setLevel(log_level)

    # Create windows
    gui = ui.UI()

    # pass command line args
    if ett: gui.est_time.set_time(ett)

    gui.swap_document(os.path.abspath(args[0])) if args else gui.pick_file()

    if notes_pos is not None:
        gui.change_notes_pos(notes_pos, force_change = True)

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
