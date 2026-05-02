CONTAINER obrickifyassembly
{
    NAME BRICKIFYASSEMBLY;
    INCLUDE Obase;

    GROUP ID_OBJECTPROPERTIES
    {
        GROUP
        {
            DEFAULT 1;
            COLUMNS 1;
            SCALE_H;

            GROUP
            {
                SCALE_H;

                LONG BRICKIFYASSEMBLY_HERO
                {
                    NAME BRICKIFYASSEMBLY_HERO;
                    CUSTOMGUI CUSTOMGUIBRICKHERO;
                    ANIM OFF;
                    SCALE_H;
                }
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_SOURCE
        {
            DEFAULT 1;
            COLUMNS 1;

            GROUP
            {
                COLUMNS 2;

                LINK BRICKIFYASSEMBLY_SOURCE
                {
                    NAME BRICKIFYASSEMBLY_SOURCE;
                    ACCEPT { Obase; }
                }

                GROUP
                {
                    SCALE_H;
                    COLUMNS 1;
                }
            }

            BOOL BRICKIFYASSEMBLY_HIDE_SOURCE_MESH
            {
                NAME BRICKIFYASSEMBLY_HIDE_SOURCE_MESH;
                DEFAULT 1;
            }

            BOOL BRICKIFYASSEMBLY_AUTO_REBUILD
            {
                NAME BRICKIFYASSEMBLY_AUTO_REBUILD;
                DEFAULT 1;
            }

            STATICTEXT BRICKIFYASSEMBLY_SPACER_1
            {
                NAME BRICKIFYASSEMBLY_SPACER_1;
            }

            BUTTON BRICKIFYASSEMBLY_REBUILD
            {
                NAME BRICKIFYASSEMBLY_REBUILD;
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_VOXEL
        {
                DEFAULT 1;
                COLUMNS 1;

                LONG BRICKIFYASSEMBLY_VOXEL_BACKEND
                {
                    NAME BRICKIFYASSEMBLY_VOXEL_BACKEND;
                    DEFAULT 1;
                    CYCLE
                    {
                        BRICKIFYASSEMBLY_VOXEL_BACKEND_INTERNAL;
                        BRICKIFYASSEMBLY_VOXEL_BACKEND_C4D_VOLUME;
                    }
                }

                REAL BRICKIFYASSEMBLY_VOXEL_RESOLUTION
                {
                    NAME BRICKIFYASSEMBLY_VOXEL_RESOLUTION;
                    MIN 0.1;
                    MAX 1.0;
                    STEP 0.1;
                    DEFAULT 1.0;
                }

                LONG BRICKIFYASSEMBLY_VOXEL_MODE
                {
                    NAME BRICKIFYASSEMBLY_VOXEL_MODE;
                    DEFAULT 0;
                    CYCLE
                    {
                        BRICKIFYASSEMBLY_VOXEL_MODE_SOLID;
                        BRICKIFYASSEMBLY_VOXEL_MODE_SHELL;
                    }
                }

                LONG BRICKIFYASSEMBLY_SHELL_THICKNESS
                {
                    NAME BRICKIFYASSEMBLY_SHELL_THICKNESS;
                    MIN 1;
                    MAX 8;
                    STEP 1;
                    DEFAULT 3;
                }

                LONG BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS
                {
                    NAME BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS;
                    MIN 0;
                    MAX 4;
                    STEP 1;
                    DEFAULT 1;
                }

                BOOL BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS
                {
                    NAME BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS;
                    DEFAULT 0;
                }

                BOOL BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY
                {
                    NAME BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY;
                    DEFAULT 0;
                }
            }

        GROUP BRICKIFYASSEMBLY_GROUP_LIBRARY
        {
            DEFAULT 1;
            COLUMNS 1;

            GROUP
            {
                DEFAULT 1;
                COLUMNS 3;

                BUTTON BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH
                {
                    NAME BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH;
                }

                BUTTON BRICKIFYASSEMBLY_SWAP_PROXY_RENDER
                {
                    NAME BRICKIFYASSEMBLY_SWAP_PROXY_RENDER;
                }

                BUTTON BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL
                {
                    NAME BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL;
                }
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

        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_SELECTION
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_ENABLE_PLATES
            {
                NAME BRICKIFYASSEMBLY_ENABLE_PLATES;
                DEFAULT 0;
            }

            LONG BRICKIFYASSEMBLY_DETAIL_MODE
            {
                NAME BRICKIFYASSEMBLY_DETAIL_MODE;
                DEFAULT 1;
                CYCLE
                {
                    BRICKIFYASSEMBLY_DETAIL_MODE_OFF;
                    BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED;
                    BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE;
                }
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_HEIGHT
        {
            DEFAULT 1;
            COLUMNS 1;

            LONG BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT
            {
                NAME BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT;
                MIN 1;
                MAX 6;
                STEP 1;
                DEFAULT 3;
            }

            GROUP
            {
                DEFAULT 1;
                COLUMNS 3;

                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE;
                }
                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED;
                }
                BUTTON BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY
                {
                    NAME BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY;
                }
            }

            BOOL BRICKIFYASSEMBLY_HEIGHT_VARIATION
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION;
                DEFAULT 0;
            }

            LONG BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED;
                MIN 0;
                MAX 1000000;
                STEP 1;
                DEFAULT 1;
            }

            REAL BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.6;
            }

            BOOL BRICKIFYASSEMBLY_MERGE_PLATES
            {
                NAME BRICKIFYASSEMBLY_MERGE_PLATES;
                DEFAULT 1;
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_ADJUSTMENTS
        {
            DEFAULT 1;
            COLUMNS 1;

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

            BOOL BRICKIFYASSEMBLY_HUMANIZE_BRICKS
            {
                NAME BRICKIFYASSEMBLY_HUMANIZE_BRICKS;
                DEFAULT 0;
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

        GROUP BRICKIFYASSEMBLY_GROUP_DISPLAY
        {
            DEFAULT 1;
            COLUMNS 1;

            LONG BRICKIFYASSEMBLY_QUALITY
            {
                NAME BRICKIFYASSEMBLY_QUALITY;
                DEFAULT 3;
                CYCLE
                {
                    BRICKIFYASSEMBLY_QUALITY_PROXY;
                    BRICKIFYASSEMBLY_QUALITY_DRAFT;
                    BRICKIFYASSEMBLY_QUALITY_STANDARD;
                    BRICKIFYASSEMBLY_QUALITY_HERO;
                }
            }
        }

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

            LONG BRICKIFYASSEMBLY_LOGO_ROTATION
            {
                NAME BRICKIFYASSEMBLY_LOGO_ROTATION;
                DEFAULT 0;
                CYCLE
                {
                    BRICKIFYASSEMBLY_LOGO_ROTATION_0;
                    BRICKIFYASSEMBLY_LOGO_ROTATION_90;
                    BRICKIFYASSEMBLY_LOGO_ROTATION_180;
                    BRICKIFYASSEMBLY_LOGO_ROTATION_270;
                }
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

            REAL BRICKIFYASSEMBLY_BUILD_PROGRESS
            {
                NAME BRICKIFYASSEMBLY_BUILD_PROGRESS;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.01;
                DEFAULT 100.0;
            }

            REAL BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS
            {
                NAME BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS;
                CUSTOMGUI REALSLIDER;
                SCALE_H;
                MIN 0.0;
                MAX 100.0;
                STEP 0.01;
                DEFAULT 100.0;
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

            BOOL BRICKIFYASSEMBLY_BUILD_SCALE_IN
            {
                NAME BRICKIFYASSEMBLY_BUILD_SCALE_IN;
                DEFAULT 0;
            }

            BOOL BRICKIFYASSEMBLY_TOP_SURFACE_BLEND
            {
                NAME BRICKIFYASSEMBLY_TOP_SURFACE_BLEND;
                DEFAULT 0;
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
