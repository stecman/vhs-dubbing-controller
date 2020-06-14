import os
import re
import subprocess
import threading
import time
import sys

if os.name == 'nt':
    FFMPEG = 'ffmpeg.exe'
else:
    FFMPEG = 'ffmpeg'

cmd_capture = [
    FFMPEG,
    '-y',
    '-f', 'dshow',
    '-video_size', '720x576',
    '-pixel_format', 'uyvy422',
    '-rtbufsize', '1000M',
    '-framerate', '25',
    '-i', 'video=Decklink Video Capture:audio=Decklink Audio Capture',
]

cmd_fake = [
    FFMPEG, '-re', '-i', os.getenv('FAKE_STREAM')
]

args_common = [
    '-loglevel', 'repeat+info',
]

args_save_ffv1 = [
    '-codec:v', 'ffv1',
    '-level', '3',
    '-coder', '1',
    '-context', '1',
    '-g', '1',
    '-slices', '4',
    '-slicecrc', '1',
    '-aspect', '4:3',
    '-top', '1',
    '-c:a',
    'copy',
    # FILENAME
]

args_hls = [
    '-preset', 'ultrafast', '-vcodec', 'libx264', '-tune', 'zerolatency', '-flags', '+cgop', '-g', '50', '-b:v', '5700k',
    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-strict', '2',
    '-movflags', '+faststart',
    '-f', 'hls',
    '-hls_time', '1',
    '-hls_list_size', '1',
    '-hls_wrap', '20',
    '-hls_delete_threshold', '1',
    '-hls_flags', 'delete_segments',
    '-hls_start_number_source', 'datetime',
    '-start_number', '10',
    # FILENAME
]

STATE_IDLE = 'idle'
STATE_PREVIEWING = 'preview'
STATE_RECORDING = 'record'

RE_IGNORE_HLS_OPENING = r'\[hls.*Opening.*for writing\n'
RE_CURRENT_FRAME = r'frame=([0-9]+) .* time=([0-9:]+).*'

class Recorder:

    __instance = None

    @staticmethod
    def instance():
        if Recorder.__instance is None:
            Recorder.__instance = Recorder()

        return Recorder.__instance

    def __init__(self):
        self.hls_path = None
        self.fake = False

        self.state = STATE_IDLE

    def preview(self):
        self.prepareHls()

        if self.fake:
            cmd = cmd_fake[:]
        else:
            cmd = cmd_capture[:]

        cmd.extend(self.getFilter(is_preview=True))

        cmd.extend(args_hls)
        cmd.append(self.getStreamFilename())

        self._thread = threading.Thread(target=self._execute, args=(cmd,))
        self._thread.start()

    def _execute(self, cmd):
        def stream_output(process):
            go = process.poll() is None
            for line in process.stdout:
                for row in line.split(b"\r"):
                    self.handleOutput(row.decode('ascii'))

            return go

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while stream_output(process):
            time.sleep(0.1)

    def handleOutput(self, line):
        # match = re.match(RE_CURRENT_FRAME, line)
        # if match:
        #     print( match.group(1), match.group(2) )
        #     print("Fuck")
        #     return
        # else:
        #     print("derp")

        # if re.match(RE_IGNORE_HLS_OPENING, line):
        #     return;

        print("---")
        print(line)

    def getStreamFilename(self):
        return os.path.join(self.hls_path, 'stream.m3u8')

    def getFilter(self, is_preview=False):
        filters = [
            'bwdif=mode=send_field:parity=tff',
            'crop=692:554:14:8',
            'format=yuv420p',
        ]

        if is_preview:
            # Draw a big warning flag that this is not recording
            filters.append(':'.join([
                r'drawtext=text=PREVIEW (NOT RECORDING)',
                # 'x=((w-tw)/2)',
                'x=(20)',
                'y=h-(2*lh)',
                'font=Mono',
                'fontcolor=black',
                'fontsize=26',
                'box=1',
                'boxcolor=yellow',
                'boxborderw=10',
            ]))

            # Draw timecode in the bottom right
            filters.append(':'.join([
                r'drawtext=text=%{pts\\:hms}',
                # 'x=((w-tw)/2)',
                'x=(w-tw-20)',
                'y=h-(2*lh) - 5',
                'font=Mono',
                'shadowx=2',
                'shadowy=2',
                'fontcolor=white',
                'fontsize=26',
                'boxborderw=10',
            ]))

        return ['-vf', ','.join(filters)]

    def prepareHls(self):
        if self.hls_path is None:
            raise Exception('hls_path not set. Unable to stream')

        os.makedirs(self.hls_path, mode=0o755, exist_ok=True)