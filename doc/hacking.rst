Hacking pympress
================

pympress is written in `Python <http://www.python.org/>`_ and uses different
libraries:

- `Poppler <http://poppler.freedesktop.org/>`_ is used for PDF rendering thanks
  to its `Python bindings <https://launchpad.net/poppler-python>`_
- `PyGTK <http://pygtk.org/>`_ for the GUI

The :program:`pympress` script is used to load a PDF file. It is then handled by
several modules:

- :mod:`pympress.document`, which defines several classes used to handle various
  aspects of PDF documents
- :mod:`pympress.ui`, which manages the GUI: display, events, keyboard and mouse
  inputs...
- :mod:`pympress.pixbufcache`, which allows to prerender pages and cache them in
  order to make the display faster
- :mod:`pympress.util`, which contains several utility functions


Modules documentation
---------------------

.. automodule:: pympress.document
   :members:

.. automodule:: pympress.ui
   :members:

.. automodule:: pympress.pixbufcache
   :members:

.. automodule:: pympress.util
   :members:


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
