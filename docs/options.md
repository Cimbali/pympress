# Configuration file

Pympress has a number of options available from its configuration file.

This file is usually located in:
- `~/.config/pympress` on Linux,
- `%APPDATA%/pympress.ini` on Windows,
- `~/Library/Preferences/pympress` on macOS,
- in the top-level of the pympress install directory for portable installations.

The path to the currently used configuration file can be checked in the `Help > About` information window.

## Shortcuts

The shortcuts are parsed using [`Gtk.accelerator_parse()`](https://lazka.github.io/pgi-docs/#Gtk-3.0/functions.html#Gtk.accelerator_parse):

> The format looks like “\<Control\>a” or “\<Shift>\<Alt\>F1” or “\<Release\>z” (the last one is for key release).
>
> The parser is fairly liberal and allows lower or upper case, and also abbreviations such as “\<Ctl\>” and “\<Ctrl\>”. Key names are parsed using [`Gdk.keyval_from_name()`](https://lazka.github.io/pgi-docs/#Gdk-3.0/functions.html#Gdk.keyval_from_name). For character keys the name is not the symbol, but the lowercase name, e.g. one would use “\<Ctrl\>minus” instead of “\<Ctrl\>-”.

This means that any value in this [list of key constants](https://lazka.github.io/pgi-docs/#Gdk-3.0/constants.html#Gdk.KEY_0) is valid (removing the initial `Gdk.KEY_` part). You can verify that this value is parsed correctly from the `Help > Shortcuts` information window.

## Layouts

The panes (current slide, next slide, notes, annotations, etc.) can be rearranged arbitrarily by setting the entries of the `layout` section in the configuration file.
 Here are a couple examples of layouts, with `Cu` the current slide, `No` the notes half of the slide, `Nx` the next slide:

- All-horizontal layout:

      +----+----+----+
      | Cu | No | Nx |
      +----+----+----+

  Setting:

      notes = {"children": ["current", "notes", "next"], "proportions": [0.33, 0.33, 0.33], "orientation": "horizontal", "resizeable": true}

- All-vertical layout:

      +----+
      | Cu |
      +----+
      | No |
      +----+
      | Nx |
      +----+

  Setting:

      notes = {"children": ["current", "notes", "next"], "proportions": [0.33, 0.33, 0.33], "orientation": "vertical", "resizeable": true}

- Vertical layout with horizontally divided top pane:

      +----+----+
      | Cu | No |
      +----+----+
      |    Nx   |
      +---------+

  Setting:

      notes = {"children": [
					{"children": ["current", "notes"], "proportions": [0.5, 0.5], "orientation": "horizontal", "resizeable": true},
					"next"
				], "proportions": [0.5, 0.5], "orientation": "vertical", "resizeable": true}


- Horizontal layout with horizontally divided right pane:

      +----+----+
      |    | Nx |
      + Cu +----+
      |    | No |
      +---------+

  Setting:

      notes = {"children": [
					"current",
					{"children": ["next", "notes"], "proportions": [0.5, 0.5], "orientation": "vertical", "resizeable": true}
				], "proportions": [0.5, 0.5], "orientation": "horizontal", "resizeable": true}

And so on. You can play with the items, their nesting, their order, and the orientation in which a set of widgets appears.

For each entry the widgets (strings that are leaves of "children" nodes in this representation) must be:

- for `notes`: "current", "notes", "next"
- for `plain`: "current", "next" and "annotations" (the annotations widget is toggled with the `A` key by default)
- for `highlight`: same as `plain` with "highlight" instead of "current"

A few further remarks:

-  If you set "resizeable" to `false`, the panes won’t be resizeable dynamically with a handle in the middle
- "proportions" are normalized, and saved on exit if you resize panes during the execution. If you set them to `4` and `1`, the panes will be `4 / (4 + 1) = 20%` and `1 / (4 + 1) = 100%`, so the ini will contain something like `0.2` and `0.8` after executing pympress.
