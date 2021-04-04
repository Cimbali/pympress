# -*- coding: utf-8 -*-
#
#       builder.py
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
:mod:`pympress.ui_builder` -- abstract GUI management
-----------------------------------------------------

This module contains the tools to load the graphical user interface of pympress,
building the widgets/objects from XML (glade) files, applying translation "manually"
to avoid dealing with all the mess of C/GNU gettext's bad portability.
"""

from __future__ import print_function, unicode_literals

import logging
import copy
logger = logging.getLogger(__name__)

from collections import deque

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib, Gio

from pympress import util


class Builder(Gtk.Builder):
    """ GUI builder, inherits from :class:`~Gtk.Builder` to read XML descriptions of GUIs and load them.
    """
    #: `set` of :class:`~Gtk.Widget`s that have been built by the builder, and translated
    __built_widgets = set()

    #: `dict` mapping :class:`~Gtk.Paned` names to the handler ids of their size-allocate signal
    pending_pane_resizes = {}

    _glib_type_strings = {
        float: 'd',
        bool: 'b',
        int: 'x',
        str: 's',
    }

    _glib_type_getters = {
        'd': GLib.Variant.get_double,
        'b': GLib.Variant.get_boolean,
        'x': GLib.Variant.get_int64,
        's': GLib.Variant.get_string,
    }

    def __init__(self):
        super(Builder, self).__init__()


    @staticmethod
    def __translate_widget_strings(a_widget):
        """ Calls gettext on all strings we can find in a_widgets.

        Args:
            a_widget (:class:`~GObject.Object`): an object built by the builder, usually a widget
        """
        for str_prop in (prop.name for prop in a_widget.props if prop.value_type == GObject.TYPE_STRING):
            try:
                str_val = getattr(a_widget.props, str_prop)
                if str_val:
                    setattr(a_widget.props, str_prop, _(str_val))
            except TypeError:
                # Thrown when a string property is not readable
                pass

    @staticmethod
    def __recursive_translate_widgets(a_widget):
        """ Calls gettext on all strings we can find in widgets, and recursively on its children.

        Args:
            a_widget (:class:`~GObject.Object`): an object built by the builder, usually a widget
        """
        Builder.__translate_widget_strings(a_widget)

        if issubclass(type(a_widget), Gtk.Container):
            # NB: Parent-loop in widgets would cause infinite loop here, but that's absurd (right?)
            # NB2: maybe forall instead of foreach if we miss some strings?
            a_widget.foreach(Builder.__recursive_translate_widgets)

        if issubclass(type(a_widget), Gtk.MenuItem) and a_widget.get_submenu() is not None:
            Builder.__recursive_translate_widgets(a_widget.get_submenu())


    def get_callback_handler(self, handler_name):
        """ Returns the handler from its name, searching in target.

        Parse handler names and split on '.' to use recursion.

        Args:
            target (`object`): An object that has a method called `handler_name`
            handler_name (`str`): The name of the function to be connected to a signal

        Returns:
            `function`: A function bound to an object
        """
        target = self

        for attr in handler_name.split('.'):
            try:
                target = getattr(target, attr)
            except AttributeError:
                logger.error('Can not reach target of signal {}.{}()'.format(self, handler_name), exc_info=True)
                return None

        return target


    def signal_connector(self, builder, object, signal_name, handler_name, connect_object, flags, *user_data):
        """ Callback for signal connection. Implements the `~Gtk.BuilderConnectFunc` function interface.

        Args:
            builder (:class:`~pympress.builder.Builder`): The builder, unused
            object (:class:`~GObject.Object`): The object (usually a wiget) that has a signal to be connected
            signal_name (`str`): The name of the signal
            handler_name (`str`): The name of the function to be connected to the signal
            connect_object (:class:`~GObject.Object`): unused
            flags (:class:`~GObject.ConnectFlags`): unused
            user_data (`tuple`): supplementary positional arguments to be passed to the handler
        """
        try:
            handler = self.get_callback_handler(handler_name)
            object.connect(signal_name, handler, *user_data)

        except Exception:
            logger.critical('Impossible to connect signal {} from object {} to handler {}'
                            .format(signal_name, object, handler_name), exc_info = True)


    def connect_signals(self, base_target):
        """ Signal connector connecting to properties of `base_target`, or properties of its properties, etc.

        Args:
            base_target (:class:`~pympress.builder.Builder`): The target object, that has functions to be connected to
            signals loaded in this builder.
        """
        Builder.connect_signals_full(base_target, self.signal_connector)


    def load_ui(self, resource_name, **kwargs):
        """ Loads the UI defined in the file named resource_name using the builder.

        Args:
            resource_name (`str`): the basename of the glade file (without extension), identifying the resource to load.
        """
        self.add_from_file(util.get_ui_resource_file(resource_name, **kwargs))

        # Get all newly built objects
        new_objects = set(self.get_objects()) - self.__built_widgets
        self.__built_widgets.update(new_objects)

        for obj in new_objects:
            # pass new objects to manual translation
            self.__translate_widget_strings(obj)

            # Instrospectively load objects. If we have a self.attr == None and this attr is the name of a built object,
            # link it together.
            if issubclass(type(obj), Gtk.Buildable):
                obj_id = Gtk.Buildable.get_name(obj)

                # set Gtk.Widget.name property to the value of the Gtk.Buildable id
                if issubclass(type(obj), Gtk.Widget):
                    Gtk.Widget.set_name(obj, obj_id)

                if hasattr(self, obj_id) and getattr(self, obj_id) is None:
                    setattr(self, obj_id, obj)


    def list_attributes(self, target):
        """ List the None-valued attributes of target.

        Args:
            target (`dict`): An object with None-valued attributes
        """
        for attr in dir(target):
            try:
                if attr[:2] + attr[-2:] != '____' and getattr(target, attr) is None:
                    yield attr
            except RuntimeError:
                pass


    def load_widgets(self, target):
        """ Fill in target with the missing elements introspectively.

        This means that all attributes of `target` that are None now must exist under the same name in the builder.

        Args:
            target (`dict`): An object with None-valued properties whose names correspond to ids of built widgets.
        """
        for attr in self.list_attributes(target):
            setattr(target, attr, self.get_object(attr))


    def replace_layout(self, layout, top_widget, leaf_widgets, pane_resize_handler = None):
        """ Remix the layout below top_widget with the layout configuration given in 'layout' (assumed to be valid!).

        Args:
            layout (`dict`): the json-parsed config string, thus a hierarchy of lists/dicts, with strings as leaves
            top_widget (:class:`~Gtk.Container`): The top-level widget under which we build the hierachyy
            leaf_widgets (`dict`): the map of valid leaf identifiers (strings) to the corresponding :class:`~Gtk.Widget`
            pane_resize_handler (function): callback function to be called when the panes are resized

        Returns:
            `dict`: The mapping of the used :class:`~Gtk.Paned` widgets to their relative handle position (in 0..1).
        """
        # take apart the previous/default layout
        containers = []
        widgets = top_widget.get_children()
        i = 0
        while i < len(widgets):
            w = widgets[i]
            if w in self.placeable_widgets.values():
                pass
            elif issubclass(type(w), Gtk.Box) or issubclass(type(w), Gtk.Paned):
                widgets.extend(w.get_children())
                containers.append(w)
            w.get_parent().remove(w)
            i += 1

        # cleanup widgets
        del widgets[:]
        while containers:
            containers.pop().destroy()
        self.pending_pane_resizes.clear()

        # iterate over new layout to build it, using a BFS
        widgets_to_add = deque([(top_widget, copy.deepcopy(layout))])
        pane_resize = set()
        pane_handle_pos = {}

        while widgets_to_add:
            parent, w_desc = widgets_to_add.popleft()

            if type(w_desc) is str:
                w = leaf_widgets[w_desc]

            else:
                # get new container widget
                if 'resizeable' in w_desc and w_desc['resizeable']:
                    orientation = getattr(Gtk.Orientation, w_desc['orientation'].upper())
                    w = Gtk.Paned.new(orientation)
                    w.set_wide_handle(True)

                    # Add on resize events
                    if pane_resize_handler:
                        w.connect("notify::position", pane_resize_handler)
                        w.connect("button-release-event", pane_resize_handler)

                    # left pane is first child
                    widgets_to_add.append((w, w_desc['children'].pop()))

                    if 'proportions' in w_desc:
                        right_pane = w_desc['proportions'].pop()
                        left_pane  = w_desc['proportions'].pop()
                        w_desc['proportions'].append(left_pane + right_pane)

                        pane_handle_pos[w] = float(left_pane) / (left_pane + right_pane)
                        pane_resize.add(w)
                    else:
                        pane_handle_pos[w] = 0.5

                    hid = w.connect("size-allocate", self.resize_paned, pane_handle_pos[w])

                    w.set_name('GtkPaned{}'.format(len(self.pending_pane_resizes)))
                    self.pending_pane_resizes[w.get_name()] = hid

                    # if more than 2 children are to be added, add the 2+ from the right side in a new child Gtk.Paned
                    widgets_to_add.append((w, w_desc['children'][0] if len(w_desc['children']) == 1 else w_desc))
                else:
                    w = Gtk.Box.new(getattr(Gtk.Orientation, w_desc['orientation'].upper()), 5)
                    w.set_homogeneous(True)
                    w.set_spacing(10)

                    widgets_to_add.extend((w, c) for c in w_desc['children'])

            if issubclass(type(parent), Gtk.Box):
                parent.pack_start(w, True, True, 0)
            else:
                # it's a Gtk.Paned
                if parent.get_child2() is None:
                    parent.pack2(w, True, True)
                    if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                        w.set_margin_start(8)
                    else:
                        w.set_margin_top(8)
                else:
                    parent.pack1(w, True, True)
                    if parent.get_orientation() == Gtk.Orientation.HORIZONTAL:
                        w.set_margin_end(8)
                    else:
                        w.set_margin_bottom(8)

        return pane_handle_pos


    def resize_paned(self, paned, rect, relpos):
        """ Resize `paned` to have its handle at `relpos`, then disconnect this signal handler.

        Called from the :func:`Gtk.Widget.signals.size_allocate` signal.

        Args:
            paned (:class:`~Gtk.Paned`): Panel whose size has just been allocated, and whose handle needs initial
                                         placement.
            rect (:class:`~Gdk.Rectangle`): The rectangle specifying the size that has just been allocated to `~paned`
            relpos (`float`): A number between `0.` and `1.` that specifies the handle position

        Returns:
            `True`
        """
        size = rect.width if paned.get_orientation() == Gtk.Orientation.HORIZONTAL else rect.height
        handle_pos = int(round(relpos * size))
        GLib.idle_add(paned.set_position, handle_pos)

        paned.disconnect(self.pending_pane_resizes.pop(paned.get_name()))
        return True


    @staticmethod
    def setup_actions(actions, action_map=None):
        """ Sets up actions with a given prefix, using the Application as the ActionMap.

        Args:
            actions (`dict`): Maps the action names to dictionaries containing their parameters.
            action_map (:class:`~Gio.ActionMap`): The object implementing the action map interface to register actions
        """
        if action_map is None:
            action_map = Gio.Application.get_default()

        for action_name, details in actions.items():
            state = details.get('state')
            param = details.get('parameter_type')
            enabled = details.get('enabled')

            if param is not None:
                param = GLib.VariantType.new(Builder._glib_type_strings[param])

            if state is not None:
                state = GLib.Variant(Builder._glib_type_strings[type(state)], state)
                action = Gio.SimpleAction.new_stateful(action_name, param, state)
            else:
                action = Gio.SimpleAction.new(action_name, param)

            for event in ['activate', 'change-state']:
                handler = details.get(event.replace('-', '_'))
                if handler is not None:
                    action.connect(event, handler)

            action_map.add_action(action)

            if enabled is not None:
                action.set_enabled(enabled)

        return action_map
