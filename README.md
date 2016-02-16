# What is Pympress?

Pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK+ for the GUI.

It is designed to be a dual-screen reader used for presentations and public talks, with two displays: the *Content window* for a projector, and the *Presenter window* for your laptop. It is portable and has been tested on various Mac, Windows and Linux systems.

It comes with many great features:
- supports embedded videos
- text annotations displayed in the presenter window
- natively supports beamer's *notes on second screen*!

Pympress is a free software, distributed under the terms of the GPL license (version 2 or, at your option, any later version).

This is now a fork of [Schnouki's original Pympress](https://github.com/Schnouki/pympress), at least for now.

# Installing

## From source

Grab [the latest source code](https://github.com/Cimbali/pympress/releases/latest), open a console where you extracted pympress, and type `python setup.py install`. See [the python documentation on installing](https://docs.python.org/3.5/install/#standard-build-and-install) for details. If it doesn't run, check that you have all [the dependencies](https://github.com/Cimbali/pympress#dependencies).

## Binary install

Grab [the latest installer for your platform](https://github.com/Cimbali/pympress/releases/latest) and execute it. You're done!

Currently binaries are only available for windows (.msi files). Choose packages with 'amd64' in the name if you have a 64 bit machine, 'x86' if you have a 32 bit machine. The 'vlc' suffix indicates that this installer ships VLC as well to support video, so try it if the other version fails to read videos.

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
- **Estimated talk time**: Click the `Time estimation` box and set your planned talk duration. You can also pass this on the command line through the `-ett` flag. The color will allow you to see at a glance how much time you have left.
- **Adjust screen centering**: If your slides' form factor doesn't fit the projectors' and you don't want the slide centered in the window, use the "Screen Center" option in the "Presentation" menu.
- **Resize Current/Next slide**: You can drag the bar between both slides on the Presenter window to adjust their relative sizes to your liking.
- **Preferences**: Some of your choices are saved in a configuration file, in *~/.config/pympress* or *~/.pympress* on linux, and in *%APPDATA%/pympress.ini* on windows.
- **Cache**: For efficiency, Pympress caches rendered pages (up to 200 by default). If this is too memory consuming for you, you can change this number in the configuration file.

# Hacking

Feel free to clone this repo and use it, modify it, redistribute it, etc, under the GPLv2+.
Pympress has inline sphinx (rst syntax) documentation, and the gh-pages branch hosts [an online documentation generated from it](https://cimbali.github.io/pympress/pympress.html).

## Dependencies

Pympress relies on:
* Python, 3.x or 2.7 (with [setuptools](https://pypi.python.org/pypi/setuptools), which is usually shipped by default with python).
* [Poppler](http://poppler.freedesktop.org/), the PDF rendering library.
* [Gtk+ 3](http://www.gtk.org/), a toolkit for creating graphical user interfaces.
* [PyGi, the python bindings for Gtk+3](https://wiki.gnome.org/Projects/PyGObject). PyGi is also known as *pygobject3*, just *pygobject* or *python3-gi*.
* optionally VLC, to play videos (with the same bitness as Python)

On windows, both GTK+3 and Poppler are shipped in [the PyGi installer](https://sourceforge.net/projects/pygobjectwin32/).
On other platforms they are often installed by default, or easily available through your package or software manager.

Sometimes you might need to make sure that the introspection bindings for poppler are shipped as well. On OpenSuse for example the packages `python3-gobject` and `typelib-1_0-Poppler-0_18` are needed.