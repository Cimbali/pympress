#       document.py
#
#       Copyright 2009, 2010 Thomas Jost <thomas.jost@gmail.com>
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

An important point is that this module is *completely* independant from the GUI:
there should not be any GUI-related code here, except for page rendering (and
only rendering itself: the preparation of the target surface must be done
elsewhere).
"""

from __future__ import print_function

import os
import sys
import shutil
import subprocess
import tempfile
import mimetypes
import webbrowser

import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler

try:
    from urllib.parse import urljoin
    from urllib.request import pathname2url
except ImportError:
    from urlparse import urljoin
    from urllib import pathname2url

# find the right function to open files
if os.name == 'nt':
    fileopen = os.startfile
else:
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    fileopen = lambda f: subprocess.call([opener, f])

import pympress.util

from pympress.ui import PDF_REGULAR, PDF_CONTENT_PAGE, PDF_NOTES_PAGE

def get_extension(mime_type):
    if not mimetypes.inited:
        mimetypes.init()
    for ext in mimetypes.types_map:
        if mimetypes.types_map[ext] == mime_type:
            return ext

class Link:
    """This class encapsulates one hyperlink of the document."""

    #: First x coordinate of the link rectangle, as a float number
    x1 = None
    #: First y coordinate of the link rectangle, as a float number
    y1 = None
    #: Second x coordinate of the link rectangle, as a float number
    x2 = None
    #: Second y coordinate of the link rectangle, as a float number
    y2 = None

    def __init__(self, x1, y1, x2, y2, action):
        """
        :param x1: first x coordinate of the link rectangle
        :type  x1: float
        :param y1: first y coordinate of the link rectangle
        :type  y1: float
        :param x2: second x coordinate of the link rectangle
        :type  x2: float
        :param y2: second y coordinate of the link rectangle
        :type  y2: float
        :param action: action to perform when the link is clicked
        :type  action: function
        """
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.follow = action

    def is_over(self, x, y):
        """
        Tell if the input coordinates are on the link rectangle.

        :param x: input x coordinate
        :type  x: float
        :param y: input y coordinate
        :type  y: float
        :return: ``True`` if the input coordinates are within the link
           rectangle, ``False`` otherwise
        :rtype: boolean
        """
        return ( (self.x1 <= x) and (x <= self.x2) and (self.y1 <= y) and (y <= self.y2) )

    def follow(self):
        """
        Follow the link to its destination.
        This is overriden by the function to perform the actual action in the constructor.
        """


class Page:
    """
    Class representing a single page.

    It provides several methods used by the GUI for preparing windows for
    displaying pages, managing hyperlinks, etc.

    """

    #: Page handled by this class (instance of :class:`Poppler.Page`)
    page = None
    #: Number of the current page (starting from 0)
    page_nb = -1
    #: All the links in the page, as a list of :class:`~pympress.document.Link` instances
    links = []
    #: All the media in the page, as a list of tuples of (area, filename)
    medias = []
    #: Page width as a float
    pw = 0.
    #: Page height as a float
    ph = 0.
    #: All text annotations
    annotations = []

    def __init__(self, page, number, parent):
        """
        :param doc: the poppler object around the page
        :type  doc: :class:`Poppler.Page`
        :param number: number of the page to fetch in the document
        :type  number: integer
        :param parent: the parent Document class
        :type  parent: :class:`pympress.document.Document`
        """
        self.page = page
        self.page_nb = number
        self.parent = parent
        self.links = []
        self.medias = []
        self.annotations = []

        # Read page size
        self.pw, self.ph = self.page.get_size()

        # Read links on the page
        for link in self.page.get_link_mapping():
            action = self.get_link_action(link.action.type, link.action)
            my_link = Link(link.area.x1, link.area.y1, link.area.x2, link.area.y2, action)
            self.links.append(my_link)

        # Read annotations, in particular those that indicate media
        for annotation in self.page.get_annot_mapping():
            annot_type = annotation.annot.get_annot_type()
            if annot_type == Poppler.AnnotType.LINK:
                # just an Annot, not subclassed -- probably redundant with links
                continue
            elif annot_type == Poppler.AnnotType.MOVIE:
                movie = annotation.annot.get_movie()
                filepath = self.parent.get_full_path(movie.get_filename())
                if filepath:
                    # TODO there is no autoplay, or repeatCount
                    media = (annotation.area.copy(), filepath, movie.show_controls())
                    self.medias.append(media)
                    action = lambda: pympress.ui.UI.play_media(hash(media))
                else:
                    print("Pympress can not find file " + movie.get_filename())
                    continue
            elif annot_type == Poppler.AnnotType.SCREEN:
                action_obj = annotation.annot.get_action()
                action = self.get_annot_action(action_obj.any.type, action_obj, annotation.area)
                if not action:
                    continue
            elif annot_type == Poppler.AnnotType.TEXT:
                self.annotations.append(annotation.annot.get_contents())
                self.page.remove_annot(annotation.annot)
                continue
            elif annot_type == Poppler.AnnotType.FREE_TEXT:
                # Poppler already renders annotation of this type
                continue
            else:
                print("Pympress can not interpret annotation of type: {} ".format(annot_type))
                continue

            my_annotation = Link(annotation.area.x1, annotation.area.y1, annotation.area.x2, annotation.area.y2, action)
            self.links.append(my_annotation)

    def get_link_action(self, link_type, action):
        """Get the function to be called when the link is followed
        """
        # Poppler.ActionType.RENDITION should only appear in annotations, right? Otherwise how do we know
        # where to render it? Any documentation on which action types are admissible in links vs in annots
        # is very welcome. For now, link is fallback to annot so contains all action types.
        fun = lambda: print("No action was defined for this link")

        if link_type == Poppler.ActionType.NONE:
            fun = None

        elif link_type == Poppler.ActionType.GOTO_DEST:
            dest_page = action.goto_dest.dest.page_num
            fun = lambda: self.parent.goto(dest_page)

        elif link_type == Poppler.ActionType.NAMED:
            dest_name = action.named.named_dest
            dest = self.parent.doc.find_dest(dest_name)

            if dest:
                fun = lambda: self.parent.goto(dest.page_num)
            elif dest_name == "GoBack":
                #TODO make a history of visited pages, use this action to jump back in history
                fun = lambda: print("Pympress does not yet support link type \"{}\" to \"{}\"".format(link_type, dest_name))
            elif dest_name == "GoForward":
                #TODO make a history of visited pages, use this action to jump forward in history
                fun = lambda: print("Pympress does not yet support link type \"{}\" to \"{}\"".format(link_type, dest_name))
            elif dest_name == "GoToPage":
                #TODO connect this to the "G" action which allows to pick a page to jump to
                fun = lambda: print("Pympress does not yet support link type \"{}\" to \"{}\"".format(link_type, dest_name))
            elif dest_name == "Find":
                #TODO popup a text box and search results with Page.find_text
                # http://lazka.github.io/pgi-docs/Poppler-0.18/classes/Page.html#Poppler.Page.find_text
                fun = lambda: print("Pympress does not yet support link type \"{}\" to \"{}\"".format(link_type, dest_name))
            else:
                #TODO find out other possible named actions?
                fun = lambda: print("Pympress does not recognize link type \"{}\" to \"{}\"".format(link_type, dest_name))

        elif link_type == Poppler.ActionType.LAUNCH:
            launch = action.launch
            if launch.params:
                print("WARNING ignoring params: " + str(launch.params))

            filepath = self.parent.get_full_path(launch.file_name)
            if not filepath:
                print("ERROR can not find file " + launch.file_name)

            else:
                fun = lambda: fileopen(filepath)

        elif link_type == Poppler.ActionType.RENDITION: # Poppler 0.22
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        elif link_type == Poppler.ActionType.MOVIE: # Poppler 0.20
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        elif link_type == Poppler.ActionType.URI:
            fun = lambda: webbrowser.open_new_tab(action.uri.uri)
        elif link_type == Poppler.ActionType.GOTO_REMOTE:
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        elif link_type == Poppler.ActionType.OCG_STATE:
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        elif link_type == Poppler.ActionType.JAVSCRIPT:
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        elif link_type == Poppler.ActionType.UNKNOWN:
            fun = lambda: print("Pympress does not yet support link type \"{}\"".format(link_type))
        else:
            fun = lambda: print("Pympress does not recognize link type \"{}\"".format(link_type))

        return fun

    def get_annot_action(self, link_type, action, rect):
        """Get the function to be called when the link is followed
        """
        if link_type == Poppler.ActionType.RENDITION:
            media = action.rendition.media
            if media.is_embedded():
                ext = get_extension(media.get_mime_type())
                with tempfile.NamedTemporaryFile('wb', suffix=ext, prefix='pdf_embed_', delete=False) as f:
                    # now the file name is shotgunned
                    filename=f.name
                if not media.save(filename):
                    print("Pympress can not extract embedded media")
                    return None
            else:
                filename = self.parent.get_full_path(media.get_filename())
                if not filename:
                    print("Pympress can not find file "+media.get_filename())
                    return None

            # TODO grab the show_controls, autoplay, repeat
            media = (rect.copy(), filename, False)
            self.medias.append(media)
            return lambda: pympress.ui.UI.play_media(hash(media))

        else:
            return self.get_link_action(link_type, action)

    def number(self):
        """Get the page number"""
        return self.page_nb

    def get_link_at(self, x, y):
        """
        Get the :class:`~pympress.document.Link` corresponding to the given
        position, or ``None`` if there is no link at this position.

        :param x: horizontal coordinate
        :type  x: float
        :param y: vertical coordinate
        :type  y: float
        :return: the link at the given coordinates if one exists, ``None``
           otherwise
        :rtype: :class:`pympress.document.Link`
        """
        xx = self.pw * x
        yy = self.ph * (1. - y)

        for link in self.links:
            if link.is_over(xx, yy):
                return link

        return None

    def get_size(self, dtype=PDF_REGULAR):
        """Get the page size.

        :param dtype: the type of document to consider
        :type  dtype: integer
        :return: page size
        :rtype: (float, float)
        """
        if dtype == PDF_REGULAR:
            return (self.pw, self.ph)
        else:
            return (self.pw/2., self.ph)

    def get_aspect_ratio(self, dtype=PDF_REGULAR):
        """Get the page aspect ratio.

        :param dtype: the type of document to consider
        :type  dtype: integer
        :return: page aspect ratio
        :rtype: float
        """
        if dtype == PDF_REGULAR:
            return self.pw / self.ph
        else:
            return (self.pw/2.) / self.ph

    def get_media(self):
        """Get the list of medias this page might want to play

        :return: page aspect ratio
        :rtype: list of tuples of area and filenames
        """
        return self.medias

    def render_cairo(self, cr, ww, wh, dtype=PDF_REGULAR):
        """Render the page on a Cairo surface.

        :param cr: target surface
        :type  cr: :class:`Gdk.CairoContext`
        :param ww: target width in pixels
        :type  ww: integer
        :param wh: target height in pixels
        :type  wh: integer
        :param dtype: the type of document that should be rendered
        :type  dtype: integer
        """

        pw, ph = self.get_size(dtype)

        cr.set_source_rgb(1, 1, 1)

        # Scale
        scale = min(ww/pw, wh/ph)
        cr.scale(scale, scale)

        cr.rectangle(0, 0, pw, ph)
        cr.fill()

        # For "regular" pages, there is no problem: just render them.
        # For "content" or "notes" pages (i.e. left or right half of a page),
        # the widget already has correct dimensions so we don't need to deal
        # with that. But for right halfs we must translate the output in order
        # to only show the right half.
        if dtype == PDF_NOTES_PAGE:
            cr.translate(-pw, 0)

        self.page.render(cr)


class Document:
    """This is the main document handling class.

    .. note:: The internal page numbering scheme is the same as in Poppler: it
       starts at 0.
    """

    #: Current PDF document (:class:`Poppler.Document` instance)
    doc = None
    #: Path to pdf
    path = None
    #: Number of pages in the document
    nb_pages = -1
    #: Number of the current page
    cur_page = -1
    #: Document with notes or not
    notes = False
    #: Pages cache (dictionary of :class:`pympress.document.Page`). This makes
    #: navigation in the document faster by avoiding calls to Poppler when loading
    #: a page that has already been loaded.
    pages_cache = {}
    #: Callback function to signal whenever we change pages
    on_page_change = None

    def __init__(self, page_change_callback, pop_doc, path, page=0):
        """
        :param page_change_callback: action to perform to signal we changed pages
        :type  page_change_callback: function
        :param pop_doc: Instance of the Poppler document at path that this class will wrap
        :type  pop_doc: Poppler.Document
        :param path: Absolute path to the PDF file to open
        :type  path: string
        :param page: page number to which the file should be opened
        :type  page: integer
        """

        self.path = path

        # Open PDF file
        self.doc = pop_doc

        # Pages number
        self.nb_pages = self.doc.get_n_pages()

        # Number of the current page
        self.cur_page = page

        # Pages cache
        self.pages_cache = {}

        # Guess if the document has notes
        page0 = self.page(page)
        if page0 is not None:
            # "Regular" pages will have an apsect ratio of 4/3, 16/9, 16/10...
            # Full A4 pages will have an aspect ratio < 1.
            # So if the aspect ratio is >= 2, we can assume it is a document with notes.
            ar = page0.get_aspect_ratio()
            self.notes = (ar >= 2)

        self.on_page_change = page_change_callback

    @staticmethod
    def create(page_change_callback, path, page=0):
        """Initializes a Document by passing it a :class:`Poppler.Document`

        :param page_change_callback: action to perform to signal we changed pages
        :type  page_change_callback: function
        :param path: Absolute path to the PDF file to open
        :type  path: string
        :param page: page number to which the file should be opened
        :type  page: integer
        :return: The initialized document
        :rtype: Pympress.Document
        """
        poppler_doc = Poppler.Document.new_from_file(urljoin('file:', pathname2url(path)), None)
        return Document(page_change_callback, poppler_doc, path, page)

    def has_notes(self):
        """Get the document mode.

        :return: ``True`` if the document has notes, ``False`` otherwise
        :rtype: boolean
        """
        return self.notes

    def page(self, number):
        """Get the specified page.

        :param number: number of the page to return
        :type  number: integer
        :return: the wanted page, or ``None`` if it does not exist
        :rtype: :class:`pympress.document.Page`
        """
        if number >= self.nb_pages or number < 0:
            return None

        if not number in self.pages_cache:
            self.pages_cache[number] = Page(self.doc.get_page(number), number, self)
        return self.pages_cache[number]


    def current_page(self):
        """Get the current page.

        :return: the current page
        :rtype: :class:`pympress.document.Page`
        """
        return self.page(self.cur_page)

    def next_page(self):
        """Get the next page.

        :return: the next page, or ``None`` if this is the last page
        :rtype: :class:`pympress.document.Page`
        """
        return self.page(self.cur_page + 1)


    def pages_number(self):
        """Get the number of pages in the document.

        :return: the number of pages in the document
        :rtype: integer
        """
        return self.nb_pages


    def goto(self, number, unpause = True):
        """Switch to another page.

        :param number: number of the destination page
        :type  number: integer
        """
        if number < 0:
            number = 0
        elif number >= self.nb_pages:
            number = self.nb_pages - 1

        if number != self.cur_page:
            self.cur_page = number
            self.on_page_change(unpause)

    def goto_next(self, *args):
        """Switch to the next page."""
        self.goto(self.cur_page + 1)

    def goto_prev(self, *args):
        """Switch to the previous page."""
        self.goto(self.cur_page - 1)

    def goto_home(self, *args):
        """Switch to the first page."""
        self.goto(0)

    def goto_end(self, *args):
        """Switch to the last page."""
        self.goto(self.nb_pages-1)

    def get_full_path(self, filename):
        """Returns full path, extrapolated from a path relative to this document
        or to the current directory.

        :param filename: Name of the file or relative path to it
        :type  filename: string
        :return: the full path to the file or None if it doesn't exist
        :rtype: string
        """
        filepath = None
        if os.path.isabs(filename):
            return os.path.normpath(filename) if os.path.exists(filename) else None

        for d in [os.path.dirname(self.path), os.getcwd()]:
            filepath = os.path.normpath(os.path.join(d, filename))
            if os.path.exists(filepath):
                return filepath


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
