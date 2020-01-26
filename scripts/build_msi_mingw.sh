# this script is meant to be run by appveyor on msys2 with mingw-w64
# arch=x86_64 or i686, py=python2 or python3, vlc=with-vlc or without-vlc
set -ve
pacman -Syu --noprogressbar --noconfirm
pacman -S --noprogressbar --noconfirm --needed base-devel mingw-w64-$arch-gtk3 mingw-w64-$arch-cairo mingw-w64-$arch-poppler mingw-w64-$arch-$py mingw-w64-$arch-gcc mingw-w64-$arch-vlc zip
pacman -S --noprogressbar --noconfirm --needed mingw-w64-$arch-$py-pip mingw-w64-$arch-$py-gobject mingw-w64-$arch-$py-cairo mingw-w64-$arch-$py-appdirs mingw-w64-$arch-$py-packaging mingw-w64-$arch-$py-cx_Freeze
$py -m pip install --disable-pip-version-check --upgrade pip
$py -m pip install watchdog python-vlc babel babelgladeextractor
$py setup.py compile_catalog
$py setup.py --freeze --$vlc build_exe
$py setup.py --freeze --$vlc bdist_msi --add-to-path True --target-name pympress-`git describe --tags --always`-$arch.msi

# Build a zip from the build_exe outputs
cd build
mv exe.mingw-* pympress
cp ../pympress/share/defaults.conf pympress/pympress.conf
zip -r ../dist/pympress-`git describe --tags --always`-$arch.zip pympress
