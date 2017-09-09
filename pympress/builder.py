#       generic_ui.py
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
------------------------------------

This module contains the tools to load the graphical user interface of pympress,
building the widgets/objects from XML (glade) files, applying translation "manually"
to avoid dealing with all the mess of C/GNU gettext's bad portability.
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

from pympress import util


class Builder(Gtk.Builder):
    """ GUI builder, inherits from :class:`~Gtk.Builder` to read XML descriptions of GUIs and load them.
    """
    #: :set: of :class:`~Gtk.Widget`s that have been built by the builder, and translated
    __built_widgets = set()

    def __init__(self):
        super(Builder, self).__init__()


    @staticmethod
    def __translate_widget_strings(a_widget):
        """ Calls gettext on all strings we can find in a_widgets.
        """
        for str_prop in (prop.name for prop in a_widget.props if prop.value_type == GObject.TYPE_STRING):
            try:
                setattr(a_widget.props, str_prop, _(getattr(a_widget.props, str_prop)))
            except TypeError:
                # Thrown when a string property is not readable
                pass

    @staticmethod
    def __recursive_translate_widgets(a_widget):
        """ Calls gettext on all strings we can find in widgets, recursively.
        """
        Builder.__translate_widget_strings(a_widget)

        if issubclass(type(a_widget), Gtk.Container):
            #NB: Parent-loop in widgets would cause infinite loop here, but that's absurd (right?)
            #NB2: maybe forall instead of foreach if we miss some strings?
            a_widget.foreach(Builder.__recursive_translate_widgets)

        if issubclass(type(a_widget), Gtk.MenuItem) and a_widget.get_submenu() is not None:
            Builder.__recursive_translate_widgets(a_widget.get_submenu())


    def signal_resolver(self, attr_list):
        """ Dynamically resolves a signal that is self.a.b.c() when attr_list is ['a', 'b', 'c'].

            This allows to specify multi-level signals in the XML files, instead of targeting everything at the main UI object.

            Also, resolving signals dynamically means the object properties of the top-level object can be replaced, and the signal
            will still connect to something meaningful. The downside is that this connection is done at runtime, thus probably less
            efficient and might fail to find the target if any attribute along the way has an unexpected value.
        """
        try:
            target = self
            for attr in attr_list:
                target = getattr(target, attr)

            return target

        except AttributeError as e:
            logger.error('Can not reach target of signal {}.{}()'.format(self, '.'.join(attr_list)), exc_info = True)


    def signal_connector(self, builder, object, signal_name, handler_name, connect_object, flags, *user_data):
        """ Callback for signal connection. Parse handler names and split on '.' to use some level of recursion
        """
        try:
            try:
                handler = getattr(self, handler_name)

            except AttributeError:
                attr_list =  handler_name.split('.')

                if len(attr_list) == 1:
                    logger.error('Handler name not in target object. Expected "." but got: {}'.format(handler_name), exc_info = True)
                    raise

                # Dynamically resolved handler for 'doc' (only) since self.doc may change
                if 'doc' in attr_list:
                    handler = lambda *args: Builder.signal_resolver(self, attr_list)(*args)
                else:
                    handler = Builder.signal_resolver(self, attr_list)

            object.connect(signal_name, handler, *user_data)

        except:
            logger.critical('Impossible to connect signal {} from object {} to hander {}'.format(signal_name, object, handler_name), exc_info = True)


    def connect_signals(self, base_target):
        """ Override default signal connector so we can map signals to the methods of (any depth of) object that are properties of self
        """
        Builder.connect_signals_full(base_target, self.signal_connector)


    def load_ui(self, resource_name):
        """ Loads the UI defined in the file named resource_name using the builder.
        """
        self.add_from_file(util.get_ui_resource_file(resource_name))

        # Get all newly built objects
        new_objects = set(self.get_objects()) - self.__built_widgets
        self.__built_widgets.update(new_objects)

        for obj in new_objects:
            # pass new objects to manual translation
            self.__translate_widget_strings(obj)

            # instrospectively load objects. If we have a self.attr == None and this attr is the name of a built object, link it together.
            if issubclass(type(obj), Gtk.Buildable):
                obj_id = Gtk.Buildable.get_name(obj)

                if hasattr(self, obj_id) and getattr(self, obj_id) is None:
                    setattr(self, obj_id, obj)


    def list_attributes(self, target):
        """
        """
        for attr in dir(target):
            try:
                if attr[:2] + attr[-2:] != '____' and getattr(target, attr) is None:
                    yield attr
            except RuntimeError:
                pass


    def load_widgets(self, target):
        """ Fill in target with the missing elements introspectively.
            This means that all attributes of target that are None at this time must exist under the same name in the builder.
        """
        for attr in self.list_attributes(target):
            setattr(target, attr, self.get_object(attr))


    def replace_layout(self, layout, top_widget, leaf_widgets, pane_resize_handler = None):
        """ Remix the layout below top_widget with the layout configuration given in 'layout' (assumed to be valid!).

            Args:
                layout (dict): the json-parsed config string, thus a hierarchy of lists/dicts, with strings as leaves
                top_widget (:class:`Gtk.Container`): The top-level widget under which we build the hierachyy
                leaf_widgets (dict): the map of valid leaf identifiers (strings) to the corresponding :class:`Gtk.Widget`s

            Returns:
                dict: The mapping of the used :class:`Gtk.Paned` widgets to their relative handle position (float between 0 and 1)
        """
        # take apart the previous/default layout
        containers = []
        widgets = top_widget.get_children()
        i = 0
        while i < len(widgets):
            w = widgets[i]
            if issubclass(type(w), Gtk.Box) or issubclass(type(w), Gtk.Paned):
                widgets.extend(w.get_children())
                containers.append(w)
            w.get_parent().remove(w)
            i += 1

        # cleanup widgets
        del widgets[:]
        while containers:
            containers.pop().destroy()

        # iterate over new layout to build it, using a BFS
        widgets_to_add = [(top_widget, layout)]
        pane_resize = set()
        pane_handle_pos = {}

        while widgets_to_add:
            parent, w_desc = widgets_to_add.pop(0)

            if type(w_desc) is str:
                w = leaf_widgets[w_desc]

            else:
                # get new container widget, attempt to recycle the containers we removed
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

                    # if more than 2 children are to be added, add the 2+ from the right side in a new child Gtk.Paned
                    widgets_to_add.append((w, w_desc['children'][0] if len(w_desc['children']) == 1 else w_desc))
                else:
                    w = Gtk.Box.new(getattr(Gtk.Orientation, w_desc['orientation'].upper()), 5)
                    w.set_homogeneous(True)
                    w.set_spacing(10)

                    widgets_to_add += [(w, c) for c in w_desc['children']]

            if issubclass(type(parent), Gtk.Box):
                parent.pack_start(w, True, True, 0)
            else: #it's a Gtk.Paned
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

            # hierarchichally ordered list of widgets
            widgets.append(w)

        for w in widgets:
            w.queue_resize()
            w.show_now()
            w.get_parent().check_resize()

        for p in (w for w in widgets if issubclass(type(w), Gtk.Box) or issubclass(type(w), Gtk.Paned)):
            p.check_resize()
            if p in pane_resize:
                if p.get_orientation() == Gtk.Orientation.HORIZONTAL:
                    pane_pos = int(round(Gtk.Widget.get_allocated_width(p) * pane_handle_pos[p]))
                else:
                    pane_pos = int(round(Gtk.Widget.get_allocated_height(p) * pane_handle_pos[p]))

                p.set_position(pane_pos)

        return pane_handle_pos


