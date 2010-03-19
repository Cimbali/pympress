#!/usr/bin/env python
#
#       document.py
#
#       Copyright 2009 Thomas Jost <thomas.jost@gmail.com>
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

import sys

import poppler

import pympress.ui
import pympress.util


class Link:
    """
    This class encapsulates one hyperlink of the document.

    @ivar x1: first x coordinate of the link rectangle
    @type x1: float
    @ivar y1: first y coordinate of the link rectangle
    @type y1: float
    @ivar x2: second x coordinate of the link rectangle
    @type x2: float
    @ivar y2: second y coordinate of the link rectangle
    @type y2: float
    @ivar dest: page number of the destination
    @type dest: integer
    """

    def __init__(self, x1, y1, x2, y2, dest):
        """
        @param x1: first x coordinate of the link rectangle
        @type  x1: float
        @param y1: first y coordinate of the link rectangle
        @type  y1: float
        @param x2: second x coordinate of the link rectangle
        @type  x2: float
        @param y2: second y coordinate of the link rectangle
        @type  y2: float
        @param dest: page number of the destination
        @type  dest: integer
        """
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.dest = dest

    def is_over(self, x, y):
        """
        Tell if the input coordinates are on the link rectangle.

        @param x: input x coordinate
        @type  x: float
        @param y: input y coordinate
        @type  y: float
        @return: C{True} if the input coordinates are within the link rectangle,
        C{False} otherwise
        @rtype: boolean
        """
        return ( (self.x1 <= x) and (x <= self.x2) and (self.y1 <= y) and (y <= self.y2) )

    def get_destination(self):
        """
        Get the link destination.

        @return: destination page number
        @rtype: integer
        """
        return self.dest


class Page:
    """
    Class representing a single page.

    @ivar page: one page of the document
    @type page: poppler.Page
    @ivar links: list of all the links in the page
    @type links: list of L{pympress.Link}s
    @ivar pw: page width
    @type pw: float
    @ivar ph: page height
    @type ph: float
    """

    def __init__(self, doc, number):
        """
        @param doc: the PDF document
        @type  doc: poppler.Document
        @param number: number of the page to fetch in the document
        @param number: integer
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
        """Return the page number"""
        return self.page_nb

    def get_link_at(self, x, y):
        """
        Get the L{pympress.Link} corresponding to the given position, or C{None}
        if there is no link at this position.

        @param x: horizontal coordinate
        @type  x: float
        @param y: vertical coordinate
        @type  y: float
        @return: the link at the given coordinates if one exists, C{None}
        otherwise
        @rtype: L{pympress.Link}
        """
        xx = self.pw * x
        yy = self.ph * (1. - y)
        
        for link in self.links:
            if link.is_over(xx, yy):
                return link

        return None

    def get_size(self):
        """Return the page size.

        @return: page size
        @rtype: (float, float)
        """
        return (self.pw, self.ph)

    def get_aspect_ratio(self):
        """Return the page aspect ratio.

        @return: page aspect ratio
        @rtype: float
        """
        return self.pw / self.ph

    def render_cairo(self, cr):
        """Render the page on a Cairo surface"""
        self.page.render(cr)


class Document:
    """
    This is the main class. It deals with the Poppler library for PDF document
    handling, and a little bit with the GUI too.

    @ivar doc: the PDF document that is currently displayed
    @type doc: poppler.Document
    @ivar nb_pages: number of pages in the document
    @type nb_pages: integer
    @ivar nb_current: number of the current page
    @type nb_current: integer
    @ivar presenter: pympress's Presenter window
    @type presenter: L{pympress.Presenter}
    @ivar content: pympress's Content window
    @type content: L{pympress.Content}

    @note: Page numbering starts at 0, so internally the first page is page 0,
    the second page is page 1, etc.
    """

    def __init__(self, uri, page=0):
        """
        @param uri: URI to the PDF file to open (local only, starting with
        file://)
        @type  uri: string
        @param page: page number to which the file should be opened
        @type  page: integer
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

        # Create windows
        self.ui = pympress.ui.UI(self)
        self.ui.on_page_change()
        self.ui.run()


    def page(self, number):
        """Return the specified page. If it does not exist, return None instead."""
        if number >= self.nb_pages or number < 0:
            return None

        return Page(self.doc, number)
    

    def current_page(self):
        """Return the current page."""
        return self.page(self.cur_page)

    def next_page(self):
        """Return the next page."""
        return self.page(self.cur_page + 1)


    def pages_number(self):
        """Return the number of pages in the document."""
        return self.nb_pages

        
    def goto(self, number):
        """
        Switch to another page.

        @param number: number of the destination page
        @type  number: integer
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


##
# Local Variables:
# mode: python
# indent-tabs-mode: nil
# py-indent-offset: 4
# fill-column: 80
# end:
