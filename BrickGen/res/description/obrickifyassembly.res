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

            STATICTEXT BRICKIFYASSEMBLY_GROUP_LIBRARY_PRESETS
            {
                NAME BRICKIFYASSEMBLY_GROUP_LIBRARY_PRESETS;
            }

            GROUP BRICKIFYASSEMBLY_GROUP_LIBRARY_GRID
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

            BOOL BRICKIFYASSEMBLY_ENABLE_PLATES
            {
                NAME BRICKIFYASSEMBLY_ENABLE_PLATES;
                DEFAULT 0;
            }

        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_SHAPE
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

        SEPARATOR {}
        SEPARATOR {}

        BOOL BRICKIFYASSEMBLY_AUTO_REBUILD
        {
            NAME BRICKIFYASSEMBLY_AUTO_REBUILD;
            DEFAULT 1;
        }

        BUTTON BRICKIFYASSEMBLY_REBUILD
        {
            NAME BRICKIFYASSEMBLY_REBUILD;
        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_LAYOUT
    {
        DEFAULT 1;
        COLUMNS 1;

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

        LONG BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT
        {
            NAME BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT;
            MIN 1;
            MAX 6;
            STEP 1;
            DEFAULT 3;
        }

        GROUP BRICKIFYASSEMBLY_GROUP_HEIGHT_PRESETS
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

        BOOL BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY
        {
            NAME BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY;
            DEFAULT 0;
        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_PREVIEW
    {
        DEFAULT 1;
        COLUMNS 1;

        LONG BRICKIFYASSEMBLY_QUALITY
        {
            NAME BRICKIFYASSEMBLY_QUALITY;
            DEFAULT 1;
            CYCLE
            {
                BRICKIFYASSEMBLY_QUALITY_DRAFT;
                BRICKIFYASSEMBLY_QUALITY_STANDARD;
                BRICKIFYASSEMBLY_QUALITY_HERO;
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

        BOOL BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES
        {
            NAME BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES;
            DEFAULT 1;
        }

        BOOL BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS
        {
            NAME BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS;
            DEFAULT 0;
        }
    }

    GROUP BRICKIFYASSEMBLY_TAB_MOGRAPH
    {
        DEFAULT 1;
        COLUMNS 1;

        BUTTON BRICKIFYASSEMBLY_CREATE_MOGRAPH
        {
            NAME BRICKIFYASSEMBLY_CREATE_MOGRAPH;
        }
    }

}
