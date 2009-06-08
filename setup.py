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

from distutils.core import setup, Extension
from distutils.command.build import build
from distutils.sysconfig import get_python_inc

import commands, os.path, subprocess

# From pygtkhex
def pkgconfig(*packages, **kw):
    flag_map = {'-I': 'include_dirs', '-L': 'library_dirs', '-l': 'libraries'}
    for token in commands.getoutput("pkg-config --libs --cflags %s" % ' '.join(packages)).split():
        if flag_map.has_key(token[:2]):
            kw.setdefault(flag_map.get(token[:2]), []).append(token[2:])
        else: # throw others to extra_link_args
            kw.setdefault('extra_link_args', []).append(token)
    for k, v in kw.iteritems(): # remove duplicated
        kw[k] = list(set(v))
    return kw

class PopplerBuild(build):
	def run(self):
		DEFS_DIR = commands.getoutput("pkg-config --variable=defsdir pygtk-2.0")

		output = open('poppler-python/poppler.c', 'w')

		subprocess.check_call(["pygobject-codegen-2.0",
			"--override", "poppler-python/poppler.override",
			"--prefix", "poppler",
			"--register", os.path.join(DEFS_DIR, "gdk-types.defs"),
			"poppler-python/poppler.defs"], stdout=output)

		build.run(self)

poppler_deps = pkgconfig("pygtk-2.0 gtk+-2.0 poppler pycairo")
poppler_deps['include_dirs'].append('poppler-python')

pycairo_version = commands.getoutput("pkg-config --modversion pycairo").split(".")
poppler_deps['define_macros'] = [
	('PYCAIRO_MAJOR_VERSION', pycairo_version[0]),
	('PYCAIRO_MINOR_VERSION', pycairo_version[1]),
	('PYCAIRO_MICRO_VERSION', pycairo_version[2]),
]

poppler = Extension('pympress.poppler', ['poppler-python/poppler.c'], **poppler_deps)

version="0.1"

setup(name="pympress",
	version=version,
	description="A simple dual-screen PDF reader designed for presentations",
	author="Thomas Jost",
	author_email="thomas.jost@gmail.com",
	url="http://wiki.schnouki.net/dev:pympress:accueil",
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
	ext_modules=[poppler],
	cmdclass= {'build': PopplerBuild}
)
