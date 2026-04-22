import os
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
from app import app

port = int(os.environ.get('PORT', 8000))
server = pywsgi.WSGIServer(('0.0.0.0', port), app, handler_class=WebSocketHandler)
print(f'Serving on http://0.0.0.0:{port}')
server.serve_forever()
