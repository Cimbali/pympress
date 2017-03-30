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

from setuptools import setup
import glob, sys, os.path, importlib

try:
      from pypandoc import convert_file
except ImportError:
      print("WARNING no pypandoc, long description will NOT BE AVAILABLE in rst format")

      from shutil import copyfile
      def convert_file(filename, ext):
            copyfile(filename, os.path.splitext(filename)[0] + '.' + ext)

#get version
pkg_meta = importlib.import_module('pympress.__init__')

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
      entry_points={
        'gui_scripts': [
            'pympress = pympress.__main__:main',
            'pympress{} = pympress.__main__:main'.format(sys.version_info.major),
        ]
      },
      license='GPLv2',
      install_requires=[
          'python-vlc',
      ],
      package_data={
        'pympress': [os.path.join('share', 'xml', '*.glade'), os.path.join('share', 'css', '*.css'), os.path.join('share', 'pixmaps', '*.png')]
        + [f.split(os.path.sep, 1)[1] for f in glob.glob(os.path.join('pympress', 'share', 'locale', '*', 'LC_MESSAGES', 'pympress.mo'))]
      },
)

##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
