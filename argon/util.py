import hashlib
import os
import platform
import re
from typing import Union

import aiohttp

from . import shared
from .version import Version
from .exceptions import UnsupportedSystem


async def list_all_versions():
    """ List all available versions from Mojang. """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        ) as resp:
            data = await resp.json()

    return [Version.from_mojang(v) for v in data["versions"]]


def get_natives_string(library: str) -> Union[str, None]:
    bits, _ = platform.architecture()
    arch = bits[:2]

    if not arch in {"64", "32"}:
        raise UnsupportedSystem("Unsupported architecture")

    if not "natives" in library:
        return None

    return library["natives"][shared.SYSTEM_TARGET].replace("${arch}", arch)


def should_use_rule(rule: dict):
    # TODO: Add features implementation.
    if "features" in rule:
        return False

    allow = rule["action"] == "allow"

    if not "os" in rule:
        return allow

    bits, _ = platform.architecture()
    arch = bits[:2]

    for k, v in rule["os"].items():
        if k == "name":
            if v == shared.SYSTEM_TARGET:
                return allow
        elif k == "arch":
            if v == "x86" and arch == "32":
                return allow
            elif v == "x64" and arch == "64":
                return allow

    return not allow


def should_use_library(library: dict) -> bool:
    if not "rules" in library:
        return True

    return any([should_use_rule(r) for r in library["rules"]])


def get_class_path(library: dict, minecraft: str) -> list:
    class_path = []

    for current in library.get("libraries", []):
        if not should_use_library(current):
            continue

        domain, name, version = current["name"].split(":")
        path = os.path.join(minecraft, "libraries", *domain.split("."), name, version)

        native = get_natives_string(current)
        file = f"{name}-{version}.jar"

        if native is not None:
            file = f"{name}-{version}-{native}.jar"

        class_path.append(os.path.join(path, file))

    class_path.append(
        os.path.join(minecraft, "versions", library["id"], f"{library['id']}.jar")
    )

    return class_path


def create_arguments(data: dict, **options):
    if isinstance(data, str):
        value = re.sub(r"\$({[a-zA-Z_]+})", "\g<1>", data)
        value = value.format(**options)

        return [value]

    arguments = []

    for item in data:
        if isinstance(item, str):
            value = re.sub(r"\$({[a-zA-Z_]+})", "\g<1>", item)
            value = value.format(**options)

            arguments.append(value)
        elif isinstance(item, dict):
            if not should_use_library(item):
                continue

            arguments += create_arguments(item["value"], **options)

    return arguments


def sha1_check_file(file_name: str, sha1_hash: str) -> bool:
    sha1 = hashlib.sha1()

    with open(file_name, "rb") as file:
        while True:
            data = file.read(shared.SHA1_BUFFER_SIZE)

            if not data:
                break

            sha1.update(data)

    return sha1.hexdigest() == sha1_hash


def is_valid_file(file: str, sha1: str):
    return os.path.isfile(file) and sha1_check_file(file, sha1)


# https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
