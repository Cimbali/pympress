# -*- coding: utf-8 -*-
#
#       document.py
#
#       Copyright 2009, 2010 Thomas Jost <thomas.jost@gmail.com>
#       Copyright 2015 Cimbali <me@cimba.li>
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
:mod:`pympress.document` -- document handling
---------------------------------------------

This module contains several classes that are used for managing documents (only
PDF documents are supported at the moment, but other formats may be added in the
future).

An important point is that this module is *completely* independent from the GUI:
there should not be any GUI-related code here, except for page rendering (and
only rendering itself: the preparation of the target surface must be done
elsewhere).
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import os
import math
import enum
import tempfile
import mimetypes
import webbrowser

import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler

try:
    from urllib.request import url2pathname
except ImportError:
    from urllib import url2pathname

from pympress.util import fileopen


def get_extension(mime_type):
    """ Returns a valid filename extension (recognized by python) for a given mime type.

    Args:
        mime_type (`str`): The mime type for which to find an extension

    Returns:
        `str`: A file extension used for the given mimetype
    """
    if not mimetypes.inited:
        mimetypes.init()
    for ext in mimetypes.types_map:
        if mimetypes.types_map[ext] == mime_type:
            return ext


class PdfPage(enum.IntEnum):
    """ Represents the part of a PDF page that we want to draw.
    """
    #: No notes on PDF page, only falsy value
    NONE    = 0
    #: Full PDF page (without notes)
    FULL    = 1
    #: Bottom half of PDF page
    BOTTOM  = 2
    #: Top half of PDF page
    TOP     = 3
    #: Right half of PDF page
    RIGHT   = 4
    #: Left half of PDF page
    LEFT    = 5
    #: Full page + draw another page for notes, which is after the slides
    AFTER   = 6
    #: Complemntary of AFTER: for a notes page, the slide page is BEFORE by half a document
    BEFORE  = 7

    def complement(val):
        """ Return the enum value for the other part of the page.
        """
        return PdfPage(val ^ 1)


    def scale(val):
        """ Return the enum value that does only scaling not shifting.
        """
        return PdfPage(val | 1)


    def direction(val):
        """ Returns whether the pdf page/notes mode is horizontal or vertical.

        Returns:
            `str`: a string representing the direction that can be used as the key in the config section
        """
        if val == PdfPage.LEFT or val == PdfPage.RIGHT:
            return 'horizontal'
        elif val == PdfPage.TOP or val == PdfPage.BOTTOM:
            return 'vertical'
        elif val == PdfPage.AFTER or val == PdfPage.BEFORE:
            return 'page number'
        else:
            return None


    def from_screen(val, x, y, x2 = None, y2 = None):
        """ Transform visible part of the page coordinates to full page coordinates.

        Pass 2 floats to transform coordinates, 4 to transform margins,
        i.e. the second pair of coordinates is taken from the opposite corner.

        Args:
            x (`float`): x coordinate on the screen, on a scale 0..1
            y (`float`): y coordinate on the screen, on a scale 0..1
            x2 (`float`): second x coordinate on the screen, from the other side, on a scale 0..1
            y2 (`float`): second y coordinate on the screen, from the other side, on a scale 0..1
        """
        if val == PdfPage.RIGHT:
            page = ((1 + x) / 2., y)
        elif val == PdfPage.LEFT:
            page = (x / 2., y)
        elif val == PdfPage.BOTTOM:
            page = (x, (1 + y) / 2.)
        elif val == PdfPage.TOP:
            page = (x, y / 2.)
        else:
            page = (x, y)

        if x2 is None or y2 is None:
            return page
        else:
            return page + val.complement().from_screen(x2, y2)


    def to_screen(val, x, y, x2 = None, y2 = None):
        """ Transform full page coordinates to visible part coordinates.

        Pass 2 floats to transform coordinates, 4 to transform margins,
        i.e. the second pair of coordinates is taken from the opposite corner.

        Args:
            x (`float`): x coordinate on the page, on a scale 0..1
            y (`float`): y coordinate on the page, on a scale 0..1
            x2 (`float`): second x coordinate on the page, from the other side, on a scale 0..1
            y2 (`float`): second y coordinate on the page, from the other side, on a scale 0..1
        """
        if val == PdfPage.RIGHT:
            screen = (x * 2 - 1, y)
        elif val == PdfPage.LEFT:
            screen = (x * 2, y)
        elif val == PdfPage.BOTTOM:
            screen = (x, y * 2 - 1)
        elif val == PdfPage.TOP:
            screen = (x, y * 2)
        else:
            screen = (x, y)

        if x2 is None or y2 is None:
            return screen
        else:
            return screen + val.complement().to_screen(x2, y2)


class Link(object):
    """ This class encapsulates one hyperlink of the document.

    Args:
        x1 (`float`):  first x coordinate of the link rectangle
        y1 (`float`):  first y coordinate of the link rectangle
        x2 (`float`):  second x coordinate of the link rectangle
        y2 (`float`):  second y coordinate of the link rectangle
        action (`function`):  action to perform when the link is clicked
    """

    #: `float`, first x coordinate of the link rectangle
    x1 = None
    #: `float`, first y coordinate of the link rectangle
    y1 = None
    #: `float`, second x coordinate of the link rectangle
    x2 = None
    #: `float`, second y coordinate of the link rectangle
    y2 = None
    #: `function`, action to be perform to follow this link
    follow = lambda *args, **kwargs: logger.error(_("no action defined for this link!"))

    def __init__(self, x1, y1, x2, y2, action):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.follow = action


    def is_over(self, x, y):
        """ Tell if the input coordinates are on the link rectangle.

        Args:
            x (`float`):  input x coordinate
            y (`float`):  input y coordinate

        Returns:
            `bool`: `True` if the input coordinates are within the link rectangle, `False` otherwise
        """
        return ((self.x1 <= x) and (x <= self.x2) and (self.y1 <= y) and (y <= self.y2))


    @staticmethod
    def build_closure(fun, *args, **kwargs):
        r""" Return a lambda that calls fun(\*args, \**kwargs), with the current value of args and kwargs.

        By creating the lambda in a new scope, we bind the arguments.

        Args:
            fun (`function`): The function to be called
            args (`tuple`): non-keyworded variable-length argument list to pass to fun()
            kwargs (`dict`): keyworded variable-length argument dict to pass to fun()
        """
        return lambda *a, **k: fun(*(tuple(args) + tuple(a)), **dict(kwargs, **k))



class Page(object):
    """ Class representing a single page.

    It provides several methods used by the GUI for preparing windows for
    displaying pages, managing hyperlinks, etc.

    Args:
        doc (:class:`~Poppler.Page`):  the poppler object around the page
        number (`int`):  number of the page to fetch in the document
        parent (:class:`~pympress.document.Document`):  the parent Document class
    """

    #: Page handled by this class (instance of :class:`~Poppler.Page`)
    page = None
    #: `int`, number of the current page (starting from 0)
    page_nb = -1
    #: `str` representing the page label
    page_label = None
    #: All the links in the page, as a `list` of :class:`~pympress.document.Link` instances
    links = []
    #: All the media in the page, as a `list` of tuples of (area, filename)
    medias = []
    #: `float`, page width
    pw = 0.
    #: `float`, page height
    ph = 0.
    #: All text annotations
    annotations = []
    #: Instance of :class:`~pympress.document.Document` that contains this page.
    parent = None

    def __init__(self, page, number, parent):
        self.page = page
        self.page_nb = number
        self.parent = parent
        self.links = []
        self.medias = []
        self.annotations = []

        if self.page is None:
            return

        # Get page label
        self.page_label = self.page.get_label()

        # Read page size
        self.pw, self.ph = self.page.get_size()

        # Read links on the page
        for link in self.page.get_link_mapping():
            action = self.get_link_action(link.action.type, link.action)
            my_link = Link(link.area.x1, link.area.y1, link.area.x2, link.area.y2, action)
            self.links.append(my_link)

        # Read annotations, in particular those that indicate media
        for annotation in self.page.get_annot_mapping():
            content = annotation.annot.get_contents()
            if content:
                self.annotations.append(content)

            annot_type = annotation.annot.get_annot_type()
            if annot_type == Poppler.AnnotType.LINK:
                # just an Annot, not subclassed -- probably redundant with links
                continue
            elif annot_type == Poppler.AnnotType.MOVIE:
                movie = annotation.annot.get_movie()
                filepath = self.parent.get_full_path(movie.get_filename())
                if filepath:
                    # TODO there is no autoplay, or repeatCount
                    relative_margins = Poppler.Rectangle()
                    relative_margins.x1 = annotation.area.x1 / self.pw        # left
                    relative_margins.x2 = 1.0 - annotation.area.x2 / self.pw  # right
                    relative_margins.y1 = annotation.area.y1 / self.ph        # bottom
                    relative_margins.y2 = 1.0 - annotation.area.y2 / self.ph  # top
                    media = (relative_margins, filepath, movie.show_controls())
                    self.medias.append(media)
                    action = Link.build_closure(self.parent.play_media, hash(media))
                else:
                    logger.error(_("Pympress can not find file ") + movie.get_filename())
                    continue
            elif annot_type == Poppler.AnnotType.SCREEN:
                action_obj = annotation.annot.get_action()
                if not action_obj:
                    continue
                action = self.get_annot_action(action_obj.any.type, action_obj, annotation.area)
                if not action:
                    continue
            elif annot_type == Poppler.AnnotType.FILE_ATTACHMENT:
                attachment = annotation.annot.get_attachment()
                prefix, ext = os.path.splitext(attachment.name)
                with tempfile.NamedTemporaryFile('wb', suffix=ext, prefix=prefix, delete=False) as f:
                    # now the file name is shotgunned
                    filename = f.name
                    self.parent.remove_on_exit(filename)
                if not attachment.save(filename):
                    logger.error(_("Pympress can not extract attached file"))
                    continue
                action = Link.build_closure(fileopen, filename)
            elif annot_type in {Poppler.AnnotType.TEXT, Poppler.AnnotType.POPUP,
                                Poppler.AnnotType.FREE_TEXT}:
                # text-only annotations, hide them from screen
                self.page.remove_annot(annotation.annot)
                continue
            elif annot_type in {Poppler.AnnotType.STRIKE_OUT, Poppler.AnnotType.HIGHLIGHT,
                                Poppler.AnnotType.UNDERLINE, Poppler.AnnotType.SQUIGGLY,
                                Poppler.AnnotType.POLYGON, Poppler.AnnotType.POLY_LINE,
                                Poppler.AnnotType.SQUARE, Poppler.AnnotType.CIRCLE,
                                Poppler.AnnotType.CARET, Poppler.AnnotType.LINE,
                                Poppler.AnnotType.STAMP, Poppler.AnnotType.INK}:
                # Poppler already renders annotation of these types, nothing more can be done
                # even though the rendering isn't always perfect.
                continue
            else:
                logger.warning(_("Pympress can not interpret annotation of type:") + " {} ".format(annot_type))
                continue

            my_annotation = Link(annotation.area.x1, annotation.area.y1, annotation.area.x2, annotation.area.y2, action)
            self.links.append(my_annotation)


    def get_link_action(self, link_type, action):
        """ Get the function to be called when the link is followed.

        Args:
            link_type (:class:`~Poppler.ActionType`): The type of action to be performed
            action (:class:`~Poppler.Action`): The atcion to be performed

        Returns:
            `function`: The function to be called to follow the link
        """
        # Poppler.ActionType.RENDITION should only appear in annotations, right? Otherwise how do we know
        # where to render it? Any documentation on which action types are admissible in links vs in annots
        # is very welcome. For now, link is fallback to annot so contains all action types.
        if link_type == Poppler.ActionType.NONE:
            return lambda: None

        elif link_type == Poppler.ActionType.GOTO_DEST:
            dest_type = action.goto_dest.dest.type
            if dest_type == Poppler.DestType.NAMED:
                dest = self.parent.doc.find_dest(action.goto_dest.dest.named_dest)
                if dest:
                    return Link.build_closure(self.parent.goto_page, dest.page_num - 1)
                else:
                    warning = _('Unrecognized named destination: ') + str(action.goto_dest.dest.named_dest)
            elif dest_type != Poppler.DestType.UNKNOWN:
                return Link.build_closure(self.parent.goto_page, action.goto_dest.dest.page_num - 1)

        elif link_type == Poppler.ActionType.NAMED:
            dest_name = action.named.named_dest
            dest = self.parent.doc.find_dest(dest_name)

            if dest:
                return Link.build_closure(self.parent.goto_page, dest.page_num)
            elif dest_name == "GoBack":
                return self.parent.goto_prev_hist
            elif dest_name == "GoForward":
                return self.parent.goto_next_hist
            elif dest_name == "FirstPage":
                return Link.build_closure(self.parent.goto_page, 0)
            elif dest_name == "PrevPage":
                return Link.build_closure(self.parent.goto_page, self.page_nb - 1)
            elif dest_name == "NextPage":
                return Link.build_closure(self.parent.goto_page, self.page_nb + 1)
            elif dest_name == "LastPage":
                return Link.build_closure(self.parent.goto_page, self.parent.pages_number() - 1)
            elif dest_name == "GoToPage":
                # Same as the 'G' action which allows one to pick a page to jump to
                return Link.build_closure(self.parent.start_editing_page_number, )
            elif dest_name == "Find":
                # TODO popup a text box and search results with Page.find_text
                # http://lazka.github.io/pgi-docs/Poppler-0.18/classes/Page.html#Poppler.Page.find_text
                warning = _("Pympress does not yet support link type \"{}\" to \"{}\"").format(link_type, dest_name)
            else:
                # TODO find out other possible named actions?
                warning = _("Pympress does not recognize link type \"{}\" to \"{}\"").format(link_type, dest_name)

        elif link_type == Poppler.ActionType.LAUNCH:
            launch = action.launch
            if launch.params:
                logger.warning("ignoring params: " + str(launch.params))

            filepath = self.parent.get_full_path(launch.file_name)
            if not filepath:
                logger.error("can not find file " + launch.file_name)
                return lambda: None

            else:
                return Link.build_closure(fileopen, filepath)

        elif link_type == Poppler.ActionType.URI:
            return Link.build_closure(webbrowser.open_new_tab, action.uri.uri)

        elif link_type == Poppler.ActionType.RENDITION:  # Poppler 0.22
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        elif link_type == Poppler.ActionType.MOVIE:  # Poppler 0.20
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        elif link_type == Poppler.ActionType.GOTO_REMOTE:
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        elif link_type == Poppler.ActionType.OCG_STATE:
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        elif link_type == Poppler.ActionType.JAVASCRIPT:
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        elif link_type == Poppler.ActionType.UNKNOWN:
            warning = _("Pympress does not yet support link type \"{}\"").format(link_type)
        else:
            warning = _("Pympress does not recognize link type \"{}\"").format(link_type)

        logger.info(warning)
        return Link.build_closure(logger.warning, _('Unsupported link clicked. ') + warning)


    def get_annot_action(self, link_type, action, rect):
        """ Get the function to be called when the link is followed.

        Args:
            link_type (:class:`~Poppler.ActionType`): The link type
            action (:class:`~Poppler.Action`): The action to be performed when the link is clicked
            rect (:class:`~Poppler.Rectangle`): The region of the page where the link is

        Returns:
            `function`: The function to be called to follow the link
        """
        if link_type == Poppler.ActionType.RENDITION:
            media = action.rendition.media
            if media.is_embedded():
                ext = get_extension(media.get_mime_type())
                with tempfile.NamedTemporaryFile('wb', suffix=ext, prefix='pdf_embed_', delete=False) as f:
                    # now the file name is shotgunned
                    filename = f.name
                    self.parent.remove_on_exit(filename)
                if not media.save(filename):
                    logger.error(_("Pympress can not extract embedded media"))
                    return None
            else:
                filename = self.parent.get_full_path(media.get_filename())
                if not filename:
                    logger.error(_("Pympress can not find file ") + media.get_filename())
                    return None

            # TODO grab the show_controls, autoplay, repeat
            relative_margins = Poppler.Rectangle()
            relative_margins.x1 = rect.x1 / self.pw        # left
            relative_margins.x2 = 1.0 - rect.x2 / self.pw  # right
            relative_margins.y1 = rect.y1 / self.ph        # bottom
            relative_margins.y2 = 1.0 - rect.y2 / self.ph  # top

            media = (relative_margins, filename, False)
            self.medias.append(media)
            return Link.build_closure(self.parent.play_media, hash(media))

        else:
            return self.get_link_action(link_type, action)


    def number(self):
        """ Get the page number.
        """
        return self.page_nb


    def label(self):
        """ Get the page label.
        """
        return self.page_label


    def get_link_at(self, x, y, dtype=PdfPage.FULL):
        """ Get the :class:`~pympress.document.Link` corresponding to the given position.

        Returns `None` if there is no link at this position.

        Args:
            x (`float`):  horizontal coordinate
            y (`float`):  vertical coordinate
            dtype (:class:`~pympress.document.PdfPage`):  the type of document to consider

        Returns:
            :class:`~pympress.document.Link`: the link at the given coordinates
            if one exists, `None` otherwise
        """
        x, y = dtype.from_screen(x, y)

        xx = self.pw * x
        yy = self.ph * (1. - y)

        for link in self.links:
            if link.is_over(xx, yy):
                return link

        return None


    def get_size(self, dtype=PdfPage.FULL):
        """ Get the page size.

        Args:
            dtype (:class:`~pympress.document.PdfPage`):  the type of document to consider

        Returns:
            `(float, float)`: page size
        """
        return dtype.scale().from_screen(self.pw, self.ph)


    def get_aspect_ratio(self, dtype=PdfPage.FULL):
        """ Get the page aspect ratio.

        Args:
            dtype (:class:`~pympress.document.PdfPage`):  the type of document to consider

        Returns:
            `float`: page aspect ratio
        """
        w, h = self.get_size(dtype)
        return w / h


    def get_annotations(self):
        """ Get the list of text annotations on this page.

        Returns:
            `list` of `str`: annotations on this page
        """
        return self.annotations


    def get_media(self):
        """ Get the list of medias this page might want to play.

        Returns:
            `list`: medias in this page
        """
        return self.medias


    def render_cairo(self, cr, ww, wh, dtype=PdfPage.FULL):
        """ Render the page on a Cairo surface.

        Args:
            cr (:class:`~Gdk.CairoContext`):  target surface
            ww (`int`):  target width in pixels
            wh (`int`):  target height in pixels
            dtype (:class:`~pympress.document.PdfPage`):  the type of document that should be rendered
        """
        pw, ph = self.get_size(dtype)

        cr.set_source_rgb(1, 1, 1)

        # Scale
        scale = min(ww / pw, wh / ph)
        cr.scale(scale, scale)

        cr.rectangle(0, 0, pw, ph)
        cr.fill()

        # For "regular" pages, there is no problem: just render them.
        # For other pages (i.e. half of a page), the widget already has correct
        # dimensions so we don't need to deal with that. But for right and bottom
        # halfs we must translate the output in order to only show the correct half.
        if dtype == PdfPage.RIGHT:
            cr.translate(-pw, 0)
        elif dtype == PdfPage.BOTTOM:
            cr.translate(0, -ph)

        self.page.render(cr)


    def can_render(self):
        """ Informs that rendering *is* necessary (avoids checking the type).

        Returns:
            `bool`: `True`, do rendering
        """
        return True



class Document(object):
    """ This is the main document handling class.

    .. note:: The internal page numbering scheme is the same as in Poppler: it
       starts at 0.

    Args:
        builder (:class:`pympress.builder.Builder`):  A builder to load callbacks
        pop_doc (:class:`~pympress.Poppler.Document`):  Instance of the Poppler document that this class will wrap
        uri (`str`):  URI of the PDF file to open
        page (`int`):  page number to which the file should be opened
    """

    #: Current PDF document (:class:`~Poppler.Document` instance)
    doc = None
    #: Path to pdf
    path = None
    #: Number of pages in the document
    nb_pages = -1
    #: Pages cache (`dict` of :class:`~pympress.document.Page`). This makes
    #: navigation in the document faster by avoiding calls to Poppler when loading
    #: a page that has already been loaded.
    pages_cache = {}
    #: Files that are temporary and need to be removed
    temp_files = set()
    #: History of pages we have visited
    history = []
    #: Our position in the history
    hist_pos = -1
    #: `dict` of all the page labels
    page_labels = []
    #: `bool` indicating whether the second half of pages are in fact notes pages
    notes_after = False

    #: callback, to be connected to :func:`~pympress.extras.Media.play`
    play_media = lambda *args: None
    #: callback, to be connected to :func:`~pympress.editable_label.PageNumber.start_editing`
    start_editing_page_number = lambda *args: None
    #: callback, to be connected to :func:`~pympress.ui.UI.goto_page`
    navigate = lambda *args: None

    def __init__(self, builder, pop_doc, uri):
        if builder is not None:
            # Connect callbacks
            self.play_media                = builder.get_callback_handler('medias.play')
            self.start_editing_page_number = builder.get_callback_handler('page_number.start_editing')
            self.goto_page                 = builder.get_callback_handler('goto_page')
            self.goto_next_hist            = builder.get_callback_handler('doc_hist_next')
            self.goto_prev_hist            = builder.get_callback_handler('doc_hist_prev')

        # Setup PDF file
        self.uri = uri
        self.doc = pop_doc

        # Pages number
        if pop_doc is not None:
            self.nb_pages = self.doc.get_n_pages()
            self.page_labels = [self.doc.get_page(n).get_label() for n in range(self.nb_pages)]
        else:
            self.nb_pages = 0
            self.page_labels = []

        # Pages cache
        self.pages_cache = {}


    def get_structure(self, index_iter = None):
        """ Gets the structure of the document from its index.

        Recursive, pass the iterator.

        Args:
            index_iter (:class:`~Poppler.IndexIter` or `None`): the iterator for the child index to explore.

        Returns:
            `list`: A list of tuples (depth, page number, title)
        """
        try:
            if index_iter is None:
                index_iter = Poppler.IndexIter(self.doc)
        except TypeError:
            return {}
        if index_iter is None:
            return {}

        index = {}
        while True:
            action = index_iter.get_action()
            title = ''
            try:
                if action.type == Poppler.ActionType.GOTO_DEST:
                    title = action.goto_dest.title
                    if action.goto_dest.dest.type == Poppler.DestType.NAMED:
                        dest = self.doc.find_dest(action.goto_dest.dest.named_dest)
                        page = dest.page_num - 1
                    elif action.goto_dest.dest.type == Poppler.DestType.UNKNOWN:
                        raise AssertionError('Unknown type of destination')
                    else:
                        page = action.goto_dest.dest.page_num - 1
                else:
                    raise AssertionError('Unexpected type of action')

            except Exception:
                logger.error(_('Unexpected action in index "{}"').format(action.type))
                page = None

            new_entry = {'title': title}
            child = index_iter.get_child()
            if child:
                new_entry['children'] = self.get_structure(child)
                if page is None:
                    page = min(new_entry['children'])

            # there should not be synonymous sections, correct the page here to a better guess
            if page in index:
                lower_bound = max(index)
                find = index[lower_bound]
                while 'children' in find:
                    lower_bound = max(find)
                    find = find[lower_bound]

                try:
                    page = min(number for number, label in enumerate(self.page_labels)
                               if label == self.page_labels[page] and number > lower_bound)
                except ValueError:  # empty iterator
                    page = lower_bound + 1


            if page is not None:
                index[page] = new_entry

            if not index_iter.next():
                break

        return index


    @staticmethod
    def create(builder, uri):
        """ Initializes a Document by passing it a :class:`~Poppler.Document`.

        Args:
            builder (:class:`pympress.builder.Builder`):  A builder to load callbacks
            uri (`str`):  URI to the PDF file to open
            page (`int`):  page number to which the file should be opened

        Returns:
            :class:`~pympress.document.Document`: The initialized document
        """
        if uri is None:
            doc = EmptyDocument()
        else:
            poppler_doc = Poppler.Document.new_from_file(uri, None)
            doc = Document(builder, poppler_doc, uri)

        return doc


    def guess_notes(self, horizontal, vertical, current_page=0):
        """ Get our best guess for the document mode.

        Args:
            horizontal (`str`): A string representing the preference for horizontal slides
            vertical (`str`): A string representing the preference for vertical slides

        Returns:
            :class:`~pympress.document.PdfPage`: the notes mode
        """
        page = self.page(current_page)
        if page is None or not page.can_render():
            return PdfPage.NONE

        ar = page.get_aspect_ratio()

        # Check whether we have N slides with one aspect ratio then N slides with a different aspect ratio
        # that is the sign if Libreoffice notes pages
        if self.nb_pages and self.nb_pages % 2 == 0:
            half_doc = self.nb_pages // 2
            ar_slides = self.page(0).get_aspect_ratio()
            ar_notes = self.page(half_doc).get_aspect_ratio()
            if ar_slides != ar_notes and \
                    all(self.page(p).get_aspect_ratio() == ar_slides for p in range(1, half_doc)) and \
                    all(self.page(half_doc + p).get_aspect_ratio() == ar_notes for p in range(1, half_doc)):
                return PdfPage.AFTER

        # "Regular" slides will have an aspect ratio of 4/3, 16/9, 16/10... i.e. in the range [1..2]
        # So if the aspect ratio is >= 2, we can assume it is a document with notes on the side.
        if ar >= 2:
            try:
                return PdfPage[horizontal.upper()]
            except KeyError:
                return PdfPage.RIGHT

        # Make exception for classic american letter format and ISO (A4, B5, etc.)
        if abs(ar - 8.5 / 11) < 1e-3 or abs(ar - 1 / math.sqrt(2)) < 1e-3:
            return PdfPage.NONE

        # If the aspect ratio is < 1, we can assume it is a document with notes above or below.
        if ar < 1:
            try:
                return PdfPage[vertical.upper()]
            except KeyError:
                return PdfPage.BOTTOM

        return PdfPage.NONE


    def set_notes_after(self, notes_after):
        """ Set whether there are notes pages after normal pages (aka Libreoffice notes mode)

        Args:
            notes_after (`bool`):  Whether there are notes pages
        """
        self.notes_after = notes_after


    def page(self, number):
        """ Get the specified page.

        Args:
            number (`int`):  number of the page to return

        Returns:
            :class:`~pympress.document.Page`: the wanted page, or `None` if it does not exist
        """
        if number >= self.pages_number() or number < 0:
            return None

        if number not in self.pages_cache:
            self.pages_cache[number] = Page(self.doc.get_page(number), number, self)
        return self.pages_cache[number]


    def notes_page(self, number):
        """ Get the specified page.

        Args:
            number (`int`):  number of the page to return

        Returns:
            :class:`~pympress.document.Page`: the wanted page, or `None` if it does not exist
        """
        if number >= self.pages_number() or number < 0:
            return None

        if self.notes_after:
            number = number + self.pages_number()

        if number not in self.pages_cache:
            self.pages_cache[number] = Page(self.doc.get_page(number), number, self)
        return self.pages_cache[number]


    def pages_number(self):
        """ Get the number of pages in the document.

        Returns:
            `int`: the number of pages in the document
        """
        return (self.nb_pages // 2) if self.notes_after else self.nb_pages


    def has_labels(self):
        """ Return whether this document has useful labels.

        Returns:
            `bool`: False iff there are no labels or they are just the page numbers
        """
        return self.page_labels != [str(n + 1) for n in range(self.nb_pages)]


    def lookup_label(self, label, prefix_unique=True):
        """ Find a page from its label.

        Args:
            label (`str`): the label we are searching for
            prefix_unique (`bool`): whether a prefix match should be unique, e.g. when the user is still typing

        Returns:
            `int`: the page
        """
        # somehow this always returns None:
        # page = self.doc.get_page_by_label(label).get_index()

        # make a shortlist: squash synonymous labels, keeping the last one
        compatible_labels = {l: n for n, l in enumerate(self.page_labels) if l.lower().startswith(label.lower())}

        if len(compatible_labels) == 1:
            return set(compatible_labels.values()).pop()

        # try exact match
        try:
            return compatible_labels[label]
        except KeyError:
            pass

        # try case-insensitive match, prefix case-sensitive match, prefix case-insensitive match (unless prefix_unique)
        full = len(label)
        for filtering in [lambda l: len(l) == full, lambda l: l.startswith(label), lambda l: not prefix_unique]:
            try:
                found = next(label for label in compatible_labels if filtering(label))
            except StopIteration:
                pass
            else:
                return compatible_labels[found]

        return None


    def goto(self, number):
        """ Switch to another page.

        Args:
            number (`int`):  number of the destination page
        """
        if number < 0:
            number = 0
        if number >= self.pages_number():
            number = self.pages_number() - 1

        if 0 <= self.hist_pos < len(self.history) and self.history[self.hist_pos] == number:
            return number

        # chop off history where we were and append
        self.hist_pos = min(len(self.history), self.hist_pos + 1)
        del self.history[self.hist_pos:]
        self.history.append(number)

        return number


    def label_after(self, page):
        """ Switch to the next page with different label.

        If we're within a set of pages with the same label we want to go to the last one.
        """
        labels_after = enumerate(self.page_labels[page + 1:], page + 1)

        try:
            next_page, next_label = next(labels_after)
        except StopIteration:
            # we're already at the last page!
            return page

        # will stop as soon as next_page + 1 (aka following_page) is a different label or due to end of iterator
        for following_page, following_label in labels_after:
            if following_label == next_label:
                next_page = following_page
            else:
                break

        return next_page


    def label_before(self, page):
        """ Switch to the previous page with different label.

        If we're within a set of pages with the same label we want to go *before* the first one.
        """
        # will stop as soon as we find a different label or due to end of iterator
        for prev_page, prev_label in enumerate(reversed(self.page_labels[:page])):
            if prev_label != self.page_labels[page]:
                return page - 1 - prev_page

        return 0


    def hist_next(self, *args):
        """ Switch to the page we viewed next.
        """
        if self.hist_pos + 1 == len(self.history):
            return None

        self.hist_pos += 1
        return self.history[self.hist_pos]


    def hist_prev(self, *args):
        """ Switch to the page we viewed before.
        """
        if self.hist_pos == 0:
            return None

        self.hist_pos -= 1
        return self.history[self.hist_pos]


    def get_uri(self):
        """ Gives access to the URI, rather than the path, of this document.

        Returns:
            `str`: the URI to the file currently opened.
        """
        return self.uri


    def get_full_path(self, filename):
        """ Returns full path, extrapolated from a path relative to this document or to the current directory.

        Args:
            filename (`str`):  Name of the file or relative path to it

        Returns:
            `str`: the full path to the file or None if it doesn't exist
        """
        filepath = None
        if os.path.isabs(filename):
            return os.path.normpath(filename) if os.path.exists(filename) else None

        for d in [os.path.dirname(url2pathname(self.uri.split('://', 1)[1])), os.getcwd()]:
            filepath = os.path.normpath(os.path.join(d, filename))
            if os.path.exists(filepath):
                return filepath


    def remove_on_exit(self, filename):
        """ Remember a temporary file to delete later.

        Args:
            filename (`str`): The path to the file to delete
        """
        self.temp_files.add(filename)


    def cleanup_media_files(self):
        """ Removes all files that were extracted from the pdf into the filesystem.
        """
        for f in self.temp_files:
            os.remove(f)
        self.temp_files.clear()


class EmptyPage(Page):
    """ A dummy page, placeholder for when there are no valid pages around.

    This page is a non-notes page with an aspect ratio of 1.3 and nothing else inside.
    Also, it has no "rendering" capability, and is made harmless by overriding its render function.
    """

    def __init__(self):
        super(EmptyPage, self).__init__(None, -1, None)
        self.page_label = None
        # by default, anything that will have a 1.3 asapect ratio
        self.pw, self.ph = 1.3, 1.0


    def render_cairo(self, cr, ww, wh, dtype=PdfPage.FULL):
        """ Overriding this purely for safety: make sure we do not accidentally try to render.

        Args:
            cr (:class:`~Gdk.CairoContext`):  target surface
            ww (`int`):  target width in pixels
            wh (`int`):  target height in pixels
            dtype (:class:`~pympress.document.PdfPage`):  the type of document that should be rendered
        """
        pass


    def can_render(self):
        """ Informs that rendering is *not* necessary (avoids checking the type).

        Returns:
            `bool`: `False`, no rendering
        """
        return False


class EmptyDocument(Document):
    """ A dummy document, placeholder for when no document is open.
    """
    def __init__(self):
        super(EmptyDocument, self).__init__(None, None, None)
        self.pages_cache[-1] = EmptyPage()


    def page(self, number):
        """ Retrieve a page from the document.

        Args:
            number (`int`): page number to be retrieved

        Returns:
            :class:`~pympress.document.EmptyPage` or `None`: -1 returns the empty page so we can display something.
        """
        return self.pages_cache[number] if number in self.pages_cache else None


    def notes_page(self, number):
        """ Retrieve a page from the document.

        Args:
            number (`int`): page number to be retrieved

        Returns:
            :class:`~pympress.document.EmptyPage` or `None`: -1 returns the empty page so we can display something.
        """
        return self.pages_cache[number] if number in self.pages_cache else None


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
