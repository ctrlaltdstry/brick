"""Shared geometry quality presets for BrickGen and BrickIt."""

QUALITY_DRAFT = 0
QUALITY_STANDARD = 1
QUALITY_HERO = 2


QUALITY_PRESETS = {
    QUALITY_DRAFT: dict(
        body_corner_segments=4,
        stud_segments=16, stud_fillet_segments=2,
        tube_segments=16, tube_fillet_segments=2,
        rib_segments=2,
    ),
    QUALITY_STANDARD: dict(
        body_corner_segments=8,
        stud_segments=32, stud_fillet_segments=4,
        tube_segments=32, tube_fillet_segments=4,
        rib_segments=4,
    ),
    QUALITY_HERO: dict(
        body_corner_segments=16,
        stud_segments=100, stud_fillet_segments=8,
        tube_segments=100, tube_fillet_segments=8,
        rib_segments=8,
        body_fillet_radius=0.4,
        stud_fillet_radius=0.18,
        tube_fillet_radius=0.18,
        rib_fillet_radius=0.10,
    ),
}

ASSEMBLY_QUALITY_PRESETS = {
    QUALITY_DRAFT: QUALITY_PRESETS[QUALITY_DRAFT],
    QUALITY_STANDARD: QUALITY_PRESETS[QUALITY_STANDARD],
    QUALITY_HERO: QUALITY_PRESETS[QUALITY_HERO],
}

QUALITY_PRESET_NAME_TO_ID = {
    "draft": QUALITY_DRAFT,
    "standard": QUALITY_STANDARD,
    "hero": QUALITY_HERO,
}

QUALITY_PRESETS_BY_NAME = {
    name: QUALITY_PRESETS[preset_id]
    for name, preset_id in QUALITY_PRESET_NAME_TO_ID.items()
}
