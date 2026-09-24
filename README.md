# Custom HTTP Server (Python, from scratch)

A basic but genuinely functional HTTP/1.1 server built from raw TCP sockets in Python —
no frameworks, no libraries beyond Python's standard library (`socket`, `threading`,
`gzip`, `os`, `sys`, `base64`, `ssl`).

## Why this exists

This started as my attempt at the [CodeCrafters "Build Your Own HTTP Server"
challenge](https://codecrafters.io/challenges/http-server). I hit their paywall partway
through the "extract URL path" stage and didn't want to stop there, so I kept building
it out with help from Claude (Anthropic's AI assistant) — both to finish the original
challenge stages, and afterward to harden it toward something closer to a real-world
implementation, then to extend it further into authentication and encryption.

**I'm being upfront about this:** a lot of this code was written collaboratively with
AI — I'd ask questions, get explanations and code, then test it myself, hit real bugs
(stale server processes, unsaved files, `/tmp` getting wiped, broken indentation from my
own copy-pasting, a false-positive security test caused by curl silently rewriting a
URL), and debug them with AI's help too. I did type and run everything myself, and by
the end I understood *why* each piece works, not just that it works — but I want that
process to be visible rather than presented as if I wrote all of this unaided from a
blank file. If you're evaluating this as a learning artifact, that's the honest context.

## What it does

- Parses raw HTTP requests directly off a TCP socket (no `http.server`, no frameworks)
- Routes based on path and method
- `GET /` — basic health check
- `GET /echo/{str}` — echoes a string back, with optional gzip compression
  (`Accept-Encoding: gzip`)
- `GET /user-agent` — reads and returns the `User-Agent` request header
- `GET /files/{filename}` — serves a file from a configured directory
- `HEAD /files/{filename}` — same as GET but headers only, no body
- `POST /files/{filename}` / `PUT /files/{filename}` — writes the request body to a file
- `DELETE /files/{filename}` — deletes a file
- Handles multiple simultaneous clients via one thread per connection
- Supports persistent (keep-alive) connections — multiple requests per TCP connection,
  closing only on `Connection: close` or client disconnect
- Reads the *entire* request (headers + body) regardless of size, instead of trusting a
  single `recv()` call
- Blocks directory traversal attempts (`/files/../../etc/passwd`) by resolving paths
  with `os.path.realpath` and checking they stay inside the served directory
- Returns proper status codes for unsupported methods (`405`), missing files (`404`),
  path traversal attempts (`403`), and unexpected server errors (`500` instead of
  hanging the client)
- **HTTP Basic Authentication** on all `/files/` routes — requires a username/password
  sent via the `Authorization` header before any file can be read, written, or deleted
- **HTTPS/TLS support** — wraps the raw socket with Python's `ssl` module and a
  self-signed certificate, encrypting the entire connection (not just the auth header)

## What I learned building this

- How HTTP actually looks as raw bytes over a socket — the request line, headers,
  `\r\n` line endings, and the `\r\n\r\n` separator between headers and body
- Why a single `recv()` call isn't reliable for anything beyond trivially small
  requests, and how to loop until you've actually received everything you were
  promised (via `Content-Length`)
- The difference between GET/POST/PUT/DELETE/HEAD semantically, not just as strings
  to switch on
- Why threading matters for concurrency, and how to actually test that it's working
- What directory traversal attacks actually look like and how `os.path.realpath` +
  a prefix check stops them — including discovering that my first "successful" test
  of this was actually a false pass, because curl silently normalizes `..` out of a
  URL unless you pass `--path-as-is`
- Why unhandled exceptions in a request handler can silently hang a client forever,
  and how `try/except` placement (wrapping the *processing*, not just the send)
  fixes that
- **How HTTP Basic Auth actually works** — that it's just Base64 encoding of
  `username:password`, not encryption, and proved this to myself by decoding a
  captured Basic Auth header with a single `base64 -d` command
- **Why TLS/HTTPS matters** — captured my own server's traffic with `tcpdump` before
  and after adding TLS. Without it, Basic Auth credentials are trivially readable.
  With it, the same request is unreadable ciphertext to anyone watching the network,
  even though the credentials and file content are identical
- Where TLS conceptually sits relative to the application — it wraps the socket
  underneath the HTTP logic, so the HTTP-handling code itself never had to change at
  all to gain encryption
- A bunch of debugging fundamentals that had nothing to do with HTTP specifically:
  killing stale processes on a port (`lsof -i :PORT` / `kill -9`), the fact that
  `/tmp` gets wiped by macOS and isn't for anything you want to persist, that editors
  need to actually save before a rerun picks up changes, running commands in the
  right order across multiple terminals for tools like `tcpdump` to actually capture
  anything

## Running it

Generate a self-signed certificate once (from the repo root):
```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

Then run the server (from the `app/` folder):
```bash
python3 main.py --directory /path/to/some/folder
```

Test it (note `https://` and `-k` since the cert is self-signed):
```bash
curl -k https://localhost:4221/
curl -k https://localhost:4221/echo/hello
curl -k https://localhost:4221/user-agent -H "User-Agent: test/1.0"
curl -k -u admin:secret123 https://localhost:4221/files/somefile.txt
curl -k -u admin:secret123 -X POST https://localhost:4221/files/newfile.txt -d "some content"
curl -k -u admin:secret123 -X DELETE https://localhost:4221/files/newfile.txt
curl -k --compressed https://localhost:4221/echo/hello
```

Default credentials are hardcoded in `main.py` (`admin` / `secret123`) — this is fine
for a local learning project, not how you'd do it for anything real (see limitations
below).

## Known limitations (honestly)

This is not production-hardened. Specifically it's missing:

- **Hardcoded credentials** — a single username/password pair, in plaintext, directly
  in the source code. A real system would use a database, hashed passwords, and
  probably a proper auth scheme (sessions, tokens) instead of Basic Auth
- **Self-signed certificate** — browsers/clients will always show a trust warning
  unless you install your own cert as trusted locally. A real deployment needs a
  certificate from a trusted authority (e.g. Let's Encrypt)
- **No rate limiting**
- **Thread-per-connection concurrency** doesn't scale the way event-loop-based servers
  (nginx, `asyncio`) do under heavy load
- Not fuzz-tested or hardened against malformed/malicious input beyond the specific
  cases (directory traversal, bad methods, missing files) handled above

It's a solid learning project and a reasonable local tool (quick encrypted file
transfer between devices on the same network, testing webhook receivers, etc.) — not
something I'd point at the open internet as-is.

## What's next

Possible next steps: real credential storage (hashed passwords, maybe a small SQLite
table), an HTML directory listing for `/files/`, and maybe a comparison version using
`asyncio` instead of threads to see how the concurrency model differs.
