# -*- coding: utf-8 -*-
#
#       extras.py
#
#       Copyright 2021 Cimbali <me@cimba.li>
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
:mod:`pympress.extras` -- Manages the display of fancy extras such as annotations, videos and cursors
-----------------------------------------------------------------------------------------------------
"""

import logging
logger = logging.getLogger(__name__)

import copy

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from pympress import builder


class TimingReport(builder.Builder):
    """ Widget tracking and displaying hierachically how much time was spent in each page/section of the presentation.
    """
    #: `list` of time at which each page was reached
    page_time = []
    #: `int` the time at which the clock was reset
    end_time = -1
    #: The :class:`~Gtk.TreeView` containing the timing data to display in the dialog
    timing_treeview = None
    #: A :class:`~Gtk.Dialog` to contain the timing to show
    time_report_dialog = None
    #: `bool` marking whether next page transition should reset the history of page timings
    clear_on_next_transition = False

    #: A `dict` containing the structure of the current document
    doc_structure = {}
    #: A `list` with the page label of each page of the current document
    page_labels = []
    #: `bool` tracking whether a document is opened
    document_open = False

    def __init__(self, parent):
        super(TimingReport, self).__init__()
        self.load_ui('time_report_dialog')
        self.time_report_dialog.set_transient_for(parent.p_win)
        self.time_report_dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        self.connect_signals(self)
        parent.setup_actions({
            'timing-report': dict(activate=self.show_report),
        })


    def transition(self, page, time):
        """ Record a transition time between slides.

        Args:
            page (`int`): the page number of the current slide
            time (`int`): the number of seconds elapsed since the beginning of the presentation
        """
        if not self.document_open:
            return

        if self.clear_on_next_transition:
            self.clear_on_next_transition = False
            del self.page_time[:]

        self.page_time.append((page, time))


    def reset(self, reset_time):
        """ A timer reset. Clear the history as soon as we start changing pages again.
        """
        self.end_time = reset_time
        self.clear_on_next_transition = True


    @staticmethod
    def format_time(secs):
        """ Formats a number of seconds as `minutes:seconds`.

        Returns:
            `str`: The formatted time, with 2+ digits for minutes and 2 digits for seconds.
        """
        return '{:02}:{:02}'.format(*divmod(secs, 60))


    def set_document_metadata(self, doc_structure, page_labels):
        """ Show the popup with the timing infortmation.

        Args:
            doc_structure (`dict`): the structure of the document
            page_labels (`list`): the page labels for each of the pages
        """
        self.document_open = len(page_labels) != 0

        # Do not update if we only close the document.
        # That way, the report is still accessible when the document is closed.
        if not self.document_open:
            return

        self.doc_structure = doc_structure
        self.page_labels = page_labels

        # Clear the report when there is a new document opened.
        del self.page_time[:]


    def show_report(self, gaction, param=None):
        """ Show the popup with the timing infortmation.
        """
        times = [time for page, time in self.page_time]
        durations = (e - s for s, e in zip(times, times[1:] + [self.end_time]))

        min_time = min(time for page, time in self.page_time) if self.page_time else 0
        infos = {'time': min_time, 'duration': 0, 'children': [], 'page': 0}
        infos['title'] = 'Full presentation'

        for (page, start_time), duration in zip(self.page_time, durations):
            if not duration:
                continue

            infos['duration'] += duration

            # lookup the position of the page in the document structure (section etc)
            lookup = self.doc_structure
            cur_info_pos = infos
            while lookup:
                try:
                    pos = max(p for p in lookup if p <= page)
                except ValueError:
                    break
                item = lookup[pos]
                lookup = item.get('children', None)

                if cur_info_pos['children'] and cur_info_pos['children'][-1]['page'] == pos:
                    cur_info_pos['children'][-1]['duration'] += duration
                else:
                    cur_info_pos['children'].append({'page': pos, 'title': item['title'], 'children': [],
                                                     'duration': duration, 'time': start_time})
                cur_info_pos = cur_info_pos['children'][-1]

            # add the actual page as a leaf node
            label = self.page_labels[page] if 0 <= page < len(self.page_labels) else 'None'
            cur_info_pos['children'].append({'page': page, 'title': _('slide #') + label,
                                             'duration': duration, 'time': start_time})


        treemodel = self.timing_treeview.get_model()
        if treemodel:
            treemodel.clear()

        treemodel = Gtk.TreeStore(str, str, str, str)

        dfs_info = [(None, infos)]
        while dfs_info:
            first_it, first = dfs_info.pop()
            page = first['page']
            label = self.page_labels[page] if 0 <= page < len(self.page_labels) else 'None'

            last_col = '{} ({}/{})'.format(label, page, len(self.page_labels))
            row = [first['title'], self.format_time(first['time']), self.format_time(first['duration']), last_col]
            it = treemodel.append(first_it, row)

            if 'children' in first:
                dfs_info.extend((it, child) for child in reversed(first['children']))

        self.timing_treeview.set_model(treemodel)
        self.timing_treeview.expand_row(Gtk.TreePath.new_first(), False)

        self.time_report_dialog.run()
        self.time_report_dialog.hide()


class LayoutEditor(builder.Builder):
    """ Widget tracking and displaying hierachically how much time was spent in each page/section of the presentation.
    """
    #: The :class:`~Gtk.TreeView` displaying the hierarchical layouts
    layout_treeview = None
    #: The :class:`~Gtk.TreeModel` containing the model of the layouts to view in the treeview
    layout_treemodel = None
    #: The :class:`~Gtk.ListModel` containing the possible orientations
    orientations_model = None
    #: A :class:`~Gtk.Dialog` to contain the layout edition dialog
    layout_dialog = None
    #: A :class:`~Gtk.Label` to contain the description of the layout
    layout_description = None
    #: :class:`~pympress.config.Config` to remember preferences
    config = None
    #: :class:`~Gio.Action` containing the number of next frames
    next_frames_action = None
    #: `str` containing the layout currently edited
    current_layout = 'plain'
    #: callback, to be connected to :func:`~pympress.ui.UI.load_layout`
    ui_load_layout = lambda *args: None

    layout_descriptions = {
        'notes':      _('Layout for beamer notes on second screen (no current slide preview in notes)'),
        'plain':      _('Plain layout, without note slides'),
        'note_pages': _('Layout for libreoffice notes on separate pages (with current slide preview in notes)'),
    }

    _model_columns = ['widget', 'is_box', 'resizeable', 'orientation', 'next_slide_count', 'widget_name']

    def __init__(self, parent, config):
        super(LayoutEditor, self).__init__()
        self.load_ui('layout_dialog')
        self.layout_dialog.set_transient_for(parent.p_win)
        self.layout_dialog.add_button(Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY)
        self.layout_dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.config = config
        self.ui_load_layout = parent.get_callback_handler('load_layout')

        self.connect_signals(self)
        parent.setup_actions({
            'edit-layout': dict(activate=self.show_editor),
        })


    def load_layout(self):
        """ Load the given layout in the treemodel for display and manipulation in the treeview
        """
        self.layout_description.set_text(self.layout_descriptions[self.current_layout])
        self.layout_treemodel.clear()

        # Display names for the widget ids
        names = {
            'box':         _('box'),
            'notes':       _('notes'),
            'current':     _('current slide'),
            'next':        _('next slide(s)'),
            'annotations': _('annotations (hideable)'),
            'vertical':    _('vertical'),
            'horizontal':  _('horizontal'),
        }

        next_count = self.next_frames_action.get_state().get_int64()
        dfs_info = [(None, self.config.get_layout(self.current_layout))]

        while dfs_info:
            it, node = dfs_info.pop()

            if type(node) is str:
                self.layout_treemodel.append(it, [node, False, False, '', next_count if node == 'next' else 0,
                                                  names[node]])

            else:
                next_it = self.layout_treemodel.append(it, ['box', True, node['resizeable'], names[node['orientation']],
                                                            0, names['box']])
                dfs_info.extend((next_it, child) for child in reversed(node['children']))

        self.layout_treeview.expand_all()


    def set_current_layout(self, layout):
        """ Update which is the layout currently used by the UI

        Args:
            layout (`str`): the layout id
        """
        self.current_layout = layout


    def layout_selected(self, widget, event=None):
        """ Manage events for the layout selector drop-down menu

        Args:
            widget (:class:`~Gtk.ComboBox`):  the widget which has been modified
            event (:class:`~Gdk.Event`):  the GTK event
        """
        self.current_layout = widget.get_active_id()
        self.load_layout()


    def get_info(self, path):
        """ Given a path string, look up the appropriate item in both the actual and GtkStore models

        Args:
            path (`str`):  A string representing a path in the treemodel

        Returns:
            `dict`, :class:`~Gtk.TreeIter`: the node and iterator representing the position in the layout and model
        """
        pos = Gtk.TreePath.new_from_string(path)
        tree_it = self.layout_treemodel.get_iter(pos)
        node = {'children': [self.config.get_layout(self.current_layout)]}
        for n in pos.get_indices():
            node = node['children'][n]
        return node, tree_it


    def resizeable_toggled(self, widget, path):
        """ Handle when box’ resizeable value is toggled

        Args:
            widget (:class:`~Gtk.ComboBox`):  the widget which has been modified
            path (`str`):  A string representing the path to the modfied item
        """
        node, tree_it = self.get_info(path)
        value = not node['resizeable']
        node['resizeable'] = value
        self.layout_treemodel.set_value(tree_it, self._model_columns.index('resizeable'), value)
        self.normalize_layout(reload=False)


    def orientation_changed(self, widget, path, orient_it):
        """ Handle when the orientation of a box is changed

        Args:
            widget (:class:`~Gtk.ComboBox`):  the widget which has been modified
            path (`str`):  A string representing the path to the modfied item
            orient_it (:class:`~Gtk.TreeIter`): the row of the newly selected value in the orientations liststore model
        """
        value = self.orientations_model.get_value(orient_it, 1)
        node, tree_it = self.get_info(path)
        node['orientation'] = value
        self.layout_treemodel.set_value(tree_it, self._model_columns.index('orientation'), value)
        self.normalize_layout(reload=False)


    def next_slide_count_edited(self, widget, path, value):
        """ Handle when the next slide count is modified

        Args:
            widget (:class:`~Gtk.ComboBox`):  the widget which has been modified
            path (`str`):  A string representing the path to the modfied item
            value (`int`): the new number of next slides
        """
        node, tree_it = self.get_info(path)
        self.layout_treemodel.set_value(tree_it, self._model_columns.index('next_slide_count'), int(value))
        self.next_frames_action.activate(GLib.Variant.new_int64(int(value)))


    def treemodel_to_tree(self, iterator, parent_horizontal=False, parent_resizeable=False):
        """ Recursive function to transform the treemodel back into our dict-based representation of the layout

        Args:
            iterator (:class:`~Gtk.TreeIter`): the position in the treemodel
            parent_horizontal (`bool`): whether the parent node is horizontal
            parent_resieable (`bool`): whether the parent node is resizeable

        Returns:
            `list`: the list of `dict` or `str` representing the widgets at this level
        """
        nodes = []
        while iterator is not None:
            values = self.layout_treemodel.get(iterator, *range(len(self._model_columns[:-2])))
            node = dict(zip(self._model_columns, values))

            # Make the node conform to either a string or a dictionary with 'children' key
            if node.pop('is_box'):
                node['children'] = []
                del node['widget']
            else:
                node = node['widget']

            if self.layout_treemodel.iter_has_child(iterator):
                children = self.treemodel_to_tree(self.layout_treemodel.iter_children(iterator), *(
                    [parent_horizontal, parent_resizeable] if type(node) is str else
                    [node['orientation'] == 'horizontal', node['resizeable']]
                ))
                if len(children) > 1 and type(node) is not str:
                    # Only assign children if there are any, allows to prune empty boxes
                    node['children'] = children
                elif children and type(node) is not str:
                    # Single-child box replaced by its children
                    node = children[0]
                elif children:
                    # Non-box node with children: create a new box and set the non-box as first child
                    node = {'children': [node] + children, 'resizeable': not parent_resizeable,
                            'orientation': 'vertical' if parent_horizontal else 'horizontal'}

            # Only append widgets, and box nodes that have children
            if type(node) is str or node['children']:
                nodes.append(node)

            iterator = self.layout_treemodel.iter_next(iterator)

        return nodes


    def normalize_layout(self, widget=None, drag_context=None, reload=True):
        """ Handler at the end of a drag-and-drop in the treeview

        Here we transform the listmodel modified by drag-and-drop back to a valid `dict` and `str` hierarchy, and then
        trigger the loading of the layout again to display the corrected layout.

        Args:
            widget (:class:`~Gtk.Widget`): The object which received the signal
            drag_context (:class:`~Gdk.DragContext`): the drag context
            reload (`bool`): whether to reload the layout into the treemodel
        """
        layout = self.treemodel_to_tree(self.layout_treemodel.get_iter_first())
        if len(layout) > 1:
            layout = {'children': layout, 'orientation': 'horizontal', 'resizeable': True}
        else:
            layout = layout[0]
        # This validates
        self.config.update_layout_tree(self.current_layout, layout)
        self.ui_load_layout(None)
        if reload:
            self.load_layout()


    def show_editor(self, gaction, param=None):
        """ Show the popup to edit the layout. Gather info to populate it, and handle apply/cancel at the end.

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        restore_layouts = {layout: copy.deepcopy(self.config.get_layout(layout)) for layout in self.layout_descriptions}

        self.next_frames_action = self.get_application().lookup_action('next-frames')
        restore_next_count = self.next_frames_action.get_state().get_int64()

        self.get_object('layout_selector').set_active_id(self.current_layout)
        self.load_layout()

        if self.layout_dialog.run() != Gtk.ResponseType.APPLY:
            for layout_name, layout in restore_layouts.items():
                self.config.update_layout_tree(layout_name, layout)
            self.next_frames_action.activate(GLib.Variant.new_int64(restore_next_count))
            self.ui_load_layout(None)

        self.layout_dialog.hide()
