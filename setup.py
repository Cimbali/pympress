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
import sys
import glob
from ctypes.util import find_library
import setuptools

from setuptools.command.develop import develop
from setuptools.command.install import install
from setuptools.command.bdist_rpm import bdist_rpm


class PatchedRpmDist(bdist_rpm):
    """ Patched bdist rpm to avoid running seds and breaking up the build system
    """
    def _make_spec_file(self):
        # Make the package name python3-pympress instead of pympress
        # NB: %{name} evaluates to the RPM package name
        spec = [
            line.replace('%{name}', '%{pythonname}')
                .replace('define name ', 'define pythonname ')
                .replace('Name: %{pythonname}', 'Name: python3-%{pythonname}')
            for line in bdist_rpm._make_spec_file(self)
            if not line.startswith('Group:')
        ]
        insert_pos = spec.index('', 6)
        # Define what this package provides a little more specifically
        spec.insert(insert_pos, 'Provides: python3dist(%{pythonname}) = %{version}')
        spec.insert(insert_pos + 1, 'Provides: python%{python3_version}dist(%{pythonname}) = %{version}')
        # For Fedora, this adds python-name to provides if python3 is the default
        spec.insert(insert_pos + 2, '%{?python_provide:%python_provide python3-%{pythonname}}')
        return spec


class PatchedDevelop(develop):
    """ Patched installation for development mode to build translations .mo files. """
    def run(self):
        """ Run compile_catalog before running (parent) develop command. """
        self.distribution.run_command('compile_catalog')
        develop.run(self)

class PatchedInstall(install):
    """Patched installation for installation mode to build translations .mo files. """
    def run(self):
        """ Run compile_catalog before running (parent) install command. """
        if not self.single_version_externally_managed:
            self.distribution.run_command('compile_catalog')
        install.run(self)


# All functions listing resources return a list of pairs: (system path, distribution relative path)
def gtk_resources():
    """ Returns a list of the non-DLL Gtk resources to include in a frozen/binary package.
    """
    base, last = os.path.split(os.path.dirname(find_library('libgtk-3-0')))
    include_path = base if last in {'bin', 'lib', 'lib64'} else os.path.join(base, last)

    include_files = []
    resources = [
        'etc',
        os.path.join('lib', 'girepository-1.0'),
        os.path.join('lib', 'gtk-3.0'),
        os.path.join('lib', 'gdk-pixbuf-2.0'),
        os.path.join('share', 'poppler'),
        os.path.join('share', 'themes'),
        os.path.join('share', 'icons'),
        os.path.join('share', 'glib-2.0'),
        os.path.join('share', 'xml')
    ]

    for f in resources:
        p = os.path.join(include_path, f)
        if os.path.exists(p):
            include_files.append((p, f))
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
    libplc4.dll libplds4.dll libpoppler-94.dll libpoppler-cpp-0.dll libpoppler-glib-8.dll libpsl-5.dll \
    libpython3.8.dll libstdc++-6.dll libthai-0.dll libtiff-5.dll libunistring-2.dll libwinpthread-1.dll \
    libzstd.dll nss3.dll nssutil3.dll smime3.dll'
    # these appear superfluous, though unexpectedly so:
    # libcairo-2.dll libcairo-gobject-2.dll libfontconfig-1.dll libfreetype-6.dll libiconv-2.dll
    # libgettextlib-0-19-8-1.dll libgettextpo-0.dll libgettextsrc-0-19-8-1.dll libintl-8.dll libjasper-4.dll

    include_files = []
    for lib in libs.split():
        path = find_library(lib)
        if path and os.path.exists(path):
            include_files.append((path, lib))
        else:
            print('WARNING: Can not find library {}'.format(lib))

    return include_files


def check_vlc_redistribution():
    """ We might want to redistribute the VLC library (DLLs etc.) with pympress.

        NB: we always depend on the vlc python package. That way, installing
        pympress on a system that has VLC installed works out of the box,
        even without redistributing it.

    Returns (bool): whether to include VLC redistributables
                    (decided from command line arguments or prompt).
    """
    opts = {'--with-vlc': True, '--without-vlc': False}

    for opt, val in opts.items():
        if opt in sys.argv[1:]:
            sys.argv.remove(opt)
            return val

    # If unclear, interactively ask whether we include VLC
    while True:
        answer = input('Include VLC in the package? [y/N] ').lower()
        if answer in {'y', 'n', ''}:
            return answer == 'y'


def vlc_resources():
    """ Return the list of VLC resources (DLLs, plugins, license file...) to redistribute.
    """
    import vlc
    print('Found VLC at ' + vlc.plugin_path)

    include_files = []
    for f in glob.glob(os.path.join(vlc.plugin_path, '*.txt')):
        base, ext = os.path.splitext(os.path.basename(f))
        include_files.append((f, base + '_VLC' + ext))

    for f in glob.glob(os.path.join(vlc.plugin_path, '*.dll')):
        include_files.append((f, os.path.basename(f)))

    base, last = os.path.split(vlc.plugin_path)
    plugin_dir = os.path.join(base, 'lib', 'vlc', 'plugins') if last == 'bin' else os.path.join(base, last, 'plugins')
    include_files.append((plugin_dir, 'plugins'))
    return include_files


def pympress_resources():
    """ Return pympress resources. Only for frozen packages, as this is redundant with package_data.
    """
    resources = [os.path.join('pympress', 'share', 'xml'), os.path.join('pympress', 'share', 'pixmaps'),
                 os.path.join('pympress', 'share', 'css'), os.path.join('pympress', 'share', 'defaults.conf')]
    translations = glob.glob(os.path.join('pympress', 'share', 'locale', '*', 'LC_MESSAGES', 'pympress.mo'))
    return [(f, f.split(os.path.sep, 1)[1]) for f in resources + translations]


if __name__ == '__main__':

    # Check our options: whether to freeze, and whether to include VLC resources (DLLs, plugins, etc).
    if '--freeze' in sys.argv[1:]:
        sys.argv.remove('--freeze')

        print('Using cx_Freeze.setup():', file=sys.stderr)
        from cx_Freeze import setup, Executable

        # List all resources we'll distribute
        setup_opts = {
            'options': {
                'build_exe': {
                    'includes': [],
                    'excludes': ['tkinter'],
                    'packages': ['codecs', 'gi', 'vlc', 'watchdog'],
                    'include_files': gtk_resources() + dlls() + pympress_resources(),
                    'silent': True
                }
            },
            'executables': [Executable(os.path.join('pympress', '__main__.py'), targetName='pympress.exe',
                                       base='Win32GUI', shortcutDir='ProgramMenuFolder', shortcutName='pympress',
                                       icon=os.path.join('pympress', 'share', 'pixmaps', 'pympress.ico'))]
        }

        if check_vlc_redistribution():
            try:
                setup_opts['options']['build_exe']['include_files'] += vlc_resources()
            except ImportError:
                print('ERROR: VLC python module not available!')
                exit(-1)
            except Exception as e:
                print('ERROR: Cannot include VLC: ' + str(e))
                exit(-1)

        setup(**setup_opts)
    else:
        # Normal behaviour: use setuptools, load options from setup.cfg
        print('Using setuptools.setup():', file=sys.stderr)

        setuptools.setup(cmdclass = {'develop': PatchedDevelop, 'install': PatchedInstall, 'bdist_rpm': PatchedRpmDist})


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
