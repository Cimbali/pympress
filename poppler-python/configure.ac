AC_PREREQ(2.52)

dnl the pypoppler version number
m4_define(pypoppler_major_version, 0)
m4_define(pypoppler_minor_version, 10)
m4_define(pypoppler_micro_version, 1)
m4_define(pypoppler_version, pypoppler_major_version.pypoppler_minor_version.pypoppler_micro_version)

dnl versions of packages we require ...
m4_define(pygobject_required_version, 2.10.1)
m4_define(pygtk_required_version, 2.10.0)
m4_define(poppler_glib_required_version, 0.10)
m4_define(atk_required_version, 1.6.0)
m4_define(pycairo_required_version,    1.2.0)

AC_INIT(pypoppler, pypoppler_version, [http://launchpad.net/poppler-python/])
AC_DEFINE(PYPOPPLER_MAJOR_VERSION, pypoppler_major_version, [pypoppler major version])
AC_DEFINE(PYPOPPLER_MINOR_VERSION, pypoppler_minor_version, [pypoppler minor version])
AC_DEFINE(PYPOPPLER_MICRO_VERSION, pypoppler_micro_version, [pypoppler macro version])

AC_CONFIG_SRCDIR([./popplermodule.c])
AM_CONFIG_HEADER(config.h)

AM_INIT_AUTOMAKE(AC_PACKAGE_NAME, AC_PACKAGE_VERSION)

dnl put the ACLOCAL flags in the makefile
ACLOCAL="$ACLOCAL $ACLOCAL_FLAGS"

AC_CANONICAL_BUILD
AC_CANONICAL_HOST
AC_MSG_CHECKING([for some Win32 platform])
case "$host" in
  *-*-mingw*|*-*-cygwin*)
    platform_win32=yes
    ;;
  *)
    platform_win32=no
    ;;
esac
AC_MSG_RESULT([$platform_win32])
AM_CONDITIONAL(PLATFORM_WIN32, test "$platform_win32" = "yes")

AC_MSG_CHECKING([for native Win32])
case "$host" in
  *-*-mingw*)
    os_win32=yes
    ;;
  *)
    os_win32=no
    ;;
esac
AC_MSG_RESULT([$os_win32])
AM_CONDITIONAL(OS_WIN32, test "$os_win32" = "yes")

AC_DISABLE_STATIC
AC_LIBTOOL_WIN32_DLL
AC_PROG_LIBTOOL

AM_PATH_PYTHON(2.2)

AM_CHECK_PYTHON_HEADERS(,[AC_MSG_ERROR(could not find Python headers)])

dnl get rid of the -export-dynamic stuff from the configure flags ...
export_dynamic=`(./libtool --config; echo eval echo \\$export_dynamic_flag_spec) | sh`

dnl pygtk
PKG_CHECK_MODULES(PYPOPPLER, [ dnl
                         pygtk-2.0 >= pygtk_required_version,
                         atk >= atk_required_version,
                         poppler-glib >= poppler_glib_required_version
                         ])
PKG_CHECK_MODULES(PYCAIRO, [pycairo >= pycairo_required_version],
			    have_pycairo=true, have_pycairo=false)

if test "x$have_pycairo" = "xtrue"; then
  AC_DEFINE_UNQUOTED(PYCAIRO_MAJOR_VERSION, [`pkg-config --modversion pycairo | cut -d '.' -f 1`], dnl
                     [pycairo major version])
  AC_DEFINE_UNQUOTED(PYCAIRO_MINOR_VERSION, [`pkg-config --modversion pycairo | cut -d '.' -f 2`], dnl
                     [pycairo minor version])
  AC_DEFINE_UNQUOTED(PYCAIRO_MICRO_VERSION, [`pkg-config --modversion pycairo | cut -d '.' -f 3`], dnl
                     [pycairo micro version])
fi

if test -n "$export_dynamic"; then
	PYPOPPLER_LIBS=`echo $PYPOPPLER_LIBS | sed -e "s/$export_dynamic//"`
fi
PYGTK_DATADIR=`pkg-config --variable=datadir pygtk-2.0`

AC_SUBST(PYGTK_CFLAGS)
AC_SUBST(PYGTK_LIBS)
AC_SUBST(PYGTK_DATADIR)


dnl codegen
AC_MSG_CHECKING(for pygtk codegen)
CODEGENDIR=`pkg-config --variable=codegendir pygtk-2.0`
if test -f $CODEGENDIR/codegen.py; then
	CODEGEN=$CODEGENDIR/codegen.py
	AC_MSG_RESULT(yes)
else 
	AC_MSG_RESULT(no)
	AC_MSG_ERROR([Error: codegen not found (should be shipped with pygtk!)])
fi
AC_SUBST(CODEGEN)

JH_ADD_CFLAG([-Wall])
JH_ADD_CFLAG([-std=c9x])
JH_ADD_CFLAG([-fno-strict-aliasing])

dnl output
AC_CONFIG_FILES(
  Makefile
  demo/Makefile
)

AC_OUTPUT
