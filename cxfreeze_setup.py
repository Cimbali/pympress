#!/usr/bin/env python
#
#       cxfreeze_setup.py
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

from cx_Freeze import setup, Executable
import os, site, sys
import glob

site_dir = site.getsitepackages()[1]

include_path = None
for dir in ["gtk", "gnome"]:
    if os.path.isdir(os.path.join(site_dir, dir)):
        include_path = os.path.join(site_dir, dir)

if include_path is None:
    print("Can not find where the GTK libraries and Python bindings are installed!")
    exit(1)

version="0.5"

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

libs_etc += ['libatk-1.0-0.dll', 'libcairo-gobject-2.dll', 'libepoxy-0.dll',
    'libffi-6.dll', 'libfontconfig-1.dll', 'libfreetype-6.dll', 'libgailutil-3-0.dll',
    'libgdk-3-0.dll', 'libgdk_pixbuf-2.0-0.dll', 'libgio-2.0-0.dll',
    'libgirepository-1.0-1.dll', 'libglib-2.0-0.dll', 'libgmodule-2.0-0.dll',
    'libgobject-2.0-0.dll', 'libgthread-2.0-0.dll', 'libgtk-3-0.dll', 'libharfbuzz-0.dll',
    'libharfbuzz-gobject-0.dll', 'libharfbuzz-icu-0.dll', 'libintl-8.dll', 'libjasper-1.dll',
    'libjpeg-8.dll', 'liblcms2-2.dll', 'libopenjp2.dll', 'libpango-1.0-0.dll',
    'libpangocairo-1.0-0.dll', 'libpangoft2-1.0-0.dll', 'libpangowin32-1.0-0.dll',
    'libpng16-16.dll', 'libpoppler-glib-8.dll', 'librsvg-2-2.dll', 'libstdc++-6.dll',
    'libtiff-5.dll', 'libwebp-5.dll', 'libwinpthread-1.dll', 'libxmlxpat.dll', 'libzzz.dll',
    'python34.dll']

include_files = [(os.path.join(include_path, item), item) for item in libs_etc]

include_files.append( (os.path.join("share", "pixmaps"), os.path.join("share", "pixmaps")) )

buildOptions = dict(
    compressed = False,
    includes = [],
    packages = ["gi"],
    include_files = include_files
)

# base hides python shell window, but beware: this can cause crashes if gi tries to output some warnings
executables = [Executable(os.path.join("bin", "pympress"), base="Win32GUI")]

setup(name="pympress",
      version=version,
      description="A simple dual-screen PDF reader designed for presentations",
      author="Thomas Jost, Cimbali",
      author_email="me@cimba.li",
      url="http://www.pympress.org/",
      download_url="https://github.com/Cimbali/pympress/releases/latest",
      classifiers=[
          'Development Status :: 4 - Beta',
          'Environment :: X11 Applications :: GTK',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Information Technology',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Natural Language :: English',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Topic :: Multimedia :: Graphics :: Presentation',
          'Topic :: Multimedia :: Graphics :: Viewers',
      ],
      packages=["pympress"],
      scripts=["bin/pympress"],
      data_files=[
          ("share/pixmaps", glob.glob("share/pixmaps/pympress*")),
      ],
      options = dict(build_exe = buildOptions),
      executables = executables
)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
