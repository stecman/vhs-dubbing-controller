import tornado.ioloop
import tornado.web
import tornado.websocket

import asyncio
import configparser
import json
import logging

from recorder import Recorder, STATE_IDLE, STATE_PREVIEWING

config = configparser.ConfigParser()
config.read('server.ini')

HLS_STREAM_PATH = config['stream']['hls_path']

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

        self.event = asyncio.Event()
        recorder = Recorder.instance()
        recorder.subscribe(self.event)

        io_loop = tornado.ioloop.IOLoop.current()
        io_loop.spawn_callback(self.auto_push_state)

        # Auto-start preview stream if no-one was connected before
        if ws_client_count == 1:
            recorder.start_preview()

    def on_message(self, message):
        recorder = Recorder.instance()

        if message == 'stop':
            recorder.stop_preview()

        if message == 'preview':
            recorder.start_preview()

    def on_close(self):
        Recorder.instance().unsubscribe(self.event)

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

    async def auto_push_state(self):
        recorder = Recorder.instance()

        while True:
            try:
                self.write_message(json.dumps({
                    "type": "state",
                    "data": recorder.getState()
                }))
            except tornado.websocket.WebSocketClosedError as e:
                # Client has disconnected: stop pushing stream info
                return

            await self.event.wait()
            self.event.clear()


def make_app():
    return tornado.web.Application([
        (r'/socket', ControllerWebSocket),
        (r'/hls/(.*)', StaticFileHandler, {'path': HLS_STREAM_PATH}),
        (r'/assets/(.*)', StaticFileHandler, {'path': "assets"}),
        (r"/", MainHandler),
    ], debug=True, autoreload = False)


if __name__ == "__main__":
    recorder = Recorder.instance()
    recorder.hls_path = HLS_STREAM_PATH
    recorder.fake = True

    app = make_app()
    app.listen(config['server']['port'])

    # Stop file GET requests spamming the log
    # There are a ton of these due to the short GOP of the HLS stream
    logging.getLogger('tornado.access').disabled = True

    tornado.ioloop.IOLoop.current().start()