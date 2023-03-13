#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

""" pympress documentation build configuration file for sphinx_build.
"""

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use the absolute path.

import sys
import pathlib
sys.path.insert(0, pathlib.Path(__file__).resolve().parents[1])

import re
import subprocess
import importlib

from urllib.parse import urlsplit, urlunsplit, urljoin
from urllib.request import url2pathname

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
needs_sphinx = '1.3'  # for sphinx.ext.napoleon

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.coverage',
    'sphinx.ext.doctest',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_template']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
source_suffix = ['.md']

github_doc_root = 'https://pympress.github.io/'

def rewrite_link(url):
    """ Make relative links in README relative to "docs/" or absolute.
    """
    split_url = urlsplit(url)
    if split_url.netloc:
        # Absolute link
        return url
    elif split_url.path.startswith('docs/'):
        return urlunsplit(split_url._replace(path = split_url.path[5:]))
    elif split_url.path:
        return urljoin(github_doc_root, url)
    elif split_url.fragment and not split_url.query and not split_url.scheme:
        # anchor links are fragment-only and work differently in (recent) myst-parser vs. github
        # myst-parser strips the spaces, whereas github creates anchors with trailing -
        return '#' + split_url.fragment.strip('-')
    else:
        return url


def setup(app):
    """ Function called by sphinx to setup this documentation.
    """
    # get the README.md as a source, but we need to move it here and adjust the relative links into docs/
    # Until relative links are allowed from the toctree, see https://github.com/sphinx-doc/sphinx/issues/701
    find_links = re.compile(r'\[([^\[\]]+)\]\(([^()]+)\)')

    here = pathlib.Path(app.srcdir)
    with open(here.parent / 'README.md') as fin, open(here / 'README.md', 'w') as fout:
        for line in fin:
            print(find_links.sub(lambda m: '[{}]({})'.format(m[1], rewrite_link(m[2])), line), end='', file=fout)

    app.connect('build-finished', lambda app, config: (here / 'README.md').unlink())


myst_heading_anchors = 3

# The encoding of source files.
#
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = 'index'

# General information about the project. Make sure we find the right omdule info.
pkg_meta = importlib.import_module('pympress.__init__')
project = 'pympress'
copyright = '2009-2011, Thomas Jost; 2015-2022 Cimbali'
author = 'Thomas Jost, Cimbali'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = pkg_meta.__version__
# The full version, including alpha/beta/rc tags.
try:
    release = str(subprocess.check_output(["git", "describe"])[1:].strip())
except Exception:
    release = version

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = 'en'

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
#
# today = ''
#
# Else, today_fmt is used as the format for a strftime call.
#
today_fmt = '%d %B, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The reST default role (used for this markup: `text`) to use for all
# documents.
#
default_role = 'obj'

# If true, '()' will be appended to :func: etc. cross-reference text.
#
# add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
#
# add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
#
# show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

# If true, keep warnings as "system message" paragraphs in the built documents.
# keep_warnings = False

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


def load_epydoc_as_intersphinx_v2(url):
    """ Get an epydoc objects list from an URL and convert it to intershphinx v2 format.

    Arguments:
        url (`str`): the URL where the documentation is available. In particular url + '/api-objects.txt'
        must contain the list of object generated by epydox.

    Returns:
        a (url, filename) tuple where the file contains the intersphinx list of objects
    """
    import codecs
    import requests
    import tempfile

    def guess_epydoc_role(name, uri):
        uri = urlsplit(uri)

        # filenames in URI are name-module.html or name-class.html
        base = pathlib.Path(url2pathname(uri.path)).stem.split('-')[-1]

        if not uri.fragment:
            return base
        elif base == 'class':
            # Is it a method or an attribute?
            return 'any'
        elif base == 'module':
            # Is it a function or a global member?
            return 'func'

    objects_inv = []
    with requests.get(urljoin(url, 'api-objects.txt')) as epy:
        for name, uri in (line.strip().split() for line in epy.text.split('\n') if line.strip()):
            role = guess_epydoc_role(name, uri)
            objects_inv.append('{name} py:{role} 1 {uri} -'.format(name = name, role = role, uri = uri))

    if objects_inv:
        with tempfile.NamedTemporaryFile(mode = 'wb', delete = False) as translated:
            translated.write('\n'.join([
                "# Sphinx inventory version 2",
                "# Project: {} {}".format('python-vlc', '2.2'),
                "# Version: {}".format('2.2.0-git-14816-gda488a7751100'),
                "# The remainder of this file is compressed using zlib.", ""
            ]).encode('ascii'))
            translated.write(codecs.encode('\n'.join(objects_inv + [""]).encode('ascii'), 'zlib'))

            filename = translated.name

    return (url, filename)


# Link to outside documentations
intersphinx_mapping = {
    'Gtk': ('https://lazka.github.io/pgi-docs/Gtk-3.0', None),
    'Gdk': ('https://lazka.github.io/pgi-docs/Gdk-3.0', None),
    'GdkPixbuf': ('https://lazka.github.io/pgi-docs/GdkPixbuf-2.0', None),
    'GObject': ('https://lazka.github.io/pgi-docs/GObject-2.0', None),
    'Poppler': ('https://lazka.github.io/pgi-docs/Poppler-0.18', None),
    'Pango': ('https://lazka.github.io/pgi-docs/Pango-1.0', None),
    'GLib': ('https://lazka.github.io/pgi-docs/GLib-2.0', None),
    'GdkX11': ('https://lazka.github.io/pgi-docs/GdkX11-3.0', None),
    'python': ('https://docs.python.org/{}.{}'.format(*sys.version_info[:2]), None),
    'cairo': ('https://www.cairographics.org/documentation/pycairo/3', None),
    'vlc': load_epydoc_as_intersphinx_v2('https://www.olivieraubert.net/vlc/python-ctypes/doc/'),
    # No mapping on https://gstreamer.freedesktop.org/documentation/gstreamer/
    'Gst': ('https://lazka.github.io/pgi-docs/Gst-1.0', None),
}

# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Read the docs theme
import sphinx_rtd_theme

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
# html_theme_options = {}

# Add any paths that contain custom themes here, relative to this directory.
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

# The name for this set of Sphinx documents.
# "<project> v<release> documentation" by default.
#
html_title = "Pympress developer documentation"

# A shorter title for the navigation bar.  Default is the same as html_title.
#
html_short_title = "Pympress v{}".format(version)

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
#
html_logo = '../pympress/share/pixmaps/pympress.png'

# The name of an image file (relative to this directory) to use as a favicon of
# the docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
#
html_favicon = '../pympress/share/pixmaps/pympress.ico'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
#
# html_extra_path = []

# If not None, a 'Last updated on:' timestamp is inserted at every page
# bottom, using the given strftime format.
# The empty string is equivalent to '%b %d, %Y'.
#
# html_last_updated_fmt = '%d %B, %Y'

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
#
# html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
#
# html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
#
# html_additional_pages = {}

# If false, no module index is generated.
#
# html_domain_indices = True

# If false, no index is generated.
#
# html_use_index = True

# If true, the index is split into individual pages for each letter.
#
# html_split_index = False

# If true, links to the reST sources are added to the pages.
#
# html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
#
# html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
#
# html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
#
# html_use_opensearch = ''

# This is the file name suffix for HTML files (e.g. ".xhtml").
# html_file_suffix = None

# Language to be used for generating the HTML full-text search index.
# Sphinx supports the following languages:
#   'da', 'de', 'en', 'es', 'fi', 'fr', 'h', 'it', 'ja'
#   'nl', 'no', 'pt', 'ro', 'r', 'sv', 'tr', 'zh'
#
html_search_language = 'en'

# A dictionary with options for the search language support, empty by default.
# 'ja' uses this config value.
# 'zh' user can custom change `jieba` dictionary path.
#
# html_search_options = {'type': 'default'}

# The name of a javascript file (relative to the configuration directory) that
# implements a search results scorer. If empty, the default will be used.
#
# html_search_scorer = 'scorer.js'

# Output file base name for HTML help builder.
htmlhelp_basename = 'pympressdoc'

# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    ('index', 'pympress.tex', u'pympress documentation', u'Thomas Jost, Cimbali', 'manual'),
]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
#
# latex_logo = None

# For "manual" documents, if this is true, then toplevel headings are parts,
# not chapters.
#
# latex_use_parts = False

# If true, show page references after internal links.
#
# latex_show_pagerefs = False

# If true, show URL addresses after external links.
#
# latex_show_urls = False

# Documents to append as an appendix to all manuals.
#
# latex_appendices = []

# It false, will not define \strong, \code,     itleref, \crossref ... but only
# \sphinxstrong, ..., \sphinxtitleref, ... To help avoid clash with user added
# packages.
#
# latex_keep_old_macro_names = True

# If false, no module index is generated.
#
# latex_domain_indices = True


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'pympress', u'pympress documentation', [u'Thomas Jost, Cimbali'], 1)
]

# If true, show URL addresses after external links.
#
# man_show_urls = False


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'pympress', 'pympress Documentation',
     author, 'pympress', 'One line description of project.',
     'Miscellaneous'),
]

# Documents to append as an appendix to all manuals.
#
# texinfo_appendices = []

# If false, no module index is generated.
#
# texinfo_domain_indices = True

# How to display URL addresses: 'footnote', 'no', or 'inline'.
#
# texinfo_show_urls = 'footnote'

# If true, do not generate a @detailmenu in the "Top" node's menu.
#
# texinfo_no_detailmenu = False


# -- Options for Epub output ----------------------------------------------

# Bibliographic Dublin Core info.
epub_title = project
epub_author = author
epub_publisher = author
epub_copyright = copyright

# The basename for the epub file. It defaults to the project name.
# epub_basename = project

# The HTML theme for the epub output. Since the default themes are not
# optimized for small screen space, using the same theme for HTML and epub
# output is usually not wise. This defaults to 'epub', a theme designed to save
# visual space.
#
# epub_theme = 'epub'

# The language of the text. It defaults to the language option
# or 'en' if the language is not set.
#
# epub_language = ''

# The scheme of the identifier. Typical schemes are ISBN or URL.
# epub_scheme = ''

# The unique identifier of the text. This can be a ISBN number
# or the project homepage.
#
# epub_identifier = ''

# A unique identification for the text.
#
# epub_uid = ''

# A tuple containing the cover image and cover page html template filenames.
#
# epub_cover = ()

# A sequence of (type, uri, title) tuples for the guide element of content.opf.
#
# epub_guide = ()

# HTML files that should be inserted before the pages created by sphinx.
# The format is a list of tuples containing the path and title.
#
# epub_pre_files = []

# HTML files that should be inserted after the pages created by sphinx.
# The format is a list of tuples containing the path and title.
#
# epub_post_files = []

# A list of files that should not be packed into the epub file.
epub_exclude_files = ['search.html']

# The depth of the table of contents in toc.ncx.
#
# epub_tocdepth = 3

# Allow duplicate toc entries.
#
# epub_tocdup = True

# Choose between 'default' and 'includehidden'.
#
# epub_tocscope = 'default'

# Fix unsupported image types using the Pillow.
#
# epub_fix_images = False

# Scale large images.
#
# epub_max_image_width = 0

# How to display URL addresses: 'footnote', 'no', or 'inline'.
#
# epub_show_urls = 'inline'

# If false, no index is generated.
#
# epub_use_index = True
