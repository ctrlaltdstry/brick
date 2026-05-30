CONTAINER obrickifyassembly
{
    NAME BRICKIFYASSEMBLY;
    INCLUDE Obase;

    GROUP ID_OBJECTPROPERTIES
    {
        // Volume-Builder-shaped layout:
        //   Algorithm + Resolution at the top (matches Volume Builder's
        //   Volume Type / Voxel Size); Sources child list directly below;
        //   the rest of the voxel/shape options follow. The Sources list
        //   is rendered by the native BrickSources custom GUI plugin.
        //
        // Two-column flat layout — widgets stream directly into the
        // parent's column slots row-by-row. This is the pattern Maxon's
        // own `ohairsdkgen.res` uses for COLUMNS 2 layouts, and it's the
        // only structure where the layout engine actually splits the AM
        // width 50/50. Nested inner-GROUPs with SCALE_H were tried and
        // produced a left-aligned non-responsive layout regardless of
        // SCALE_H/LAYOUTGROUP combinations — the engine treats each
        // inner group as one cell and sizes it to its widest child.
        //
        // Row order is the layout:
        //   row 1: Algorithm           | Rebuild Now
        //   row 2: Resolution          | Live Update
        //   row 3: Use Custom Scale    | (empty)
        //   row 4: Stud Size           | (empty)
        // Empty cells use BRICKIFYASSEMBLY_SPACER_N as a STATICTEXT with
        // an empty NAME string.
        GROUP BRICKIFYASSEMBLY_GROUP_VOXEL
        {
            COLUMNS 2;
            DEFAULT 1;
            SCALE_H;

            LONG BRICKIFYASSEMBLY_VOXEL_BACKEND
            {
                NAME BRICKIFYASSEMBLY_VOXEL_BACKEND;
                DEFAULT 1;
                SCALE_H;
                CYCLE
                {
                    BRICKIFYASSEMBLY_VOXEL_BACKEND_INTERNAL;
                    BRICKIFYASSEMBLY_VOXEL_BACKEND_C4D_VOLUME;
                }
            }

            BUTTON BRICKIFYASSEMBLY_REBUILD
            {
                NAME BRICKIFYASSEMBLY_REBUILD;
                SCALE_H;
            }

            REAL BRICKIFYASSEMBLY_VOXEL_RESOLUTION
            {
                NAME BRICKIFYASSEMBLY_VOXEL_RESOLUTION;
                MIN 0.1;
                MAX 1.0;
                STEP 0.1;
                DEFAULT 1.0;
                SCALE_H;
            }

            BOOL BRICKIFYASSEMBLY_AUTO_REBUILD
            {
                NAME BRICKIFYASSEMBLY_AUTO_REBUILD;
                DEFAULT 1;
                SCALE_H;
            }

            // Row 3: Use Custom Scale gates Stud Size via GetDEnabling
            // so the field greys out when auto-scale is on. Build Type
            // (Solid / Shell) sits next to it on the right since the
            // shell-related Wall Thickness lives just below it.
            BOOL BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE
            {
                NAME BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE;
                DEFAULT 0;
                SCALE_H;
            }

            LONG BRICKIFYASSEMBLY_VOXEL_MODE
            {
                NAME BRICKIFYASSEMBLY_VOXEL_MODE;
                DEFAULT 0;
                SCALE_H;
                CYCLE
                {
                    BRICKIFYASSEMBLY_VOXEL_MODE_SOLID;
                    BRICKIFYASSEMBLY_VOXEL_MODE_SHELL;
                }
            }

            // Row 4: Stud Size | Wall Thickness
            REAL BRICKIFYASSEMBLY_STUD_SIZE
            {
                NAME BRICKIFYASSEMBLY_STUD_SIZE;
                MIN 0.1;
                MAX 1000.0;
                STEP 0.1;
                DEFAULT 8.0;
                UNIT METER;
                SCALE_H;
            }

            LONG BRICKIFYASSEMBLY_SHELL_THICKNESS
            {
                NAME BRICKIFYASSEMBLY_SHELL_THICKNESS;
                MIN 1;
                MAX 8;
                STEP 1;
                DEFAULT 3;
                SCALE_H;
            }

            // Row 5: Keep Tiny Gaps | Clean Small Details
            BOOL BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS
            {
                NAME BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS;
                DEFAULT 0;
                SCALE_H;
            }

            LONG BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS
            {
                NAME BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS;
                MIN 0;
                MAX 4;
                STEP 1;
                DEFAULT 1;
                SCALE_H;
            }

            // Row 6: Make Physically Accurate | (empty)
            BOOL BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY
            {
                NAME BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY;
                DEFAULT 0;
                SCALE_H;
            }

            // Row 7: Mirror X | (empty)
            BOOL BRICKIFYASSEMBLY_MIRROR_X
            {
                NAME BRICKIFYASSEMBLY_MIRROR_X;
                DEFAULT 0;
                SCALE_H;
            }

            STATICTEXT BRICKIFYASSEMBLY_SPACER_1
            {
                NAME BRICKIFYASSEMBLY_SPACER_1;
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_SOURCE
        {
            DEFAULT 1;
            COLUMNS 1;

            // Native custom GUI: dark-framed inset list of the BrickIt op's
            // direct children with a per-row Mode control (Union / Subtract /
            // Intersect). Implemented by RegisterBrickSourcesCustomGUI in
            // native/bricklibrary.inline_gui/source/main.cpp. The IN_EXCLUDE
            // base type declares the InExcludeData parameter; the CUSTOMGUI
            // attribute swaps the renderer to our custom GUI.
            IN_EXCLUDE BRICKIFYASSEMBLY_SOURCES
            {
                NAME BRICKIFYASSEMBLY_SOURCES;
                CUSTOMGUI CUSTOMGUIBRICKSOURCES;
                ACCEPT { Obase; }
            }
        }

        // Bind to Source Deformation lives on the Object tab (it's an
        // object-level scene-graph behavior, not a brick-pipeline option).
        // Placed directly under the Sources list and above the voxel/shape
        // options so users find it adjacent to what it binds against.
        GROUP BRICKIFYASSEMBLY_GROUP_BIND
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION
            {
                NAME BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION;
                DEFAULT 0;
            }

            LONG BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE
            {
                NAME BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE;
                DEFAULT 0;
                CYCLE
                {
                    BRICKIFYASSEMBLY_BIND_ORIENT_WORLD_UP;
                    BRICKIFYASSEMBLY_BIND_ORIENT_FOLLOW_NORMAL;
                }
            }

            REAL BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO
            {
                NAME BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.6;
            }

            REAL BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING
            {
                NAME BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.7;
            }

            LONG BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME
            {
                NAME BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME;
                MIN 0;
                MAX 1000000;
                STEP 1;
                DEFAULT 0;
            }

            STATICTEXT BRICKIFYASSEMBLY_SPACER_5
            {
                NAME BRICKIFYASSEMBLY_SPACER_5;
            }

            BUTTON BRICKIFYASSEMBLY_REBIND_TO_CURRENT_FRAME
            {
                NAME BRICKIFYASSEMBLY_REBIND_TO_CURRENT_FRAME;
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_LIBRARY
        {
            DEFAULT 1;
            COLUMNS 1;

            // Row 1: Proxy Style dropdown | Brick Mesh Detail dropdown
            GROUP
            {
                DEFAULT 1;
                COLUMNS 2;

                LONG BRICKIFYASSEMBLY_PROXY_STYLE
                {
                    NAME BRICKIFYASSEMBLY_PROXY_STYLE;
                    DEFAULT 0;
                    SCALE_H;
                    CYCLE
                    {
                        BRICKIFYASSEMBLY_PROXY_STYLE_STUDDED;
                        BRICKIFYASSEMBLY_PROXY_STYLE_SIMPLIFIED;
                    }
                }

                LONG BRICKIFYASSEMBLY_QUALITY
                {
                    NAME BRICKIFYASSEMBLY_QUALITY;
                    DEFAULT 3;
                    SCALE_H;
                    CYCLE
                    {
                        BRICKIFYASSEMBLY_QUALITY_PROXY;
                        BRICKIFYASSEMBLY_QUALITY_DRAFT;
                        BRICKIFYASSEMBLY_QUALITY_STANDARD;
                        BRICKIFYASSEMBLY_QUALITY_HERO;
                    }
                }
            }

            // Spacer for vertical padding between row 1 and the Create
            // Proxies button.
            STATICTEXT BRICKIFYASSEMBLY_SPACER_4
            {
                NAME BRICKIFYASSEMBLY_SPACER_4;
            }

            // Row 2: Create Proxies button — spans the full width as a
            // single-column inner group with SCALE_H. The button is the
            // primary action of the Tools section, so it gets visual
            // weight by being the only widget on its row.
            GROUP
            {
                DEFAULT 1;
                COLUMNS 1;
                SCALE_H;

                BUTTON BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH
                {
                    NAME BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH;
                    SCALE_H;
                }
            }

            // Spacer between the Create Proxies row and the secondary
            // actions row.
            STATICTEXT BRICKIFYASSEMBLY_SPACER_2
            {
                NAME BRICKIFYASSEMBLY_SPACER_2;
            }

            // Row 3: Proxy/High Res swap | Create RS Color Material —
            // each button takes half the row width, matching the visual
            // width of the Create Proxies button above. SCALE_H on both
            // the inner group and each button is what gets the layout
            // engine to actually stretch them to fill 50/50.
            GROUP
            {
                DEFAULT 1;
                COLUMNS 2;
                SCALE_H;

                BUTTON BRICKIFYASSEMBLY_SWAP_PROXY_RENDER
                {
                    NAME BRICKIFYASSEMBLY_SWAP_PROXY_RENDER;
                    SCALE_H;
                }

                BUTTON BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL
                {
                    NAME BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL;
                    SCALE_H;
                }
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_BUILD_INFO
        {
            DEFAULT 0;
            COLUMNS 2;

            STRING BRICKIFYASSEMBLY_INFO_BRICK_COUNT
            {
                NAME BRICKIFYASSEMBLY_INFO_BRICK_COUNT;
                CUSTOMGUI STATICTEXT;
            }

            STRING BRICKIFYASSEMBLY_INFO_LIBRARY_ITEMS
            {
                NAME BRICKIFYASSEMBLY_INFO_LIBRARY_ITEMS;
                CUSTOMGUI STATICTEXT;
            }

            STRING BRICKIFYASSEMBLY_INFO_COVERAGE
            {
                NAME BRICKIFYASSEMBLY_INFO_COVERAGE;
                CUSTOMGUI STATICTEXT;
            }

            STRING BRICKIFYASSEMBLY_INFO_COMPONENTS
            {
                NAME BRICKIFYASSEMBLY_INFO_COMPONENTS;
                CUSTOMGUI STATICTEXT;
            }

            STRING BRICKIFYASSEMBLY_INFO_GRID_DIMS
            {
                NAME BRICKIFYASSEMBLY_INFO_GRID_DIMS;
                CUSTOMGUI STATICTEXT;
            }

            STRING BRICKIFYASSEMBLY_INFO_BUILDABLE
            {
                NAME BRICKIFYASSEMBLY_INFO_BUILDABLE;
                CUSTOMGUI STATICTEXT;
            }
        }

        // User manual sits last on the Object tab — peripheral action,
        // doesn't compete with the brick-pipeline controls above. Wrapped
        // in its own COLUMNS 1 group so it picks up the same left edge as
        // every other top-level group on the tab. One empty STATICTEXT
        // above the button adds ~22px of vertical breathing room — the
        // description grammar doesn't have a SPACE attribute (dialog-only),
        // so empty parameter rows are the canonical spacer.
        GROUP
        {
            DEFAULT 1;
            COLUMNS 1;
            SCALE_H;

            STATICTEXT BRICKIFYASSEMBLY_SPACER_3
            {
                NAME BRICKIFYASSEMBLY_SPACER_3;
            }

            BUTTON BRICKIFYASSEMBLY_OPEN_USER_MANUAL
            {
                NAME BRICKIFYASSEMBLY_OPEN_USER_MANUAL;
            }
        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_LAYOUT
    {
        DEFAULT 1;
        COLUMNS 1;

        STATICTEXT BRICKIFYASSEMBLY_LABEL_CHOOSE_BRICKS
        {
            NAME BRICKIFYASSEMBLY_LABEL_CHOOSE_BRICKS;
        }

        GROUP BRICKIFYASSEMBLY_GROUP_LIBRARY_THUMBS
        {
            DEFAULT 1;
            LAYOUTGROUP;
            COLUMNS 1;

            GROUP
            {
                SCALE_H;

                LONG BRICKIFYASSEMBLY_LIBRARY_MASK
                {
                    CUSTOMGUI CUSTOMGUIBRICKLIBRARY;
                    ANIM OFF;
                    SCALE_H;
                }
            }
        }

        STATICTEXT BRICKIFYASSEMBLY_GROUP_LIBRARY_PRESETS
        {
            NAME BRICKIFYASSEMBLY_GROUP_LIBRARY_PRESETS;
        }

        GROUP
        {
            DEFAULT 1;
            COLUMNS 4;

            BUTTON BRICKIFYASSEMBLY_LIB_PRESET_ALL
            {
                NAME BRICKIFYASSEMBLY_LIB_PRESET_ALL;
            }
            BUTTON BRICKIFYASSEMBLY_LIB_PRESET_NONE
            {
                NAME BRICKIFYASSEMBLY_LIB_PRESET_NONE;
            }
            BUTTON BRICKIFYASSEMBLY_LIB_PRESET_INVERT
            {
                NAME BRICKIFYASSEMBLY_LIB_PRESET_INVERT;
            }
            BUTTON BRICKIFYASSEMBLY_LIB_PRESET_1X1
            {
                NAME BRICKIFYASSEMBLY_LIB_PRESET_1X1;
            }
        }

        // Brick Selection — flat 2-column layout. Use Plates (boolean
        // toggle) on the left, Brick Size Style (3-way dropdown) on the
        // right since they're related selection-shaping options. Both
        // widgets get SCALE_H so the columns claim their 50/50 share
        // (matches the Shape-group justified pattern).
        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_SELECTION
        {
            COLUMNS 2;
            DEFAULT 1;
            SCALE_H;

            BOOL BRICKIFYASSEMBLY_ENABLE_PLATES
            {
                NAME BRICKIFYASSEMBLY_ENABLE_PLATES;
                DEFAULT 0;
                SCALE_H;
            }

            LONG BRICKIFYASSEMBLY_DETAIL_MODE
            {
                NAME BRICKIFYASSEMBLY_DETAIL_MODE;
                DEFAULT 1;
                SCALE_H;
                CYCLE
                {
                    BRICKIFYASSEMBLY_DETAIL_MODE_OFF;
                    BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED;
                    BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE;
                }
            }
        }

        // Brick Height — original 1-column layout. Tried pairing the
        // preset buttons inline with the Brick Height field but the
        // nested-COLUMNS-3 sub-group inside a flat COLUMNS 2 parent
        // either overflowed to a full-width row underneath or, with
        // LAYOUTGROUP, vanished entirely. The auto-generated label
        // column for LONG widgets makes "field + 3 buttons in one row"
        // not cleanly expressible without restructuring everything as a
        // COLUMNS 4 layout that conflicts with the rest of the rows.
        // Keeping the presets stacked underneath; later rows use the
        // flat 2-column pattern that does work.
        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_HEIGHT
        {
            DEFAULT 1;
            COLUMNS 1;
            SCALE_H;

            LONG BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT
            {
                NAME BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT;
                MIN 1;
                MAX 6;
                STEP 1;
                DEFAULT 3;
                SCALE_H;
            }

            GROUP
            {
                DEFAULT 1;
                COLUMNS 3;
                SCALE_H;

                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE;
                    SCALE_H;
                }
                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED;
                    SCALE_H;
                }
                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY;
                    SCALE_H;
                }
            }

            BOOL BRICKIFYASSEMBLY_HEIGHT_VARIATION
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION;
                DEFAULT 0;
            }

            // Variation Amount drives the visible result; Seed only
            // matters once Amount > 0. Showing Amount first keeps the
            // primary control directly under the gate toggle.
            REAL BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.6;
                SCALE_H;
            }

            LONG BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED;
                MIN 0;
                MAX 1000000;
                STEP 1;
                DEFAULT 1;
                SCALE_H;
            }

            BOOL BRICKIFYASSEMBLY_MERGE_PLATES
            {
                NAME BRICKIFYASSEMBLY_MERGE_PLATES;
                DEFAULT 1;
            }
        }

        // Per-Brick Variation — Humanize Bricks gates the entire group
        // including Brick Separation. Per user direction: when Humanize
        // is off, no per-brick variation should be active, so all sub-
        // options (Brick Separation, Humanize Seed, Position Variation,
        // Rotation Variation) grey out together.
        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_ADJUSTMENTS
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_HUMANIZE_BRICKS
            {
                NAME BRICKIFYASSEMBLY_HUMANIZE_BRICKS;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_BRICK_SEPARATION
            {
                NAME BRICKIFYASSEMBLY_BRICK_SEPARATION;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.0;
            }

            LONG BRICKIFYASSEMBLY_HUMANIZE_SEED
            {
                NAME BRICKIFYASSEMBLY_HUMANIZE_SEED;
                MIN 0;
                MAX 1000000;
                STEP 1;
                DEFAULT 1;
            }

            REAL BRICKIFYASSEMBLY_HUMANIZE_POSITION
            {
                NAME BRICKIFYASSEMBLY_HUMANIZE_POSITION;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.0;
            }

            REAL BRICKIFYASSEMBLY_HUMANIZE_ROTATION
            {
                NAME BRICKIFYASSEMBLY_HUMANIZE_ROTATION;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 2.0;
                STEP 0.01;
                DEFAULT 0.0;
            }
        }

    }

    GROUP BRICKIFYASSEMBLY_TAB_PREVIEW
    {
        DEFAULT 1;
        COLUMNS 1;

        GROUP BRICKIFYASSEMBLY_GROUP_PREVIEW_DEBUG
        {
            DEFAULT 1;
            COLUMNS 1;

            LONG BRICKIFYASSEMBLY_VISUALIZATION_MODE
            {
                NAME BRICKIFYASSEMBLY_VISUALIZATION_MODE;
                DEFAULT 0;
                CYCLE
                {
                    BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE;
                    BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME;
                    BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG;
                }
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_ACTIONS
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES
            {
                NAME BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES;
                DEFAULT 1;
            }

            LONG BRICKIFYASSEMBLY_CAP_STYLE
            {
                NAME BRICKIFYASSEMBLY_CAP_STYLE;
                CYCLE
                {
                    BRICKIFYASSEMBLY_CAP_STYLE_MATCH_BELOW;
                    BRICKIFYASSEMBLY_CAP_STYLE_MERGED_COVER;
                    BRICKIFYASSEMBLY_CAP_STYLE_RANDOM_MIX;
                }
                DEFAULT 0;
            }

            LONG BRICKIFYASSEMBLY_CAP_RANDOM_SEED
            {
                NAME BRICKIFYASSEMBLY_CAP_RANDOM_SEED;
                MIN 0;
                MAX 999999;
                STEP 1;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE
            {
                NAME BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 100.0;
                STEP 0.1;
                DEFAULT 100.0;
            }

            BOOL BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER
            {
                NAME BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER;
                DEFAULT 0;
            }

        }

        GROUP BRICKIFYASSEMBLY_GROUP_LOGO
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_ENABLE_LOGO
            {
                NAME BRICKIFYASSEMBLY_ENABLE_LOGO;
                DEFAULT 0;
            }

            LINK BRICKIFYASSEMBLY_LOGO_SOURCE
            {
                NAME BRICKIFYASSEMBLY_LOGO_SOURCE;
                ACCEPT { Obase; }
            }

            REAL BRICKIFYASSEMBLY_LOGO_ROTATION
            {
                NAME BRICKIFYASSEMBLY_LOGO_ROTATION;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 360.0;
                STEP 1.0;
                DEFAULT 0.0;
            }

            BOOL BRICKIFYASSEMBLY_LOGO_MIX_FLIP
            {
                NAME BRICKIFYASSEMBLY_LOGO_MIX_FLIP;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_LOGO_MIX_AMOUNT
            {
                NAME BRICKIFYASSEMBLY_LOGO_MIX_AMOUNT;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 100.0;
                STEP 1.0;
                DEFAULT 50.0;
            }

            LONG BRICKIFYASSEMBLY_LOGO_MIX_SEED
            {
                NAME BRICKIFYASSEMBLY_LOGO_MIX_SEED;
                MIN 0;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_LOGO_DIAMETER
            {
                NAME BRICKIFYASSEMBLY_LOGO_DIAMETER;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 100.0;
                STEP 1.0;
                DEFAULT 0.0;
            }

            REAL BRICKIFYASSEMBLY_LOGO_HEIGHT
            {
                NAME BRICKIFYASSEMBLY_LOGO_HEIGHT;
                CUSTOMGUI REALSLIDER;
                MIN 0.02;
                MAX 0.25;
                STEP 0.01;
                DEFAULT 0.06;
            }

            REAL BRICKIFYASSEMBLY_LOGO_BLEND
            {
                NAME BRICKIFYASSEMBLY_LOGO_BLEND;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 1.0;
                STEP 0.05;
                DEFAULT 1.0;
            }

            REAL BRICKIFYASSEMBLY_LOGO_SINK
            {
                NAME BRICKIFYASSEMBLY_LOGO_SINK;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 0.05;
                STEP 0.001;
                DEFAULT 0.015;
            }
        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_MOGRAPH
    {
        DEFAULT 1;
        COLUMNS 1;
        SCALE_H;

        GROUP BRICKIFYASSEMBLY_GROUP_BUILD_ANIM
        {
            DEFAULT 1;
            COLUMNS 1;
            SCALE_H;

            // Build Step (authoritative): REAL stepper + slider that maps
            // 1:1 to bricks placed so far. Range [0, total_bricks];
            // step==0 → no bricks visible, step==total → full build.
            // CUSTOMGUI REALSLIDER renders both the editable number AND
            // a slider track, so the user can scrub for assemblies with
            // many bricks. The MAX is 100000 as a placeholder — the
            // runtime clamps the value to total_bricks on commit.
            REAL BRICKIFYASSEMBLY_BUILD_STEP
            {
                NAME BRICKIFYASSEMBLY_BUILD_STEP;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                ANIM ON;
                MIN 0.0;
                MAX 100000.0;
                STEP 0.01;
                DEFAULT 0.0;
            }

            // Progress + Total Bricks read-out row, below the stepper+slider.
            GROUP
            {
                DEFAULT 1;
                COLUMNS 2;
                SCALE_H;

                STRING BRICKIFYASSEMBLY_BUILD_PROGRESS_PCT
                {
                    NAME BRICKIFYASSEMBLY_BUILD_PROGRESS_PCT;
                    CUSTOMGUI STATICTEXT;
                }

                STRING BRICKIFYASSEMBLY_BUILD_TOTAL_BRICKS
                {
                    NAME BRICKIFYASSEMBLY_BUILD_TOTAL_BRICKS;
                    CUSTOMGUI STATICTEXT;
                }
            }

            REAL BRICKIFYASSEMBLY_BUILD_Y_OFFSET
            {
                NAME BRICKIFYASSEMBLY_BUILD_Y_OFFSET;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.1;
                DEFAULT 25.0;
            }

            REAL BRICKIFYASSEMBLY_BUILD_STAGGER
            {
                NAME BRICKIFYASSEMBLY_BUILD_STAGGER;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.1;
                DEFAULT 10.0;
            }

            REAL BRICKIFYASSEMBLY_BUILD_HANG_TIME
            {
                NAME BRICKIFYASSEMBLY_BUILD_HANG_TIME;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.1;
                DEFAULT 0.0;
            }

            LONG BRICKIFYASSEMBLY_BUILD_MOTION_CURVE
            {
                NAME BRICKIFYASSEMBLY_BUILD_MOTION_CURVE;
                SCALE_H;
                DEFAULT 4;
                CYCLE
                {
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE_IN;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE_OUT;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SPRING;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_QUADRATIC;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_CUSTOM;
                    BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_BOUNCE;
                }
            }

            REAL BRICKIFYASSEMBLY_BUILD_DAMPING
            {
                NAME BRICKIFYASSEMBLY_BUILD_DAMPING;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.1;
                DEFAULT 50.0;
            }

            BOOL BRICKIFYASSEMBLY_BUILD_SCALE_IN
            {
                NAME BRICKIFYASSEMBLY_BUILD_SCALE_IN;
                DEFAULT 0;
            }

            BOOL BRICKIFYASSEMBLY_TOP_SURFACE_BLEND
            {
                NAME BRICKIFYASSEMBLY_TOP_SURFACE_BLEND;
                DEFAULT 1;
            }

            BOOL BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION
            {
                NAME BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT
            {
                NAME BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT;
                CUSTOMGUI REALSLIDER;
                ANIM ON;
                SCALE_H;
                MIN 0.0;
                MAX 360.0;
                STEP 0.1;
                DEFAULT 5.0;
            }

        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_EFFECTORS
    {
        DEFAULT 1;
        COLUMNS 1;
    }

}
