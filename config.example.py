#
# Web Server
#

listen_port = 8000
listen_address = '0.0.0.0'


#
# Directories
#

# Directory to write the HLS stream to and serve it from
# This is continuously written to by FFmpeg's HLS muxer when previwing or recording.
# The disk usage in this folder stays relatively constant (<20MB for my SD stream),
# so it's quite safe to use a ramdisk (/dev/shm/ on Linux).
hls_path = "R:\\"

# Base directory for FFV1 MKV recordings
# Folders will automatically be created in here based on the current archive number.
storage_path = "K:\\vhs-test"

# Persisted location of the archive number
# This is written to when the archive number is incremented (no need for a database)
count_file = "K:\\vhs-test\\count.txt"


#
# FFMPEG input arguments
#

# `capture_args` is a list of arguments to pass to FFmpeg to define the input stream.
# This is intended to be a capture device or a file to emulate a capture device, but
# any input supported by FFmpeg can be used.

# Example SD PAL capture using a Blackmagic Design Intensity Shuttle
capture_args = [
    '-f', 'dshow',
    '-video_size', '720x576',
    '-pixel_format', 'uyvy422',
    '-rtbufsize', '1000M',
    '-framerate', '25',
    '-i', 'video=Decklink Video Capture:audio=Decklink Audio Capture',
]

# Example streaming from a file for testing
# capture_args = [
#     '-re', # Process the input file in real-time (rather than as faster as possible)
# 	'-i', os.getenv('FAKE_STREAM')
# ]

# Example capturing from a USB camera on Linux
# capture_args = [
#     '-f', 'v4l2',
#     '-framerate', '30',
#     '-video_size', '1280x720',
#     '-i', '/dev/video0',
# ]