#!/usr/bin/env bash

p=`realpath $0`
cd `dirname $p`
pot=pympress/share/locale/pympress.pot
translated=`ls pympress/share/locale/*/*.po`
version=`git describe --tags --abbrev=0`
opts="--no-location --no-wrap --sort-output"
pkg="--package-name=Pympress --package-version=${version} --msgid-bugs-address=me@cimba.li"
pkg="--omit-header" # Don't re-output headers as we update files

xgettext -d python $opts $pkg -L Python --from-code utf-8 --keyword=_ `find pympress/ -name "*.py"`
xgettext -d glade  $opts $pkg -L Glade --keyword=translatable pympress/share/xml/*.glade

sed -i 's/CHARSET/UTF-8/g' python.po glade.po

sed '/^$/q' $pot > header.po
msgcat $opts -t utf-8 -o $pot header.po glade.po python.po && rm glade.po python.po header.po

# Do some updates and remove comments
sed -i '/^msgid ""$/,$!d;/^"#-#-#-#-#  \(glade\|pympress\)\.pot (Pympress v\S\+)  #-#-#-#-#\\n"$/d' $pot
sed -i "/Project-Id-Version: Pympress v/s/v[.0-9a-z]\\+/${version}/" $pot $translated

# gettext doesn't like .pot, only .po
for t in $translated; do
	printf "Updating %s: " "$t"
	msgmerge -U $opts $t $pot
	rm -f ${t}~

	echo "Missing and fuzzy translations:"
	sed -rn '1N;N;/^#, fuzzy/p;/\nmsgstr ""\n$/P;$s/\n(msgid ".*")\nmsgstr ""$/\1/p;D' $t
	echo
	echo after updating translations:
	echo "msgfmt $t -fo `dirname $t`/LC_MESSAGES/pympress.mo"
	echo
done

