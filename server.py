import tornado.ioloop
import tornado.web

import configparser
import logging

from recorder import Recorder

config = configparser.ConfigParser()
config.read('server.ini')

HLS_STREAM_PATH = config['stream']['hls_path']

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.htm")

def make_app():
    return tornado.web.Application([
        (r'/hls/(.*)', tornado.web.StaticFileHandler, {'path': HLS_STREAM_PATH}),
        (r'/assets/(.*)', tornado.web.StaticFileHandler, {'path': "assets"}),
        (r"/", MainHandler),
    ], debug=True, autoreload = False)

if __name__ == "__main__":
    recorder = Recorder.instance()
    recorder.hls_path = HLS_STREAM_PATH
    recorder.fake = True

    recorder.preview()

    app = make_app()
    app.listen(config['server']['port'])

    # Stop file GET requests spamming the log
    # There are a ton of these due to the short GOP of the HLS stream
    logging.getLogger('tornado.access').disabled = True

    tornado.ioloop.IOLoop.current().start()