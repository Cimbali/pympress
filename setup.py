#!/usr/bin/env python
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

import os, site, sys, importlib
from ctypes.util import find_library
import glob

def open_file(filename):
    with open(filename, 'r') as f:
        return f.read()

try: read_input = raw_input
except NameError: read_input = input


# get Pympress version
pkg_meta = importlib.import_module('pympress.__init__')

# All functions listing resources return a list of pairs: (system path, distribution relative path)

def gtk_resources():
    """ Returns a list of the Gtk resources we need
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
    """ Returns a list of all DLL files we need, for now return them all and sort it later.
    """
    if os.name != 'nt': return []

    # Hardcoded list tested for the appveyor build setup
    libs = 'libatk-2.0-0.dll libbrotlicommon.dll libbrotlidec.dll libcurl-4.dll libdatrie-1.dll \
    libepoxy-0.dll libfribidi-0.dll libgdk-3-0.dll libgdk_pixbuf-2.0-0.dll libgif-7.dll \
    libgio-2.0-0.dll libgirepository-1.0-1.dll libglib-2.0-0.dll libgobject-2.0-0.dll libgtk-3-0.dll \
    libidn2-0.dll libjpeg-8.dll liblcms2-2.dll libnghttp2-14.dll libnspr4.dll libopenjp2-7.dll \
    libpango-1.0-0.dll libpangocairo-1.0-0.dll libpangoft2-1.0-0.dll libpangowin32-1.0-0.dll \
    libplc4.dll libplds4.dll libpoppler-89.dll libpoppler-cpp-0.dll libpoppler-glib-8.dll libpsl-5.dll \
    libpython3.7m.dll libstdc++-6.dll libthai-0.dll libtiff-5.dll libunistring-2.dll libwinpthread-1.dll \
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


def vlc_resources():
    """ Return VLC resources
    """
    import vlc
    buildOptions['packages'].append('vlc')
    print('Found VLC at '+vlc.plugin_path)

    include_files = []
    for f in glob.glob(os.path.join(vlc.plugin_path, '*.txt')):
        base, ext = os.path.splitext(os.path.basename(f))
        include_files.append((f, base + '_VLC' + ext))

    for f in glob.glob(os.path.join(vlc.plugin_path, '*.dll')):
        include_files.append((f, os.path.basename(f)))

    include_files.append((os.path.join(vlc.plugin_path, 'plugins'), 'plugins'))
    return include_files


def pympress_resources():
    """ Return pympress resources
    """
    resources = [os.path.join('share', 'xml'), os.path.join('share', 'pixmaps'), os.path.join('share', 'css')]
    translations = glob.glob(os.path.join('pympress', 'share', 'locale', '*', 'LC_MESSAGES', 'pympress.mo'))
    return [(os.path.join('pympress', f), f) for f in resources] + [(t, t.split(os.path.sep, 1)[1]) for t in translations]


# Options that are common, whichever setup() function we call eventually
setup_opts = dict(name='pympress',
    version=pkg_meta.__version__,
    description=pkg_meta.__doc__.split('\n')[0],
    long_description = open_file('README.md'),
    long_description_content_type = 'text/markdown',
    author='Cimbali, Thomas Jost, Christof Rath, Epithumia',
    author_email='me@cimba.li',
    url='https://github.com/Cimbali/pympress/',
    download_url='https://github.com/Cimbali/pympress/releases/latest',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: Education',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Natural Language :: English',
        'Natural Language :: French',
        'Natural Language :: German',
        'Natural Language :: Polish',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Multimedia :: Graphics :: Presentation',
        'Topic :: Multimedia :: Graphics :: Viewers',
    ],
    license='GPLv2',
    packages=['pympress'],
)


# List of options we support but that aren't part of setuptools/cx_Freeze
homemade_opts = ['--with-vlc', '--without-vlc', '--freeze']


if __name__ == '__main__':
    # Check our options: whether to freeze, and whether to include VLC resources (DLLs, plugins, etc).
    use_cxfreeze = '--freeze' in sys.argv[1:]

    # NB: we always include the vlc package. That way, installing pympress on a system
    # that has VLC installed works out of the box, without redistributing it.
    include_vlc = True if '--with-vlc' in sys.argv[1:] else \
            False if '--without-vlc' in sys.argv[1:] or not use_cxfreeze else None

    # cleanup argv for setup()
    for opt in homemade_opts:
        try: sys.argv.remove(opt)
        except ValueError: pass


    # If unclear, interactively ask whether we include VLC
    while include_vlc is None:
        answer = read_input('Include VLC in the package? [y/N] ').lower()
        if answer in {'y', 'n', ''}:
            include_vlc = answer == 'y'


    # List all resources we'll distribute
    include_files = gtk_resources() + dlls() + pympress_resources() if use_cxfreeze else []

    if include_vlc:
        try:
            include_files += vlc_resources()
        except ImportError:
            print('ERROR: VLC python module not available!')
            exit(-1)
        except Exception as e:
            print('ERROR: Cannot include VLC: ' + str(e))
            exit(-1)


    if not use_cxfreeze:
        print('Using setuptools.setup():')
        from setuptools import setup
        setup_opts.update(dict(entry_points={'gui_scripts': [
                'pympress = pympress.__main__:main',
                'pympress{} = pympress.__main__:main'.format(sys.version_info.major),
            ]},
            install_requires=['python-vlc', 'watchdog', 'enum34;python_version<"3.4"'],
            package_data={'pympress':
                [os.path.join('share', 'xml', '*.glade'), os.path.join('share', 'css', '*.css'), os.path.join('share', 'pixmaps', '*.png')]
                + [f.split(os.path.sep, 1)[1] for f in glob.glob(os.path.join('pympress', 'share', 'locale', '*', 'LC_MESSAGES', 'pympress.mo'))]
            }
        ))

    else:
        print('Using cx_Freeze.setup():',)
        from cx_Freeze import setup, Executable
        setup_opts.update(dict(options = {'build_exe':{
              'includes': [],
              'excludes': [],
              'packages': ['codecs', 'gi', 'packaging', 'six', 'appdirs', 'vlc', 'watchdog'],
              'include_files': include_files,
              'silent': True
          }},
          executables = [Executable(os.path.join('pympress', '__main__.py'), targetName='pympress.exe', base='Win32GUI')]
        ))

    setup(**setup_opts)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
