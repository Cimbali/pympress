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

import logging
logger = logging.getLogger(__name__)

import os.path
import sys
import getopt
import signal
import locale
import gettext
import ctypes

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import pympress.util

if pympress.util.IS_WINDOWS:
    if os.getenv('LANG') is None:
        lang, enc = locale.getdefaultlocale()
        os.environ['LANG'] = lang

locale.setlocale(locale.LC_ALL, '')
gettext.install('pympress', pympress.util.get_resource_path('share', 'locale'))

# Catch all uncaught exceptions in the log file:
def uncaught_handler(*exc_info):
    logger.critical('Uncaught exception:\n{}'.format(logging.Formatter().formatException(exc_info)))
    sys.__excepthook__(*exc_info)

sys.excepthook = uncaught_handler

def usage():
    print(_("Usage: {} [options] <presentation_file>").format(sys.argv[0]))
    print("")
    print(_("Options:"))
    print("    -h, --help: " + _("This help"))
    print("    -t xx, --talk-time=xx: " + _("The estimated (intended) talk time in minutes"))
    print("")

def main(argv = sys.argv[1:]):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        opts, args = getopt.getopt(argv, "ht:", ["help", "talk-time=", "log="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    ett = 0
    log_level = logging.ERROR

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
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

    logging.basicConfig(filename='pympress.log', level=log_level)

    # PDF file to open passed on command line?
    name = None
    if len(args) > 0:
        name = os.path.abspath(args[0])

        # Check if the path is valid
        if not os.path.exists(name):
            msg=_("Could not find the file \"{}\"").format(name)
            dialog = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format=msg)
            dialog.set_position(Gtk.WindowPosition.CENTER)
            dialog.run()
            name = None

    # Create windows
    import pympress.ui
    ui = pympress.ui.UI(ett, name)
    if not name:
        GLib.idle_add(ui.pick_file)
    ui.run()


if __name__ == "__main__":
    main()

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
