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

        }

        GROUP BRICKIFYASSEMBLY_GROUP_RESOLUTION
        {
            DEFAULT 1;
            COLUMNS 1;

            REAL BRICKIFYASSEMBLY_VOXEL_RESOLUTION
            {
                NAME BRICKIFYASSEMBLY_VOXEL_RESOLUTION;
                MIN 0.1;
                MAX 1.0;
                STEP 0.01;
                DEFAULT 0.8;
            }

            BOOL BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE
            {
                NAME BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE;
                DEFAULT 0;
            }

            REAL BRICKIFYASSEMBLY_STUD_SIZE
            {
                NAME BRICKIFYASSEMBLY_STUD_SIZE;
                MIN 0.001;
                MAX 100000.0;
                STEP 0.1;
                DEFAULT 8.0;
            }

            SEPARATOR {}
            SEPARATOR {}
            SEPARATOR {}
            SEPARATOR {}
            SEPARATOR {}
            SEPARATOR {}

            BUTTON BRICKIFYASSEMBLY_REBUILD
            {
                NAME BRICKIFYASSEMBLY_REBUILD;
            }

            BOOL BRICKIFYASSEMBLY_AUTO_REBUILD
            {
                NAME BRICKIFYASSEMBLY_AUTO_REBUILD;
                DEFAULT 1;
            }
        }

        GROUP BRICKIFYASSEMBLY_GROUP_VOXEL
        {
            DEFAULT 1;

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
        }

        GROUP BRICKIFYASSEMBLY_GROUP_BRICK_FITTING
        {
            DEFAULT 1;

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

        GROUP BRICKIFYASSEMBLY_GROUP_HEIGHT_MIX
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKIFYASSEMBLY_HEIGHT_VARIATION
            {
                NAME BRICKIFYASSEMBLY_HEIGHT_VARIATION;
                DEFAULT 0;
            }

            LONG BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT
            {
                NAME BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT;
                MIN 1;
                MAX 6;
                STEP 1;
                DEFAULT 3;
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
        }

        GROUP BRICKIFYASSEMBLY_GROUP_DISPLAY
        {
            DEFAULT 1;

            LONG BRICKIFYASSEMBLY_COLOR_MODE
            {
                NAME BRICKIFYASSEMBLY_COLOR_MODE;
                DEFAULT 1;
                CYCLE
                {
                    BRICKIFYASSEMBLY_COLOR_MODE_NONE;
                    BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL;
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
        }

        GROUP BRICKIFYASSEMBLY_GROUP_ACTIONS
        {
            DEFAULT 1;
            COLUMNS 2;

            BOOL BRICKIFYASSEMBLY_MERGE_PLATES
            {
                NAME BRICKIFYASSEMBLY_MERGE_PLATES;
                DEFAULT 1;
            }

            BOOL BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY
            {
                NAME BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY;
                DEFAULT 1;
            }

            BOOL BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS
            {
                NAME BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS;
                DEFAULT 0;
            }

            BOOL BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES
            {
                NAME BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES;
                DEFAULT 1;
            }

            BOOL BRICKIFYASSEMBLY_ENABLE_PLATES
            {
                NAME BRICKIFYASSEMBLY_ENABLE_PLATES;
                DEFAULT 0;
            }
        }

    }
}
