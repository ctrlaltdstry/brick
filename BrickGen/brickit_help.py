"""In-app parameter help for the Brick (BrickGen) and BrickIt plugins.

Cinema 4D's Attribute Manager exposes "Show Help" on every parameter via
right-click. In Cinema 4D 2026 the C++ contract is:

    typedef Bool (*PluginHelpDelegate)(opType, baseType, group, property);
    Bool RegisterPluginHelpDelegate(Int32 pluginId, PluginHelpDelegate delegate);

The delegate **returns Bool** (true = "I displayed help, don't fall back to
C4D's default browser") and is expected to *open its own help UI*. Returning
a string from the delegate crashes C4D — it interprets the truthy return as
"I handled it" then tries to open its own help browser with no entry. So we
pop a `MessageDialog` ourselves and return True/False based on whether the
queried symbol has an entry.

Each registry below is a `{resource_symbol: text}` mapping. Keep entries
concise and mirror the wording in `USER_MANUAL.md`. The dialog is plain
text (`MessageDialog` doesn't render HTML), so use blank lines and bullet
prefixes rather than tags.
"""

import c4d
from c4d import plugins

from c4d_symbols import (
    ID_BRICKGENERATOR,
    ID_BRICKIFYASSEMBLY,
)


# Brick (single-brick generator) parameters.
BRICK_HELP = {
    "BRICKGENERATOR_TYPE": (
        "Type\n\n"
        "Choose Brick for a full-height brick (3 plates) or Plate for a "
        "1-plate-tall variant. The Height parameter still scales the "
        "result vertically in either case."
    ),
    "BRICKGENERATOR_WIDTH": (
        "Width\n\n"
        "Number of studs along the X axis (1-8)."
    ),
    "BRICKGENERATOR_DEPTH": (
        "Depth\n\n"
        "Number of studs along the Z axis (1-8)."
    ),
    "BRICKGENERATOR_HEIGHT": (
        "Height\n\n"
        "Brick height in plates (1-8). One plate is 3.2 mm; three plates "
        "make a full brick."
    ),
    "BRICKGENERATOR_QUALITY": (
        "Quality\n\n"
        "Geometry density preset:\n\n"
        "  Draft - about 1k tris. Fastest, no edge fillets.\n"
        "  Standard - about 5k tris. Good for layout and distant shots.\n"
        "  Hero - about 50k verts on a 2x3 with full edge fillets, dense "
        "studs and tubes. Use for hero renders."
    ),

    "BRICKGENERATOR_ENABLE_LOGO": (
        "Use Custom Stud Logo\n\n"
        "Replace each stud's flat top with an embossed custom logo "
        "derived from the linked source mesh."
    ),
    "BRICKGENERATOR_LOGO_SOURCE": (
        "Logo Source Mesh\n\n"
        "Polygon object whose silhouette is projected onto every stud "
        "top. Any polygon shape works - text made editable, an "
        "SVG-extruded logo, a small icon mesh, etc."
    ),
    "BRICKGENERATOR_LOGO_ROTATION": (
        "Logo Rotation\n\n"
        "Rotate the logo by 0, 90, 180, or 270 degrees around the stud's "
        "vertical axis."
    ),
    "BRICKGENERATOR_LOGO_DIAMETER": (
        "Logo Fill %\n\n"
        "Fraction of the stud top the logo occupies. 100% fills the "
        "entire stud disk; smaller values leave a margin around the logo."
    ),
    "BRICKGENERATOR_LOGO_HEIGHT": (
        "Logo Height\n\n"
        "Embossed depth above the stud surface. Negative values combined "
        "with Logo Sink recess the logo into the stud."
    ),
    "BRICKGENERATOR_LOGO_BLEND": (
        "Logo Blend\n\n"
        "How softly the logo edges fade into the surrounding stud "
        "surface. 0 = hard edges. Higher values give a smoother, more "
        "printed look."
    ),
    "BRICKGENERATOR_LOGO_SINK": (
        "Logo Sink\n\n"
        "Recess the logo below the stud surface (carved-in look) instead "
        "of raising it. Combine with a small Logo Height for a subtle "
        "engraved effect."
    ),
}


# BrickIt (assembly) parameters.
BRICKIT_HELP = {
    "BRICKIFYASSEMBLY_SOURCE": (
        "Source Mesh\n\n"
        "Polygon object that BrickIt voxelizes and tiles with bricks. "
        "Any polygon shape works. The source's world transform places "
        "the brick assembly - moving the source moves the bricks; "
        "scaling it scales the assembly. BrickIt's own position adds an "
        "extra parent transform on top."
    ),
    "BRICKIFYASSEMBLY_HIDE_SOURCE_MESH": (
        "Hide Source Mesh\n\n"
        "Toggle the source polygon object's editor and render "
        "visibility. Convenient because the source usually overlaps the "
        "brick output."
    ),

    # Shape tab - voxelization.
    "BRICKIFYASSEMBLY_VOXEL_RESOLUTION": (
        "Resolution\n\n"
        "How densely the source mesh is sampled (0.1-1.0). Lower values "
        "produce chunkier bricks and faster builds; higher values "
        "capture more detail at the cost of build time and brick count."
    ),
    "BRICKIFYASSEMBLY_STUDS_ACROSS": (
        "Target Studs Across\n\n"
        "Target width of the brick assembly in studs. Increase to get "
        "finer detail at the same source size; decrease for a blockier "
        "look. The fitter derives stud size from this unless Use Custom "
        "Scale is on."
    ),
    "BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE": (
        "Use Custom Scale\n\n"
        "Override the auto-derived stud size with an explicit value. Use "
        "this when the brickified output needs to match a specific "
        "real-world scale or align with another scene element."
    ),
    "BRICKIFYASSEMBLY_STUD_SIZE": (
        "Stud Size\n\n"
        "Stud size in scene units. Only used when Use Custom Scale is "
        "enabled. Real LEGO is 8 mm."
    ),
    "BRICKIFYASSEMBLY_VOXEL_BACKEND": (
        "Algorithm\n\n"
        "Voxelization algorithm:\n\n"
        "  Simple - internal voxelizer. Faster, less precise on thin or "
        "concave features.\n"
        "  Detailed - Cinema 4D Volume sampling. Slower but handles "
        "thin walls, concave surfaces, and overhangs much better. "
        "Recommended for production work."
    ),

    # Shape tab - build type.
    "BRICKIFYASSEMBLY_VOXEL_MODE": (
        "Build Type\n\n"
        "How interior cells are filled:\n\n"
        "  Solid - fill the entire interior with bricks.\n"
        "  Shell - only place bricks within Wall Thickness of the "
        "surface. Lighter assemblies, hollow inside."
    ),
    "BRICKIFYASSEMBLY_SHELL_THICKNESS": (
        "Wall Thickness\n\n"
        "Number of brick layers inward from the surface. Only used when "
        "Build Type is Shell."
    ),
    "BRICKIFYASSEMBLY_DETAIL_MODE": (
        "Brick Size Style\n\n"
        "How aggressively the fitter prefers larger bricks vs smaller:\n\n"
        "  Simple - favors the largest bricks. Fewest pieces, least "
        "surface fidelity.\n"
        "  Balanced - default mix.\n"
        "  Preserve Small Features - uses many small bricks to keep "
        "thin source details readable."
    ),

    # Shape tab - finishing.
    "BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY": (
        "Make Physically Accurate\n\n"
        "When ON, the assembly must be a single connected structure - "
        "floating clusters are dropped so the result is buildable in "
        "real bricks. When OFF, BrickIt prioritizes silhouette accuracy "
        "and fills boundary cells with 1x1s as needed; physically "
        "separate islands are kept."
    ),
    "BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS": (
        "Keep Tiny Gaps\n\n"
        "Preserve narrow gaps in the source by allowing smaller bricks "
        "near them. Off by default for cleaner output."
    ),
    "BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS": (
        "Clean Small Details\n\n"
        "Remove stray single-brick protrusions that read as noise rather "
        "than detail."
    ),

    # Shape tab - smooth top.
    "BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES": (
        "Smooth Top Surfaces\n\n"
        "Replace the lumpy top of the assembly with flat plates. The "
        "Cap Style parameter controls which plates get used."
    ),
    "BRICKIFYASSEMBLY_CAP_STYLE": (
        "Cap Style\n\n"
        "How the top cap is generated when Smooth Top Surfaces is on:\n\n"
        "  Match Brick Below - cap each top column with a plate "
        "matching the footprint of the brick beneath it. Most uniform.\n"
        "  Largest Merged Plates - pack the top with the biggest plates "
        "that fit. Cleanest geometric look.\n"
        "  Random Library Mix - random plates from your library "
        "selection. Most organic."
    ),
    "BRICKIFYASSEMBLY_CAP_RANDOM_SEED": (
        "Cap Random Seed\n\n"
        "Seed value that determines the random cap layout when Cap "
        "Style is Random Library Mix."
    ),
    "BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE": (
        "Smooth Top Coverage\n\n"
        "Fraction of top cells that get smoothed (0.0-1.0). 1.0 covers "
        "every top cell; lower values leave some studs poking through "
        "for an unfinished look."
    ),
    "BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER": (
        "Randomize Top Finish\n\n"
        "Reveal the smooth-top plates in random order during animation "
        "rather than a deterministic sweep."
    ),
    "BRICKIFYASSEMBLY_TOP_SURFACE_BLEND": (
        "Blend Top Finish\n\n"
        "Cross-fade the smooth-top reveal so plates ease in and out "
        "rather than popping on at a single threshold."
    ),
    "BRICKIFYASSEMBLY_TOP_SURFACE_START": (
        "Top Finish Starts At\n\n"
        "Fraction of Build Progress at which the smooth-top reveal "
        "begins. 0.85 means the body finishes before the cap starts."
    ),
    "BRICKIFYASSEMBLY_TOP_SURFACE_PHASE": (
        "Top Finish Duration\n\n"
        "Duration of the smooth-top reveal as a fraction of the "
        "timeline. Combined with Top Finish Starts At."
    ),

    # Bricks tab.
    "BRICKIFYASSEMBLY_LIBRARY_MASK": (
        "Choose Bricks\n\n"
        "Bitmask of which library bricks the fitter is allowed to use. "
        "Use the thumbnail picker or the Quick Select buttons to modify "
        "it rather than editing the value directly."
    ),
    "BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER": (
        "Open Thumbnail Picker\n\n"
        "Open a larger floating thumbnail picker for selecting brick "
        "sizes. Useful on smaller monitors where the AM grid is cramped."
    ),
    "BRICKIFYASSEMBLY_ENABLE_PLATES": (
        "Use Plates\n\n"
        "When ON, the fitter can use 1-plate-tall bricks (plates) in "
        "addition to 3-plate bricks. Lets the assembly hug curves more "
        "tightly at the cost of more total pieces."
    ),
    "BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT": (
        "Brick Height\n\n"
        "Quick preset for which brick heights the fitter can use:\n\n"
        "  Fine - allow plates and tall bricks.\n"
        "  Balanced - default mix.\n"
        "  Blocky - bias toward full bricks."
    ),
    "BRICKIFYASSEMBLY_HEIGHT_VARIATION": (
        "Vary Brick Heights\n\n"
        "Randomly mix tall and short bricks across the assembly for a "
        "less grid-uniform, more handmade look."
    ),
    "BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED": (
        "Variation Seed\n\n"
        "Random seed for the height-variation pattern."
    ),
    "BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT": (
        "Variation Amount\n\n"
        "Strength of the height variation (0-1). Higher values produce "
        "more dramatic mixing."
    ),
    "BRICKIFYASSEMBLY_MERGE_PLATES": (
        "Merge Plate Stacks into Bricks\n\n"
        "When three vertically-aligned plates can be replaced by one "
        "brick, do so. Reduces piece count without changing the "
        "silhouette."
    ),
    "BRICKIFYASSEMBLY_BRICK_SEPARATION": (
        "Brick Separation\n\n"
        "Adds a tiny gap between bricks (in scene units) so the seams "
        "read in renders. 0 = bricks touch exactly."
    ),
    "BRICKIFYASSEMBLY_HUMANIZE_BRICKS": (
        "Humanize Bricks\n\n"
        "Give every brick a small random position and rotation offset "
        "so the assembly looks hand-built rather than CNC-perfect."
    ),
    "BRICKIFYASSEMBLY_HUMANIZE_SEED": (
        "Humanize Seed\n\n"
        "Random seed for the humanize pattern."
    ),
    "BRICKIFYASSEMBLY_HUMANIZE_POSITION": (
        "Position Variation\n\n"
        "Magnitude of the position jitter (0-1). Use small values; the "
        "effect compounds across hundreds of bricks."
    ),
    "BRICKIFYASSEMBLY_HUMANIZE_ROTATION": (
        "Rotation Variation\n\n"
        "Magnitude of the rotation jitter (0-2). Subtle values feel "
        "natural; high values look chaotic."
    ),

    # Look tab.
    "BRICKIFYASSEMBLY_QUALITY": (
        "Brick Mesh Detail\n\n"
        "Per-brick geometry density:\n\n"
        "  Proxy - hollow shell + coarse studs. Lightest possible. "
        "Default; use for layout, animation playback, effector setup.\n"
        "  Draft - about 1k tris per brick.\n"
        "  Standard - about 5k tris, full anatomy. Good for distant "
        "shots.\n"
        "  Hero - about 50k verts per brick with full edge fillets, "
        "dense studs and tubes, baked stud logos. Use for hero renders."
    ),
    "BRICKIFYASSEMBLY_VISUALIZATION_MODE": (
        "Preview Mode\n\n"
        "Preview mode for the brick assembly:\n\n"
        "  Source Color - live brick assembly with per-brick color "
        "from the source mesh. Normal working mode.\n"
        "  Shell Wireframe - debug overlay showing brick outlines on "
        "the source shell.\n"
        "  Voxel Overlay - debug overlay showing raw voxel cells, "
        "color-coded by shell depth."
    ),
    "BRICKIFYASSEMBLY_AUTO_REBUILD": (
        "Live Update\n\n"
        "When ON, the assembly rebuilds whenever a slider changes. "
        "Best for interactive scrubbing on light scenes. When OFF, "
        "sliders stage changes silently and you commit them with "
        "Rebuild Now - useful when scrubbing feels sluggish on heavy "
        "scenes."
    ),
    "BRICKIFYASSEMBLY_REBUILD": (
        "Rebuild Now\n\n"
        "Force a full rebuild of the brick assembly. Used together "
        "with Live Update off to apply staged changes."
    ),

    # Look tab - custom logo (mirrors BrickGen logo group).
    "BRICKIFYASSEMBLY_ENABLE_LOGO": (
        "Custom Logo\n\n"
        "Replace each stud's flat top with an embossed custom logo. "
        "Only baked at Hero quality - lower qualities skip stud logos "
        "for performance."
    ),
    "BRICKIFYASSEMBLY_LOGO_SOURCE": (
        "Logo Source Mesh\n\n"
        "Polygon object whose silhouette is projected onto every stud "
        "top."
    ),
    "BRICKIFYASSEMBLY_LOGO_ROTATION": (
        "Logo Rotation\n\n"
        "Rotate the logo by 0, 90, 180, or 270 degrees on each stud."
    ),
    "BRICKIFYASSEMBLY_LOGO_DIAMETER": (
        "Logo Fill %\n\n"
        "Fraction of the stud top the logo occupies (100% fills the "
        "disk)."
    ),
    "BRICKIFYASSEMBLY_LOGO_HEIGHT": (
        "Logo Height\n\n"
        "Embossed depth above the stud surface."
    ),
    "BRICKIFYASSEMBLY_LOGO_BLEND": (
        "Logo Blend\n\n"
        "How softly the logo edges fade into the stud surface."
    ),
    "BRICKIFYASSEMBLY_LOGO_SINK": (
        "Logo Sink\n\n"
        "Recess the logo below the stud surface for a carved-in look."
    ),

    # Animate tab.
    "BRICKIFYASSEMBLY_BUILD_PROGRESS": (
        "Build Progress\n\n"
        "Reveals the assembly from 0 (empty) to 1 (fully built). "
        "Keyframe this for a build animation. Bricks appear in stagger "
        "order driven by the other Animate-tab parameters."
    ),
    "BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS": (
        "Smooth Top Progress\n\n"
        "Reveals the smooth-top cap separately from the body (0 -> 1). "
        "Has no effect unless Smooth Top Surfaces is on."
    ),
    "BRICKIFYASSEMBLY_BUILD_Y_OFFSET": (
        "Lift Height\n\n"
        "How far above its final position each brick starts, in scene "
        "units. Higher values produce a longer fall."
    ),
    "BRICKIFYASSEMBLY_BUILD_STAGGER": (
        "Stagger Amount\n\n"
        "How spread out the per-brick landings are across the timeline. "
        "0 = all bricks land simultaneously. Higher values stagger by "
        "Y-layer so lower bricks land first."
    ),
    "BRICKIFYASSEMBLY_BUILD_HANG_TIME": (
        "Brick Hang Time\n\n"
        "Pause before each brick starts moving. Lets later bricks "
        "build anticipation while earlier ones are already mid-fall."
    ),
    "BRICKIFYASSEMBLY_BUILD_MOTION_CURVE": (
        "Motion Style\n\n"
        "Per-brick easing curve. Slam is the default LEGO drop feel. "
        "Spring and Bounce overshoot and settle. Custom Curve uses the "
        "editable curve below."
    ),
    "BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE": (
        "Custom Motion Curve\n\n"
        "Editable motion curve used when Motion Style is Custom Curve. "
        "Draw the per-brick fall profile here."
    ),
    "BRICKIFYASSEMBLY_BUILD_SCALE_IN": (
        "Scale Bricks In\n\n"
        "Bricks scale up from a point as they land, rather than "
        "appearing at full size and only translating. Pairs well with "
        "bouncy motion styles."
    ),
    "BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION": (
        "Use Rotation\n\n"
        "Bricks tumble slightly while falling. Tilt magnitude is set "
        "by Tilt Amount."
    ),
    "BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT": (
        "Tilt Amount\n\n"
        "How strong the per-brick tumble is, in degrees. Keyframeable. "
        "Subtle values (3-7 deg) feel natural; large values look "
        "chaotic."
    ),

    # Effectors tab.
    "BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS": (
        "Effectors\n\n"
        "List of MoGraph effectors that drive per-brick matrix and "
        "color (and visibility) on this BrickIt. Drag effectors in "
        "manually, or rely on auto-link: when you create a new "
        "effector while a BrickIt is selected, the new effector is "
        "appended here automatically.\n\n"
        "Standard effectors are supported: Plain, Random, Shader, "
        "Delay, Formula, Step, Sound, Time, Push Apart, Inheritance, "
        "Python, ReEffector, Effector Target, Weight Effector. They "
        "drive Position / Rotation / Scale, Color (User Defined or "
        "Field), and Visibility (the Plain effector's Visibility "
        "checkbox + a Field hides bricks where the field touches them)."
    ),

    # Tools / Surface Finish.
    "BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH": (
        "Create Proxies\n\n"
        "Bake the live brick assembly into a static hierarchy under "
        "BrickIt: one Fracture object containing grouped Nulls per "
        "source-mesh region, with per-brick instances inside. Use this "
        "when you need real edit-able geometry - for dynamics, manual "
        "selection, or material assignment that can't go through the "
        "live cache."
    ),
    "BRICKIFYASSEMBLY_SWAP_PROXY_RENDER": (
        "Proxy / High Res\n\n"
        "Toggle the proxy hierarchy between Proxy-quality carrier "
        "meshes (light, for interaction) and the current Brick Mesh "
        "Detail quality (renderable). Quick way to hide proxies during "
        "scrubbing and bring them back for the render pass."
    ),
    "BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL": (
        "Create RS Color Material\n\n"
        "Create and assign BrickIt_PerBrick_Color, a Redshift material "
        "wired to the RSObjectColor user-data attribute. Required for "
        "per-brick color (from the source mesh or from a MoGraph "
        "effector's Color mode) to render in Redshift.\n\n"
        "If you build the material yourself, use a Color User Data "
        "node with Attribute Name = RSObjectColor (case-sensitive)."
    ),
}


def _make_delegate(registry, plugin_label):
    """Build a PluginHelpDelegate that opens a MessageDialog for known
    parameters. Returns Bool: True if a help entry was shown, False to let
    Cinema 4D fall back to its default help browser behavior.
    """
    def _delegate(opType, baseType, group, property):
        try:
            text = registry.get(str(property), "")
        except Exception:
            text = ""
        if not text:
            return False
        try:
            c4d.gui.MessageDialog(text)
        except Exception as exc:
            print(
                "[brick] {0} help dialog failed for {1}: {2}".format(
                    plugin_label, property, exc,
                )
            )
            return False
        return True
    return _delegate


def register():
    """Wire BRICK_HELP and BRICKIT_HELP into Cinema 4D's Show Help system.

    Tries the C4D 2026+ name `RegisterPluginHelpDelegate` first. Falls back
    to `RegisterPluginHelpCallback` for older SDKs that still expose the
    legacy name. Both contracts expect a Bool-returning callback in 2026+.
    Silent-skip if neither is exported.
    """
    fn = (
        getattr(plugins, "RegisterPluginHelpDelegate", None)
        or getattr(plugins, "RegisterPluginHelpCallback", None)
    )
    if fn is None:
        return False
    ok = True
    try:
        if not bool(fn(int(ID_BRICKGENERATOR), _make_delegate(BRICK_HELP, "BrickGen"))):
            ok = False
    except Exception as exc:
        print("[brick] BrickGen help delegate register failed:", exc)
        ok = False
    try:
        if not bool(fn(int(ID_BRICKIFYASSEMBLY), _make_delegate(BRICKIT_HELP, "BrickIt"))):
            ok = False
    except Exception as exc:
        print("[brick] BrickIt help delegate register failed:", exc)
        ok = False
    return ok
