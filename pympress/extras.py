#       extras.py
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
:mod:`pympress.extras` -- Manages the display of fancy extras such as annotations, videos and cursors
-----------------------------------------------------------------------------------------------------
"""

from __future__ import print_function

import logging
logger = logging.getLogger(__name__)

import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango

try:
    from pympress import vlcvideo
    vlc_enabled = True
except Exception as e:
    vlc_enabled = False
    logger.exception(_("video support is disabled"))


class Annotations(object):
    #: The containing widget for the annotations
    scrollable_treelist = None
    #: Making the annotations list scroll if it's too long
    scrolled_window = None

    #: :class:`~Gtk.CellRendererText` Text renderer for the annotations
    annotation_renderer = Gtk.CellRendererText()

    def __init__(self, builder):
        """ Load the widgets and setup for the annotations' display.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        builder.load_widgets(self)

        # wrap text
        self.annotation_renderer.props.wrap_mode = Pango.WrapMode.WORD_CHAR

        column = Gtk.TreeViewColumn(None, self.annotation_renderer, text=0)
        column.props.sizing = Gtk.TreeViewColumnSizing.AUTOSIZE
        column.set_fixed_width(1)

        self.scrollable_treelist.set_model(Gtk.ListStore(str))
        self.scrollable_treelist.append_column(column)

        self.scrolled_window.set_hexpand(True)


    def add_annotations(self, annotations):
        """ Insert text annotations into the tree view that displays them.

        Args:
            annotations (`list`): A list of strings, that are the annotations to be displayed
        """
        list_annot = Gtk.ListStore(str)

        bullet = b'\xe2\x97\x8f '.decode('utf-8') if sys.version_info > (3, 0) else '\xe2\x97\x8f '

        for annot in annotations:
            list_annot.append((bullet + annot,))

        self.scrollable_treelist.set_model(list_annot)


    def on_configure_annot(self, widget, event):
        """ Adjust wrap width in annotations when they are resized.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which was resized.
            event (:class:`~Gdk.Event`):  the GTK event.
        """
        self.annotation_renderer.props.wrap_width = max(30, widget.get_allocated_width() - 10)
        self.scrolled_window.queue_resize()
        self.scrollable_treelist.get_column(0).queue_resize()


    def on_scroll(self, widget, event):
        """ Try scrolling the annotations window.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        adj = self.scrolled_window.get_vadjustment()
        if event.direction == Gdk.ScrollDirection.UP:
            adj.set_value(adj.get_value() - adj.get_step_increment())
        elif event.direction == Gdk.ScrollDirection.DOWN:
            adj.set_value(adj.get_value() + adj.get_step_increment())
        else:
            return False
        return True


class Media(object):
    #: `dict` of :class:`~pympress.vlcvideo.VLCVideo` ready to be added on top of the slides
    _media_overlays = {}

    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None

    def __init__(self, builder):
        """ Set up the required widgets and queue an initial draw.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        builder.load_widgets(self)

        self.c_overlay.queue_draw()


    def replace_media_overlays(self, current_page):
        """ Remove current media overlays, add new ones if page contains media.

        Args:
            current_page (:class:`~pympress.document.Page`): The page for twhich to prepare medias
        """
        if not vlc_enabled:
            return

        self.c_overlay.foreach(lambda child, *ignored: child.hide() if type(child) is vlcvideo.VLCVideo else None, None)

        pw, ph = current_page.get_size()

        for relative_margins, filename, show_controls in current_page.get_media():
            media_id = hash((relative_margins, filename, show_controls))

            if media_id not in self._media_overlays:
                v_da = vlcvideo.VLCVideo(self.c_overlay, show_controls, relative_margins)
                v_da.set_file(filename)

                self._media_overlays[media_id] = v_da


    def resize(self):
        """ Resize all media overlays that are a child of c_overlay
        """
        if not vlc_enabled:
            return

        self.c_overlay.foreach(lambda child, *ignored: child.resize() if type(child) is vlcvideo.VLCVideo else None, None)


    def play(self, media_id):
        """ Starts playing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        if media_id in self._media_overlays:
            self._media_overlays[media_id].play()


class Cursor(object):
    #: a static `dict` of :class:`~Gdk.Cursor`s, ready to use
    _cursors = {
        'parent': None,
        'default': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default'),
        'pointer': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'pointer'),
        'invisible': Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'none'),
    }

    @classmethod
    def set_cursor(cls, widget, cursor_name = 'parent'):
        """ Set the cursor named cursor_name'

        Args:
            widget (:class:`~Gtk.Widget`): The widget triggering the cursor change, used to retrieve a Gdk.Window
            cursor_name (`str`): Name of the cursor to be set
        """
        widget.get_window().set_cursor(cls._cursors[cursor_name])


