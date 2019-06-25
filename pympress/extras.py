# -*- coding: utf-8 -*-
#
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

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import sys
import os.path
import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

import mimetypes

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pympress import media_overlay, document, builder


class TimingReport(builder.Builder):
    #: `list` of time at which each page was reached
    page_time = []
    #: `int` the time at which the clock was reset
    reset_time = -1
    #: The :class:`~Gtk.TreeView` containing the timing data to display in the dialog.
    timing_treeview = None
    #: A :class:`~Gtk.Dialog` to contain the timing to show.
    time_report_dialog = None

    def __init__(self, parent):
        super(TimingReport, self).__init__()
        self.load_ui('time_report_dialog')
        self.time_report_dialog.set_transient_for(parent.p_win)
        self.time_report_dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.connect_signals(self)


    def transition(self, page, time):
        ''' Record a transition time between slides

        Args:
            page (`int`): the page number of the current slide
            time (`int`): the number of seconds elapsed since the beginning of the presentation
        '''
        if self.reset_time >= 0:
            self.reset_time = -1
            self.page_time.clear()
        self.page_time.append((page, time))


    def reset(self, reset_time):
        ''' A timer reset. Clear the history as soon as we start changing pages again.
        '''
        self.reset_time = reset_time


    def show(self, current_time, doc_structure, page_labels):
        ''' Show the popup with the timing infortmation

        Args:
            current_time (`int`): the number of seconds elapsed since the beginning of the presentation
            doc_structure (`dict`): the structure of the document
            page_labels (`list`): the page labels for each of the pages
        '''
        times = [time for page, time in self.page_time] + [current_time if self.reset_time < 0 else self.reset_time]
        durations = (e - s for e, s in zip(times[1:], times[:-1]))

        infos = {'time': min(time for page, time in self.page_time), 'duration': 0, 'children': [], 'page': 0}
        infos['title'] = 'Full presentation'

        for (page, start_time), duration in zip(self.page_time, durations):
            if not duration:
                continue

            infos['duration'] += duration

            # lookup the position of the page in the document structure (section etc)
            lookup = doc_structure
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
            cur_info_pos['children'].append({'page': page, 'title': _('slide #') + page_labels[page],
                                        'duration': duration, 'time': start_time})


        treemodel = self.timing_treeview.get_model()
        if treemodel:
            treemodel.clear()

        treemodel = Gtk.TreeStore(str, str, str, str)

        dfs_info = [(None, infos)]
        while dfs_info:
            first_it, first = dfs_info.pop()
            fmt = lambda val: '{:02}:{:02}'.format(*divmod(val, 60))
            last_col = '{} ({}/{})'.format(page_labels[first['page']], first['page'], len(page_labels))
            row = [first['title'], fmt(first['time']), fmt(first['duration']), last_col]
            it = treemodel.append(first_it, row)

            if 'children' in first:
                dfs_info.extend((it, child) for child in reversed(first['children']))

        self.timing_treeview.set_model(treemodel)
        self.timing_treeview.expand_row(Gtk.TreePath.new_first(), False)

        self.time_report_dialog.run()
        self.time_report_dialog.hide()


class Annotations(object):
    #: The containing widget for the annotations
    scrollable_treelist = None
    #: Making the annotations list scroll if it's too long
    scrolled_window = None
    #: :class:`~Gtk.CellRendererText` Text renderer for the annotations
    annotation_renderer = None

    def __init__(self, builder):
        """ Load the widgets and setup for the annotations' display.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Annotations, self).__init__()
        builder.load_widgets(self)

        self.scrolled_window.set_hexpand(True)


    def add_annotations(self, annotations):
        """ Insert text annotations into the tree view that displays them.

        Args:
            annotations (`list`): A list of strings, that are the annotations to be displayed
        """
        prev_annots = self.scrollable_treelist.get_model()
        if prev_annots:
            prev_annots.clear()
        list_annot = Gtk.ListStore(str)

        for annot in annotations:
            list_annot.append(('● ' + annot,))

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
    #: `dict` of :class:`~pympress.media_overlay.VideoOverlay` ready to be added on top of the slides
    _media_overlays = {}

    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None
    #: :class:`~Gtk.Overlay` for the Presenter window.
    p_overlay = None

    def __init__(self, builder):
        """ Set up the required widgets and queue an initial draw.

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Media, self).__init__()
        builder.load_widgets(self)

        self.c_overlay.queue_draw()
        self.p_overlay.queue_draw()


    def remove_media_overlays(self):
        """ Remove current media overlays.
        """
        for media_id in self._media_overlays:
            self.hide(media_id)


    def purge_media_overlays(self):
        """ Remove current media overlays.
        """
        self.remove_media_overlays()
        self._media_overlays.clear()


    def replace_media_overlays(self, current_page, page_type):
        """ Remove current media overlays, add new ones if page contains media.

        Args:
            current_page (:class:`~pympress.document.Page`): The page for which to prepare medias
            page_type (:class:`~pympress.document.PdfPage`): The part of the page to consider
        """
        if page_type == document.PdfPage.NONE:
            return

        self.remove_media_overlays()

        for relative_margins, filename, show_controls in current_page.get_media():
            media_id = hash((relative_margins, filename, show_controls))

            if media_id not in self._media_overlays:
                mime_type, enc = mimetypes.guess_type(filename)
                factory = media_overlay.VideoOverlay.get_factory(mime_type)

                if not factory:
                    logger.warning('No available overlay for mime type {}, ignoring media {}'.format(mime_type, filename))
                    continue

                def get_curryfied_callback(name, media_id = media_id):
                    """ Return a callback for signal 'name' that has the value 'media_id' pre-set, and remembered by this closure.
                    """
                    return lambda *args: media_overlay.VideoOverlay.find_callback_handler(self, name)(media_id, *args)

                v_da_c = factory(self.c_overlay, show_controls, relative_margins, page_type, get_curryfied_callback)
                v_da_p = factory(self.p_overlay, True, relative_margins, page_type, get_curryfied_callback)

                v_da_c.set_file(filename)
                v_da_p.set_file(filename)

                self._media_overlays[media_id] = (v_da_c, v_da_p)

            self._media_overlays[media_id][0].mute(True)
            self._media_overlays[media_id][1].mute(False)

            for w in self._media_overlays[media_id]:
                if w.autoplay:
                    w.set_time(0)
                    w.show()


    def resize(self, which = None):
        """ Resize all media overlays that are a child of an overlay
        """
        needs_resizing = (which == 'content', which == 'presenter') if which is not None else (True, True)
        for media_id in self._media_overlays:
            for widget in (w for w, r in zip(self._media_overlays[media_id], needs_resizing) if r and w.is_shown()):
                widget.resize()


    def adjust_margins_for_mode(self, page_type):
        """ Adjust the relative margins of child widgets for notes mode update.

        Args:
            page_type (:class:`~pympress.document.PdfPage`): The part of the page to display
        """
        for media_id in self._media_overlays:
            for widget in self._media_overlays[media_id]:
                widget.update_margins_for_page(page_type)


    def play(self, media_id, button = None):
        """ Starts playing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        if media_id in self._media_overlays:
            c, p = self._media_overlays[media_id]
            p.show()
            c.show()
            GLib.idle_add(lambda: any(p.do_play() for p in self._media_overlays[media_id]))


    def hide(self, media_id, button = None):
        """ Stops playing a media and hides the player. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        for p in self._media_overlays[media_id]:
            c, p = self._media_overlays[media_id]
            if c.is_shown(): c.do_hide()
            if p.is_shown(): p.do_hide()


    def play_pause(self, media_id, *args):
        """ Toggles playing and pausing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
        """
        GLib.idle_add(lambda: any(p.do_play_pause() for p in self._media_overlays[media_id]))


    def set_time(self, media_id, t, *args):
        """ Set the player of a given media at time t. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
            t (`float`): the timestamp, in s
        """
        GLib.idle_add(lambda: any(p.do_set_time(t) for p in self._media_overlays[media_id]))


    @staticmethod
    def backend_version():
        """ Returns which backend is used.

        Returns:
            `str`: The name and version of the backend.
        """
        return media_overlay.VideoOverlay.backend_version()


class Cursor(object):
    #: a static `dict` of :class:`~Gdk.Cursor`s, ready to use
    _cursors = {
        'parent': None,
        'default': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.LEFT_PTR),
        'pointer': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.HAND1),
        'crosshair': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.CROSSHAIR),
        'invisible': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR),
    }

    @classmethod
    def set_cursor(cls, widget, cursor_name = 'parent'):
        """ Set the cursor named cursor_name'

        Args:
            widget (:class:`~Gtk.Widget`): The widget triggering the cursor change, used to retrieve a Gdk.Window
            cursor_name (`str`): Name of the cursor to be set
        """
        widget.get_window().set_cursor(cls._cursors[cursor_name])


class Zoom(object):
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    zoom_selecting = False
    zoom_points = None
    scale = 1.
    shift = (0, 0)

    #: a callback for the :func:`~Gtk.Button.set_sensitive` function of the zoom-out button in the scribble interface
    set_scribble_zoomout_sensitive = lambda: None
    #: :class:`~Gtk.MenuItem` that is clicked to stop zooming
    menu_zoom_out = None
    #: :class:`~Gtk.Box` in the Presenter window, used to reliably set cursors.
    p_central = None

    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda: None
    #: callback, to be connected to :func:`~pympress.ui.UI.clear_cache`
    clear_cache = lambda: None

    def __init__(self, builder):
        """ Setup all the necessary for zooming

        Args:
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Zoom, self).__init__()
        builder.load_widgets(self)

        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.clear_cache = builder.get_callback_handler('clear_zoom_cache')


    def delayed_callback_connection(self, scribble_builder):
        """ Connect callbacks later than at init, due to circular dependencies.
        Call this when the page_number module is initialized, but before needing the callback.

        Args:
            builder (builder.Builder): The builder from which to load widgets for scribble
        """
        self.set_scribble_zoomout_sensitive = scribble_builder.get_callback_handler('zoom_stop_button.set_sensitive')


    def start_zooming(self, *args):
        """ Setup for the user to select the zooming area.

        Returns:
            `bool`: whether the event was consumed
        """
        self.zoom_selecting = True
        Cursor.set_cursor(self.p_central, 'crosshair')

        return True


    def stop_zooming(self, *args):
        """ Cancel the zooming, if it was enabled.

        Returns:
            `bool`: whether the event was consumed
        """
        Cursor.set_cursor(self.p_central)
        self.zoom_selecting = False
        self.zoom_points = None
        self.scale = 1.
        self.shift = (0, 0)
        self.set_scribble_zoomout_sensitive(False)
        self.menu_zoom_out.set_sensitive(False)

        self.redraw_current_slide()
        self.clear_cache()

        return True


    def nav_zoom(self, name, ctrl_pressed):
        """ Handles an key press event: stop trying to select an area to zoom.

        Args:
            name (`str`): The name of the key pressed
            ctrl_pressed (`bool`): whether the ctrl modifier key was pressed

        Returns:
            `bool`: whether the event was consumed
        """
        if name == 'Escape' and self.zoom_selecting:
            Cursor.set_cursor(self.p_central)
            self.zoom_selecting = False
            self.zoom_points = None
            return True

        return False


    def get_slide_point(self, widget, event):
        """ Gets the point on the slide on a scale (0..1, 0..1), from its position in the widget.
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
        ex, ey = event.get_coords()

        return ((ex / ww - self.shift[0]) / self.scale, (ey / wh - self.shift[1]) / self.scale)


    def get_matrix(self, ww, wh):
        """ Returns the :class:`~cairo.Matrix` used to perform the zoom for the widget of size ww x wh.

        Args:
            ww (`float`):  widget width
            wh (`float`):  widget height

        Returns:
            :class:`~cairo.Matrix`: the zoom transformation matrix
        """
        return cairo.Matrix(xx = self.scale, x0 = ww * self.shift[0],
                            yy = self.scale, y0 = wh * self.shift[1])


    def track_zoom_target(self, widget, event):
        """ Draw the zoom's target rectangle.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.zoom_selecting and self.zoom_points:
            self.zoom_points[1] = self.get_slide_point(widget, event)

            self.redraw_current_slide()
            return True

        return False


    def toggle_zoom_target(self, widget, event):
        """ Start/stop drawing the zoom's target rectangle.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if not self.zoom_selecting:
            return False

        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            p = self.get_slide_point(widget, event)
            self.zoom_points = [p, p]

            return self.track_zoom_target(widget, event)

        elif event.get_event_type() == Gdk.EventType.BUTTON_RELEASE and self.zoom_points:
            self.zoom_points[1] = self.get_slide_point(widget, event)

            xmin, xmax = sorted(p[0] for p in self.zoom_points)
            ymin, ymax = sorted(p[1] for p in self.zoom_points)
            self.zoom_points = None

            try:
                # zoom by dimension less zoomed, to fit box while maintaining aspect ratio
                self.scale = 1. / max(ymax - ymin, xmax - xmin)

                # make center of drawn rectangle the center of the zoomed slide
                self.shift = (.5 - self.scale * (xmin + xmax) / 2,
                                    .5 - self.scale * (ymin + ymax) / 2)
            except ZeroDivisionError:
                self.scale = 1.
                self.shift = (0, 0)

            # stop drawing rectangles and reset cursor (NB don't use window, this bugs)
            Cursor.set_cursor(self.p_central)

            self.zoom_selecting = False
            self.clear_cache()
            self.redraw_current_slide()
            self.set_scribble_zoomout_sensitive(True)
            self.menu_zoom_out.set_sensitive(True)

            return True

        return False


    def draw_zoom_target(self, widget, cairo_context):
        """ Perform the drawings by user.

        Args:
            widget (:class:`~Gtk.DrawingArea`): The widget where to draw the scribbles.
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the drawings
        """
        ww, wh = widget.get_allocated_width(), widget.get_allocated_height()

        if self.zoom_selecting and self.zoom_points:
            xmin, xmax = sorted(p[0] * ww for p in self.zoom_points)
            ymin, ymax = sorted(p[1] * wh for p in self.zoom_points)

            rect = Gdk.Rectangle()
            rect.x = xmin
            rect.width = xmax - xmin
            rect.y = ymin
            rect.height = ymax - ymin

            cairo_context.set_line_width(3)
            cairo_context.set_line_cap(cairo.LINE_CAP_SQUARE)
            Gdk.cairo_rectangle(cairo_context, rect)
            cairo_context.set_source_rgba(.1, .1, 1, .4)
            cairo_context.stroke()

            Gdk.cairo_rectangle(cairo_context, rect)
            cairo_context.set_source_rgba(.5, .5, 1, .2)
            cairo_context.fill()



class FileWatcher(object):
    """ A class with only static methods that wraps object watchdogs, to trigger callbacks when a file changes.
    """
    #: A :class:`~watchdog.observers.Observer` to watch when the file changes
    observer = Observer()

    #: A :class:`~watchdog.events.FileSystemEventHandler` to get notified when the file changes
    monitor = FileSystemEventHandler()

    # `int` that is a GLib timeout id to delay the callback
    timeout = 0

    @classmethod
    def watch_file(cls, path, callback, *args, **kwargs):
        """ Watches a new file with a new callback. Removes any precedent watched files.

        Args:
            path (`str`): full path to the file to watch
            callback (`function`): callback to call with all the further arguments when the file changes
        """
        cls.start_daemon()
        cls.stop_watching()

        directory = os.path.dirname(path)
        cls.monitor.on_modified = lambda evt: cls.enqueue(callback, *args, **kwargs) if evt.src_path == path else None
        try:
            cls.observer.schedule(cls.monitor, directory)
        except OSError:
            logger.error('Impossible to open dir at {}'.format(directory), exc_info = True)

    @classmethod
    def enqueue(cls, callback, *args, **kwargs):
        """ Do not call callback directly, instead delay as to avoid repeated calls in short periods of time.

        Args:
            callback (`function`): callback to call with all the further arguments
        """
        if cls.timeout:
            GLib.Source.remove(cls.timeout)
        cls.timeout = GLib.timeout_add(200, cls.call, callback, *args, **kwargs)


    @classmethod
    def call(cls, callback, *args, **kwargs):
        """ Call the callback

        Args:
            callback (`function`): callback to call with all the further arguments
        """
        if cls.timeout:
            cls.timeout = 0
        callback(*args, **kwargs)


    @classmethod
    def stop_watching(cls):
        """ Remove all files that are being watched
        """
        cls.observer.unschedule_all()


    @classmethod
    def start_daemon(cls):
        """ Start the watchdog observer thread
        """
        if not cls.observer.is_alive():
            cls.observer.start()


    @classmethod
    def stop_daemon(cls, wait = False):
        """ Stop the watchdog observer thread.

        Args:
            wait (`bool`): whether to wait for the thread to have joined before returning
        """
        cls.observer.unschedule_all()
        if cls.observer.is_alive():
            cls.observer.stop()

        while wait and cls.observer.is_alive():
            cls.observer.join()
