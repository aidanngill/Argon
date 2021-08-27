import argparse
import asyncio
import logging
import sys

from .argon import Argon

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

loop = asyncio.get_event_loop()


async def main():
    parser = argparse.ArgumentParser(description="Minecraft client written in Python.")

    parser.add_argument(
        "-v", "--version", type=str, default=None, help="Version of Minecraft to play."
    )
    parser.add_argument(
        "-u",
        "--username",
        type=str,
        default=None,
        help="Username of the account to use.",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Password of the account to use.",
    )

    # One off functions.
    parser.add_argument(
        "--list-accounts",
        action="store_true",
        default=False,
        help="List all of the available accounts.",
    )

    opts = parser.parse_args()

    client = Argon()

    user = None
    users = client.load_users()

    if opts.list_accounts is True:
        log.info(f"There are {len(users)} available accounts.")

        for user in users:
            log.info(f"User: {user.alias} ({user.uuid})")

        sys.exit(0)

    # Try to get an existing user if no password is available.
    if opts.username:
        if not opts.password:
            for item in users:
                if item.alias.lower() == opts.username.lower():
                    user = item
                    break
        else:
            user = client.login(opts.username, opts.password)

    if user is None:
        log.fatal("Invalid account credentials were provided.")
        sys.exit(1)

    # Save new accounts.
    # TODO: Add validation to make sure the account doesn't already exist.
    if opts.password:
        client.save_users(users + [user])

    version = await client.get_version(opts.version)

    if version is None:
        log.fatal("An invalid version was given.")
        sys.exit(1)

    users = client.load_users()
    await client.play(version, users[0])


if __name__ == "__main__":
    loop.run_until_complete(main())
