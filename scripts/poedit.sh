#!/usr/bin/env bash

cd `git rev-parse --show-toplevel`
pot=pympress/share/locale/pympress.pot

upload() {
    printf 'Uploading new strings to poeditor: '
    curl -sX POST https://api.poeditor.com/v2/projects/upload \
          -F api_token="$poeditor_api_token" \
          -F id="301055" -F updating="terms" -F file=@"$pot" \
          | jq -r '.response.message'
}

languages() {
    curl -sX POST https://api.poeditor.com/v2/languages/list \
          -F api_token="$poeditor_api_token" \
          -F id="301055" | jq -r 'select(.response.code == "200") | .result.languages[].code'
}

badges() {
    curl -sX POST https://api.poeditor.com/v2/languages/list \
          -F api_token="$poeditor_api_token" \
          -F id="301055" | jq -r 'select(.response.code == "200") | .result.languages[] | [.name, .code, .percentage] |@tsv' |
        while read name code percentage; do
            # Locale code differs from country ISO code
            if test "$name" = "Czech" -a "$code" = "cs"; then code=cz; fi

            #printf %d 'N -> ord(N) -> %F0%9F%87%{ 0xA6 + N - ord('a') } the urlencoded ISO 3166 flag
            flag=`echo $code | sed "s/./\\\\\\'& /g" | xargs printf "%d + 69\n" | bc | xargs printf '%%F0%%9F%%87%%%02X'`

            # linearly interpolate FF0000 0% -> FFFF00 50% -> 00FF00 100%
            colors=`bc <<EOF | xargs printf '%01x%01x%01x'
                p = (30 * $percentage) / 100
                if (p < 15) 15 else 2 * 15 - p
                if (p < 15) p else 15
                0
EOF
            `

            image="![${name}: ${percentage}%](https://img.shields.io/badge/${flag}%20${name}-${percentage}%25-${colors})"
            # delete + insert instead of change, so new images get added correctly
            sed -Ei "/^\!\[${name}: [0-9]+%\]/d;/<!-- insert badge -->/i${image}" README.md
        done
}


contributors() {
    curl -sX POST https://api.poeditor.com/v2/contributors/list \
          -F api_token="$poeditor_api_token" \
          -F id="301055" | jq -r 'select(.response.code == "200") | .result.contributors[].name' |
        while read name; do
            # hold "name,", hold & delete any line matching name, at the last translator insert the hold space
            sed -e "1{h;s/.*/${name},/;x}" -e "/\<${name}\>/{h;d}" -e '/<!-- last translator -->/{x;G}' -i README.md
        done
}

download() {
    lang=$1
    printf "Updating %s:\n" "$lang"

    url=`curl -sX POST https://api.poeditor.com/v2/projects/export \
          -F api_token="$poeditor_api_token" \
          -F id="301055" -F language="$lang" -F type="po" \
        | jq -r 'select(.response.code == "200") | .result.url'`

    test -n "$url" && curl -so "pympress/share/locale/${lang}/LC_MESSAGES/pympress.po" "$url"
}

getpass() {
    if test -z "$poeditor_api_token"; then
        poeditor_api_token=`$SSH_ASKPASS "Password for 'https://api.poeditor.com/projects/v2/': "`
    fi
}


if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    echo "Where command is one of: upload, languages, download, progress, contributors"
    echo "requires curl and jq"
fi

while [ $# -gt 0 ]; do
    if test "$1" = "upload"; then
        getpass
        upload
    elif test "$1" = "languages"; then
        getpass
        languages
    elif test "$1" = "download"; then
        getpass
        for lang in `languages`; do
            download $lang
        done
        contributors
        badges
    elif test "$1" = "progress"; then
        getpass
        badges
    elif test "$1" = "contributors"; then
        getpass
        contributors
    else
        echo "Unrecognised command $1 use one of: upload, languages, download, progress, contributors"
        exit 1
    fi
    shift
done
