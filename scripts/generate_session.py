"""Generate a Telethon StringSession for Telegram channel monitoring.

Run this script ONCE on your own computer, not on Render:
  python scripts/generate_session.py

It requires a phone number, the login code Telegram sends you, and 2FA if
enabled. Copy the printed session string into Render as TG_SESSION_STRING.
The string is equivalent to a login credential: never publish or log it.
"""
import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = os.environ.get("TG_API_ID") or input("TG_API_ID: ").strip()
    api_hash = os.environ.get("TG_API_HASH") or input("TG_API_HASH: ").strip()
    if not api_id or not api_hash:
        raise SystemExit("TG_API_ID and TG_API_HASH are required")

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.start()
        print("\nTG_SESSION_STRING (store it only as a secret):")
        print(client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
