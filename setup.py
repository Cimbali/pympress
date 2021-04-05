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
import glob
from ctypes.util import find_library
import setuptools

from setuptools.command.develop import develop
from setuptools.command.install import install
from setuptools.command.bdist_rpm import bdist_rpm


def find_index_startstring(haystack, needle, start = 0, stop = sys.maxsize):
    """ Return the index of the first string in haystack starting with needle, or raise ValueError if none match.
    """
    try:
        return next(n for n, v in enumerate(haystack[start:stop], start) if v.startswith(needle))
    except StopIteration:
        raise ValueError('No string starts with ' + needle)


class PatchedRpmDist(bdist_rpm):
    """ Patched bdist rpm to avoid running seds and breaking up the build system
    """

    user_options = bdist_rpm.user_options + [
        ('recommends=', None, "capabilities recommendd by this package"),
        ('suggests=', None, "capabilities suggestd by this package"),
    ]

    recommends = None
    suggests = None

    def finalize_package_data(self):
        """ Add recommends/suggests option validation
        """
        bdist_rpm.finalize_package_data(self)

        self.ensure_string_list('recommends')
        self.ensure_string_list('suggests')


    def _make_spec_file(self):
        # Make the package name python3-pympress instead of pympress
        # NB: %{name} evaluates to the RPM package name
        spec = [
            line.replace('%{name}', '%{pythonname}')
                .replace('define name ', 'define pythonname ')
                .replace('Name: %{pythonname}', 'Name: python3-%{pythonname}')
            for line in bdist_rpm._make_spec_file(self) if not line.startswith('Group:')
        ]

        insert_pos = find_index_startstring(spec, 'Requires:') + 1
        insert = [
            # Define what this package provides in terms of capabilities
            'Provides: python3dist(%{pythonname}) = %{version}',
            'Provides: python%{python3_version}dist(%{pythonname}) = %{version}',

            # For Fedora, this adds python-name to provides if python3 is the default
            '%{?python_provide:%python_provide python3-%{pythonname}}',
        ]

        if self.recommends:
            insert.append('Recommends: ' + ' '.join(self.recommends))

        if self.suggests:
            insert.append('Suggests: ' + ' '.join(self.suggests))

        # Roll our own py3_dist if it doesn’t exist on this platform, only for requires.
        # Also define typelib_deps if we are on suse or mageia, to specify dependencies using typelib capabilities.
        return [
            '%define normalize() %(echo %* | tr "[:upper:]_ " "[:lower:]--")',
            '%{?!py3_dist:%define py3_dist() (python%{python3_version}dist(%{normalize %1}) or python3-%1)}',
            '%{?suse_version:%define typelib_deps 1}', '%{?mga_version:%define typelib_deps 1}', ''
        ] + spec[:insert_pos] + insert + spec[insert_pos:]



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

    include_files = [(find_library('gdbus.exe'), os.path.join('lib', 'gi', 'gdbus.exe'))]
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
    libplc4.dll libplds4.dll libpoppler-105.dll libpoppler-cpp-0.dll libpoppler-glib-8.dll libpsl-5.dll \
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
            lib_root, lib_ext = os.path.splitext(lib)
            find_glob = list(glob.glob(os.path.join(
                os.path.dirname(find_library('libgtk-3-0')),  # other directories to look in ?
                re.sub('-[0-9.]*$', '-*', lib_root) + lib_ext
            )))
            if len(find_glob) == 1:
                found_path = find_glob[0]
                found_lib = os.path.basename(found_path)
                include_files.append((path, lib))
                print('WARNING: Can not find library {}, including {} instead'.format(lib, found_lib))
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

    options = {}

    # subtle tweak: don’t put an install section in installed packages
    with open('README.md') as f:
        readme = f.readlines()

        install_section = find_index_startstring(readme, '# Install')
        next_section = find_index_startstring(readme, '# ', install_section + 1)
        del readme[install_section:next_section]

        options['long_description'] = ''.join(readme)


    # Check our options: whether to freeze, and whether to include VLC resources (DLLs, plugins, etc).
    if '--freeze' in sys.argv[1:]:
        sys.argv.remove('--freeze')

        print('Using cx_Freeze.setup():', file=sys.stderr)
        from cx_Freeze import setup, Executable

        # List all resources we'll distribute
        setup_opts = {
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
                    # 'target_name': 'pympress-{version}-{arch}.msi'.format(...),
                    # 'data': {}, #  arbitrary MSI data by table name, 1 tuple per row
                }
            },
            'executables': [
                Executable(os.path.join('pympress', '__main__.py'), target_name='pympress-gui.exe',
                           base='Win32GUI', shortcut_dir='ProgramMenuFolder', shortcut_name='pympress',
                           icon=os.path.join('pympress', 'share', 'pixmaps', 'pympress.ico')),
                Executable(os.path.join('pympress', '__main__.py'), target_name='pympress.exe',
                           base='Console', icon=os.path.join('pympress', 'share', 'pixmaps', 'pympress.ico')),
            ]
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

        options['cmdclass'] = {'develop': PatchedDevelop, 'install': PatchedInstall, 'bdist_rpm': PatchedRpmDist}

        setuptols_version = tuple(int(n) for n in setuptools.__version__.split('.'))
        # older versions are missing out!
        if setuptols_version >= (30, 5):
            options['data_files'] = [
                ('share/pixmaps/', ['pympress/share/pixmaps/pympress.png']),
                ('share/applications/', ['pympress/share/applications/pympress.desktop']),
            ]

        setuptools.setup(**options)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
