import asyncio
import json
import logging
import os
import platform
import urllib.parse
from typing import List

import aiofiles
import aiohttp

from . import shared, util
from .exceptions import InvalidPath

log = logging.getLogger(__name__)


class Version:
    def __init__(
        self,
        name: str,
        type: str,
        data: dict = None,
        url: str = None,
        release_time: str = None,
    ):
        self.name = name
        self.type = type

        self.release_time = release_time

        # Version information such as arguments, libraries, and downloads.
        # We only download specific data about the version when we need to.
        self.url = url

        self._data = data
        self._has_data = data is not None

        self._inherits = None

    @classmethod
    def from_mojang(cls, data: dict):
        return cls(
            name=data.get("id"),
            type=data.get("type"),
            url=data.get("url"),
            release_time=data.get("releaseTime"),
        )

    @classmethod
    def from_path(cls, version_path: str, version_name: str):
        path = os.path.join(version_path, "versions", version_name)
        file = os.path.join(path, f"{version_name}.json")

        if not os.path.isfile(file):
            raise InvalidPath(
                f"Version '{version_name}' does not exist in '{version_path}'"
            )

        with open(file, "r", encoding="utf-8") as file:
            data = json.load(file)

        return cls(
            name=data.get("id"),
            type=data.get("type"),
            data=data,
            release_time=data.get("releaseTime"),
        )

    @property
    def has_data(self) -> bool:
        return self._has_data

    @property
    def is_release(self) -> bool:
        return self.type == "release"

    @property
    def is_snapshot(self) -> bool:
        return self.type == "snapshot"

    async def fetch_inherited(self):
        if self._inherits is bool:
            if self._inherits is True:
                return self._inherits

            return None

        data = await self.fetch_data()

        if data.get("inheritsFrom", None) is None:
            self._inherits = False
            return None

        versions = await util.list_all_versions()

        for item in versions:
            if data["inheritsFrom"] == item.name:
                self._inherits = item

        # TODO: Also get version information from the folder.
        # TODO: Warning for unfound inherited version.
        return self._inherits

    async def fetch_data(self):
        if self._has_data is True:
            return self._data

        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as resp:
                self._data = await resp.json()
                self._has_data = True

        return self._data

    async def fetch_asset_index(self) -> str:
        inherits = await self.fetch_inherited()

        if inherits is not None:
            return await inherits.fetch_asset_index()

        return (await self.fetch_data())["assetIndex"]

    async def fetch_libraries(self) -> List[dict]:
        data = await self.fetch_data()
        inherits = await self.fetch_inherited()

        libraries = data.get("libraries", [])

        if inherits is not None:
            libraries += await inherits.fetch_libraries()

        return libraries

    async def fetch_jar_url(self) -> str:
        return (await self.fetch_data())["downloads"]["client"]["url"]

    async def fetch_main_class(self) -> str:
        return (await self.fetch_data())["mainClass"]

    async def fetch_java_version(self) -> dict:
        inherits = await self.fetch_inherited()

        if inherits is not None:
            return await inherits.fetch_java_version()

        return (await self.fetch_data())["javaVersion"]

    async def get_java_path(self, base_path: str) -> str:
        return os.path.join(
            base_path,
            "java",
            (await self.fetch_java_version())["component"],
            "bin",
            "java.exe",
        )

    async def download_assets(self, game_path: str) -> None:
        """Download all necessary asset files.

        :param path: Argon base path.
        """
        asset_index = await self.fetch_asset_index()

        index_path = os.path.join(game_path, "assets", "indexes")
        index_file = os.path.join(index_path, "{0}.json".format(asset_index["id"]))

        if not os.path.isdir(index_path):
            os.makedirs(index_path)

        async with aiohttp.ClientSession() as session:
            async with session.get(asset_index["url"]) as resp:
                data = await resp.json()

        async with aiofiles.open(index_file, "wb") as file:
            await file.write(json.dumps(data).encode())

        objects_path = os.path.join(game_path, "assets", "objects")

        if not os.path.isdir(objects_path):
            os.makedirs(objects_path)

        async def _download_object(data):
            full_hash = data["hash"]
            start_hash = full_hash[:2]

            object_path = os.path.join(objects_path, start_hash)
            object_file = os.path.join(object_path, full_hash)

            if util.is_valid_file(object_file, full_hash):
                return

            if not os.path.isdir(object_path):
                os.makedirs(object_path)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://resources.download.minecraft.net/{start_hash}/{full_hash}"
                ) as resp:
                    async with aiofiles.open(object_file, "wb") as file:
                        await file.write(await resp.read())

            log.debug(f"Downloaded an object to {full_hash}")

        task_list = [_download_object(o) for o in data.get("objects", {}).values()]

        for chunk in util.chunks(task_list, 16):
            await asyncio.gather(*chunk)

    async def download_libraries(self, game_path: str) -> None:
        """ Download all of the necessary libraries. """
        libraries_path = os.path.join(game_path, "libraries")

        bits, _ = platform.architecture()
        arch = bits[:2]

        for library in await self.fetch_libraries():
            # [url]     -> Base URL for the repository that holds the libraries.
            # [name]    -> The name of the Java library.
            if "url" in library:
                full_path, full_name = library["name"].split(":", 1)
                lib_path = full_path.split(".") + full_name.split(":")

                lib_path.append(full_name.replace(":", "-", 1) + ".jar")

                async with aiohttp.ClientSession() as session:
                    url = library["url"] + "/".join(
                        [urllib.parse.quote(i) for i in lib_path]
                    )

                    async with session.get(url) as resp:
                        lib_dir = os.path.join(libraries_path, *lib_path[:-1])
                        lib_file = os.path.join(lib_dir, lib_path[-1])

                        if not os.path.isdir(lib_dir):
                            os.makedirs(lib_dir)

                        async with aiofiles.open(lib_file, "wb") as file:
                            await file.write(await resp.read())

                continue

            elif "downloads" in library:
                lib_downloads = library["downloads"]

                if "artifact" in lib_downloads:
                    artifact_data = lib_downloads["artifact"]
                    artifact_file = os.path.join(libraries_path, artifact_data["path"])

                    lib_base = os.path.dirname(artifact_file)

                    if not util.is_valid_file(artifact_file, artifact_data["sha1"]):
                        if not os.path.isdir(lib_base):
                            os.makedirs(lib_base)

                        async with aiohttp.ClientSession() as session:
                            async with session.get(artifact_data["url"]) as resp:
                                async with aiofiles.open(artifact_file, "wb") as file:
                                    await file.write(await resp.read())

                if "natives" in library:
                    key = "natives-{0}".format(shared.SYSTEM_TARGET)
                    key_arch = "{0}-{1}".format(key, arch)

                    if not key in lib_downloads["classifiers"]:
                        if not key_arch in lib_downloads["classifiers"]:
                            continue

                        key = key_arch

                    native = lib_downloads["classifiers"][key]
                    native_file = os.path.join(libraries_path, native["path"])

                    lib_base = os.path.dirname(native_file)

                    if not util.is_valid_file(native_file, native["sha1"]):
                        if not os.path.isdir(lib_base):
                            os.makedirs(lib_base)

                        async with aiohttp.ClientSession() as session:
                            async with session.get(native["url"]) as resp:
                                async with aiofiles.open(native_file, "wb") as file:
                                    await file.write(await resp.read())
