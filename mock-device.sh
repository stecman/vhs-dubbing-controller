#!/bin/bash

# ffmpeg -re -i "$1" -vf "bwdif=mode=send_field:parity=tff,crop=692:554:14:8,format=yuv420p" \
#     -preset ultrafast -vcodec libx264 -tune zerolatency -flags +cgop -g 50 -b:v 5700k \
#     -c:a aac -b:a 192k -ar 48000 -strict 2 \
#     -movflags +faststart \
#     -f mpegts \
#     'udp://127.0.0.1:5333/?pkt_size=1024&buffer_size=65535'

ffmpeg -re -i "$1" -c:v libx264 -preset ultrafast -crf 25 -flags +cgop -g 17 -c:a aac -b:a 192k -ar 48000 -strict 2 -f mpegts 'udp://127.0.0.1:5333'