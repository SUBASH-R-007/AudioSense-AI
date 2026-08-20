"""Mint the AUDIOSENSE_USERS entry for an account.

    python -m scripts.make_user alice

Prompts for the password without echoing it, prints the line to paste into the
deployment's environment, and never writes the plaintext anywhere.

Add more accounts by joining entries with commas:

    AUDIOSENSE_USERS="alice:pbkdf2_sha256$...,bob:pbkdf2_sha256$..."
"""
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.auth import hash_password  # noqa: E402


def main() -> int:
    username = (sys.argv[1] if len(sys.argv) > 1 else input("Username: ")).strip()
    if not username or ":" in username or "," in username:
        print("Username must be non-empty and contain no ':' or ','.")
        return 1

    password = getpass.getpass("Password: ")
    if len(password) < 12:
        # Short passwords are the whole attack. PBKDF2 buys time against an
        # offline attacker who has the hash; it buys nothing against someone
        # guessing "clinic123" online.
        print("Use at least 12 characters.")
        return 1
    if password != getpass.getpass("Repeat: "):
        print("Passwords do not match.")
        return 1

    print()
    print("Add this to the backend environment (append to AUDIOSENSE_USERS,")
    print("comma-separated, to keep existing accounts):")
    print()
    print(f'  {username}:{hash_password(password)}')
    print()
    print("And set a stable signing secret, or sessions will be dropped on")
    print("every restart and will not be shared between replicas:")
    print()
    print(f"  AUDIOSENSE_SECRET={secrets.token_urlsafe(48)}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
