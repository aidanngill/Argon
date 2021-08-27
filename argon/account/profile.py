class Profile:
    """ Minecraft profile, holding username and UUID. """

    def __init__(self, username: str, uuid: str, selected: bool = False):
        """
        :param username: Profile username.
        :param uuid: Profile UUID.
        :param selected: Whether or not this profile is selected.
        """
        self.username = username
        self.uuid = uuid
        self.selected = selected

    @classmethod
    def from_mojang(cls, data: dict, selected: bool = False):
        return cls(data.get("name"), data.get("id"), selected)

    def to_mojang(self):
        return {"name": self.username, "id": self.uuid}
