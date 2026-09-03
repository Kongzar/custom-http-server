# Custom HTTP Server (Python, from scratch)

A basic but genuinely functional HTTP/1.1 server built from raw TCP sockets in Python —
no frameworks, no libraries beyond Python's standard library (`socket`, `threading`,
`gzip`, `os`, `sys`).

## Why this exists

This started as my attempt at the [CodeCrafters "Build Your Own HTTP Server"
challenge](https://codecrafters.io/challenges/http-server). I hit their paywall partway
through the "extract URL path" stage and didn't want to stop there, so I kept building
it out with help from Claude (Anthropic's AI assistant) — both to finish the original
challenge stages, and afterward to harden it toward something closer to a real-world
implementation.

**I'm being upfront about this:** a lot of this code was written collaboratively with
AI — I'd ask questions, get explanations and code, then test it myself, hit real bugs
(stale server processes, unsaved files, `/tmp` getting wiped, broken indentation from my
own copy-pasting), and debug them with AI's help too. I did type and run everything
myself, and by the end I understood *why* each piece works, not just that it works — but
I want that process to be visible rather than presented as if I wrote 400 lines of
socket-level HTTP handling unaided from a blank file. If you're evaluating this as a
learning artifact, that's the honest context.

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

## What I learned building this

- How HTTP actually looks as raw bytes over a socket — the request line, headers,
  `\r\n` line endings, and the `\r\n\r\n` separator between headers and body
- Why a single `recv()` call isn't reliable for anything beyond trivially small
  requests, and how to loop until you've actually received everything you were
  promised (via `Content-Length`)
- The difference between GET/POST/PUT/DELETE/HEAD semantically, not just as strings
  to switch on
- Why threading matters for concurrency, and how to actually test that it's working
  (and how easy it is to write a test that *looks* like it proves something but
  doesn't — see the `curl --path-as-is` lesson below)
- What directory traversal attacks actually look like and how `os.path.realpath` +
  a prefix check stops them
- Why unhandled exceptions in a request handler can silently hang a client forever,
  and how `try/except` placement (wrapping the *processing*, not just the send)
  fixes that
- A bunch of debugging fundamentals that had nothing to do with HTTP: killing stale
  processes on a port (`lsof -i :PORT` / `kill -9`), the fact that `/tmp` gets wiped
  by macOS and isn't for anything you want to persist, that editors need to actually
  save before a rerun picks up changes, and that curl silently normalizes `..` in
  URLs unless you pass `--path-as-is` (a fun one — my first "successful" traversal
  test was actually a false pass, because curl had already stripped the attack out
  of the URL before it ever reached my server)

## Running it

```bash
python3 main.py --directory /path/to/some/folder
```

Then, in another terminal:

```bash
curl localhost:4221/
curl localhost:4221/echo/hello
curl localhost:4221/user-agent -H "User-Agent: test/1.0"
curl localhost:4221/files/somefile.txt
curl -X POST localhost:4221/files/newfile.txt -d "some content"
curl -X DELETE localhost:4221/files/newfile.txt
curl --compressed localhost:4221/echo/hello
```

## Known limitations (honestly)

This is not production-hardened. Specifically it's missing:

- **No TLS/HTTPS** — everything is sent in plaintext
- **No authentication** — anyone who can reach the port can read/write/delete any file
  in the served directory
- **No rate limiting**
- **Thread-per-connection concurrency** doesn't scale the way event-loop-based servers
  (nginx, `asyncio`) do under heavy load
- Not fuzz-tested or hardened against malformed/malicious input beyond the specific
  cases (directory traversal, bad methods, missing files) handled above

It's a solid learning project and a reasonable local tool (quick file transfer between
devices on the same network, testing webhook receivers, etc.) — not something I'd point
at the open internet.

## What's next

Planning to keep extending this — possible next steps: basic auth, an HTML directory
listing for `/files/`, HTTPS via `ssl.wrap_socket`/`ssl.SSLContext`, and maybe a
comparison version using `asyncio` instead of threads.
