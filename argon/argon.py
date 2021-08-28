import json
import logging
import os
import platform
import shutil
import subprocess
import uuid
from typing import List, Union
from zipfile import ZipFile

import aiofiles
import aiohttp

from . import shared, util
from .account import User
from .exceptions import InvalidPath
from .version import Version

log = logging.getLogger(__name__)


class Argon:
    """ Any data pertaining to the client itself, and its managed folders/files. """

    def __init__(self, path: str = ...):
        """
        :param path: The path at which Argon should reside.
        """

        # Process the directory, and make it if it does not exist.
        self.path = self.default_directory()

        if path is not Ellipsis:
            self.path = path

        if not os.path.isdir(self.path):
            os.makedirs(self.path)

        log.debug(f"Initialized the Argon directory to '{self.path}'.")

        # Any persistent data.
        self._all_versions = None

    @staticmethod
    def default_directory():
        """ Get the default Argon path in the Roaming AppData directory. """
        return os.path.join(os.getenv("APPDATA"), ".argon")

    @property
    def versions_path(self):
        """ Get the version path. If it does not exist, create it. """
        path = os.path.join(self.path, "versions")

        if not os.path.isdir(path):
            os.makedirs(path)

        return path

    def has_version(self, version: str) -> bool:
        """
        Check whether we have a certain version installed.
        TODO: Add version checker for the Version object.

        :param version: The version string identifier.
        """
        path = os.path.join(self.versions_path, version)

        if not os.path.isdir(path):
            return False

        file = os.path.join(path, f"{version}.jar")
        return os.path.isfile(file)

    async def _download_version(
        self, version_name: str, exist_ok: bool = True
    ) -> Version:
        """Download the given version online.

        :param version_name: The name of the version to find and download from Mojang.
        :param exist_ok: Whether or not to panic if the version already exists.
        """
        version_path = os.path.join(self.versions_path, version_name)

        if not exist_ok and os.path.isdir(version_path):
            raise InvalidPath(f"Version path for '{version_name}' already exists")

        os.makedirs(version_path, exist_ok=exist_ok)

        version_data = None

        for version in await util.list_all_versions():
            if version.name == version_name:
                version_data = version
                break

        if version_data is None:
            raise InvalidPath(f"Version '{version_name}' does not exist")

        if not version.has_data:
            await version.fetch_data()

        jar_file = os.path.join(version_path, "{0}.jar".format(version.name))
        json_file = os.path.join(version_path, "{0}.json".format(version.name))

        async with aiohttp.ClientSession() as session:
            async with session.get(await version_data.fetch_jar_url()) as resp:
                async with aiofiles.open(jar_file, "wb") as file:
                    await file.write(await resp.read())

        async with aiofiles.open(json_file, "wb") as file:
            await file.write(json.dumps(await version_data.fetch_data()).encode())

        return version

    async def get_version(
        self, version_name: str, is_local: bool = True
    ) -> Union[Version, None]:
        """Get the specified version.

        :param version_name: The name of the version to locate or download.
        :param is_local: Whether or not the version should be downloaded if it is not found locally.
        """

        if not isinstance(version_name, str):
            return None

        # Try to find the version locally initially.
        version_path = os.path.join(self.versions_path, version_name)

        try:
            version = Version.from_path(self.path, version_name)
        except InvalidPath:
            version = await self._download_version(version_name)

        await version.download_assets(self.path)
        await version.download_libraries(self.path)

        return version

    def load_users(self, file_name: str = "users.json") -> List[User]:
        file_path = os.path.join(self.path, file_name)

        if not os.path.isfile(file_path):
            return []

        with open(file_path, "r", encoding="utf-8") as file:
            cont = file.read()

        try:
            data = json.loads(cont)
            assert isinstance(data, list)

            return [User.from_mojang(a) for a in data]
        except Exception:
            return []

    def save_users(self, users: List[User], file_name: str = "users.json") -> None:
        """ Save all given to the file. """
        file_path = os.path.join(self.path, file_name)
        data = [u.to_mojang() for u in users]

        with open(file_path, "w+", encoding="utf-8") as file:
            json.dump(data, file)

        log.debug(f"Dumped {len(users)} users to '{file_name}'.")

    async def login(self, username: str, password: str) -> User:
        """Log in to the given account.

        :param username: The account username or email. Unmigrated accounts
                         will use a username, and vice versa for unmigrated
                         accounts.
        :param password: The account's password.
        """
        data = {
            "agent": {"name": "Minecraft", "version": 1},
            "username": username,
            "password": password,
            "requestUser": True,
        }

        headers = {"Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            url = "https://authserver.mojang.com/authenticate"

            async with session.post(url, json=data, headers=headers) as resp:
                data = await resp.json()

                if not resp.ok:
                    log.error(
                        f"Failed to log in as {username} (code {resp.status_code})."
                    )
                    return None

        log.info(f"Logged in as {username} successfully.")
        return User.from_mojang(data)

    async def has_java_version(self, version: Version) -> bool:
        """ Check if we have the required Java version. """
        java_version = await version.fetch_java_version()

        java_path = os.path.join(self.path, "java", java_version["component"])
        java_file = os.path.join(java_path, "bin", "java.exe")

        return os.path.isdir(java_path) and os.path.isfile(java_file)

    async def download_java(self, version: Version) -> None:
        """ Download the correct version of Java. """
        system = platform.system()
        target = shared.SYSTEM_DEFINITIONS[system]

        bits, _ = platform.architecture()
        arch = bits[:2]

        java_version = await version.fetch_java_version()

        path = [
            "v3",
            "binary",
            "latest",
            str(java_version["majorVersion"]),
            "ga",
            target,
            "x64" if arch == "64" else "x86",
            "jdk",
            "hotspot",
            "normal",
            "adoptopenjdk",
        ]

        java_path = os.path.join(self.path, "java", java_version["component"])
        java_file = os.path.join(java_path, "java.zip")

        if not os.path.isdir(java_path):
            os.makedirs(java_path)

        async with aiohttp.ClientSession() as session:
            url = f"https://api.adoptopenjdk.net/{'/'.join(path)}"

            async with session.get(url) as resp:
                async with aiofiles.open(java_file, "wb") as file:
                    await file.write(await resp.read())

        with ZipFile(java_file, "r") as file:
            java_folder = file.namelist()[0].rstrip("/")
            file.extractall(java_path)

        for file in os.listdir(os.path.join(java_path, java_folder)):
            shutil.move(
                os.path.join(java_path, java_folder, file),
                os.path.join(java_path, file),
            )

        os.rmdir(os.path.join(java_path, java_folder))
        os.remove(java_file)

    async def play(self, version: Version, user: User) -> None:
        """
        Start the game on the specified version logged in as the specified user.

        :param version: Version to play.
        :param user: User to log in as.
        """

        if not await self.has_java_version(version):
            await self.download_java(version)

        # Generate the class path string.
        version_data = await version.fetch_data()
        inherit_data = await version.fetch_inherited()

        class_path = util.get_class_path(version_data, self.path)

        if inherit_data is not None:
            if not self.has_version(inherit_data.name):
                self.get_version(inherit_data.name)

            # Make sure to copy the inherited version's JAR to the current JAR.
            # TODO: Modded JARs (e.g., Fabric) will be empty, and then copied
            # from the inherited version. Is this the case for all?
            original_file = os.path.join(
                self.versions_path, version.name, f"{version.name}.jar"
            )

            if os.path.getsize(original_file) == 0:
                inherited_path = os.path.join(self.versions_path, inherit_data.name)
                inherited_file = os.path.join(
                    inherited_path, f"{inherit_data.name}.jar"
                )

                shutil.copy(inherited_file, original_file)

            class_path += util.get_class_path(
                await inherit_data.fetch_data(), self.path
            )

        # Extract DLLs to a temporary location.
        bin_path = os.path.join(self.path, "bin", str(uuid.uuid4()))

        if not os.path.isdir(bin_path):
            os.makedirs(bin_path)

        await version.extract_native_libraries(self.path, bin_path)

        kwargs = {
            "natives_directory": bin_path,
            "launcher_name": "argon",
            "launcher_version": "0.1.0",
            "auth_player_name": user.alias,
            "version_name": version.name,
            "game_directory": self.path,
            "assets_root": os.path.join(self.path, "assets"),
            "assets_index_name": (await version.fetch_asset_index())["id"],
            "auth_uuid": user.uuid,
            "auth_access_token": user.access_token,
            "user_type": "mojang",
            "version_type": version.type,
            "classpath": os.pathsep.join(class_path),
        }

        # Adjust Kwargs for older versions.
        kwargs.update(
            {
                "game_assets": kwargs["assets_root"],
                "auth_session": f"token:{user.access_token}:{user.uuid}",
                "user_properties": "{}",
            }
        )

        runtime = os.path.join(self.path, "runtime")

        if not os.path.isdir(runtime):
            os.makedirs(runtime)

        os.chdir(runtime)

        java_arguments = await version.fetch_jvm_arguments()
        game_arguments = await version.fetch_game_arguments()

        args = [
            await version.get_java_path(self.path),
            *util.create_arguments(java_arguments, **kwargs),
            await version.fetch_main_class(),
            *util.create_arguments(game_arguments, **kwargs),
        ]

        subprocess.call(args)

        # Clean up after ourselves.
        shutil.rmtree(bin_path)
        log.debug("Cleaned up the binary directory.")
