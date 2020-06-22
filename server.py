import tornado.ioloop
import tornado.web
import tornado.websocket

import asyncio
import configparser
import json
import logging
import sys

from recorder import Recorder, STATE_IDLE, STATE_PREVIEWING
from filemanager import FileManager

config = configparser.ConfigParser()
config.read('server.ini')

def addNoCacheHeader(handler):
    """
    Add headers that all responses should have
    """
    handler.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        addNoCacheHeader(self)
        self.render("index.htm")


class StaticFileHandler(tornado.web.StaticFileHandler):
    """
    Static file handler that prevents caching
    """
    def set_extra_headers(self, path):
        if path.endswith(".css") or path.endswith(".js"):
            addNoCacheHeader(self)

ws_client_count = 0

class ControllerWebSocket(tornado.websocket.WebSocketHandler):
    """
    Web socket server as the primary API for the web page
    """
    def open(self):
        global ws_client_count

        # Send messages as soon as possible
        self.set_nodelay(True)
        ws_client_count += 1

        self.queue = asyncio.Queue()
        recorder = Recorder.instance()
        recorder.subscribe(self.queue)

        io_loop = tornado.ioloop.IOLoop.current()
        io_loop.spawn_callback(self.push_video_state)

        # Auto-start preview stream if no-one was connected before
        if ws_client_count == 1:
            recorder.start_preview()

    def on_message(self, message):
        recorder = Recorder.instance()

        if message == 'stop':
            recorder.stop_preview()
            recorder.stop_recording()

        elif message == 'preview':
            recorder.start_preview()

        elif message.startswith('record'):
            parts = message.split(':')
            if len(parts) == 2:
                cmd, durationSeconds = parts
                recorder.set_duration( int(durationSeconds) );
                recorder.start_recording()

        elif message == 'fileinfo':
            self.write_message(json.dumps({
                "type": "fileinfo",
                "data": FileManager.instance().get_state()
            }))

        elif message == 'increment':
            FileManager.instance().increment_tape_number()

            self.write_message(json.dumps({
                "type": "fileinfo",
                "data": FileManager.instance().get_state()
            }))


    def on_close(self):
        Recorder.instance().unsubscribe(self.queue)

        global ws_client_count
        ws_client_count -= 1

        io_loop = tornado.ioloop.IOLoop.current()
        io_loop.spawn_callback(self.auto_close_preview)

    async def auto_close_preview(self):
        global ws_client_count

        # Keep the preview running for 5 seconds after the last client disconnects
        # This allows for page refreshing without restarting the preview stream
        await asyncio.sleep(5)

        if ws_client_count == 0:
            recorder.stop_preview()

    async def push_video_state(self):
        recorder = Recorder.instance()

        # Push the initial state at connection
        state = recorder.getState()

        while True:
            try:
                self.write_message(json.dumps({
                    "type": "state",
                    "data": state
                }))
            except tornado.websocket.WebSocketClosedError as e:
                # Client has disconnected: stop pushing stream info
                return

            state = await self.queue.get()


def make_app():
    return tornado.web.Application([
        (r'/socket', ControllerWebSocket),
        (r'/hls/(.*)', StaticFileHandler, {'path': config['stream']['hls_path']}),
        (r'/assets/(.*)', StaticFileHandler, {'path': "assets"}),
        (r"/", MainHandler),
    ], debug=True, autoreload = False)


if __name__ == "__main__":

    # Fix tornado exiting on startup under Windows with Python >=3.8
    # (https://github.com/tornadoweb/tornado/issues/2751)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    file_manager = FileManager(
        storage_path = config['archive']['storage_path'],
        db_file = config['archive']['count_file'],
    )

    recorder = Recorder(
        hls_path = config['stream']['hls_path'],
        file_manager = file_manager,
    )

    recorder.fake = True

    # Cheap hack for now to make these available in websockets without being global variables
    Recorder.set_instance(recorder)
    FileManager.set_instance(file_manager)

    app = make_app()
    app.listen(config['server']['port'])

    # Stop file GET requests spamming the log
    # There are a ton of these due to the short GOP of the HLS stream
    logging.getLogger('tornado.access').disabled = True

    tornado.ioloop.IOLoop.current().start()
