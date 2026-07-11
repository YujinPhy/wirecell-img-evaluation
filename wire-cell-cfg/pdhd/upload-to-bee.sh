LOGIN_URL=https://www.phy.bnl.gov/twister/bee
COOKIES=cookies.txt
CURL_BIN="curl -k -s -c $COOKIES -b $COOKIES -e $LOGIN_URL"

$CURL_BIN $LOGIN_URL > /dev/null
echo -n "Django Auth: get csrftoken ... " >&2
DJANGO_TOKEN="$(grep csrftoken $COOKIES | sed 's/^.*csrftoken\s*//')"
echo $DJANGO_TOKEN >&2

FILENAME=$1
echo "uploading file $FILENAME ... " >&2
UUID="$($CURL_BIN \
    -H "X-CSRFToken: $DJANGO_TOKEN" \
    -F "file=@$FILENAME" \
    $LOGIN_URL/upload/)"

URL="$LOGIN_URL/set/$UUID/event/list/"
# Always print the URL on stdout so callers can capture it (e.g. via
# command substitution); optionally also open it in $BROWSER if set.
echo "$URL"
if [ -n "$BROWSER" ]; then
    "$BROWSER" "$URL"
fi

rm $COOKIES
