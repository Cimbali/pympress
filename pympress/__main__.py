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
import locale
import gettext

from pympress import util


# Setup logging, and catch all uncaught exceptions in the log file.
# Load pympress.util early (OS and path-specific things) to load and setup gettext translation asap.
logger = logging.getLogger(__name__)
logging.basicConfig(filename=util.get_log_path(), level=logging.DEBUG)


def uncaught_handler(*exc_info):
    """ Exception handler, to log uncuaght exceptions to our log file.
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
    from gi.repository import Gtk, Gdk, GLib, Gio
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
from pympress import app


def main(argv = sys.argv[:]):
    """ Entry point of pympress. Parse command line arguments, instantiate the UI, and start the main loop.
    """
    app.Pympress().run(argv)


if __name__ == "__main__":
    main()

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
