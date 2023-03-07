#!/usr/bin/env bash

cd `git rev-parse --show-toplevel || readlink -f "$0" | xargs dirname | xargs dirname`
pot=pympress/share/locale/pympress.pot

upload() {
    printf 'Uploading new strings to poeditor: '
    curl -sX POST https://api.poeditor.com/v2/projects/upload \
          -F api_token="$poeditor_api_token" \
          -F id="301055" -F updating="terms" -F file=@"$pot" \
          -F tags="{\"obsolete\":\"removed\"}" \
          | jq -r '.response.message'
}

languages() {
    curl -sX POST https://api.poeditor.com/v2/languages/list \
          -F api_token="$poeditor_api_token" \
          -F id="301055" | jq -r "select(.response.code == \"200\") | .result.languages[] | select(.percentage > $1) | \"\(.code)\t\(.percentage)%\""
}

contributors() {
    curl -sX POST https://api.poeditor.com/v2/contributors/list \
          -F api_token="$poeditor_api_token" \
          -F id="301055" | jq --arg lang "$*" -r 'select(.response.code == "200") | .result.contributors[] | select(IN(.permissions[].languages[]; $lang | split(" ")[])) | .name' |
        while read name; do
            # hold "name,", hold & delete any line matching name, at the last translator insert the hold space
            sed -e "1{h;s/.*/${name},/;x}" -e "/\<${name}\>/{h;d}" -e '/<!-- last translator -->/{x;G}' -i README.md
        done
}

download() {
    lang=$1
    printf "Updating %s:\n" "$lang"
    # Normalize separator to _ and capitalised locale
    norm=`echo "$lang" | sed -E 's/-(\w+)$/_\U\1\E/;s/^zh_HANS$/zh_CN/'`

    url=`curl -sX POST https://api.poeditor.com/v2/projects/export \
          -F api_token="$poeditor_api_token" \
          -F id="301055" -F language="$lang" -F type="po" \
        | jq -r 'select(.response.code == "200") | .result.url'`

    test -n "$url" && mkdir -p "pympress/share/locale/${norm}/LC_MESSAGES" &&
        curl -so - "$url" | sed "/Language/s/$lang/$norm/" > "pympress/share/locale/${norm}/LC_MESSAGES/pympress.po"

    # test the file
    msgfmt --use-fuzzy "pympress/share/locale/${norm}/LC_MESSAGES/pympress.po" -o /dev/null
}

getpass() {
    if test -z "$poeditor_api_token"; then
        poeditor_api_token=`$SSH_ASKPASS "Password for 'https://api.poeditor.com/projects/v2/': "`
    fi
}


if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    echo "Where command is one of: upload, languages, download, contributors"
    echo
    echo "MIN_LANG_COMPLETE can be set to override minimum percentage of completion. Requires curl and jq."
fi

while [ $# -gt 0 ]; do
    if test "$1" = "upload"; then
        getpass
        upload
    elif test "$1" = "languages"; then
        getpass
        languages ${MIN_LANG_COMPLETE:-0}
    elif test "$1" = "download"; then
        getpass
        avail_lang=`languages ${MIN_LANG_COMPLETE:-5} | cut -f1`
        for lang in $avail_lang; do
            download $lang
        done
        contributors $avail_lang
    elif test "$1" = "contributors"; then
        getpass
        avail_lang=`languages ${MIN_LANG_COMPLETE:-5} | cut -f1`
        contributors $avail_lang
    else
        echo "Unrecognised command $1 use one of: upload, languages, download, contributors"
        exit 1
    fi
    shift
done
