# What is Pympress?

Pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK+ for the GUI.

It is designed to be a dual-screen reader used for presentations and public talks, with two displays: the *Content window* for a projector, and the *Presenter window* for your laptop. It also supports beamer's *notes on second screen*!

Pympress is a free software, distributed under the terms of the GPL license (version 2 or, at your option, any later version).

# How-to install

All dependencies are really basic, and installation is standard for a python package.

## Dependencies

You will need:
* Python 3.x, with [setuptools](https://pypi.python.org/pypi/setuptools)
* [PyGi, the python bindings for GTK+3](https://wiki.gnome.org/Projects/PyGObject), which itself depends on GTK+3, cairo, etc. PyGi is also known as *pygobject3*, just *pygobject* or *python3-gi*.
* [Poppler, the PDF rendering library](http://poppler.freedesktop.org/), which is available in every good package manager.

On windows, both GTK+3 and Poppler are shipped in the PyGi installer.

## Installing

Open any console where you extracted pympress, and type `python setup.py install`. See [the python documentation on installing](https://docs.python.org/3.5/install/#standard-build-and-install) for details.

# Usage

## Opening a file
Simply start Pympress and it will ask you what file you want to open.
You can also start pympress from the command line with a file to open like so:
`pympress slides.pdf`

## Functionalities

All functionalities are available from the menus of the window with slide previews. Don't be afraid to experiment with them!

Keyboard shortcuts are also listed in these menus. Some more usual shortcuts are often available, for example `Ctrl`+`L`, and `F11` also toggle fullscreen, though the main shortcut is just `F`.

A few of the fancier functionalities are listed here:
- **Swap screens**: If Pympress mixed up which screen is the projector and which is not, press `S`
- **Go To Slide**: To jump to a selected slide without flashing through the whole presentation on the projector, press `G` or click the "current  slide" box.

  A spin box will appear, and you will be able to navigate through your slides in the presenter window only by scrolling your mouse, with the `Home`/`Up`/`Down`/`End` keys, with the + and - buttons of the spin box, or simply by typing in the number of the slide. Press `Enter` to validate going to the new slide or `Esc` to cancel.
- **Adjust screen centering**: If your slides' form factor doesn't fit the projectors' and you don't want the slide centered in the window, use the "Screen Center" option in the "Presentation" menu.
- **Resize Current/Next slide**: You can drag the bar between both slides on the Presenter window to adjust their relative sizes to your liking.
- **Preferences**: Some of your choices are saved in a configuration file, in *~/.config/pympress* or *~/.pympress* on linux, and in *%APPDATA%/pympress.ini* on windows.
- **Cache**: For efficiency, Pympress caches rendered pages (up to 200 by default). If this is too memory consuming for you, you can change this number in the configuration file.

# Hacking

Feel free to clone this repo and use it, modify it, redistribute it, etc, under the GPLv2+.
Pympress has sphinx inline (rst-syntax) documentation, and the gh-pages branch hosts [an online documentation generated from it](https://rawgit.com/Cimbali/pympress/gh-pages/pympress.html).

