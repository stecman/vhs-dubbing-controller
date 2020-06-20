import asyncio
import fcntl
import os
import re
import subprocess
import sys
import threading
import time

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
    '-hls_allow_cache', '0',
    '-start_number', '10',
    '-ignore_io_errors', '1',
    # FILENAME
]

STATE_IDLE = 'idle'
STATE_STOPPING = 'stopping'
STATE_STARTING_PREVIEW = 'start-preview'
STATE_STARTING_RECORDING = 'start-recording'
STATE_PREVIEWING = 'preview'
STATE_RECORDING = 'recording'

RE_MODULE_OUTPUT = r'^\[(.*?) @ (0x[0-9a-fA-F]+)\] (.*)'
RE_INFO_LINE_DETECT = r'^frame= *([0-9]+) ?'
RE_INFO_LINE = r'([a-zA-z]+)=\s*([^ ]+)(?: |$)'

def non_block_read(output):
    # fd = output.fileno()
    # fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    # fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return output.read(1)
    except:
        return ""

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

        # Recorder state
        self.state = STATE_IDLE
        self.subscriptions = set()

        # FFMPEG state
        self._ffmpeg_output = None

        # HLS Stream state
        self._stream_ready = False
        self._m3u8_write_count = 0

        # Get a reference to the asyncio event loop
        # This is used for pushing events back into the main thread
        self._main_loop = asyncio.get_event_loop()

    def subscribe(self, event):
        self.subscriptions.add(event)

    def unsubscribe(self, event):
        self.subscriptions.remove(event)

    def getState(self):
        return {
            "recorder": self.state,
            "ffmpeg": self._ffmpeg_output,
            "streamReady": self._stream_ready,
        }

    def start_preview(self):
        print("start_preview called")

        # Only permit starting preview from idle
        if self.state != STATE_IDLE:
            return False

        self.state = STATE_STARTING_PREVIEW
        self.emitState()

        self.prepareHls()

        if self.fake:
            cmd = cmd_fake[:]
        else:
            cmd = cmd_capture[:]

        cmd.extend(self.getHlsFilter(is_preview=True))

        cmd.extend(args_hls)
        cmd.append(self.getStreamFilename())

        self._thread = threading.Thread(
            name="ffmpeg-preview",
            target=self._execute,
            args=(cmd, STATE_PREVIEWING)
        )
        self._thread.start()

        return True

    def emitState(self):
        """ Thread-safe emit state changed signal """

        # Assume the main thread owns the asyncio loop
        if threading.main_thread() == threading.currentThread():
            self._emitState()
        else:
            self._main_loop.call_soon_threadsafe(self._emitState)

    def _emitState(self):
        """ Actually emit state changed signal (must be called on the main thread) """
        for async_event in self.subscriptions:
            async_event.set()

    def stop_preview(self):
        print("stop_preview called")
        if self.state == STATE_PREVIEWING:
            self.state = STATE_STOPPING
            self.emitState()

    def stop_recording(self):
        if self.state == STATE_RECORDING:
            self.state = STATE_STOPPING
            self.emitState()

    def handleFrameInfo(self, info):
        self._ffmpeg_output = info
        self.emitState()

    def handleHlsOutput(self, output):
        if output.startswith('Opening'):
            if self._stream_ready == False:
                if 'm3u8' in output:
                    self._stream_ready = True
            
            # Capture message to avoid these being logged
            return True

        return False



    def _execute(self, cmd, newState):
        stop_signal_sent = False
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        self._m3u8_write_count = 0
        self._stream_ready = False

        self.state = newState
        self.emitState()

        buf = ''
        while True:
            if self.state == STATE_STOPPING and not stop_signal_sent:
                print("Sending stop signal to ffmpeg subprocess...")
                process.send_signal(subprocess.signal.SIGINT)
                stop_signal_sent = True

            # Stream ffmpeg output in from stdout
            byte = non_block_read(process.stdout)
            if byte:
                buf += byte.decode('ascii')

                if byte in [b'\r', b'\n']:
                    self.handleOutput(buf.strip())
                    buf = ''

            if process.poll() is not None:
                break

        self.state = STATE_IDLE
        self._ffmpeg_output = None
        self._stream_ready = False
        self.emitState()

        exit_code = process.poll()
        return exit_code

    def handleOutput(self, line):
        # Catch the frame, time and size info lines
        match = re.match(RE_INFO_LINE_DETECT, line)
        if match:
            self.handleFrameInfo(dict(re.findall(RE_INFO_LINE, line)))
            return

        # Catch the HLS muxer's "opening file for writing" messages
        match = re.match(RE_MODULE_OUTPUT, line)
        if match:
            module, address, output = match.groups()

            if module == 'hls':
                if self.handleHlsOutput(output):
                    return

        print(line)

    def getStreamFilename(self):
        return os.path.join(self.hls_path, 'stream.m3u8')

    def getHlsFilter(self, is_preview=False):
        """
        Return a list of FFMPEG arguments to apply a filter to apply to the HLS video stream
        This provides de-interlacing to a 50 fps output and some text overlays.
        """
        filters = [
            # Deinterlace the captured signal to one output frame per field
            'bwdif=mode=send_field:parity=tff',
            # Crop out the useless parts of the video signal for streaming
            'crop=692:554:14:8',
            # Reduce the sampling from the input 4:2:2 to something better supported
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
        """
        Ensure the HLS configuration is valid and prepare the filesystem
        """
        if self.hls_path is None:
            raise Exception('hls_path not set. Unable to stream')

        os.makedirs(self.hls_path, mode=0o755, exist_ok=True)