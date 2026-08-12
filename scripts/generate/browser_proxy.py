import select
import socketserver
import threading
from urllib.parse import unquote, urlparse, urlunparse

import socks


def _split_host_port(value, default_port):
    host_port = str(value or "").strip()
    if host_port.startswith("["):
        end = host_port.find("]")
        if end != -1:
            host = host_port[1:end]
            rest = host_port[end + 1 :]
            return host, int(rest[1:]) if rest.startswith(":") else default_port

    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
        return host, int(port)
    return host_port, default_port


def _relay_sockets(left, right):
    sockets = [left, right]
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, 60)
        if exceptional or not readable:
            return

        for source in readable:
            destination = right if source is left else left
            try:
                data = source.recv(65536)
                if not data:
                    return
                destination.sendall(data)
            except OSError:
                return


def _upstream_socket(proxy, target_host, target_port, timeout_seconds):
    parsed = urlparse(proxy)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("socks", "socks5", "socks5h"):
        raise RuntimeError(f"Unsupported Selenium proxy scheme: {scheme}")
    if not parsed.hostname:
        raise RuntimeError("Selenium proxy URL is missing a host")

    sock = socks.socksocket()
    sock.set_proxy(
        socks.SOCKS5,
        parsed.hostname,
        parsed.port or 1080,
        rdns=scheme == "socks5h",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
    )
    sock.settimeout(timeout_seconds)
    sock.connect((target_host, target_port))
    return sock


class _BrowserProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BrowserProxyHandler(socketserver.StreamRequestHandler):
    def handle(self):
        request_line = self.rfile.readline(65536).decode("iso-8859-1", errors="replace")
        parts = request_line.rstrip("\r\n").split()
        if len(parts) != 3:
            return
        method, target, version = parts

        headers = []
        while True:
            line = self.rfile.readline(65536)
            if not line or line in (b"\r\n", b"\n"):
                break
            headers.append(line)

        if method.upper() == "CONNECT":
            target_host, target_port = _split_host_port(target, 443)
            upstream = _upstream_socket(
                self.server.upstream_proxy,
                target_host,
                target_port,
                self.server.connect_timeout_seconds,
            )
            try:
                self.wfile.write(f"{version} 200 Connection Established\r\n\r\n".encode("ascii"))
                self.wfile.flush()
                _relay_sockets(self.connection, upstream)
            finally:
                upstream.close()
            return

        parsed = urlparse(target)
        if parsed.scheme and parsed.netloc:
            target_host = parsed.hostname
            target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = urlunparse(
                ("", "", parsed.path or "/", parsed.params, parsed.query, parsed.fragment)
            )
        else:
            host_header = next(
                (line for line in headers if line.lower().startswith(b"host:")), None
            )
            if not host_header:
                return
            host_value = host_header.decode("iso-8859-1").split(":", 1)[1]
            target_host, target_port = _split_host_port(host_value, 80)
            path = target or "/"

        upstream = _upstream_socket(
            self.server.upstream_proxy,
            target_host,
            target_port,
            self.server.connect_timeout_seconds,
        )
        try:
            upstream.sendall(f"{method} {path} {version}\r\n".encode("iso-8859-1"))
            for header in headers:
                if not header.lower().startswith(b"proxy-connection:"):
                    upstream.sendall(header)
            upstream.sendall(b"\r\n")
            _relay_sockets(self.connection, upstream)
        finally:
            upstream.close()


class BrowserProxyBridge:
    def __init__(self, upstream_proxy, timeout_seconds):
        self._server = _BrowserProxyServer(("127.0.0.1", 0), _BrowserProxyHandler)
        self._server.upstream_proxy = upstream_proxy
        self._server.connect_timeout_seconds = timeout_seconds
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}"

    def close(self):
        self._server.shutdown()
        self._server.server_close()


def configure_firefox_proxy(options, proxy_url):
    parsed = urlparse(proxy_url)
    if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
        raise RuntimeError("Local browser proxy must be an HTTP URL with a host and port")

    options.set_preference("network.proxy.type", 1)
    options.set_preference("network.proxy.no_proxies_on", "")
    options.set_preference("network.proxy.http", parsed.hostname)
    options.set_preference("network.proxy.http_port", parsed.port)
    options.set_preference("network.proxy.ssl", parsed.hostname)
    options.set_preference("network.proxy.ssl_port", parsed.port)
