import socket
import threading
import sys
import os
import gzip
import base64
import hashlib
import ssl

directory = "."  # default to current folder if not provided

if "--directory" in sys.argv:
    directory_index = sys.argv.index("--directory") + 1
    directory = sys.argv[directory_index]

VALID_USERNAME = "admin"
VALID_PASSWORD_HASH = "fcf730b6d95236ecd3c9fc2d92d7b6b2bb061514961aec041d6c7a7192f592e4"  # sha256("secret123")

def check_auth(lines):
    auth_header = ""
    for line in lines[1:]:
        if line.lower().startswith("authorization:"):
            auth_header = line.split(":", 1)[1].strip()
            break

    if not auth_header.startswith("Basic "):
        return False

    encoded_creds = auth_header[len("Basic "):]
    try:
        decoded = base64.b64decode(encoded_creds).decode('utf-8')
        username, password = decoded.split(":", 1)
    except Exception:
        return False

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    return username == VALID_USERNAME and password_hash == VALID_PASSWORD_HASH

def handle_client(client_socket):
    while True:
        should_close = False
        try:
            # ---- STAGE A: read until we have the full headers ----
            request_data = b""
            while b"\r\n\r\n" not in request_data:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break
                request_data += chunk

            if not request_data:
                break  # client disconnected before sending anything

            # Decode just enough to parse the request line + headers
            header_end = request_data.find(b"\r\n\r\n") + 4
            header_text = request_data[:header_end].decode('utf-8')
            lines = header_text.split("\r\n")
            request_line = lines[0]
            parts = request_line.split(" ")

            # ---- STAGE B: if there's a Content-Length, read until body is complete ----
            content_length = 0
            for line in lines[1:]:
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break

            body_so_far = request_data[header_end:]
            while len(body_so_far) < content_length:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break
                body_so_far += chunk
                request_data += chunk

            # Default response
            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

            # Check for Connection: close header
            connection_header = ""
            for line in lines[1:]:
                if line.lower().startswith("connection:"):
                    connection_header = line.split(":", 1)[1].strip().lower()
                    break
            should_close = (connection_header == "close")

            if len(parts) >= 2:
                path = parts[1]

                if path == "/":
                    method = parts[0]
                    if method != "GET":
                        response = b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"
                    else:
                        response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"

                elif path.startswith("/echo/"):
                    method = parts[0]
                    if method != "GET":
                        response = b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"
                    else:
                        content = path[len("/echo/"):]
                        body = content.encode()

                        accept_encoding = ""
                        for line in lines[1:]:
                            if line.lower().startswith("accept-encoding:"):
                                accept_encoding = line.split(":", 1)[1].strip()
                                break

                        use_gzip = "gzip" in accept_encoding

                        if use_gzip:
                            body = gzip.compress(body)
                            response = (
                                f"HTTP/1.1 200 OK\r\n"
                                f"Content-Type: text/plain\r\n"
                                f"Content-Encoding: gzip\r\n"
                                f"Content-Length: {len(body)}\r\n"
                                f"\r\n"
                            ).encode() + body
                        else:
                            response = (
                                f"HTTP/1.1 200 OK\r\n"
                                f"Content-Type: text/plain\r\n"
                                f"Content-Length: {len(body)}\r\n"
                                f"\r\n"
                            ).encode() + body

                elif path == "/user-agent":
                    method = parts[0]
                    if method != "GET":
                        response = b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"
                    else:
                        user_agent = ""
                        for line in lines[1:]:
                            if line.lower().startswith("user-agent:"):
                                user_agent = line.split(":", 1)[1].strip()
                                break
                        body = user_agent.encode()
                        response = (
                            f"HTTP/1.1 200 OK\r\n"
                            f"Content-Type: text/plain\r\n"
                            f"Content-Length: {len(body)}\r\n"
                            f"\r\n"
                        ).encode() + body

                elif path.startswith("/files/"):
                    if not check_auth(lines):
                        response = (
                            b"HTTP/1.1 401 Unauthorized\r\n"
                            b"WWW-Authenticate: Basic realm=\"Files\"\r\n"
                            b"Content-Length: 0\r\n\r\n"
                        )
                    else:
                        filename = path[len("/files/"):]
                        base_dir = os.path.realpath(directory)
                        full_path = os.path.realpath(os.path.join(directory, filename))
                        method = parts[0]

                        if not full_path.startswith(base_dir + os.sep):
                            response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"

                        elif method == "GET":
                            if os.path.isfile(full_path):
                                with open(full_path, "rb") as f:
                                    body = f.read()
                                response = (
                                    f"HTTP/1.1 200 OK\r\n"
                                    f"Content-Type: application/octet-stream\r\n"
                                    f"Content-Length: {len(body)}\r\n"
                                    f"\r\n"
                                ).encode() + body
                            else:
                                response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

                        elif method == "HEAD":
                            if os.path.isfile(full_path):
                                file_size = os.path.getsize(full_path)
                                response = (
                                    f"HTTP/1.1 200 OK\r\n"
                                    f"Content-Type: application/octet-stream\r\n"
                                    f"Content-Length: {file_size}\r\n"
                                    f"\r\n"
                                ).encode()
                            else:
                                response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

                        elif method == "POST" or method == "PUT":
                            with open(full_path, "wb") as f:
                                f.write(body_so_far)
                            response = b"HTTP/1.1 201 Created\r\nContent-Length: 0\r\n\r\n"

                        elif method == "DELETE":
                            if os.path.isfile(full_path):
                                os.remove(full_path)
                                response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
                            else:
                                response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

                        else:
                            response = b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"

                else:
                    response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

            # Patch in "Connection: close" if needed
            if should_close:
                resp_header_end = response.find(b"\r\n")
                response = response[:resp_header_end + 2] + b"Connection: close\r\n" + response[resp_header_end + 2:]

        except Exception as e:
            print(f"Error handling request: {e}")
            response = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"
            should_close = True

        try:
            client_socket.sendall(response)
        except Exception as e:
            print(f"Error sending response: {e}")
            break

        if should_close:
            break

    client_socket.close()

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("localhost", 4221))
    server_socket.listen()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="../cert.pem", keyfile="../key.pem")
    server_socket = context.wrap_socket(server_socket, server_side=True)

    print("Server is listening on port 4221 (HTTPS)...")
    while True:
        client_socket, _ = server_socket.accept()
        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.start()

if __name__ == "__main__":
    main()