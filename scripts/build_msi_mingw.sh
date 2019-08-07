# this script is meant to be run by appveyor on msys2 with mingw-w64
# arch=x86_64 or i686, py=python2 or python3, vlc=with-vlc or without-vlc
pacman -Syu --noprogressbar --noconfirm
pacman -S --noprogressbar --noconfirm --needed base-devel mingw-w64-$arch-{gtk3,cairo,poppler,$py,gcc,vlc}
pacman -S --noprogressbar --noconfirm --needed mingw-w64-$arch-$py-{pip,gobject,cairo,appdirs,packaging,cx_Freeze}
$py -m pip install --disable-pip-version-check --upgrade pip
$py -m pip install watchdog python-vlc
$py setup.py --freeze --$vlc build_exe
$py setup.py --freeze --$vlc bdist_msi --add-to-path True
