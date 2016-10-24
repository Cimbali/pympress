#!/usr/bin/env bash

p=`realpath $0`
cd `dirname $p`
pot=pympress/share/locale/pympress.pot
translated=`ls pympress/share/locale/*/*.po`
opts="--no-location --no-wrap --sort-output"
pkg="--package-name=Pympress --package-version=`git describe --abbrev=0` --msgid-bugs-address=me@cimba.li"

xgettext -d python $opts $pkg -L Python --from-code utf-8 --keyword=_ pympress/*.py
xgettext -d glade  $opts $pkg -L glade --keyword=translatable pympress/share/*.glade

sed -i 's/CHARSET/UTF-8/g' python.po glade.po

msgcat $opts -t utf-8 -o temp.po $pot glade.po python.po && rm glade.po python.po
sed '/^"#-#-#-#-#  pympress\.pot (Pympress v\S\+)  #-#-#-#-#\\n"$/d;/^"#-#-#-#-# .* #-#-#-#-#\\n"$/,/^$/d' temp.po > $pot && rm temp.po

# gettext doesn't like .pot, only .po
for t in $translated; do
	msgmerge -U $opts $t $pot
done

# then after updating translations:
# (cd `dirname $t` && msgfmt pympress.po -o LC_MESSAGES/pympress.mo )

