"""Supported native game sizes; UI readers keep their original pixels."""
SUPPORTED_SIZES = ((1920, 1080), (1366, 768))
RESOLUTION_HELP = "Use a 1920 x 1080 or 1366 x 768 game client at native UI scale."


def validate_frame(image):
    if image is None or image.ndim != 3 or image.shape[2] != 3 or (image.shape[1], image.shape[0]) not in SUPPORTED_SIZES:
        raise ValueError(RESOLUTION_HELP)
