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

import logging
logger = logging.getLogger(__name__)

import pathlib
import mimetypes
import functools
from urllib.request import url2pathname

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio

from pympress import document, builder, util


class Annotations(object):
    """ Widget displaying a PDF’s text annotations.
    """
    #: The containing :class:`~Gtk.TreeView` widget for the annotations
    annotations_treeview = None
    #: The containing :class:`~Gtk.ListStore` storing the annotations to be displayed
    annotations_liststore = None
    #: The :class:`~Gtk.Entry` in which we are currently editing an annotation, or None
    editing = None

    new_doc_annotation = lambda *args: None
    set_doc_annotation = lambda *args: None
    remove_doc_annotation = lambda *args: None

    def __init__(self, builder):
        super(Annotations, self).__init__()
        builder.load_widgets(self)
        builder.setup_actions({
            'add-annotation': dict(activate=self.add_annotation),
            'remove-annotation': dict(activate=self.remove_annotation),
        })


    def load_annotations(self, annot_page):
        """ Add annotations to be displayed (typically on going to a new slide).

        Args:
            annot_page (:class:`~pympress.document.Page`): The page object that contains the annotations
        """
        self.annotations_liststore.clear()
        for num, annot in enumerate(annot_page.get_annotations()):
            self.annotations_liststore.append([annot.get_contents(), num])

        self.new_doc_annotation = annot_page.new_annotation
        self.set_doc_annotation = annot_page.set_annotation
        self.remove_doc_annotation = annot_page.remove_annotation


    def try_cancel(self):
        """ Try to cancel editing

        Returns:
            `bool`: whether editing was enabled and thus canceled
        """
        if self.editing is None:
            return False

        rows = self.annotations_treeview.get_selection().get_selected_rows()[1]
        if rows:
            self.annotations_treeview.set_cursor(rows[0], None, False)
        return True


    def key_event(self, widget, event):
        """ Handle a key (press/release) event.

        Needed to forward events directly to the :class:`~Gtk.Entry`, bypassing the global action accelerators.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.editing is None:
            return False
        elif event.get_event_type() == Gdk.EventType.KEY_PRESS:
            return self.editing.do_key_press_event(self.editing, event)
        elif event.get_event_type() == Gdk.EventType.KEY_RELEASE:
            return self.editing.do_key_release_event(self.editing, event)
        return False


    def editing_started(self, cell_renderer, widget, entry_number):
        """ Handle edit start

        Args:
            cell_renderer (:class:`~Gtk.CellRenderer`): The renderer which received the signal
            widget (:class:`~Gtk.CellEditable`): the Gtk entry editing the annotation entry
            entry_number (`str`): the string representation of the path identifying the edited cell
        """
        self.editing = widget


    def editing_validated(self, cell_renderer, entry_number, new_content):
        """ Handle successful edit: store the new cell value in the model and the document

        Args:
            cell_renderer (:class:`~Gtk.CellRenderer`): The renderer which received the signal
            entry_number (`str`): the string representation of the path identifying the edited cell
            new_content (`str`): the new value of the edited cell
        """
        path = Gtk.TreePath.new_from_string(entry_number)
        row = self.annotations_liststore.get_iter(path)
        self.annotations_liststore.set_value(row, 0, new_content)
        self.set_doc_annotation(path.get_indices()[0], new_content)
        self.editing_finished(cell_renderer)


    def editing_finished(self, cell_renderer):
        """ Handle the end of editing

        Args:
            cell_renderer (:class:`~Gtk.CellRenderer`): The renderer which received the signal
        """
        self.editing = None


    def add_annotation(self, gaction, param=None):
        """ Add an annotation to the the page’s annotation list

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call, which identifies which backend
            param (:class:`~GLib.Variant`): an optional parameter
        """
        path = self.annotations_liststore.get_path(self.annotations_liststore.append())
        self.annotations_treeview.set_cursor(path, self.annotations_treeview.get_columns()[0], True)
        self.new_doc_annotation(path.get_indices()[0])
        return True


    def remove_annotation(self, gaction, param=None):
        """ Remove an annotation to the from the page’s annotation list

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call, which identifies which backend
            param (:class:`~GLib.Variant`): an optional parameter
        """
        rows = self.annotations_treeview.get_selection().get_selected_rows()[1]
        if not rows:
            return False
        self.annotations_liststore.remove(self.annotations_liststore.get_iter(rows[0]))
        self.remove_doc_annotation(rows[0].get_indices()[0])
        return True



class Media(object):
    """ Class managing statically the medias and media player backends, to enable play/pause callbacks.

    Args:
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        conf (:class:`~pympress.config.Config`): An object containing the preferences
    """
    #: `dict` of :class:`~pympress.media_overlays.base.VideoOverlay` ready to be added on top of the slides
    _media_overlays = {}

    #: :class:`~Gtk.Overlay` for the Content window.
    c_overlay = None
    #: :class:`~Gtk.Overlay` for the Presenter window.
    p_overlay = None

    #: `dict` with the backend modules that were correctly loaded, mapping backend identifiers (`str`)
    #: to :class:`~pympress.media_overlays.base.VideoOverlay` sub-classes
    _backends = {}
    #: `dict` containing backends and their mappings to mime type lists for which they are enabled.
    #: A default backend is marked by an empty list.
    types_list = {}

    def __init__(self, builder, conf):
        super(Media, self).__init__()
        self.conf = conf

        self._setup_backends()
        builder.load_widgets(self)

        builder.setup_actions({
            'use-{}-backend'.format(backend): {
                'activate': self.toggle,
                'state': backend in self.types_list,
                'enabled': backend in self._backends,
            } for backend in self._backends
        })

        self.c_overlay.queue_draw()
        self.p_overlay.queue_draw()


    def toggle(self, gaction, param=None):
        """ Toggle a backend (if it was loaded correctly)

        Args:
            gaction (:class:`~Gio.Action`): the action triggering the call, which identifies which backend
            param (:class:`~GLib.Variant`): an optional parameter
        """
        backend = gaction.get_name().split('-')[1]
        if backend not in self._backends:
            return ValueError('Unexpected backend')

        enable = backend not in self.types_list

        if enable:
            self.types_list[backend] = self.conf.getlist(backend, 'mime_types')
        else:
            del self.types_list[backend]

        gaction.change_state(GLib.Variant.new_boolean(enable))
        self.conf.set(backend, 'enabled', 'on' if enable else 'off')


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

        for media in current_page.get_media():
            media_id = hash(media)

            if media_id not in self._media_overlays:
                mime_type, enc = mimetypes.guess_type(media.filename)
                factory = self.get_factory(mime_type)

                if not factory:
                    logger.warning('No available overlay for mime type {}, ignoring media {}'
                                   .format(mime_type, media.filename))
                    continue

                action_group = Gio.SimpleActionGroup.new()
                builder.Builder.setup_actions({
                    'play':     dict(activate=functools.partial(self.play, media_id)),
                    'stop':     dict(activate=functools.partial(self.hide, media_id)),
                    'pause':    dict(activate=functools.partial(self.play_pause, media_id)),
                    'set_time': dict(activate=functools.partial(self.set_time, media_id), parameter_type=float)
                }, action_group)

                v_da_c = factory(self.c_overlay, page_type, action_group, media)
                v_da_p = factory(self.p_overlay, page_type, action_group, media._replace(show_controls=True))

                self._media_overlays[media_id] = (v_da_c, v_da_p)

            self._media_overlays[media_id][0].mute(True)
            self._media_overlays[media_id][1].mute(False)

            if any(overlay.autoplay for overlay in self._media_overlays[media_id]):
                GLib.idle_add(self.play, media_id)
            # TODO: handle poster


    def resize(self, which=None):
        """ Resize all media overlays that are a child of an overlay.
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


    def play(self, media_id, gaction=None, param=None):
        """ Starts playing a media. Used as a callback.

        Args:
            media_id (`int`): A unique identifier of the media to start playing
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        if media_id in self._media_overlays:
            c, p = self._media_overlays[media_id]
            p.show()
            c.show()
            GLib.idle_add(lambda: any(p.do_play() for p in self._media_overlays[media_id]))


    def hide(self, media_id, gaction=None, param=None):
        """ Stops playing a media and hides the player. Used as a callback.

        Args:
            media_id (`int`): A unique identifier of the media to start playing
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        if media_id in self._media_overlays:
            c, p = self._media_overlays[media_id]
            if c.is_shown(): GLib.idle_add(c.do_hide)
            if p.is_shown(): GLib.idle_add(p.do_hide)


    def hide_all(self):
        """ Stops all playing medias and hides the players. Used before exit.
        """
        for c, p in self._media_overlays.values():
            if c.is_shown(): GLib.idle_add(c.do_hide)
            if p.is_shown(): GLib.idle_add(p.do_hide)


    def play_pause(self, media_id, gaction=None, param=None):
        """ Toggles playing and pausing a media. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): the parameter as a variant, or None
        """
        GLib.idle_add(lambda: any(p.do_play_pause() for p in self._media_overlays[media_id]))


    def set_time(self, media_id, gaction=None, param=None):
        """ Set the player of a given media at time t. Used as a callback.

        Args:
            media_id (`int`): A unique idientifier of the media to start playing
            gaction (:class:`~Gio.Action`): the action triggering the call
            param (:class:`~GLib.Variant`): A wrapped float containing the time to which we have to go.
        """
        t = param.get_double()
        GLib.idle_add(lambda: any(p.do_set_time(t) for p in self._media_overlays[media_id]))


    def _setup_backends(self):
        """ Load the backends for video overlays.
        """
        try:
            from pympress.media_overlays.gif_backend import GifOverlay

            gif_version = GifOverlay.setup_backend()
            self._backends['gif'] = GifOverlay
            self.types_list['gif'] = ['image/gif', 'image/svg+xml']

        except Exception as e:
            gif_version = 'GdkPixbuf not available'
            logger.error(_('Media support using {} is disabled.').format('GdkPixbuf'))
            logger.info(_('Caused by ') + type(e).__name__ + ': ' + str(e))


        if not self.conf.getboolean('gstreamer', 'enabled'):
            gst_version = 'GStreamer disabled'
        else:
            try:
                from pympress.media_overlays.gst_backend import GstOverlay
                gst_version = GstOverlay.setup_backend(self.conf.getlist('gstreamer', 'init_options'))
            except Exception as e:
                gst_version = 'GStreamer not available'
                logger.debug(_('Media support using {} is disabled.').format('GStreamer'))
                logger.debug(_('Caused by ') + type(e).__name__ + ': ' + str(e))
            else:
                self._backends['gstreamer'] = GstOverlay
                self.types_list['gstreamer'] = self.conf.getlist('gstreamer', 'mime_types')


        if not self.conf.getboolean('vlc', 'enabled'):
            vlc_version = 'VLC disabled'
        else:
            try:
                from pympress.media_overlays.vlc_backend import VlcOverlay
                vlc_version = VlcOverlay.setup_backend(self.conf.getlist('vlc', 'init_options'))
            except Exception as e:
                vlc_version = 'VLC not available'
                logger.debug(_('Media support using {} is disabled.').format('VLC'))
                logger.debug(_('Caused by ') + type(e).__name__ + ': ' + str(e))
            else:
                self._backends['vlc'] = VlcOverlay
                self.types_list['vlc'] = self.conf.getlist('vlc', 'mime_types')

        self.backend_version = ', '.join([gif_version, gst_version, vlc_version])
        logger.info(_('Media support: ') + self.backend_version)


    def get_factory(self, mime_type):
        """ Returns a class of type :attr:`~_backend`.
        """
        # Search for specific mime type, if no matches fall back to empty lists which mean any mime types
        options = [backend for backend, mime_types in self.types_list.items() if mime_type in mime_types]
        if not options:
            options = [backend for backend, mime_types in self.types_list.items() if len(mime_types) == 0]

        if not options:
            return None

        # Prefer more stable backends with less external dependencies
        priority = ['gif', 'vlc', 'gstreamer'] if util.IS_WINDOWS else ['gif', 'gstreamer', 'vlc']
        return self._backends[sorted(options, key=priority.index)[0]]



class Cursor(object):
    """ Class managing cursors statically for displays, so we can select the mouse cursor with a simple string.
    """
    #: a static `dict` of :class:`~Gdk.Cursor`s, ready to use
    _cursors = {
        'parent': None,
    }

    @classmethod
    def _populate_cursors(cls):
        cls._cursors.update({
            'default': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.LEFT_PTR),
            'pointer': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.HAND1),
            'crosshair': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.CROSSHAIR),
            'invisible': Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR),
        })

    @classmethod
    def set_cursor(cls, widget, cursor_name = 'parent'):
        """ Set the cursor named cursor_name'.

        Args:
            widget (:class:`~Gtk.Widget`): The widget triggering the cursor change, used to retrieve a Gdk.Window
            cursor_name (`str`): Name of the cursor to be set
        """
        try:
            cursor = cls._cursors[cursor_name]
        except KeyError:
            cls._populate_cursors()
            cursor = cls._cursors[cursor_name]

        window = widget.get_window()
        if window is not None:
            window.set_cursor(cursor)


class Zoom(object):
    """ Manage the zoom level (using a cairo matrix), draw area that will be zoomed while it is being selected.

    Args:
        builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
    """
    #: Whether we are displaying the interface to scribble on screen and the overlays containing said scribbles
    zoom_selecting = False
    zoom_points = None
    scale = 1.
    shift = (0, 0)

    #: :class:`~Gtk.Box` in the Presenter window, used to reliably set cursors.
    p_central = None
    #: callback, to be connected to :meth:`~pympress.app.Pympress.set_action_enabled`
    set_action_enabled = None

    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.clear_cache`
    clear_cache = lambda *args: None

    def __init__(self, builder):
        super(Zoom, self).__init__()
        builder.load_widgets(self)

        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')
        self.clear_cache = builder.get_callback_handler('clear_zoom_cache')
        self.set_action_enabled = builder.get_callback_handler('app.set_action_enabled')

        builder.setup_actions({
            'zoom':   dict(activate=self.start_zooming),
            'unzoom': dict(activate=self.stop_zooming),
        })


    def start_zooming(self, *args):
        """ Setup for the user to select the zooming area.

        Returns:
            `bool`: whether the event was consumed
        """
        self.zoom_selecting = True
        Cursor.set_cursor(self.p_central, 'crosshair')

        return True


    def stop_zooming(self, *args):
        """ Cancel the zooming, reset the zoom level to full page.

        Returns:
            `bool`: whether the event was consumed
        """
        Cursor.set_cursor(self.p_central)
        self.zoom_selecting = False
        self.zoom_points = None
        self.scale = 1.
        self.shift = (0, 0)
        self.set_action_enabled('unzoom', False)

        self.redraw_current_slide()
        self.clear_cache()

        return True


    def try_cancel(self):
        """ Cancel the zoom selection, if it was enabled.

        Returns:
            `bool`: `True` if the zoom was cancelled, `False` if a zoom selection was not in progress.
        """
        if not self.zoom_selecting:
            return False

        Cursor.set_cursor(self.p_central)
        self.zoom_selecting = False
        self.zoom_points = None
        return True


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
            self.set_action_enabled('unzoom', True)

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


    def nop(*args, **kwargs):
        """ Do nothing
        """
        pass



class FileWatcher(object):
    """ A class that wraps watchdog objects, to trigger callbacks when a file changes.
    """
    #: A :class:`~watchdog.observers.Observer` to watch when the file changes
    observer = None

    #: A :class:`~watchdog.events.FileSystemEventHandler` to get notified when the file changes
    monitor = None

    # `int` that is a GLib timeout id to delay the callback
    timeout = 0

    #: The :class:`~pathlib.Path` to the file being watched
    path = None

    #: Callback to be called on file changes, usually connected to :meth:`~pympress.ui.UI.reload_document`
    callback = lambda: None

    def __init__(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            self.observer = Observer()
            self.monitor = FileSystemEventHandler()

            self.observer.start()

        except ImportError:
            logger.error(_('Missing dependency: python "{}" package').format('watchdog'))
            logger.info(_('Monitoring of changes to reload files automatically is not available'))


    def __del__(self):
        """ On finalize, cancel the watchdog observer thread.
        """
        self.stop_watching()
        if self.observer.is_alive():
            self.observer.stop()

        self.observer = None


    def watch_file(self, uri, callback, *args, **kwargs):
        """ Watches a new file with a new callback. Removes any precedent watched files.

        If the optional watchdog dependency is missing, does nothing.

        Args:
            uri (`str`): URI of the file to watch
            callback (`function`): callback to call with all the further arguments when the file changes
        """
        if self.observer is None:
            return

        self.stop_watching()

        scheme, path = uri.split('://', 1)
        self.path = pathlib.Path(url2pathname(path))
        if scheme != 'file':
            logger.error('Impossible to watch files with {} schemes'.format(scheme), exc_info = True)
            return

        self.callback = lambda: callback(*args, **kwargs)
        self.monitor.on_modified = self._enqueue
        try:
            self.observer.schedule(self.monitor, str(self.path.parent), recursive=False)
        except OSError:
            logger.error('Impossible to open dir at {}'.format(str(self.path.parent)), exc_info = True)


    def stop_watching(self):
        """ Remove all files that are being watched.
        """
        self.observer.unschedule_all()


    def _enqueue(self, event):
        """ Call callback with delay, to avoid repeated calls in short periods of time.

        Args:
            event (:class:`~watchdog.events.FileSystemEvent`): the event that caused the callback to be triggered
        """
        if event.src_path != str(self.path):
            return
        if self.timeout:
            GLib.Source.remove(self.timeout)
        self.timeout = GLib.timeout_add(200, self._call)


    def _call(self):
        """ Call the callback.
        """
        if self.timeout:
            self.timeout = 0
        self.callback()
