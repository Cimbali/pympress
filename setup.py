#!/usr/bin/env python3
#
#       setup.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
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

""" pympress setup script.

Mostly wrapping logic for freezing (with cx_Freeze for windows builds).
All configuration is in setup.cfg.
"""

import os
import re
import sys
import pathlib
import subprocess
from ctypes.util import find_library
import setuptools

from setuptools import Command
from setuptools.command.build_py import build_py


def find_index_startstring(haystack, needle, start=0, stop=sys.maxsize):
    """ Return the index of the first string in haystack starting with needle, or raise ValueError if none match.
    """
    try:
        return next(n for n, v in enumerate(haystack[start:stop], start) if v.startswith(needle))
    except StopIteration:
        raise ValueError('No string starts with ' + needle)


class GettextBuildCatalog(Command):
    """ Patched build command to generate translations .mo files using gettext’s msgfmt

    This is used for build systems that do not have easy access to Babel
    """
    user_options = [
        ('domain=', 'D', "domains of PO files (space separated list, default 'messages')"),
        ('directory=', 'd', 'path to base directory containing the catalogs'),
        ('use-fuzzy', 'f', 'also include fuzzy translations'),
        ('statistics', None, 'print statistics about translations')
    ]

    def initialize_options(self):
        """ Initialize options
        """
        self.domain = None
        self.directory = None
        self.use_fuzzy = False
        self.statistics = True


    def finalize_options(self):
        """ Finalize options
        """
        assert self.domain is not None and self.directory is not None


    def run(self):
        """ Run msgfmt before running (parent) develop command
        """
        po_wildcard = pathlib.Path(self.directory).glob(str(pathlib.Path('*', 'LC_MESSAGES', self.domain + '.po')))
        for po in po_wildcard:
            print(po)
            mo = po.with_suffix('.mo')

            cmd = ['msgfmt', str(po), '-o', str(mo)]
            if self.use_fuzzy:
                cmd.insert(1, '--use-fuzzy')
            if self.statistics:
                cmd.insert(1, '--statistics')

            subprocess.check_output(cmd)



class BuildWithCatalogs(build_py):
    """ Patched build command to generate translations .mo files using Babel

    This is what we use by default, e.g. when distributing through PyPI
    """
    def run(self):
        """ Run compile_catalog before running (parent) develop command
        """
        try:
            self.distribution.run_command('compile_catalog')
        except Exception as err:
            if err.args == ('no message catalogs found',):
                pass  # Running from a source tarball − compiling already done
            else:
                raise
        build_py.run(self)


# All functions listing resources return a list of pairs: (system path, distribution relative path)
def gtk_resources():
    """ Returns a list of the non-DLL Gtk resources to include in a frozen/binary package.
    """
    include_path = pathlib.Path(find_library('libgtk-3-0')).parent
    include_path = include_path.parent if include_path.name in {'bin', 'lib', 'lib64'} else include_path

    include_files = []
    resources = [
        pathlib.Path('etc'),
        pathlib.Path('lib', 'girepository-1.0'),
        pathlib.Path('lib', 'gtk-3.0'),
        pathlib.Path('lib', 'gdk-pixbuf-2.0'),
        pathlib.Path('share', 'poppler'),
        pathlib.Path('share', 'themes'),
        pathlib.Path('share', 'icons'),
        pathlib.Path('share', 'glib-2.0'),
        pathlib.Path('share', 'xml')
    ]

    for f in resources:
        p = include_path.joinpath(f)
        if p.exists():
            include_files.append((str(p), str(f)))
        else:
            print('WARNING: Can not find {} (at {})'.format(f, p))

    return include_files


def dlls():
    """ Returns a list of all DLL files we need to include, in a frozen/binary package on windows.

    Relies on a hardcoded list tested for the appveyor build setup.
    """
    if os.name != 'nt':
        return []

    libs = 'libatk-1.0-0.dll libbrotlicommon.dll libbrotlidec.dll libcurl-4.dll libdatrie-1.dll \
    libepoxy-0.dll libfribidi-0.dll libgdk-3-0.dll libgdk_pixbuf-2.0-0.dll libgif-7.dll \
    libgio-2.0-0.dll libgirepository-1.0-1.dll libglib-2.0-0.dll libgobject-2.0-0.dll libgtk-3-0.dll \
    libidn2-0.dll libjpeg-8.dll liblcms2-2.dll libnghttp2-14.dll libnspr4.dll libopenjp2-7.dll \
    libpango-1.0-0.dll libpangocairo-1.0-0.dll libpangoft2-1.0-0.dll libpangowin32-1.0-0.dll \
    libplc4.dll libplds4.dll libpoppler-105.dll libpoppler-cpp-0.dll libpoppler-glib-8.dll libpsl-5.dll \
    libpython{0.major}.{0.minor}.dll libstdc++-6.dll libthai-0.dll libtiff-5.dll libunistring-2.dll \
    libwinpthread-1.dll libzstd.dll nss3.dll nssutil3.dll smime3.dll'.format(sys.version_info)
    # these appear superfluous, though unexpectedly so:
    # libcairo-2.dll libcairo-gobject-2.dll libfontconfig-1.dll libfreetype-6.dll libiconv-2.dll
    # libgettextlib-0-19-8-1.dll libgettextpo-0.dll libgettextsrc-0-19-8-1.dll libintl-8.dll libjasper-4.dll

    lib_gtk_dir = pathlib.Path(find_library('libgtk-3-0')).parent

    gdbus = pathlib.Path(find_library('gdbus.exe'))
    include_files = [(str(gdbus), str(pathlib.Path('lib', 'gi', 'gdbus.exe'))), (str(gdbus), 'gdbus.exe')]
    for lib in libs.split():
        path = find_library(lib)
        path = pathlib.Path(path) if path is not None else path
        if path is not None and path.exists():
            include_files.append((str(path), lib))
        else:
            lib = pathlib.Path(lib)
            # Look in other directories?
            for path in lib_gtk_dir.glob(re.sub('-[0-9.]*$', '-*', lib.stem) + lib.suffix):
                include_files.append((str(path), path.name))
                print('WARNING: Can not find library {}, including {} instead'.format(lib, path.name))
            else:
                print('WARNING: Can not find library {}'.format(lib))

    return include_files


def check_cli_arg(val):
    """ Check whether an argument was passed, and clear it from sys.argv

    Returns (bool): whether the arguement was present
    """
    if val in sys.argv[1:]:
        sys.argv.remove(val)
        return True

    return False


def pympress_resources():
    """ Return pympress resources. Only for frozen packages, as this is redundant with package_data.
    """
    share = pathlib.Path('pympress', 'share')
    dirs = [share.joinpath('xml'), share.joinpath('pixmaps'), share.joinpath('css'), share.joinpath('defaults.conf')]
    translations = share.glob(str(pathlib.Path('*', 'LC_MESSAGES', 'pympress.mo')))

    return [(str(f), str(f.relative_to('pympress'))) for f in dirs + list(translations)]


if __name__ == '__main__':

    try:
        from babel.messages.frontend import compile_catalog
    except ImportError:
        compile_catalog = GettextBuildCatalog

    options = {'cmdclass': {
        'build_py': BuildWithCatalogs,
        'compile_catalog': compile_catalog,
    }}

    # subtle tweak: don’t put an install section in installed packages
    with open('README.md', encoding='utf-8') as f:
        readme = f.readlines()

        install_section = find_index_startstring(readme, '# Install')
        next_section = find_index_startstring(readme, '# ', install_section + 1)
        del readme[install_section:next_section]

        options['long_description'] = ''.join(readme)


    # Check whether to create a frozen distribution
    if check_cli_arg('--freeze'):
        print('Using cx_Freeze.setup():', file=sys.stderr)
        from cx_Freeze import setup, Executable

        setup(**{
            **options,
            'options': {
                'build_exe': {
                    'includes': [],
                    'excludes': ['tkinter'],
                    'packages': ['codecs', 'gi', 'vlc', 'watchdog'],
                    'include_files': gtk_resources() + dlls() + pympress_resources(),
                    'silent': True
                },
                'bdist_msi': {
                    'add_to_path': True,
                    'all_users': False,
                    'summary_data': {
                        'comments': 'https://github.com/Cimbali/pympress/',
                        'keywords': 'pdf-viewer, beamer, presenter, slide, projector, pdf-reader, \
                                    presentation, python, poppler, gtk, pygi, vlc',
                    },
                    'upgrade_code': '{5D156784-ED69-49FF-A972-CBAD312187F7}',
                    'install_icon': str(pathlib.Path('pympress', 'share', 'pixmaps', 'pympress.ico')),
                    'extensions': [{
                        'extension': 'pdf',
                        'verb': 'open',
                        'executable': 'pympress-gui.exe',
                        'argument': '"%1"',
                        'mime': 'application/pdf',
                        'context': 'Open with p&ympress',
                    }],
                }
            },
            'executables': [
                Executable(str(pathlib.Path('pympress', '__main__.py')), target_name='pympress-gui.exe',
                           base='Win32GUI', shortcut_dir='ProgramMenuFolder', shortcut_name='pympress',
                           icon=str(pathlib.Path('pympress', 'share', 'pixmaps', 'pympress.ico'))),
                Executable(str(pathlib.Path('pympress', '__main__.py')), target_name='pympress.exe',
                           base='Console', icon=str(pathlib.Path('pympress', 'share', 'pixmaps', 'pympress.ico'))),
            ]
        })
    else:
        # Normal behaviour: use setuptools, load options from setup.cfg
        print('Using setuptools.setup():', file=sys.stderr)

        setuptools_version = tuple(int(n) for n in setuptools.__version__.split('.')[:2])
        # older versions are missing out!
        if setuptools_version >= (30, 5):
            options['data_files'] = [
                ('share/pixmaps/', ['pympress/share/pixmaps/pympress.png']),
                ('share/applications/', ['pympress/share/applications/io.github.pympress.desktop']),
            ]

        setuptools.setup(**options)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
