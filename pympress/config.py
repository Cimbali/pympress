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

import os.path
import json
from collections import deque

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS


try:
    unicode # trigger NameError in python3

    def recursive_unicode_to_str(obj):
        """ Recursively convert unicode to str (for python2)
        Raises NameError in python3 as 'unicode' is undefined

        Args:
            obj (`unicode` or `str` or `dict` or `list`): A unicode string to transform, or a container whose children to transform
        """
        if isinstance(obj, unicode):
            return str(obj)
        elif isinstance(obj, dict):
            return {recursive_unicode_to_str(k):recursive_unicode_to_str(obj[k]) for k in obj}
        elif isinstance(obj, list):
            return [recursive_unicode_to_str(i) for i in obj]
        else:
            return obj

except NameError:
    def recursive_unicode_to_str(obj):
        return obj


def layout_from_json(layout_string):
    """ Load the layout from config, with all strings cast to type `str` (even on python2 where they default to `unicode`)
    Raises ValueError until python 3.4, json.decoder.JSONDecodeError afterwards, on invalid input.

    Args:
        layout_string (`str`): A JSON string to be loaded.
    """
    if not layout_string:
        raise ValueError('No layout string passed. Ignore this error if you just upgraded pympress or reset your configuration file.')

    return recursive_unicode_to_str(json.loads(layout_string))


class Config(configparser.ConfigParser, object): # python 2 fix
    """ Manage configuration :Get the configuration from its file and store its back.
    """
    #: `dict`-tree of presenter layouts for various modes
    layout = {}

    #: Map of strings that are the valid representations of widgets from the presenter window that can be dynamically rearranged, mapping to their names
    placeable_widgets = {"notes": "p_frame_notes", "current": "p_frame_cur", "next": "p_frame_next", "annotations": "p_frame_annot", "highlight": "scribble_overlay"}

    @staticmethod
    def path_to_config():
        """ Return the OS-specific path to the configuration file.
        """
        if IS_POSIX:
            conf_dir = os.path.expanduser('~/.config')
            conf_file_nodir = os.path.expanduser('~/.pympress')
            conf_file_indir = os.path.expanduser('~/.config/pympress')

            if os.path.isfile(conf_file_indir):
                return conf_file_indir
            elif os.path.isfile(conf_file_nodir):
                return conf_file_nodir

            elif os.path.isdir(conf_dir):
                return conf_file_indir
            else:
                return conf_file_nodir
        else:
            return os.path.join(os.environ['APPDATA'], 'pympress.ini')


    def __init__(config):
        super(Config, config).__init__()

        config.add_section('content')
        config.add_section('presenter')
        config.add_section('layout')
        config.add_section('cache')
        config.add_section('scribble')

        config.read(config.path_to_config())

        if not config.has_option('cache', 'maxpages'):
            config.set('cache', 'maxpages', '200')

        if not config.has_option('content', 'xalign'):
            config.set('content', 'xalign', '0.50')

        if not config.has_option('content', 'yalign'):
            config.set('content', 'yalign', '0.50')

        if not config.has_option('content', 'monitor'):
            config.set('content', 'monitor', '0')

        if not config.has_option('content', 'start_blanked'):
            config.set('content', 'start_blanked', 'off')

        if not config.has_option('content', 'start_fullscreen'):
            config.set('content', 'start_fullscreen', 'on')

        if not config.has_option('presenter', 'monitor'):
            config.set('presenter', 'monitor', '1')

        if not config.has_option('presenter', 'start_fullscreen'):
            config.set('presenter', 'start_fullscreen', 'off')

        if not config.has_option('presenter', 'pointer'):
            config.set('presenter', 'pointer', 'red')

        if not config.has_option('presenter', 'show_bigbuttons'):
            config.set('presenter', 'show_bigbuttons', 'off')

        if not config.has_option('presenter', 'show_annotations'):
            config.set('presenter', 'show_annotations', 'off')

        if not config.has_option('presenter', 'scroll_number'):
            config.set('presenter', 'scroll_number', 'off')

        if not config.has_option('layout', 'notes'):
            config.set('layout', 'notes', '')

        if not config.has_option('layout', 'plain'):
            config.set('layout', 'plain', '')

        if not config.has_option('layout', 'highlight'):
            config.set('layout', 'highlight', '')

        if not config.has_option('scribble', 'color'):
            config.set('scribble', 'color', Gdk.RGBA(1., 0., 0., 1.).to_string())

        if not config.has_option('scribble', 'width'):
            config.set('scribble', 'width', '8')

        config.load_window_layouts()


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
        window, start_conf = check_item.get_name().split('.')
        self.set(window, start_conf, 'on' if check_item.get_active() else 'off')


    def validate_layout(self, layout, expected_widgets, optional_widgets = set()):
        """ Validate layout: check whether the layout of widgets built from the config string is valid.

        Args:
            layout (`dict`): the json-parsed config string
            expected_widgets (`set`): strings with the names of widgets that have to be used in this layout
            optional_widgets (`set`): strings with the names of widgets that may or may not be used in this layout


        Layout must have all self.placeable_widgets (leaves of the tree, as `str`) and only allowed properties
        on the nodes of the tree (as `dict`).

        Contraints on the only allowed properties of the nodes are:
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
                    raise ValueError('Unrecognized widget "{}", pick one of: {}'.format(w_desc, ', '.join(expected_widgets)))
                elif w_desc in widget_seen:
                    raise ValueError('Duplicate widget "{}", all expected_widgets can only appear once'.format(w_desc))
                widget_seen.add(w_desc)

            elif type(w_desc) is dict:
                if 'orientation' not in w_desc or w_desc['orientation'] not in ['horizontal', 'vertical']:
                    raise ValueError('"orientation" is mandatory and must be "horizontal" or "vertical" at node {}'.format(w_desc))
                elif 'children' not in w_desc or type(w_desc['children']) is not list or len(w_desc['children']) < 2:
                    raise ValueError('"children" is mandatory and must be a list of 2+ items at node {}'.format(w_desc))
                elif 'resizeable' in w_desc and type(w_desc['resizeable']) is not bool:
                    raise ValueError('"resizeable" must be boolean at node {}'.format(w_desc))

                elif 'proportions' in w_desc:
                    if 'resizeable' not in w_desc or not w_desc['resizeable']:
                        raise ValueError('"proportions" is only valid for resizeable widgets at node {}'.format(w_desc))
                    elif type(w_desc['proportions']) is not list or any(type(n) is not float for n in w_desc['proportions']) or len(w_desc['proportions']) != len(w_desc['children']) or abs(sum(w_desc['proportions']) - 1) > 1e-10:
                        raise ValueError('"proportions" must be a list of floats (one per separator), between 0 and 1, at node {}'.format(w_desc))

                next_visits.extend(w_desc['children'])
            else:
                raise ValueError('Unexpected type {}, nodes must be dicts or strings, at node {}'.format(type(w_desc), w_desc))
        widget_missing = expected_widgets - widget_seen
        if widget_missing:
            raise ValueError('Following placeable_widgets were not specified: {}'.format(', '.join(widget_missing)))


    def load_window_layouts(self):
        """ Parse and validate layouts loaded from config, with fallbacks if needed.
        """
        default_layout = {
            'notes':     '{"resizeable":true, "orientation":"horizontal", "children":["notes", {"resizeable":false, "children":["current", "next"], "orientation":"vertical"}], "proportions": [0.60, 0.40]}',
            'plain':     '{"resizeable":true, "orientation":"horizontal", "children":["current", {"resizeable":true, "orientation":"vertical", "children":["next", "annotations"], "proportions":[0.55, 0.45]}], "proportions":[0.67, 0.33]}',
            'highlight': '{"resizeable":true, "orientation":"horizontal", "children":["highlight", {"resizeable":true, "orientation":"vertical", "children":["next", "annotations"], "proportions":[0.55, 0.45]}], "proportions":[0.67, 0.33]}'
        }

        widget_reqs = {
            'notes':     (set(self.placeable_widgets.keys()) - {"annotations", "highlight"},),
            'plain':     (set(self.placeable_widgets.keys()) - {"notes", "highlight"},),
            'highlight': ({"highlight"}, set(self.placeable_widgets.keys()) - {"highlight"})
        }

        for layout_name in default_layout:
            # Log error and keep default layout
            try:
                self.layout[layout_name] = layout_from_json(self.get('layout', layout_name))
                self.validate_layout(self.layout[layout_name] , *widget_reqs[layout_name])
            except ValueError as e:
                logger.exception('Invalid layout')
                self.layout[layout_name] = layout_from_json(default_layout[layout_name])


    def widget_layout_to_tree(self, widget, pane_handle_pos):
        """ Build a tree representing a widget hierarchy, leaves are strings and nodes are `dict`.
        Recursive function. See validate_layout() for more info on the tree structure.

        Args:
            widget (:class:`~Gtk.Widget`): the widget where to start
            pane_handle_pos (`dict`): Map of :class:`~Gtk.Paned` to the relative position (float between 0 and 1) of its handle

        Returns:
            `dict`: A tree of dicts reprensenting the widget hierarchy
        """
        orientation_names = {Gtk.Orientation.HORIZONTAL:'horizontal', Gtk.Orientation.VERTICAL:'vertical'}

        name = widget.get_name()
        matching_widget_names = [k for k, v in self.placeable_widgets.items() if v == name]

        if matching_widget_names:
            return matching_widget_names[0]

        elif issubclass(type(widget), Gtk.Box):
            return {'resizeable': False, 'children': [self.widget_layout_to_tree(c, pane_handle_pos) for c in widget.get_children()],
                    'orientation': orientation_names[widget.get_orientation()]}

        elif issubclass(type(widget), Gtk.Paned):
            proportions = [1]
            reverse_children = []
            orientation = widget.get_orientation()
            get_size = Gtk.Widget.get_allocated_width if orientation == Gtk.Orientation.HORIZONTAL else Gtk.Widget.get_allocated_height

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

            return {'resizeable': True, 'children': [self.widget_layout_to_tree(c, pane_handle_pos) for c in reversed(reverse_children)],
                    'proportions': proportions, 'orientation': orientation_names[orientation]}

        raise ValueError('Error serializing layout: widget of type {} is not an expected container or named widget: "{}"'.format(type(widget), name))


    def get_layout(self, layout_name):
        """ Getter for the `~layout_name` layout.
        """
        return recursive_unicode_to_str(self.layout[layout_name])


    def update_layout(self, layout_name, widget, pane_handle_pos):
        """ Setter for the notes layout.

        Args:
            layout_name (`str`): the name of the layout to update
            widget (:class:`~Gtk.Widget`): the widget that will contain the layout.
            pane_handle_pos (`dict`): Map of :class:`~Gtk.Paned` to the relative position (float between 0 and 1) of its handle
        """
        self.layout[layout_name] = self.widget_layout_to_tree(widget, pane_handle_pos)
