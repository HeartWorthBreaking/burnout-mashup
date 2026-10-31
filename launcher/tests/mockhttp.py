"""mockhttp.py - a local HTTP server for the BUILD MASHUP download tests (127.0.0.1, a free port; nothing leaves this PC).

    srv = MockServer({"/path/file.zip": ("ok", data), "/gone.zip": ("404", b""), "/cut.zip": ("cut", data), "/bad.zip": ("wrong", data)})
    srv.url  -> "http://127.0.0.1:PORT"   ...   srv.stop()
Modes: ok (the bytes), 404, cut (announces the full length, sends half, closes: an interrupted download), wrong (same length, other
bytes: a tampered file), head (HEAD only answers). srv.hits lists the paths asked for. Original code (MIT)."""
import http.server
import socketserver
import threading


class MockServer:
    def __init__(self, routes):
        self.routes = routes
        self.hits = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _route(self):
                outer.hits.append(self.path)
                return outer.routes.get(self.path, ("404", b""))

            def do_HEAD(self):
                mode, data = self._route()
                if mode == "404":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()

            def do_GET(self):
                mode, data = self._route()
                if mode == "404":
                    self.send_error(404, "Not Found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if mode == "cut":
                    self.wfile.write(data[:len(data) // 2])
                    self.wfile.flush()
                    self.close_connection = True
                    try:
                        self.connection.shutdown(2)
                    except OSError:
                        pass
                    return
                if mode == "wrong":
                    data = bytes((b ^ 0x5A) for b in data[:64]) + data[64:]
                self.wfile.write(data)

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.httpd = S(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
