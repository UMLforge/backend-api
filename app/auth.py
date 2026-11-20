"""Admin accounts for the monitoring dashboard. Deliberately minimal: this is NOT a user system.

- Accounts are created only on the server, with the CLI (python -m app.admin create-user NAME).
  There is no sign-up, no password reset by email, and nothing else in the app needs a login.
- Passwords: scrypt (Python stdlib) with a random salt per user.
- Login returns a random session token (sent as "Authorization: Bearer <token>"); only its SHA-256 is
  stored, sessions expire after ADMIN_SESSION_HOURS, and login attempts are rate-limited per IP.
"""
import hashlib
import hmac
import os
import secrets
import time

SESSION_HOURS = float(os.getenv("ADMIN_SESSION_HOURS", "12"))
MIN_PASSWORD = 10
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, **_SCRYPT)
    return hmac.compare_digest(check.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AdminStore:
    def __init__(self, db):
        self.db = db

    # -- users (CLI only) --
    def create_user(self, username: str, password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        if self.db.run("SELECT 1 FROM admin_users WHERE username = ?", (username,))[0]:
            raise ValueError(f"user '{username}' already exists")
        self.db.run("INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, hash_password(password), time.time()))

    def set_password(self, username: str, password: str) -> bool:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        _, count = self.db.run("UPDATE admin_users SET password_hash = ? WHERE username = ?", (hash_password(password), username))
        self.logout_user(username)
        return count > 0

    def delete_user(self, username: str) -> bool:
        self.logout_user(username)
        return self.db.run("DELETE FROM admin_users WHERE username = ?", (username,))[1] > 0

    def list_users(self) -> list[dict]:
        return self.db.run("SELECT username, created_at FROM admin_users ORDER BY username")[0]

    # -- sessions --
    def login(self, username: str, password: str, ip: str) -> dict | None:
        rows, _ = self.db.run("SELECT password_hash FROM admin_users WHERE username = ?", (username,))
        # hash anyway when the user doesn't exist, so timing doesn't reveal valid usernames
        stored = rows[0]["password_hash"] if rows else hash_password(secrets.token_hex(8))
        if not rows or not verify_password(password, stored):
            return None
        now = time.time()
        self.db.run("DELETE FROM admin_sessions WHERE expires_at < ?", (now,))
        token = secrets.token_urlsafe(32)
        expires = now + SESSION_HOURS * 3600
        self.db.run("INSERT INTO admin_sessions (token_hash, username, created_at, expires_at, ip) VALUES (?, ?, ?, ?, ?)",
                    (_token_hash(token), username, now, expires, ip))
        return {"token": token, "username": username, "expires_at": expires}

    def user_for(self, token: str) -> str | None:
        rows, _ = self.db.run("SELECT username, expires_at FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))
        return rows[0]["username"] if rows and rows[0]["expires_at"] > time.time() else None

    def logout(self, token: str) -> None:
        self.db.run("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))

    def logout_user(self, username: str) -> None:
        self.db.run("DELETE FROM admin_sessions WHERE username = ?", (username,))

    def logout_all(self) -> int:
        return self.db.run("DELETE FROM admin_sessions")[1]
