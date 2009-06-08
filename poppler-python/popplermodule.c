/* -*- Mode: C; c-basic-offset: 4 -*-
 * Copyright (C) 2007-2008, Gian Mario Tagliaretti
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2, or (at your option)
 * any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street - Fifth Floor, Boston, MA 02110-1301, USA.
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

/* include this first, before NO_IMPORT_PYGOBJECT is defined */

#include <pygobject.h>
#include <pygtk/pygtk.h>
#include <glib/poppler.h>

#include <pycairo.h>
Pycairo_CAPI_t *Pycairo_CAPI;

void py_poppler_register_classes (PyObject *d);
void py_poppler_add_constants (PyObject *module, const gchar *strip_prefix);

extern PyMethodDef py_poppler_functions[];

DL_EXPORT(void)
initpoppler(void)
{
    PyObject *m, *d;

    Pycairo_IMPORT;

    init_pygobject ();

    m = Py_InitModule ("poppler", py_poppler_functions);
    d = PyModule_GetDict (m);

    py_poppler_register_classes (d);
    
    py_poppler_add_constants(m, "POPPLER_");

    PyModule_AddObject(m, "pypoppler_version",
                       Py_BuildValue("iii",
                                     PYPOPPLER_MAJOR_VERSION,
                                     PYPOPPLER_MINOR_VERSION,
                                     PYPOPPLER_MICRO_VERSION));
    
    if (PyErr_Occurred ()) {
        Py_FatalError ("can't initialise module globalkeys");
    }
}
