import asyncio
import os
import re
import subprocess
import sys
import threading
import time

if sys.platform == 'win32':
    FFMPEG = 'ffmpeg.exe'
else:
    FFMPEG = 'ffmpeg'

cmd_base = [
    FFMPEG,
    '-y', # Overwrite output file without asking. We'll handle this Python
    '-nostdin', # Disallow interactive input on stdin
]

# Output stream arguments for capture to file
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
    # <output-filename>
]

# Output stream arguments for HLS preview/monitoring
args_hls = [
    '-preset', 'ultrafast', '-vcodec', 'libx264', '-tune', 'zerolatency', '-flags', '+cgop', '-g', '50', '-b:v', '5700k',
    '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-strict', '2',
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
    # <output-filename>
]

STATE_IDLE = 'idle'
STATE_STOPPING = 'stopping'
STATE_STARTING_PREVIEW = 'start-preview'
STATE_STARTING_RECORDING = 'start-recording'
STATE_PREVIEWING = 'preview'
STATE_RECORDING = 'recording'

RE_MODULE_OUTPUT = r'^\[(.*?) @ ((?:0x)?[0-9a-fA-F]+)\] (.*)'
RE_INFO_LINE_DETECT = r'^frame= *([0-9]+) ?'
RE_INFO_LINE = r'([a-zA-z]+)=\s*([^ ]+)(?: |$)'

def format_num_bytes(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.2f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.2f%s%s" % (num, 'Y', suffix)

class Recorder:
    """
    Controller that manages FFMPEG processeses in a background thread
    """
    __instance = None

    @staticmethod
    def instance():
        if Recorder.__instance is None:
            raise Exception("No instance set. Pass a Recorder instance to set_instance()")

        return Recorder.__instance

    @staticmethod
    def set_instance(recorder):
        Recorder.__instance = recorder

    def __init__(self, capture_args, hls_path, file_manager):
        self.hls_path = hls_path
        self.file_manager = file_manager
        self.capture_args = capture_args

        # Recorder state
        self.state = STATE_IDLE
        self.subscriptions = set()

        # FFMPEG state
        self._ffmpeg_output = None
        self._duration_secs = 0

        # HLS Stream state
        self._stream_ready = False
        self._m3u8_write_count = 0

        # Get a reference to the asyncio event loop
        # This is used for pushing events back into the main thread
        self._main_loop = asyncio.get_event_loop()

    def subscribe(self, queue):
        """
        Subscribe to get callbacks when state changes
        """
        self.subscriptions.add(queue)

    def unsubscribe(self, queue):
        """
        Unsubscribe from state change callbacks
        """
        self.subscriptions.remove(queue)

    def getState(self):
        return {
            "recorder": self.state,
            "ffmpeg": self._ffmpeg_output,
            "streamReady": self._stream_ready,
            "duration": self._duration_secs
        }

    def set_duration(self, seconds):
        """
        Set the capture duration the recording should automatically stop after
        """
        if self.state not in [STATE_RECORDING, STATE_STARTING_RECORDING]:
            self._duration_secs = seconds

    def start_preview(self):
        """
        Start a preview HLS output stream, but don't save anything to file
        """
        # Only permit starting preview from idle
        if self.state != STATE_IDLE:
            return False

        self.state = STATE_STARTING_PREVIEW
        self.emitState()

        self.prepareHls()

        cmd = cmd_base[:]

        # Input stream args
        cmd.extend(self.capture_args)

        # Filter for streamed output
        cmd.extend(self.getHlsFilter(is_preview=True))

        # Stream as HLS
        cmd.extend(args_hls)
        cmd.append(self.getStreamFilename())

        self._thread = threading.Thread(
            name="ffmpeg-preview",
            target=self._execute,
            args=(cmd, STATE_PREVIEWING)
        )
        self._thread.start()

        return True

    def start_recording(self):
        """
        Start a video capture to file and an generate an HLS output stream for monitoring
        """
        if self.state == STATE_RECORDING or self.state == STATE_STARTING_RECORDING:
            # Already recording or starting to record
            return False

        # Preview process is still using the capture device
        # We need to stop the existing process as only one process can attach to the device at a time
        if self.state != STATE_IDLE:
            # Wait for preview to start before we can stop it
            while self.state == STATE_STARTING_PREVIEW:
                time.sleep(0.1)

            # Signal the preview process to stop
            if self.state == STATE_PREVIEWING:
                self.state = STATE_STOPPING
                self.emitState()

            # Wait for preview to end
            while self.state == STATE_STOPPING:
                time.sleep(0.1)

        self.state = STATE_STARTING_RECORDING
        self.emitState()

        self.prepareHls()

        cmd = cmd_base[:]

        # Limit capture to specified length
        # This is always required as we don't want to accidentally be left recording indefinitely
        cmd.extend(['-t', str(self._duration_secs)])

        # Input stream args
        cmd.extend(self.capture_args)

        # Save archive copy
        output_file = self.file_manager.new_recording_path()

        cmd.extend(args_save_ffv1)
        cmd.append(output_file)

        # Filter for streamed output
        cmd.extend(self.getHlsFilter())

        # Stream as HLS
        # This needs the time specified as well so it stops when the recording does
        cmd.extend(args_hls)
        cmd.append(self.getStreamFilename())

        print(' '.join(cmd))

        self._thread = threading.Thread(
            name="ffmpeg-preview",
            target=self._execute,
            args=(cmd, STATE_RECORDING)
        )
        self._thread.start()

        return True

    def stop_preview(self):
        if self.state == STATE_PREVIEWING:
            self.state = STATE_STOPPING
            self.emitState()

    def stop_recording(self):
        if self.state == STATE_RECORDING:
            self.state = STATE_STOPPING
            self.emitState()

    def emitState(self):
        """
        Thread-safe emit state changed signal
        """

        # Assume the main thread owns the asyncio loop
        if threading.main_thread() == threading.currentThread():
            self._emitState()
        else:
            self._main_loop.call_soon_threadsafe(self._emitState)

    def _emitState(self):
        """
        Actually emit state changed signal (must be called on the main thread)
        """
        state = self.getState()

        for async_queue in self.subscriptions:
            async_queue.put_nowait(state)

    def handleFrameInfo(self, info):
        if 'size' in info:
            if info['size'] != 'N/A':
                number = re.sub(r'[^0-9]+', '', info['size'])
                if number:
                    info['size'] = format_num_bytes(int(number) * 1024)

        self._ffmpeg_output = info
        self.emitState()

    def handleHlsOutput(self, output):
        if output.startswith('Opening'):
            if self._stream_ready == False:
                if 'm3u8' in output:
                    self._stream_ready = True
            #
            # Capture message to avoid these being logged
            return True

        return False


    def _execute(self, cmd, newState):
        stop_signal_sent = False
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

        self._m3u8_write_count = 0
        self._stream_ready = False

        self.state = newState
        self.emitState()

        buf = ''
        while True:
            if self.state == STATE_STOPPING and not stop_signal_sent:
                print("Sending stop signal to ffmpeg subprocess...")
                process.terminate()
                stop_signal_sent = True

            # Stream ffmpeg output in from stdout
            byte = process.stdout.read(1)
            if byte:
                buf += byte.decode('ascii')

                if byte in [b'\r', b'\n']:
                    line = buf.strip()
                    if line:
                        self.handleOutput(line)
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
                'font=%s' % self._getDrawTextFont(),
                'fontcolor=black',
                'fontsize=26',
                'box=1',
                'boxcolor=yellow',
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

    def _getDrawTextFont(self):
        """
        Return a font that's likely to be on this system
        """
        if sys.platform == 'win32':
            return 'Consolas'
        else:
            return 'Mono'