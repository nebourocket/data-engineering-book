mkdir -p deb-practice/shop/photos
cd deb-practice/shop
pwd
echo "アイマスク 1500" > items.txt
cp items.txt items-backup.txt
mv items-backup.txt photos/backup.txt
ls photos
cat photos/backup.txt
cd photos
cd ../..
pwd
