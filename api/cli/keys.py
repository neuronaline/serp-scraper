#!/usr/bin/env python3
"""CLI tool for generating API keys.

Usage:
    python -m api.cli.keys generate

Output:
    Displays the plain API key (only shown once) and the hashed key
    to be added to the .env file.
"""

import secrets
import sys
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (plain_key, hashed_key)
        The plain_key should be shown to the user once and never stored.
        The hashed_key should be added to the .env file.
    """
    # Generate a URL-safe random string
    plain_key = secrets.token_urlsafe(32)  # 43 characters
    hashed_key = pwd_context.hash(plain_key)
    return plain_key, hashed_key


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify a plain key against a hashed key.

    Args:
        plain_key: The plain API key
        hashed_key: The hashed API key

    Returns:
        True if the key matches, False otherwise
    """
    return pwd_context.verify(plain_key, hashed_key)


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2 or sys.argv[1] != "generate":
        print("Usage: python -m api.cli.keys generate")
        print("\nGenerates a new API key pair.")
        print("Add the hashed key to your .env file as API_KEYS_HASHED")
        return 1

    plain_key, hashed_key = generate_api_key()

    print("=" * 60)
    print("NEW API KEY GENERATED")
    print("=" * 60)
    print()
    print("PLAIN KEY (save this, it will not be shown again):")
    print(f"  {plain_key}")
    print()
    print("HASHED KEY (add this to your .env file):")
    print(f"  {hashed_key}")
    print()
    print("=" * 60)
    print("Add to .env:")
    print(f'  API_KEYS_HASHED="{hashed_key}"')
    print("=" * 60)
    print()
    print("IMPORTANT: Store the plain key securely.")
    print("You will need it to access the API.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
