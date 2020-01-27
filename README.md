# ![Pympress logo](https://raw.githubusercontent.com/Cimbali/pympress/master/pympress/share/pixmaps/pympress-32.png) What is Pympress?

Pympress is a PDF presentation tool designed for dual-screen setups such as presentations and public talks.
Highly configurable, fully-featured, and portable

It comes with many great features ([more below](#functionalities)):
- supports embedded gifs and videos
- text annotations displayed in the presenter window
- natively supports beamer's *notes on second screen*!

Pympress is a free software, distributed under the terms of the GPL license (version 2 or, at your option, any later version).

Pympress was originally created and maintained by [Schnouki](https://github.com/Schnouki), on [his repo](https://github.com/Schnouki/pympress).

Here is what the 2 screen setup looks like, with a big notes slide next to 2 small slides (current and next) on the presenter side:
![A screenshot with Pympress’ 2 screens](https://repository-images.githubusercontent.com/42637225/925da680-886b-11e9-9a12-28b48debbf19)

# Installing

- Ubuntu 20.04 focal or newer, Debian 11 Bullseye or newer:

      apt-get install pympress libgtk-3-0 libpoppler-glib8 libcairo2 python3-gi python3-gi-cairo gobject-introspection libgirepository-1.0-1 gir1.2-gtk-3.0 gir1.2-poppler-0.18

- Arch Linux (from AUR):

      git clone https://aur.archlinux.org/python-pympress.git
      cd python-pympress
      makepkg -si
      pacman -S poppler-glib  # dependency temporarily missing from AUR package

  Or using any other tool to manage AUR packages (yay, pacaur, etc.):

      yay -S pympress
      pacman -S poppler-glib  # dependency temporarily missing from AUR package

- Other Linux, requires [python, gtk+3, poppler, and their python bindings](#dependencies):

      pip install pympress

- macOS, using [Homebrew](https://brew.sh/):

      brew install pympress

- Windows, with [Chocolatey](https://chocolatey.org/):

      choco install pympress

  Or download the installer from the [latest Github release](https://github.com/Cimbali/pympress/releases/latest).

### Notes
- To support playing embedded videos in the PDFs, your system must have VLC installed (with the same bitness as pympress). VLC is not distributed with pympress, but it is certainly available in your system’s package manager and [on their website](https://www.videolan.org/vlc/).
- On Linux, make sure you have all [the dependencies](#dependencies), as they do not come via pip. (On Windows and macOS, they are included in the package.)
- Using pip, you may want to use `python3 -m pip` as the command if `pip` points to the python 2.x pip. You may also want to install with the `--user` option, or install from github or downloaded sources. See [the python documentation on installing](https://docs.python.org/3.7/installing/index.html) for more details.

### Troubleshooting
- If your python environment lacks the Gobject Introspections module, try
   1. checking you have all [the dependencies](#dependencies),
   2. using `--system-site-packages` for [virtual environments](https://docs.python.org/3.7/library/venv.html),
   3. installing pygobject from pip (`pip install pygobject`, which requires the correct development/header packages. See [the PyPI installation instructions of PyGObject for your system](https://pygobject.readthedocs.io/en/latest/getting_started.html)).
- For manually downloaded installers, if you get an error message along the lines of "MSVCP100.dll is missing", get the Visual C++ 2010 redistributables from Microsoft ([x86 (32 bit)](https://www.microsoft.com/en-in/download/details.aspx?id=5555) or [x64 (64 bits)](https://www.microsoft.com/en-us/download/details.aspx?id=14632)). Those libraries really should already be installed on your system.


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
- **Two-screen display**: See on your laptop or tablet display the current slide, the next slide, the talk time and wall-clock time, and annotations (either PDF annotations, or beamer notes on second slide). The position of the beamer notes in the slide is detected automatically and can be overridden via a menu option.
- **Media support**: supports playing video, audio, and gif files embedded in (or linked from) the PDF file.
- **Highlight mode**: Allows one to draw freehand on the slide currently on screen.
- **Go To Slide**: To jump to a selected slide without flashing through the whole presentation on the projector, press `G` or click the "current  slide" box.
  Using `J` or clicking the slide label will allow you to navigate slide labels instead of page numbers, useful e.g. for multi-page slides from beamer `\pause`.

  A spin box will appear, and you will be able to navigate through your slides in the presenter window only by scrolling your mouse, with the `Home`/`Up`/`Down`/`End` keys, with the + and - buttons of the spin box, or simply by typing in the number of the slide. Press `Enter` to validate going to the new slide or `Esc` to cancel.

- **Software pointer**: Clicking on the slide (in either window) while holding `ctrl` down will display a software laser pointer on the slide. Or press `L` to permanently switch on the laser pointer.
- **Talk time breakdown**: The `Presentation > Timing Breakdown` menu item displays a breakdown of how much time was spent on each slide, with a hierarchical breakdown per chapters/sections/etc. if available in the PDF.
- **Automatic file reloading**: If the file is modified, pympress will reload it (and preserve the current slide, current time, etc.)
- **Big button mode**: Add big buttons (duh) for touch displays.
- **Swap screens**: If Pympress mixed up which screen is the projector and which is not, press `S`
- **Estimated talk time**: Click the `Time estimation` box and set your planned talk duration. The color will allow you to see at a glance how much time you have left.
- **Adjust screen centering**: If your slides' form factor doesn't fit the projectors' and you don't want the slide centered in the window, use the "Screen Center" option in the "Presentation" menu.
- **Resize Current/Next slide**: You can drag the bar between both slides on the Presenter window to adjust their relative sizes to your liking.
- **Preferences**: Some of your choices are saved in a configuration file, and more options are accessible there. See the [configuration file documentation](docs/options.md) for more details.
- **Caching**: For efficiency, Pympress caches rendered pages (up to 200 by default). If this is too memory consuming for you, you can change this number in the configuration file.

## Command line arguments

-  `-h, --help`: Shows a list of all command line arguments.
- `-t mm[:ss], --talk-time=mm[:ss]`: The estimated (intended) talk time in minutes and optionally seconds.
- `-n position, --notes=position`: Set the position of notes on the pdf page (none, left, right, top, or bottom). Overrides the detection from the file.
- `--log=level`: Set level of verbosity in log file (DEBUG, INFO, WARNING, ERROR).

# Dependencies

Pympress relies on:
* Python (version 3.x strongly recommended though 2.7 should still work fine).
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

    apt-get install python3 python3-pip libgtk-3-0 libpoppler-glib8 libcairo2 python3-gi python3-cairo python3-gi-cairo gobject-introspection libgirepository-1.0-1 libgirepository1.0-dev gir1.2-gtk-3.0 gir1.2-poppler-0.18

Different distributions might have different package naming conventions, for example the equivalent on OpenSUSE would be:

    zypper install python3 python3-pip libgtk-3-0 libpoppler-glib8 libcairo2 python3-gobject python3-gobject-Gdk python3-cairo python3-gobject-cairo typelib-1_0-GdkPixbuf-2_0 typelib-1_0-Gtk-3_0 typelib-1_0-Poppler-0_18

On CentOS/RHEL/Fedora the dependencies would be:

    yum install python36 python3-pip gtk3 poppler-glib cairo gdk-pixbuf2 python3-gobject python3-cairo

And on Arch Linux:

    pacman -S --needed python python-pip gtk3 poppler cairo gobject-introspection poppler-glib python-gobject


### On macOS

Dependencies can be installed using [Homebrew](https://brew.sh/):

    brew install --only-dependencies pympress

### On windows
The [binary installer for windows](#installing) comes with pympress and all its dependencies packaged.

Alternately, in order to install from pypi or from source on windows, there are two ways to get the dependencies:

1. using MSYS2 (replace x86_64 with i686 if you're using a 32 bit machine).

   **Warning:** this can take a substantial amount of disk size as it requires a full software distribution and building platform.

        pacman -S --needed mingw-w64-x86_64-gtk3 mingw-w64-x86_64-cairo mingw-w64-x86_64-poppler mingw-w64-x86_64-python3 mingw-w64-x86_64-vlc python3-pip mingw-w64-x86_64-python3-pip mingw-w64-x86_64-python3-gobject mingw-w64-x86_64-python3-cairo

    This is also the strategy used to automate [builds on appveyor](https://github.com/Cimbali/pympress/tree/master/scripts/build_msi_mingw.sh).

2. Using PyGobjectWin32. *Be sure to check the supported Python versions (up to 3.4 at the time of writing)*, they appear in the FEATURES list in the linked page.
  - Install native [python for windows](https://www.python.org/downloads/windows/)
  - Get GTK+3, Poppler and their python bindings by executing [the PyGi installer](https://sourceforge.net/projects/pygobjectwin32/).  Be sure to tick all the necessary dependencies in the installer (Poppler, Cairo, Gdk-Pixbuf).

Alternately, you can build your Gtk+3 stack from source using MSVC, see [the Gnome wiki](https://wiki.gnome.org/Projects/GTK+/Win32/MSVCCompilationOfGTKStack) and [this python script that compiles the whole Gtk+3 stack](https://github.com/wingtk/gvsbuild/).
This strategy has not been used successfully yet, due to problems building Poppler with its introspection bidings (i.e. typelib) − see [#109](https://github.com/Cimbali/pympress/issues/109).

# Contributing

Feel free to clone this repo and use it, modify it, redistribute it, etc, under the GPLv2+.
A [number of contributors](https://github.com/Cimbali/pympress/graphs/contributors) have taken part in the development of pympress and submitted pull requests to improve it.

**Be respectful of everyone and keep this community friendly, welcoming, and harrasment-free.
Abusive behaviour will not be tolerated, and can be reported by email at me@cimba.li − wrongdoers may be permanently banned.**

Pympress has inline sphinx documentation ([Google style](http://www.sphinx-doc.org/en/latest/ext/example_google.html), contains rst syntax), and the [docs generated from it are hosted on the github pages of this repo](https://cimbali.github.io/pympress/).

## Translations

![Czech: 98%](https://img.shields.io/badge/%F0%9F%87%A8%F0%9F%87%BF%20Czech-98%25-1f0)
![French: 100%](https://img.shields.io/badge/%F0%9F%87%AB%F0%9F%87%B7%20French-100%25-0f0)
![German: 98%](https://img.shields.io/badge/%F0%9F%87%A9%F0%9F%87%AA%20German-98%25-1f0)
![Polish: 84%](https://img.shields.io/badge/%F0%9F%87%B5%F0%9F%87%B1%20Polish-84%25-5f0)
![Spanish: 84%](https://img.shields.io/badge/%F0%9F%87%AA%F0%9F%87%B8%20Spanish-84%25-5f0)
<!-- insert badge -->

If you want to add or contribute to a translation, check [pympress’ page on POEditor](https://poeditor.com/join/project/nKfRxeN8pS) and add your efforts to make pympress available in your own language to those of
[@Vulpeculus](https://github.com/Vulpeculus),
[@polaksta](https://github.com/polaksta),
[@susobaco](https://github.com/susobaco),
[FriedrichFröbel](https://github.com/FriedrichFroebel),
[Jaroslav Svoboda](https://github.com/multiflexi),
and <!-- last translator --> Cimbali.

## Packages

Official releases are made to [PyPI](https://pypi.org/) and with [github releases](https://github.com/Cimbali/pympress/releases). The community maintains a number of other packages or recipes to install pympress (additions welcome):
- [@Jose1711](https://github.com/jose1711) made the [AUR pympress package](https://aur.archlinux.org/packages/python-pympress/)
- [@ComFreek](https://github.com/ComFreek) maintains the [Chocolatey pympress package](https://chocolatey.org/packages/pympress)
- [@mans0954](https://github.com/mans0954) maintains the [Debian pympress package](https://packages.debian.org/bullseye/pympress) and the [Ubuntu pympress package](https://packages.ubuntu.com/focal/pympress)
