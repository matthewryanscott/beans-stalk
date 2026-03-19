import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

CONFIG_FILENAME = "beans-stalk.toml"

DEFAULT_PALETTE = [
    "#e06c75",
    "#61afef",
    "#98c379",
    "#e5c07b",
    "#c678dd",
    "#56b6c2",
    "#d19a66",
    "#be5046",
    "#528bff",
    "#7ec699",
    "#f0c674",
    "#a9a1e1",
]

UNASSIGNED_COLOR = "#888888"


@dataclass
class StalkConfig:
    fade_minutes: int = 5
    poll_interval_seconds: int = 2
    colors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, beans_dir: Path) -> "StalkConfig":
        toml_path = beans_dir / CONFIG_FILENAME
        if not toml_path.exists():
            return cls()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            fade_minutes=data.get("fade_minutes", 5),
            poll_interval_seconds=data.get("poll_interval_seconds", 2),
            colors=dict(data.get("colors", {})),
        )

    def save(self, beans_dir: Path) -> None:
        toml_path = beans_dir / CONFIG_FILENAME
        data = {
            "fade_minutes": self.fade_minutes,
            "poll_interval_seconds": self.poll_interval_seconds,
            "colors": self.colors,
        }
        with open(toml_path, "wb") as f:
            tomli_w.dump(data, f)

    def get_color(self, assignee: str | None) -> str:
        if assignee is None:
            return UNASSIGNED_COLOR
        if assignee in self.colors:
            return self.colors[assignee]
        used = set(self.colors.values())
        for color in DEFAULT_PALETTE:
            if color not in used:
                self.colors[assignee] = color
                return color
        h = hashlib.sha256(assignee.encode()).hexdigest()[:6]
        color = f"#{h}"
        self.colors[assignee] = color
        return color
