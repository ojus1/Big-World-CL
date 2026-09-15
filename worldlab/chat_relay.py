"""Container-local HTTP relay to one controller-owned attempt Unix socket.

The solver sees only models and chat completions. The relay has no TCP upstream,
credentials, retries or benchmark data. Share a network-none namespace with the solver.
"""
import argparse
import http.client
import http.server
import socket


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__('attempt', timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Relay(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, socket_path, timeout):
        super().__init__(address, Handler)
        self.socket_path, self.upstream_timeout = socket_path, timeout


class Handler(http.server.BaseHTTPRequestHandler):
    # Close-delimited responses preserve streaming without inventing framing.
    protocol_version = 'HTTP/1.0'

    def do_GET(self):
        self.forward('GET')

    def do_POST(self):
        self.forward('POST')

    def forward(self, method):
        if (method, self.path) not in {('GET', '/v1/models'), ('POST', '/v1/chat/completions')}:
            self.send_error(404); return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get_all('Transfer-Encoding') or len(lengths) > 1 or (
                lengths and not lengths[0].isascii()) or (lengths and not lengths[0].isdigit()):
            self.send_error(400); return
        if method == 'POST' and not lengths:
            self.send_error(411); return
        length = int(lengths[0]) if lengths else 0
        if length > 256 * 1024 * 1024:
            self.send_error(413); return
        self.connection.settimeout(self.server.upstream_timeout)
        body = self.rfile.read(length) if length else None
        if body is not None and len(body) != length:
            self.send_error(400); return
        upstream = UnixConnection(self.server.socket_path, self.server.upstream_timeout)
        sent = False
        try:
            # Never forward Authorization, Host, proxy headers or user endpoints.
            upstream.request(method, self.path, body=body,
                             headers={'Content-Type': 'application/json', 'Accept-Encoding': 'identity'})
            response = upstream.getresponse()
            sent, connected = True, True
            try:
                self.send_response(response.status)
                self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.end_headers()
            except OSError:
                connected = False
            while chunk := response.read1(65536):
                if connected:
                    try:
                        self.wfile.write(chunk); self.wfile.flush()
                    except OSError:
                        connected = False
                # Fluso can exit with an accepted background request in flight.
                # Drain its already-dispatched response so the controller can
                # retain usage; never turn client exit into uncharged work.
        except (OSError, http.client.HTTPException):
            if not sent:
                self.send_error(502)
        finally:
            upstream.close()
            self.close_connection = True

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--timeout', type=int, required=True)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    with Relay(('0.0.0.0', args.port), args.socket, args.timeout) as server:
        server.serve_forever()


if __name__ == '__main__': main()
