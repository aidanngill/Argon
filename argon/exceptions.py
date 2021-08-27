class ArgonError(Exception):
    """ Base Argon error. """

    pass


class UnsupportedSystem(ArgonError):
    """ Libraries aren't supported on your platform. """


class InvalidPath(ArgonError):
    """ Provided path was invalid. """

    pass


class InvalidVersion(ArgonError):
    """ Provided version was invalid. """

    pass
