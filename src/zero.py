"""Zero's Lazuli and Lapis: one enhanced weapon worn in the weapon and secondary slots."""

MIRROR_NOTE = "Mirrors Zero's weapon: both swords share every enhancement, so this is priced with the weapon."
# The partner sword grants its Boss/Damage (base and flame) and the shared potential.
# Its ATT, stats and Star Force do not apply.
SHARED_FLAME_STATS = ("Boss Damage", "Damage")


def mirrored(character_class, slot):
    """The secondary-slot sword repeats the weapon's stars, flames and potential."""
    return character_class == "Zero" and slot == "secondary"


def copies(character_class, slot):
    """How many times the weapon's potential and flame Boss/Damage apply.

    An equipped Astra Hourglass would replace the partner's share, but its slot is
    not scanned yet, so both swords are assumed to apply."""
    return 2 if character_class == "Zero" and slot == "weapon" else 1
