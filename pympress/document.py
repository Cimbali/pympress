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

This modules contains several classes that are used for managing documents (only
PDF documents are supported at the moment, but other formats may be added in the
future).

An important point is that this module is *completely* independant from the GUI:
there should not be any GUI-related code here, except for page rendering (and
only rendering itself: the preparation of the target surface must be done
elsewhere).
"""


import sys

import poppler

import pympress.ui
import pympress.util


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
    #: Page number of the link destination
    dest = None

    def __init__(self, x1, y1, x2, y2, dest):
        """
        :param x1: first x coordinate of the link rectangle
        :type  x1: float
        :param y1: first y coordinate of the link rectangle
        :type  y1: float
        :param x2: second x coordinate of the link rectangle
        :type  x2: float
        :param y2: second y coordinate of the link rectangle
        :type  y2: float
        :param dest: page number of the destination
        :type  dest: integer
        """
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.dest = dest

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

    def get_destination(self):
        """
        Get the link destination.

        :return: destination page number
        :rtype: integer
        """
        return self.dest


class Page:
    """
    Class representing a single page.
    
    It provides several methods used by the GUI for preparing windows for
    displaying pages, managing hyperlinks, etc.

    """

    #: Page handled by this class (instance of :class:`poppler.Page`)
    page = None
    #: Number of the current page (starting from 0)
    page_nb = -1
    #: All the links in the page, as a list of :class:`~pympress.document.Link`
    #: instances
    links = []
    #: Page width as a float
    pw = 0.
    #: Page height as a float
    ph = 0.

    def __init__(self, doc, number):
        """
        :param doc: the PDF document
        :type  doc: :class:`poppler.Document`
        :param number: number of the page to fetch in the document
        :type  number: integer
        """
        self.page = doc.get_page(number)
        self.page_nb = number

        # Read page size
        self.pw, self.ph = self.page.get_size()

        if pympress.util.poppler_links_available():
            # Read links on the page
            link_mapping = self.page.get_link_mapping()
            self.links = []

            for link in link_mapping:
                if type(link.action) is poppler.ActionGotoDest:
                    dest = link.action.dest
                    page_num = dest.page_num

                    if dest.type == poppler.DEST_NAMED:
                        page_num = doc.find_dest(dest.named_dest).page_num

                    # Page numbering starts at 0
                    page_num -= 1

                    my_link = Link(link.area.x1, link.area.y1, link.area.x2, link.area.y2, page_num)
                    self.links.append(my_link)

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

    def get_size(self, type=0):
        """Get the page size.

        :return: page size
        :rtype: (float, float)
        """
        if type==0 :
            return (self.pw, self.ph)
        else :
            return (self.pw*0.5, self.ph)

    def get_aspect_ratio(self, type=0):
        """Get the page aspect ratio.

        :return: page aspect ratio
        :rtype: float
        """
        if type==0 :
            return self.pw / self.ph
        else :
            return (self.pw*0.5) / self.ph

    ##== this method should be abandoned since it cannot render a page by
    ##== specifying pixel ranges.
    def render_cairo(self, cr):
        """Render the page on a Cairo surface.

        :param cr: target surface
        :type  cr: :class:`gtk.gdk.CairoContext`
        """
        self.page.render(cr)

    def render_pixbuf(self, pixbuf, width, height, scale, type=0):
        """Render the page on a :class:`gtk.gdk.Pixbuf`.
        
        :param pixbuf: target pixbuf
        :type  pixbuf: :class:`gtk.gdk.Pixbuf`
        :param width: pixbuf width
        :type  width: integer
        :param height: pixbuf height
        :type  height: integer
        :param scale: scaling factor
        :type  scale: float
        :param type: page type (0-without notes; 1-left half; 2-right half)
        :type  type: integer
        """
        if type==0 or type==1 :
            self.page.render_to_pixbuf(0, 0, width, height, scale, 0, pixbuf)
        else :
            self.page.render_to_pixbuf(width, 0, width, height, scale, 0, pixbuf)




class Document:
    """This is the main document handling class.

    .. note:: The internal page numbering scheme is the same as in Poppler: it
       starts at 0.
    """

    #: Current PDF document (:class:`poppler.Document` instance)
    doc = None
    #: Number of pages in the document
    nb_pages = -1
    #: Number of the current page
    cur_page = -1
    #: Pages cache (dictionary of :class:`pympress.document.Page`). This makes
    #: navigation in the document faster by avoiding calls to Poppler when loading
    #: a page that has already been loaded.
    pages_cache = {}
    #: Instance of :class:`pympress.ui.UI` used when opening a document
    ui = None
    #: Document mode with notes or not
    note_mode = 0

    def __init__(self, uri, page=0):
        """
        :param uri: URI to the PDF file to open (local only, starting with
           :file:`file://`)
        :type  uri: string
        :param page: page number to which the file should be opened
        :type  page: integer
        """

        # Check poppler-python version -- we need Bazaar rev. 62
        if not pympress.util.poppler_links_available():
            print >>sys.stderr, "Hyperlink support not found in poppler-python -- be sure to use at least bazaar rev. 62 to have them working"

        # Open PDF file
        self.doc = poppler.document_new_from_file(uri, None)

        # Pages number
        self.nb_pages = self.doc.get_n_pages()

        # Number of the current page
        self.cur_page = page

        # Pages cache
        self.pages_cache = {}

        # Detect note mode
        self.note_mode = self.detect_mode(page)
        #print "note_mode = %d" % self.note_mode

        # Create windows
        self.ui = pympress.ui.UI(self)
        self.ui.on_page_change(False)
        self.ui.run()

    def detect_mode(self, page=0):
        """Detect document mode -- whether it is in note mode or not

        :param page: page number
        :type  page: integer
        :return: mode type, 0-without notes, 1-with notes
        :rtye: integer, 0 or 1
        """
        p = self.page(page)
        if p is None:
            return 0

        if round(p.get_aspect_ratio(),2) <= 4.0/3.0 :
            return 0
        else :
            return 1

    def get_mode(self):
        """Get the document mode.

        :return: note mode, value 0 or 1
        :rtype: integer
        """
        return self.note_mode

    def set_mode(self, mode=0):
        """Set the document mode.

        :param mode: the value of note mode, 0 or 1
        :type  mode: integer
        """
        self.note_mode = mode

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
            self.pages_cache[number] = Page(self.doc, number)
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

        
    def goto(self, number):
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
            self.ui.on_page_change()

    def goto_next(self):
        """Switch to the next page."""
        self.goto(self.cur_page + 1)

    def goto_prev(self):
        """Switch to the previous page."""
        self.goto(self.cur_page - 1)

    def goto_home(self):
        """Switch to the first page."""
        self.goto(0)

    def goto_end(self):
        """Switch to the last page."""
        self.goto(self.nb_pages-1)


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
