"""
CivicLens - create (or change) the admin login.

Run this once on the machine where the backend runs:

    python setup_admin.py

It asks for a username and a password, stores only a salted HASH of the
password (never the password itself) in backend/.env, and creates the
secret key that signs login sessions. Other lines in .env (for example
DASHSCOPE_API_KEY) are left untouched.

Run it again any time to change the password. Changing the secret key
(answer "y" when asked) logs every admin out.
"""

import getpass
import os
import re
import secrets
import sys

from werkzeug.security import generate_password_hash

ENV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".env"
)

MIN_PASSWORD_LENGTH = 10


def read_env_lines():

    if not os.path.exists(ENV_PATH):
        return []

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def get_env_value(lines, key):

    for line in lines:
        match = re.match(rf"^\s*{key}\s*=\s*(.*)$", line)
        if match:
            return match.group(1).strip().strip("'\"")

    return None


def set_env_value(lines, key, value):
    """Replace the KEY=... line, or add it at the end."""

    new_line = f"{key}='{value}'"

    for i, line in enumerate(lines):
        if re.match(rf"^\s*{key}\s*=", line):
            lines[i] = new_line
            return

    lines.append(new_line)


def ask_username(current):

    default = current or "admin"

    while True:

        username = input(f"Admin username [{default}]: ").strip() or default

        if re.fullmatch(r"[A-Za-z0-9_.@-]{3,40}", username):
            return username

        print("Use 3-40 letters, numbers or . _ @ - (no spaces or quotes).")


def ask_password():

    while True:

        password = getpass.getpass(
            f"New password (at least {MIN_PASSWORD_LENGTH} characters): "
        )

        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Too short - use at least {MIN_PASSWORD_LENGTH} characters.")
            continue

        if getpass.getpass("Repeat password: ") != password:
            print("Passwords do not match. Try again.")
            continue

        return password


def main():

    lines = read_env_lines()

    username = ask_username(get_env_value(lines, "ADMIN_USERNAME"))

    password = ask_password()

    password_hash = generate_password_hash(
        password,
        method="pbkdf2:sha256:600000"
    )

    set_env_value(lines, "ADMIN_USERNAME", username)

    set_env_value(lines, "ADMIN_PASSWORD_HASH", password_hash)

    existing_secret = get_env_value(lines, "ADMIN_SECRET_KEY")

    if existing_secret:

        rotate = input(
            "Create a NEW session secret (logs everyone out)? [y/N]: "
        ).strip().lower()

        if rotate == "y":
            set_env_value(lines, "ADMIN_SECRET_KEY", secrets.token_hex(32))

    else:
        set_env_value(lines, "ADMIN_SECRET_KEY", secrets.token_hex(32))

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass

    print()
    print(f"Done. Admin login saved for user '{username}' in {ENV_PATH}")
    print("Restart / reload the backend so it picks up the change.")


if __name__ == "__main__":

    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
