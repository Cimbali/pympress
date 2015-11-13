#!/usr/bin/env python
#
#       setup.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
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

version="0.3"

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

#include all Gtk DLLs, because litteraly the only we can skip would save us 104kB, they are:
#libgailutil-3.0.dll, libharfbuzz-gobject-0.dll, libharfbuzz-icu-0.dll, libgthread-2.0.dll
libs_etc += [f for f in os.listdir(include_path) if os.path.splitext(f)[1].lower() == ".dll"]

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
      author="Thomas Jost",
      author_email="thomas.jost@gmail.com",
      url="http://www.pympress.org/",
      download_url="http://github.com/Schnouki/pympress/downloads",
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
