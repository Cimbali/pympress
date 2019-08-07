# What is Pympress?

Pympress is a little PDF reader written in Python using Poppler for PDF rendering and GTK+ for the GUI.

It is designed to be a dual-screen reader used for presentations and public talks, with two displays: the *Content window* for a projector, and the *Presenter window* for your laptop. It is portable and has been tested on various Mac, Windows and Linux systems.

It comes with many great features ([more below](#functionalities)):
- supports embedded videos
- text annotations displayed in the presenter window
- natively supports beamer's *notes on second screen*!

Pympress is a free software, distributed under the terms of the GPL license (version 2 or, at your option, any later version).

Pympress was originally created and maintained by [Schnouki](https://github.com/Schnouki), on [his repo](https://github.com/Schnouki/pympress).

Here is what the 2 screen setup looks like, with a big notes slide next to 2 small slides (current and next) on the presenter side:
![A screenshot with Pympress’ 2 screens](https://repository-images.githubusercontent.com/42637225/925da680-886b-11e9-9a12-28b48debbf19)

# Installing

## Using pip (requires python)

This technique is preferred on Linux and macOS, and also requires you to have all [the dependencies](#dependencies). On Windows, it is easier to use the [binary installer](#binary-install-currently-only-for-windows).

### From PyPI (the Python Package Index)

Run the following command in your shell (or replace `python3 -m pip` with `python -m pip` or just `pip`, and ):

    python3 -m pip install pympress

Or you can get it from github:

    python3 -m pip install git+https://github.com/Cimbali/pympress#egg=pympress

If you don't have pip, see [the python documentation on installing](https://docs.python.org/3.7/installing/index.html).

### From source

If you also want the source code, you can clone this repo or grab [the latest releases' source](https://github.com/Cimbali/pympress/releases/latest), open a console where you put the code, and type `python3 -m pip install .` (or, if you plan on modifying that code, `python3 -m pip install -e .`).

## Binary install (currently only for windows)

Grab [the latest installer for your platform](https://github.com/Cimbali/pympress/releases/latest) and execute it.
If you don't want to know about source code or dependencies, this is for you.

Packages with 'amd64' in the name are for 64 bit machines, 'x86' for 32 bit machines. The 'vlc' suffix indicates that the installer ships VLC as well, so try it if the other version fails to read videos.

If you get an error message along the lines of "MSVCP100.dll is missing", get the Visual C++ 2010 redistributables from Microsoft ([x86 (32 bit)](https://www.microsoft.com/en-in/download/details.aspx?id=5555) or [x64 (64 bits)](https://www.microsoft.com/en-us/download/details.aspx?id=14632)). Those libraries really should already be installed on your system.

# Usage

## Opening a file
Simply start Pympress and it will ask you what file you want to open.
You can also start pympress from the command line with a file to open like so:
`pympress slides.pdf`
or
`python3 -m pympress slides.pdf`

## Functionalities

All functionalities are available from the menus of the window with slide previews. Don't be afraid to experiment with them!

Keyboard shortcuts are also listed in these menus. Some more usual shortcuts are often available, for example `Ctrl`+`L`, and `F11` also toggle fullscreen, though the main shortcut is just `F`.

A few of the fancier functionalities are listed here:
- **Two-screen display**: See on your laptop or tablet display the current slide, the next slide, the talk time and wall-clock time, and annotations (either PDF annotations, or beamer notes on second slide). The position of the beamer notes in the slide is detected automatically and can be overriden via a menu option.
- **Media support**: supports playing video, audio, and gif files embedded in (or linked from) the PDF file.
- **Highlight mode**: Allows to draw freehand on the slide currently on screen.
- **Go To Slide**: To jump to a selected slide without flashing through the whole presentation on the projector, press `G` or click the "current  slide" box.
  Using `J` or clicking the slide label will allow you to navigate slide labels instead of page numbers, useful e.g. for multi-page slides from beamer `\pause`.

  A spin box will appear, and you will be able to navigate through your slides in the presenter window only by scrolling your mouse, with the `Home`/`Up`/`Down`/`End` keys, with the + and - buttons of the spin box, or simply by typing in the number of the slide. Press `Enter` to validate going to the new slide or `Esc` to cancel.
  
- **Software pointer**: Clicking on the slide (in either window) while holding `ctrl` down will display a software laser pointer on the slide.
- **Talk time breakdown**: The `Presentation > Timing Breakdown` menu item displays a breakdown of how much time was spent on each slide, with a hierarchical breakdown per chapters/sections/etc. if available in the PDF.
- **Automatic file reloading**: If the file is modified, pympress will reload it (and preserve the current slide, current time, etc.)
- **Big button mode**: Add big buttons (duh) for touch displays.
- **Swap screens**: If Pympress mixed up which screen is the projector and which is not, press `S`
- **Estimated talk time**: Click the `Time estimation` box and set your planned talk duration. The color will allow you to see at a glance how much time you have left.
- **Adjust screen centering**: If your slides' form factor doesn't fit the projectors' and you don't want the slide centered in the window, use the "Screen Center" option in the "Presentation" menu.
- **Resize Current/Next slide**: You can drag the bar between both slides on the Presenter window to adjust their relative sizes to your liking.
- **Preferences**: Some of your choices are saved in a configuration file, in *~/.config/pympress* or *~/.pympress* on linux, and in *%APPDATA%/pympress.ini* on windows.
- **Caching**: For efficiency, Pympress caches rendered pages (up to 200 by default). If this is too memory consuming for you, you can change this number in the configuration file.

## Command line arguments

-  `-h, --help`: Shows a list of all command line arguments.
- `-t mm[:ss], --talk-time=mm[:ss]`: The estimated (intended) talk time in minutes and optionally seconds.
- `-n position, --notes=position`: Set the position of notes on the pdf page (none, left, right, top, or bottom). Overrides the detection from the file.
- `--log=level`: Set level of verbosity in log file (DEBUG, INFO, WARNING, ERROR).

# Dependencies

Pympress relies on:
* Python, 3.x or 2.7 (with [setuptools](https://pypi.python.org/pypi/setuptools), which is usually shipped by default with python).
* [Poppler](http://poppler.freedesktop.org/), the PDF rendering library.
* [Gtk+ 3](http://www.gtk.org/), a toolkit for creating graphical user interfaces, and [its dependencies](https://www.gtk.org/overview.php), specifically:
  * [Cairo](https://www.cairographics.org/) (and python bindings for cairo), the graphics library which is used to pre-render and draw over PDF pages.
  * Gdk, a lower-level graphics library to handle icons.
* [PyGi, the python bindings for Gtk+3](https://wiki.gnome.org/Projects/PyGObject). PyGi is also known as *pygobject3*, just *pygobject* or *python3-gi*.
  * Introspection bindings for poppler may be shipped separately, ensure you have those as well (`typelib-1_0-Poppler-0_18` on OpenSUSE, `gir1.2-poppler-0.18` on Ubuntu)
* optionally [VLC](https://www.videolan.org/vlc/), to play videos (with the same bitness as Python)

### On linux platforms
The dependencies are often installed by default, or easily available through your package or software manager.
For example, on ubuntu, you can run the following as root to make sure you have all the prerequisites *assuming you use python3*:

    apt-get install python3 python3-pip libgtk-3-0 libpoppler-glib8 libcairo2 python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-poppler-0.18

Different distributions might have different package naming conventions, for example the equivalent on OpenSUSE would be:

    zypper in python3 python3-pip libgtk-3-0 libpoppler-glib8 libcairo2 python3-gobject python3-gobject-Gdk python3-cairo python3-gobject-cairo typelib-1_0-GdkPixbuf-2_0 typelib-1_0-Gtk-3_0 typelib-1_0-Poppler-0_18

### On macOS

Dependencies can be installed using [Homebrew](https://brew.sh/):

    brew install gtk+3 poppler gobject-introspection pygobject3

### On windows
The [binary installer for windows](#binary-install-currently-only-for-windows) comes with pympress and all its dependencies packaged.

In order to install from pypi or from source on windows, there are two ways to get the dependencies:

1. using MSYS2 (replace x86_64 with i686 if you're using a 32 bit machine).

   **Warning:** this can take a substantial amount of disk size as it requires a full software distribution and building platform.

        pacman -S --needed mingw-w64-x86_64-gtk3 mingw-w64-x86_64-cairo mingw-w64-x86_64-poppler mingw-w64-x86_64-python3 mingw-w64-x86_64-vlc python3-pip mingw-w64-x86_64-python3-pip mingw-w64-x86_64-python3-gobject mingw-w64-x86_64-python3-cairo

2. Using PyGobjectWin32. *Be sure to check the supported Python versions (up to 3.4 at the time of writing)*, they appear in the FEATURES list in the linked page.
  - Install native [python for windows](https://www.python.org/downloads/windows/)
  - Get GTK+3, Poppler and their python bindings by executing [the PyGi installer](https://sourceforge.net/projects/pygobjectwin32/).  Be sure to tick all the necessary dependencies in the installer (Poppler, Cairo, Gdk-Pixbuf).

Alternately, you can build your Gtk+3 stack from source using MSVC, see [the Gnome wiki](https://wiki.gnome.org/Projects/GTK+/Win32/MSVCCompilationOfGTKStack) and [this python script that compiles the whole Gtk+3 stack](https://github.com/wingtk/gvsbuild/).

# Contributing

Feel free to clone this repo and use it, modify it, redistribute it, etc, under the GPLv2+.
Pympress has inline sphinx documentation ([Google style](http://www.sphinx-doc.org/en/latest/ext/example_google.html), contains rst syntax), and the [docs folder](https://github.com/Cimbali/pympress/tree/master/docs/) contains the documentation generated from it, hosted on [the github pages of this repo](https://cimbali.github.io/pympress/pympress.html).

## Translations

If you want to add a translation, check if `pympress/share/locale/<language>/pympress.po` already exists. If not, take [the template file](https://github.com/Cimbali/pympress/tree/master/pympress/share/locale/pympress.pot) as input and translate all the strings, then add it to the repo in `pympress/share/locale/<language>/pympress.po`.
Finally pass this .po file to msgfmt and add the output to the repo at `pympress/share/locale/<language>/LC_MESSAGES/pympress.mo`.
