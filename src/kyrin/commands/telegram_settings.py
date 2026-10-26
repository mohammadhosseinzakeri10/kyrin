"""Bounded English names for visible Telegram Desktop settings destinations."""

SETTING_SECTIONS: dict[str, str] = {
    "my_account": "My Account",
    "notifications": "Notifications and Sounds",
    "privacy": "Privacy and Security",
    "chat_settings": "Chat Settings",
    "folders": "Folders",
    "advanced": "Advanced",
    "speakers_camera": "Speakers and Camera",
    "battery": "Battery and Animations",
    "language": "Language",
    "default_scale": "Default interface scale",
    "faq": "Telegram FAQ",
    "features": "Telegram Features",
    "ask_question": "Ask a Question",
}

SPOKEN_SECTIONS: dict[str, str] = {
    label.casefold(): key for key, label in SETTING_SECTIONS.items()
}
SPOKEN_SECTIONS.update({
    "notification and sound": "notifications",
    "notifications and sound": "notifications",
    "notification and sounds": "notifications",
    "chat setting": "chat_settings",
    "chat seating": "chat_settings",
    "speaker and camera": "speakers_camera",
    "battery and animation": "battery",
})
