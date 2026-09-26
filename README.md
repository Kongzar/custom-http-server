# Custom HTTP Server (Python, from scratch)

A basic but genuinely functional HTTP/1.1 server built from raw TCP sockets in Python —
no frameworks, no libraries beyond Python's standard library (`socket`, `threading`,
`gzip`, `os`, `sys`, `base64`, `hashlib`, `sqlite3`, `ssl`).

## Why this exists

This started as my attempt at the [CodeCrafters "Build Your Own HTTP Server"
challenge](https://codecrafters.io/challenges/http-server). I hit their paywall partway
through the "extract URL path" stage and didn't want to stop there, so I kept building
it out with help from Claude (Anthropic's AI assistant) — both to finish the original
challenge stages, and afterward to harden it toward something closer to a real-world
implementation, then to extend it further into authentication, encryption, and
persistent user storage.

**I'm being upfront about this:** a lot of this code was written collaboratively with
AI — I'd ask questions, get explanations and code, then test it myself, hit real bugs
and debug them with AI's help too. I did type and run everything myself, and by the end
I understood *why* each piece works, not just that it works — but I want that process to
be visible rather than presented as if I wrote all of this unaided from a blank file. If
you're evaluating this as a learning artifact, that's the honest context. This included
some genuinely rough debugging stretches — see "What I learned" below for the more
interesting ones, including a bug that took a long time to track down because the file I
thought was running wasn't actually the file that was running.

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
- **Hashed passwords** — passwords are stored as SHA-256 hashes, never in plaintext, and
  compared by hashing the incoming credential and checking it against the stored hash
- **Multiple users via a SQLite database** — `users.db` holds a `users` table
  (`username`, `password_hash`); any number of users can be added without touching the
  server code, and `check_auth()` looks each one up at request time

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
  With it, the same request is unreadable ciphertext to anyone watching the network
- **What password hashing actually buys you** — that SHA-256 is one-way (you can't
  reverse a hash back to the password, not even as the legitimate owner, which is
  exactly why "forgot password" flows always reset rather than recover), and saw the
  avalanche effect firsthand (changing one character of input completely changes the
  output hash, with no partial resemblance)
- **Basic SQL and SQLite** — creating a table, inserting rows with parameterized
  queries (`?` placeholders) instead of string-formatting values directly into SQL,
  specifically to avoid SQL injection, and looking a row up by a unique key
- A long, genuinely humbling debugging stretch where a `kongzar` user that was
  correctly stored in the database, with a hash that matched perfectly when checked
  by hand, still failed to authenticate — because the file being edited, saved, and
  inspected with `cat` was not, for a stretch, the same file the running server
  process had actually loaded. The lesson: when every piece of logic checks out in
  isolation but real behavior still contradicts it, stop trusting assumptions about
  *what's running* and verify it directly, rather than re-checking the logic again
- A bunch of debugging fundamentals that had nothing to do with HTTP specifically:
  killing stale processes on a port (`lsof -i :PORT` / `kill -9`), the fact that
  `/tmp` gets wiped by macOS and isn't for anything you want to persist, that editors
  need to actually save before a rerun picks up changes, and untangling a genuinely
  messy git situation involving two nested repositories and a remote that was still
  pointed at CodeCrafters instead of GitHub

## Running it

Generate a self-signed certificate once (from the repo root):
```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

Create the user database once (from the repo root), then add at least one user:
```bash
python3
>>> import sqlite3, hashlib
>>> conn = sqlite3.connect("users.db")
>>> cursor = conn.cursor()
>>> cursor.execute("CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)")
>>> username = "admin"
>>> password_hash = hashlib.sha256("secret123".encode()).hexdigest()
>>> cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
>>> conn.commit()
>>> exit()
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

## Known limitations (honestly)

This is not production-hardened. Specifically it's missing:

- **Self-signed certificate** — browsers/clients will always show a trust warning
  unless you install your own cert as trusted locally. A real deployment needs a
  certificate from a trusted authority (e.g. Let's Encrypt)
- **No salting on password hashes** — plain SHA-256 is vulnerable to precomputed
  rainbow-table attacks in a way that a proper password hashing function (bcrypt,
  scrypt, or Argon2, with a per-user salt) is not. This is a real gap, not a stylistic
  choice — SHA-256 was used here for learning the *concept* of hashing, not as a
  production-grade password storage recommendation
- **No account creation flow** — new users are added by hand via the Python shell,
  not through the server itself
- **No rate limiting**
- **Thread-per-connection concurrency** doesn't scale the way event-loop-based servers
  (nginx, `asyncio`) do under heavy load
- Not fuzz-tested or hardened against malformed/malicious input beyond the specific
  cases (directory traversal, bad methods, missing files) handled above

It's a solid learning project and a reasonable local tool (quick encrypted file
transfer between devices on the same network, testing webhook receivers, etc.) — not
something I'd point at the open internet as-is.

## What's next

Possible next steps: switch password hashing to bcrypt with per-user salts (fixing the
limitation above), an HTML directory listing for `/files/`, a basic rate limiter, and
maybe a comparison version using `asyncio` instead of threads to see how the
concurrency model differs under load.
