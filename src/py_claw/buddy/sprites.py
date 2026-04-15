"""ASCII sprite rendering for companions.

Provides sprite and face rendering for different companion
species with animation support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.buddy.types import Companion, CompanionBones

# Sprite frames for idle animation
IDLE_FRAMES = 4


@dataclass
class SpriteConfig:
    """Configuration for sprite rendering."""

    width: int = 20
    height: int = 10
    use_color: bool = True
    show_bubble: bool = False
    bubble_text: str | None = None


# Species sprite definitions
# Each sprite is a list of strings representing frames
SPECIES_SPRITES: dict[str, list[list[str]]] = {
    "duck": [
        # Frame 0 - Standing
        [
            "      ____       ",
            "     /    \\      ",
            "    | o  o |     ",
            "    |  <>  |     ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    /      \\     ",
            "   ^        ^    ",
            "                   ",
        ],
        # Frame 1 - Slight bounce
        [
            "      ____       ",
            "     /    \\      ",
            "    | o  o |     ",
            "    |  <>  |     ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    /      \\     ",
            "   ^        ^    ",
            "                   ",
        ],
        # Frame 2 - Higher bounce
        [
            "                   ",
            "      ____       ",
            "     /    \\      ",
            "    | o  o |     ",
            "    |  <>  |     ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    ^        ^    ",
            "                   ",
        ],
        # Frame 3 - Landing
        [
            "      ____       ",
            "     /    \\      ",
            "    | o  o |     ",
            "    |  <>  |     ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    /      \\     ",
            "   ^        ^    ",
            "                   ",
        ],
    ],
    "cat": [
        # Frame 0 - Sitting
        [
            "    /\\_____/\\    ",
            "   /  o   o  \\   ",
            "  (    ---    )  ",
            "   \\  \\___/  /   ",
            "    \\_______/    ",
            "       ||       ",
            "      /  \\      ",
            "     /    \\     ",
            "    /      \\    ",
            "                   ",
        ],
        # Frame 1 - Tail up
        [
            "    /\\_____/\\    ",
            "   /  o   o  \\   ",
            "  (    ---    )  ",
            "   \\  \\___/  /   ",
            "    \\_______/    ",
            "       ||       ",
            "      /  \\      ",
            "     /    \\     ",
            "    ^      ^    ",
            "                   ",
        ],
        # Frame 2 - Stretch
        [
            "                   ",
            "    /\\_____/\\    ",
            "   /  o   o  \\   ",
            "  (    ---    )  ",
            "   \\  \\___/  /   ",
            "    \\_______/    ",
            "       ||       ",
            "      /  \\      ",
            "     /    \\     ",
            "                   ",
        ],
        # Frame 3 - curl
        [
            "    /\\_____/\\    ",
            "   /  o   o  \\   ",
            "  (    ---    )  ",
            "   \\  \\___/  /   ",
            "    \\_______/    ",
            "      /  \\      ",
            "     /    \\     ",
            "    /      \\    ",
            "   ^        ^   ",
            "                   ",
        ],
    ],
    "dog": [
        [
            "      ____       ",
            "     /    \\      ",
            "    |  oo  |     ",
            "    |  \\/   |    ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    /      \\     ",
            "   ^        ^    ",
            "                   ",
        ],
        [
            "      ____       ",
            "     /    \\      ",
            "    |  oo  |     ",
            "    |  \\/   |    ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    ^      ^    ",
            "                   ",
            "                   ",
        ],
        [
            "                   ",
            "      ____       ",
            "     /    \\      ",
            "    |  oo  |     ",
            "    |  \\/   |    ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    ^        ^   ",
            "                   ",
        ],
        [
            "      ____       ",
            "     /    \\      ",
            "    |  oo  |     ",
            "    |  \\/   |    ",
            "     \\____/      ",
            "      /  \\       ",
            "     /    \\      ",
            "    ^      ^    ",
            "                   ",
            "                   ",
        ],
    ],
    "fox": [
        [
            "     /\\____/\\    ",
            "    /  o  o  \\   ",
            "   (    <>    )  ",
            "    \\  ____  /   ",
            "     \\/    \\/    ",
            "       ||       ",
            "      /  \\      ",
            "     /    \\     ",
            "    ^      ^   ",
            "                   ",
        ],
        [
            "     /\\____/\\    ",
            "    /  o  o  \\   ",
            "   (    <>    )  ",
            "    \\  ____  /   ",
            "     \\/    \\/    ",
            "       ||       ",
            "      /  \\      ",
            "     ^    ^    ",
            "                   ",
            "                   ",
        ],
        [
            "                   ",
            "     /\\____/\\    ",
            "    /  o  o  \\   ",
            "   (    <>    )  ",
            "    \\  ____  /   ",
            "     \\/    \\/    ",
            "       ||       ",
            "      /  \\      ",
            "     ^      ^   ",
            "                   ",
        ],
        [
            "     /\\____/\\    ",
            "    /  o  o  \\   ",
            "   (    <>    )  ",
            "    \\  ____  /   ",
            "     \\/    \\/    ",
            "      /  \\      ",
            "     /    \\     ",
            "     ^    ^    ",
            "                   ",
            "                   ",
        ],
    ],
    "owl": [
        [
            "    ,_,  ,_,     ",
            "   (o.o) (o.o)   ",
            "    (___) (___)   ",
            "     /|   |\\     ",
            "    / |   | \\    ",
            "   /__|   |__\\   ",
            "       ||       ",
            "      /  \\      ",
            "     /    \\     ",
            "                   ",
        ],
        [
            "    ,_,  ,_,     ",
            "   (o.o) (o.o)   ",
            "    (___) (___)   ",
            "     /|   |\\     ",
            "    / |   | \\    ",
            "   /__|   |__\\   ",
            "       ||       ",
            "      /  \\      ",
            "     ^    ^    ",
            "                   ",
        ],
        [
            "                   ",
            "    ,_,  ,_,     ",
            "   (o.o) (o.o)   ",
            "    (___) (___)   ",
            "     /|   |\\     ",
            "    / |   | \\    ",
            "   /__|   |__\\   ",
            "       ||       ",
            "      /  \\      ",
            "                   ",
        ],
        [
            "    ,_,  ,_,     ",
            "   (o.o) (o.o)   ",
            "    (___) (___)   ",
            "     /|   |\\     ",
            "    / |   | \\    ",
            "   /__|   |__\\   ",
            "      /  \\      ",
            "     /    \\     ",
            "     ^    ^    ",
            "                   ",
        ],
    ],
    "bunny": [
        [
            "    (\\ _ /)    ",
            "   ( o.o )     ",
            "    ( > < )     ",
            "     /|\\      ",
            "    / | \\     ",
            "     / \\      ",
            "    /   \\     ",
            "   ^     ^    ",
            "               ",
            "               ",
        ],
        [
            "    (\\ _ /)    ",
            "   ( o.o )     ",
            "    ( > < )     ",
            "     /|\\      ",
            "    / | \\     ",
            "     / \\      ",
            "    ^   ^    ",
            "               ",
            "               ",
            "               ",
        ],
        [
            "               ",
            "    (\\ _ /)    ",
            "   ( o.o )     ",
            "    ( > < )     ",
            "     /|\\      ",
            "    / | \\     ",
            "     / \\      ",
            "    /   \\     ",
            "   ^     ^   ",
            "               ",
        ],
        [
            "    (\\ _ /)    ",
            "   ( o.o )     ",
            "    ( > < )     ",
            "     /|\\      ",
            "    / | \\     ",
            "      / \\      ",
            "     ^   ^    ",
            "               ",
            "               ",
            "               ",
        ],
    ],
}


# Face-only sprites for compact display
FACE_SPRITES: dict[str, dict[str, list[str]]] = {
    "duck": {
        "happy": ["><>    <>v"],
        "sleepy": ["-o    o- "],
        "excited": ["*o    o*"],
        "curious": [">?    ?<"],
        "cool": ["-o    oD"],
    },
    "cat": {
        "happy": ["^o    o^"],
        "sleepy": ["-o    o-"],
        "excited": ["*o    o*"],
        "curious": [">?    ?<"],
        "cool": ["-o    o3"],
    },
    "dog": {
        "happy": [">o    o<"],
        "sleepy": ["-o    o-"],
        "excited": ["*o    o*"],
        "curious": [">?    ?<"],
        "cool": [">o    oD"],
    },
    "fox": {
        "happy": [">^    ^<"],
        "sleepy": ["-o    o-"],
        "excited": ["*^   ^*"],
        "curious": [">?    ?<"],
        "cool": [">^    ^3"],
    },
    "owl": {
        "happy": ["^o    o^"],
        "sleepy": [".o    o."],
        "excited": ["*o    o*"],
        "curious": [">o    o<"],
        "cool": ["^o    o3"],
    },
    "bunny": {
        "happy": [">o    o<"],
        "sleepy": ["-o    o-"],
        "excited": ["*o    o*"],
        "curious": [">?    ?<"],
        "cool": [">o    o3"],
    },
}


def sprite_frame_count(species: str) -> int:
    """Get the number of animation frames for a species.

    Args:
        species: Species name

    Returns:
        Number of frames
    """
    return len(SPECIES_SPRITES.get(species, [[]]))


def render_sprite(
    bones: CompanionBones,
    frame: int = 0,
    config: SpriteConfig | None = None,
) -> str:
    """Render a companion sprite as ASCII art.

    Args:
        bones: Companion appearance data
        frame: Animation frame index
        config: Rendering configuration

    Returns:
        ASCII sprite string
    """
    if config is None:
        config = SpriteConfig()

    frames = SPECIES_SPRITES.get(bones.species)
    if not frames:
        return f"[Unknown species: {bones.species}]"

    frame_index = frame % len(frames)
    sprite_lines = frames[frame_index]

    # Build colored sprite
    result_lines = []
    for line in sprite_lines:
        if config.use_color:
            # Apply species-appropriate color
            color = get_species_color(bones.species)
            result_lines.append(f"{color}{line}\033[0m")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def render_face(
    bones: CompanionBones,
    config: SpriteConfig | None = None,
) -> str:
    """Render a compact face representation.

    Args:
        bones: Companion appearance data
        config: Rendering configuration

    Returns:
        ASCII face string
    """
    if config is None:
        config = SpriteConfig()

    species_faces = FACE_SPRITES.get(bones.species)
    if not species_faces:
        return f"[{bones.species[0].upper()}]"

    face = species_faces.get(bones.eyes, species_faces.get("happy", ["?" * 8]))

    if config.use_color:
        color = get_species_color(bones.species)
        return f"{color}{face[0]}\033[0m"

    return face[0]


def get_species_color(species: str) -> str:
    """Get the ANSI color code for a species.

    Args:
        species: Species name

    Returns:
        ANSI color escape sequence
    """
    colors = {
        "duck": "\033[33m",     # Yellow
        "cat": "\033[35m",     # Magenta
        "dog": "\033[33m",     # Brown/Yellow
        "fox": "\033[31m",     # Red/Orange
        "owl": "\033[35m",     # Magenta
        "bunny": "\033[37m",   # White/Grey
    }
    return colors.get(species, "\033[37m")


def render_bubble(text: str, style: str = "speech") -> str:
    """Render a speech/thought bubble.

    Args:
        text: Text to put in bubble
        style: 'speech' or 'thought'

    Returns:
        Bubble string
    """
    if style == "thought":
        lines = [
            "     .--.     ",
            "    ( oo )    ",
            "    (  ..)    ",
            f"     `--' {text}",
        ]
    else:
        lines = [
            f"  ,--.  ",
            f" {text}  )",
            f"  `--'  ",
        ]

    return "\n".join(lines)
