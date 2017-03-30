#!/usr/bin/env python
#
#       cxfreeze_setup.py
#
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

from cx_Freeze import setup, Executable
import os, site, sys, importlib
import glob

try:
      from pypandoc import convert_file
except ImportError:
      print("WARNING no pypandoc, long description will NOT BE AVAILABLE in rst format")

      from shutil import copyfile
      def convert_file(filename, ext):
            copyfile(filename, os.path.splitext(filename)[0] + '.' + ext)


IS_POSIX = os.name == 'posix'
IS_MAC_OS = sys.platform == 'darwin'
IS_WINDOWS = os.name == 'nt'

install_dir, site_dir = site.getsitepackages()[:2]

include_path = None
for dir in ['gtk', 'gnome']:
    if os.path.isdir(os.path.join(site_dir, dir)):
        include_path = os.path.join(site_dir, dir)

if include_path is None:
    print('Can not find where the GTK libraries and Python bindings are installed!')
    exit(1)

#get version
pkg_meta = importlib.import_module('pympress.__init__')

include_files=[]
libs_etc = [
    'etc',
    os.path.join('lib', 'girepository-1.0'),
    os.path.join('lib', 'gtk-3.0'),
    os.path.join('share', 'poppler'),
    os.path.join('share', 'themes'),
    os.path.join('share', 'icons'),
    os.path.join('share', 'fonts'),
    os.path.join('share', 'glib-2.0'),
    os.path.join('share', 'xml')
]

if IS_WINDOWS:
    # This is all relatively hardcoded and only tested with Python3.4/PyGobjet3.18
    # for example sometimes we need libstdc++-6.dll, other times libstdc++.dll
    libs_etc += ['libatk-1.0-0.dll', 'libcairo-gobject-2.dll', 'libepoxy-0.dll',
    'libffi-6.dll', 'libfontconfig-1.dll', 'libfreetype-6.dll', 'libgailutil-3-0.dll',
    'libgdk-3-0.dll', 'libgdk_pixbuf-2.0-0.dll', 'libgio-2.0-0.dll',
    'libgirepository-1.0-1.dll', 'libglib-2.0-0.dll', 'libgmodule-2.0-0.dll',
    'libgobject-2.0-0.dll', 'libgthread-2.0-0.dll', 'libgtk-3-0.dll', 'libharfbuzz-0.dll',
    'libharfbuzz-gobject-0.dll', 'libharfbuzz-icu-0.dll', 'libintl-8.dll', 'libjasper-1.dll',
    'libjpeg-8.dll', 'liblcms2-2.dll', 'libopenjp2.dll', 'libpango-1.0-0.dll',
    'libpangocairo-1.0-0.dll', 'libpangoft2-1.0-0.dll', 'libpangowin32-1.0-0.dll',
    'libpng16-16.dll', 'libpoppler-glib-8.dll', 'librsvg-2-2.dll', 'libstdc++.dll',
    'libtiff-5.dll', 'libwebp-5.dll', 'libwinpthread-1.dll', 'libxmlxpat.dll', 'libzzz.dll',
    'libintl-8.dll']

    python_dll='python{}{}.dll'.format(sys.version_info.major, sys.version_info.minor)
    for d in [install_dir, include_path, os.environ['SYSTEMROOT'],
        os.path.join(os.environ['SYSTEMROOT'], 'System32'),
        os.path.join(os.environ['SYSTEMROOT'], 'SysWOW64')]:

        if os.path.isfile(os.path.join(d, python_dll)):
            include_files.append(os.path.join(d, python_dll))
            break

include_files += [(os.path.join(include_path, item), item) for item in libs_etc]
include_files.append( (os.path.join('pympress', 'share', 'xml'), os.path.join('share', 'xml')) )
include_files.append( (os.path.join('pympress', 'share', 'css'), os.path.join('share', 'css')) )
include_files.append( (os.path.join('pympress', 'share', 'pixmaps'), os.path.join('share', 'pixmaps')) )
include_files += [(f,  f.split(os.path.sep, 1)[1]) for f in glob.glob(os.path.join('pympress', 'share', 'locale', '*', 'LC_MESSAGES', 'pympress.mo'))]

buildOptions = dict(
    compressed = False,
    includes = [],
    excludes = [],
    packages = ['gi', 'vlc'],
    include_files = include_files,
    silent = True
)

include_vlc = None
while include_vlc not in ['y', 'n', '']:
    try:
        include_vlc=raw_input('Include VLC in the package? [y/N] ')
    except NameError:
        include_vlc=input('Include VLC in the package? [y/N] ')

if include_vlc == 'y':
    try:
        import vlc
        buildOptions['packages'].append('vlc')
        print('Found VLC at '+vlc.plugin_path)

        for f in glob.glob(os.path.join(vlc.plugin_path, '*.txt')):
            base, ext = os.path.splitext(os.path.basename(f))
            include_files.append((f, base + '_VLC' + ext))

        for f in glob.glob(os.path.join(vlc.plugin_path, '*.dll')):
            include_files.append((f, os.path.basename(f)))

        include_files.append((os.path.join(vlc.plugin_path, 'plugins'), ('plugins')))
    except ImportError:
        print('ERROR: VLC python module not available!')
        exit(-1)
    except Exception as e:
        print('ERROR: Cannot include VLC: ' + str(e))
        exit(-1)

# base hides python shell window, but beware: this can cause crashes if gi tries to output some warnings
executable = Executable(os.path.join('pympress', '__main__.py'), targetName='pympress.exe', base='Win32GUI')

setup(name='pympress',
      version=pkg_meta.__version__,
      description='A simple dual-screen PDF reader designed for presentations',
      long_description = convert_file('README.md', 'rst'),
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
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Topic :: Multimedia :: Graphics :: Presentation',
          'Topic :: Multimedia :: Graphics :: Viewers',
      ],
      packages=['pympress'],
      options = dict(build_exe = buildOptions),
      executables = [executable]
)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
