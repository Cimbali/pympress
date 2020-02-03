# -*- coding: utf-8 -*-
#
#       config.py
#
#       Copyright 2017 Cimbali <me@cimba.li>
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
"""
:mod:`pympress.config` -- Configuration
---------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import os
import shutil
import json
from collections import deque

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from pympress import util


try:
    unicode  # trigger NameError in python3

    def recursive_unicode_to_str(obj):
        """Recursively convert unicode to str (for python2).

        Raises NameError in python3 as 'unicode' is undefined

        Args:
            obj (`unicode` or `str` or `dict` or `list`): A unicode string to transform,
                                                          or a container whose children to transform
        """
        if isinstance(obj, unicode):
            return str(obj)
        elif isinstance(obj, dict):
            return {recursive_unicode_to_str(k): recursive_unicode_to_str(obj[k]) for k in obj}
        elif isinstance(obj, list):
            return [recursive_unicode_to_str(i) for i in obj]
        else:
            return obj

except NameError:
    def recursive_unicode_to_str(obj):
        """ Dummy function that does nothing, for python3.

        For python2 the equivalent function transforms strings to unicode.
        """
        return obj


def layout_from_json(layout_string):
    """ Load the layout from config, with all strings cast to type `str` (even on python2 where they default to `unicode`).

    Raises ValueError until python 3.4, json.decoder.JSONDecodeError afterwards, on invalid input.

    Args:
        layout_string (`str`): A JSON string to be loaded.
    """
    return recursive_unicode_to_str(json.loads(layout_string))


class Config(configparser.ConfigParser, object):  # python 2 fix
    """ Manage configuration :Get the configuration from its file and store its back.
    """
    #: `dict`-tree of presenter layouts for various modes
    layout = {}

    #: `dict` of strings that are the valid representations of widgets from the presenter window
    #: that can be dynamically rearranged, mapping to their names
    placeable_widgets = {"notes": "p_frame_notes", "current": "p_frame_cur", "next": "p_frame_next",
                         "annotations": "p_frame_annot", "highlight": "scribble_overlay"}

    #: Map of (keyval, Gdk.ModifierType) to string, which representing the shortcuts for each command
    shortcuts = {}

    @staticmethod
    def path_to_config(search_legacy_locations = False):
        """ Return the path to the currently used configuration file.

        Args:
            search_legacy_locations (`bool`): whether to look in previously used locations
        """
        portable_config = util.get_portable_config()
        if os.path.exists(portable_config):
            return portable_config

        user_config = util.get_user_config()

        # migrate old configuration files from previously-used erroneous locations
        if search_legacy_locations and (util.IS_POSIX or util.IS_MAC_OS) and not os.path.exists(user_config):
            for legacy_location in [os.path.expanduser('~/.pympress'), os.path.expanduser('~/.config/pympress')]:
                if os.path.exists(legacy_location):
                    shutil.move(legacy_location, user_config)

        return user_config


    @staticmethod
    def toggle_portable_config(*args):
        """ Create or remove a configuration file for portable installs.

        The portable install file will be used by default, and deleting it causes the config
        to fall back to the user profile location.

        No need to populate the new config file, this will be done on pympress exit.
        """
        if Config.using_portable_config():
            os.remove(util.get_portable_config())
        else:
            with open(util.get_portable_config(), 'w'):
                pass


    @staticmethod
    def using_portable_config():
        """ Checks which configuration file location is in use.

        Returns:
            `bool`: `True` iff we are using the portable (i.e. in install dir) location
        """
        return util.get_portable_config() == Config.path_to_config()


    def __init__(config):
        super(Config, config).__init__()

        # populate values first from the default config file, then from the proper one
        config.read(util.get_default_config())
        config.load_window_layouts()

        all_commands = dict(config.items('shortcuts')).keys()

        config.read(config.path_to_config(True))
        config.upgrade()
        config.load_window_layouts()

        for command in all_commands:
            parsed = {Gtk.accelerator_parse(l) for l in config.get('shortcuts', command).split()}

            if (0, 0) in parsed:
                logger.warning('Failed parsing 1 or more shortcuts for ' + command)
                parsed.remove((0, 0))

            config.shortcuts.update({s: command for s in parsed})


    def upgrade(self):
        """ Update obsolete config options when pympress updates.
        """
        if self.get('presenter', 'pointer') == 'pointer_none':
            self.set('presenter', 'pointer', 'red')
            self.set('presenter', 'pointer_mode', 'disabled')


    def getlist(self, *args):
        """ Parse a config value and return the list by splitting the value on commas.

        i.e. bar = foo,qux  returns the list ['foo', 'qux']

        Returns:
            `list`: a config value split into a list.
        """
        return [t.strip() for t in self.get(*args).split(',') if t.strip()]


    def save_config(self):
        """ Save the configuration to its file.
        """
        # serialize the layouts
        for layout_name in self.layout:
            self.set('layout', layout_name, json.dumps(self.layout[layout_name], indent=4))

        with open(self.path_to_config(), 'w') as configfile:
            self.write(configfile)


    def toggle_start(self, check_item):
        """ Generic function to toggle some boolean startup configuration.

        Args:
            check_item (:class:`~Gtk.:CheckMenuItem`): the check button triggering the call
        """
        # button is named start(_[pc]win)?_property
        start, *win, prop = check_item.get_name().split('_')

        window = {(): 'content', ('pwin',): 'presenter', ('cwin',): 'content'}[tuple(win)]
        start_conf = 'start_' + prop

        self.set(window, start_conf, 'on' if check_item.get_active() else 'off')


    def validate_layout(self, layout, expected_widgets, optional_widgets = set()):
        """ Validate layout: check whether the layout of widgets built from the config string is valid.

        Args:
            layout (`dict`): the json-parsed config string
            expected_widgets (`set`): strings with the names of widgets that have to be used in this layout
            optional_widgets (`set`): strings with the names of widgets that may or may not be used in this layout


        Layout must have all self.placeable_widgets (leaves of the tree, as `str`) and only allowed properties
        on the nodes of the tree (as `dict`).

        Constraints on the only allowed properties of the nodes are:
        - resizeable: `bool` (optional, defaults to no),
        - orientation: `str`, either "vertical" or "horizontal" (mandatory)
        - children: `list` of size >= 2, containing `str`s or `dict`s (mandatory)
        - proportions: `list` of `float` with sum = 1, length == len(children), representing the relative sizes
        of all the resizeable items (if and only if resizeable).

        """
        next_visits = deque([layout])
        widget_seen = set()
        while next_visits:
            w_desc = next_visits.popleft()
            if type(w_desc) is str:
                if w_desc not in expected_widgets and w_desc not in optional_widgets:
                    raise ValueError('Unrecognized widget "{}", pick one of: {}'
                                     .format(w_desc, ', '.join(expected_widgets)))
                elif w_desc in widget_seen:
                    raise ValueError('Duplicate widget "{}", all expected_widgets can only appear once'.format(w_desc))
                widget_seen.add(w_desc)

            elif type(w_desc) is dict:
                if 'orientation' not in w_desc or w_desc['orientation'] not in ['horizontal', 'vertical']:
                    raise ValueError('"orientation" is mandatory and must be "horizontal" or "vertical" at node {}'
                                     .format(w_desc))
                elif 'children' not in w_desc or type(w_desc['children']) is not list or len(w_desc['children']) < 2:
                    raise ValueError('"children" is mandatory and must be a list of 2+ items at node {}'.format(w_desc))
                elif 'resizeable' in w_desc and type(w_desc['resizeable']) is not bool:
                    raise ValueError('"resizeable" must be boolean at node {}'.format(w_desc))

                elif 'proportions' in w_desc:
                    if 'resizeable' not in w_desc or not w_desc['resizeable']:
                        raise ValueError('"proportions" is only valid for resizeable widgets at node {}'.format(w_desc))
                    elif type(w_desc['proportions']) is not list or \
                            any(type(n) is not float for n in w_desc['proportions']) or \
                            len(w_desc['proportions']) != len(w_desc['children']) or \
                            abs(sum(w_desc['proportions']) - 1) > 1e-10:
                        raise ValueError('"proportions" must be a list of floats (one per separator), ' -
                                         'between 0 and 1, at node {}'.format(w_desc))

                next_visits.extend(w_desc['children'])
            else:
                raise ValueError('Unexpected type {}, nodes must be dicts or strings, at node {}'
                                 .format(type(w_desc), w_desc))
        widget_missing = expected_widgets - widget_seen
        if widget_missing:
            raise ValueError('Following placeable_widgets were not specified: {}'.format(', '.join(widget_missing)))


    def load_window_layouts(self):
        """ Parse and validate layouts loaded from config, with fallbacks if needed.
        """
        widget_reqs = {
            'notes':     (set(self.placeable_widgets.keys()) - {"annotations", "highlight"},),
            'plain':     (set(self.placeable_widgets.keys()) - {"notes", "highlight"},),
            'highlight': ({"highlight"}, set(self.placeable_widgets.keys()) - {"highlight"})
        }

        for layout_name in widget_reqs:
            # Log error and keep default layout
            try:
                loaded_layout = layout_from_json(self.get('layout', layout_name))
                self.validate_layout(loaded_layout, *widget_reqs[layout_name])
                self.layout[layout_name] = loaded_layout
            except ValueError:
                logger.exception('Invalid layout')


    def widget_layout_to_tree(self, widget, pane_handle_pos):
        """ Build a tree representing a widget hierarchy, leaves are strings and nodes are `dict`.

        Recursive function. See validate_layout() for more info on the tree structure.

        Args:
            widget (:class:`~Gtk.Widget`): the widget where to start
            pane_handle_pos (`dict`): Map of :class:`~Gtk.Paned` to the relative handle position (float in 0..1)

        Returns:
            `dict`: A tree of dicts reprensenting the widget hierarchy
        """
        orientation_names = {Gtk.Orientation.HORIZONTAL: 'horizontal', Gtk.Orientation.VERTICAL: 'vertical'}

        name = widget.get_name()
        matching_widget_names = [k for k, v in self.placeable_widgets.items() if v == name]

        if matching_widget_names:
            return matching_widget_names[0]

        elif issubclass(type(widget), Gtk.Box):
            return {'resizeable': False, 'orientation': orientation_names[widget.get_orientation()],
                    'children': [self.widget_layout_to_tree(c, pane_handle_pos) for c in widget.get_children()]}

        elif issubclass(type(widget), Gtk.Paned):
            proportions = [1]
            reverse_children = []
            orientation = widget.get_orientation()
            if orientation == Gtk.Orientation.HORIZONTAL:
                get_size = Gtk.Widget.get_allocated_width
            else:
                get_size = Gtk.Widget.get_allocated_height

            while issubclass(type(widget), Gtk.Paned) and orientation == widget.get_orientation():
                left_pane = widget.get_child1()
                right_pane = widget.get_child2()

                visible = left_pane.get_visible() and right_pane.get_visible()
                position = widget.get_position()
                widget_size = get_size(widget)

                if not visible or widget_size <= 1:
                    # reuse number that was in config initially, otherwise gets overwritten with 0
                    ratio = pane_handle_pos[widget]
                else:
                    ratio = float(position) / widget_size

                proportions = [ratio] + [(1 - ratio) * p for p in proportions]
                reverse_children.append(right_pane)
                widget = left_pane

            reverse_children.append(left_pane)

            return {'resizeable': True, 'proportions': proportions, 'orientation': orientation_names[orientation],
                    'children': [self.widget_layout_to_tree(c, pane_handle_pos) for c in reversed(reverse_children)]}

        raise ValueError('Error serializing layout: widget of type {} '.format(type(widget)) +
                         'is not an expected container or named widget: "{}"'.format(name))


    def get_layout(self, layout_name):
        """ Getter for the `~layout_name` layout.
        """
        return recursive_unicode_to_str(self.layout[layout_name])


    def update_layout(self, layout_name, widget, pane_handle_pos):
        """ Setter for the notes layout.

        Args:
            layout_name (`str`): the name of the layout to update
            widget (:class:`~Gtk.Widget`): the widget that will contain the layout.
            pane_handle_pos (`dict`): Map of :class:`~Gtk.Paned` to the relative handle position (float in 0..1)
        """
        self.layout[layout_name] = self.widget_layout_to_tree(widget, pane_handle_pos)
