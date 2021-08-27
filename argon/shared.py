""" Any values that are shared or constant. """

import platform

# Convert from `platform.system()`'s definitions to standard names.
SYSTEM_DEFINITIONS = {"Windows": "windows", "Darwin": "osx", "Linux": "linux"}

# How many bytes to iterate through a file at once for SHA1 checks (64kb).
SHA1_BUFFER_SIZE = 64 * 1024

SYSTEM_NAME = platform.system()
SYSTEM_TARGET = SYSTEM_DEFINITIONS.get(SYSTEM_NAME, None)
