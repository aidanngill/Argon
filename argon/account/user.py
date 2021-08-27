from typing import List

from .profile import Profile


class User:
    """ Minecraft user, including session details. """

    def __init__(
        self,
        username: str,
        client_token: str,
        access_token: str,
        selected_profile: Profile,
        available_profiles: List[Profile] = None,
    ):
        self.username = username

        self.client_token = client_token
        self.access_token = access_token

        self.selected_profile = selected_profile
        self.available_profiles = available_profiles

    @classmethod
    def from_mojang(cls, data):
        profile_list = [Profile.from_mojang(p) for p in data["availableProfiles"]]
        profile_selected = Profile.from_mojang(data["selectedProfile"], selected=True)

        for profile in profile_list:
            if profile.uuid == profile_selected.uuid:
                profile.selected = True

        return cls(
            data["user"]["username"],
            data["clientToken"],
            data["accessToken"],
            profile_selected,
            profile_list,
        )

    @property
    def alias(self):
        return self.selected_profile.username

    @property
    def uuid(self):
        return self.selected_profile.uuid

    def to_mojang(self):
        return {
            "user": {"username": self.username},
            "clientToken": self.client_token,
            "accessToken": self.access_token,
            "availableProfiles": [p.to_mojang() for p in self.available_profiles],
            "selectedProfile": self.selected_profile.to_mojang(),
        }
