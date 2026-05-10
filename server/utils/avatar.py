AVATAR_COLORS = [
    ("oklch(0.22 0.08 150)", "oklch(0.92 0.16 145)"),
    ("oklch(0.24 0.09 260)", "oklch(0.88 0.12 255)"),
    ("oklch(0.25 0.1 25)", "oklch(0.88 0.13 35)"),
    ("oklch(0.24 0.08 310)", "oklch(0.9 0.13 315)"),
    ("oklch(0.25 0.08 85)", "oklch(0.9 0.14 95)"),
    ("oklch(0.23 0.08 205)", "oklch(0.9 0.11 205)"),
]


def avatar_colors(seed: str) -> tuple[str, str]:
    value = 0
    for char in seed:
        value = (value * 31 + ord(char)) & 0xFFFFFFFF
    return AVATAR_COLORS[value % len(AVATAR_COLORS)]

