/usr/bin/dpkg --force-overwrite -i "$1"
killall -9 SpringBoard
uicache -a
su -c uicache mobile
rm -rf "$1"
