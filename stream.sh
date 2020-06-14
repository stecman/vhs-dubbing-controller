#!/bin/bash

#ffmpeg -re -ss 5500 -i "$1" -vf "bwdif=mode=send_field:parity=tff,crop=692:554:14:8,format=yuv420p" -preset ultrafast -vcodec libx264 -tune zerolatency -g 50 -b:v 2500k -c:a aac -b:a 192k -ar 48000 -strict 2 -movflags +faststart -f matroska tcp://localhost:1234

#ffmpeg -re -i "$1" -vf "bwdif=mode=send_frame:parity=tff,hqdn3d=20,crop=692:554:14:8:keep_aspect=1,scale=320:-1" -preset ultrafast -vcodec libx264 -tune zerolatency -b:v 800k -c:a aac -b:a 128k -ar 48000 -strict 2 -f matroska - | /home/stecman/sources/mkvserver_mk2/server

# Ensure there's a clean HLS directory
mkdir -p /dev/shm/hls;
rm /dev/shm/hls*

ffmpeg -re -i "$1" -vf "bwdif=mode=send_field:parity=tff,crop=692:554:14:8,format=yuv420p" \
    -loglevel repeat+info \
    -preset ultrafast -vcodec libx264 -tune zerolatency -flags +cgop -g 50 -b:v 5700k \
    -c:a aac -b:a 192k -ar 48000 -strict 2 \
    -movflags +faststart \
    -f hls \
    -hls_time 1\
    -hls_list_size 1 \
    -hls_wrap 20 \
    -hls_delete_threshold 1 \
    -hls_flags delete_segments \
    -hls_start_number_source datetime \
    -start_number 10 \
    /dev/shm/hls/stream.m3u8
