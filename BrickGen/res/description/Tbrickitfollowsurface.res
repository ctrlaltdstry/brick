CONTAINER Tbrickitfollowsurface
{
    NAME Tbrickitfollowsurface;

    INCLUDE Texpression;

    GROUP ID_TAGPROPERTIES
    {
        DEFAULT 1;
        COLUMNS 1;

        BOOL BRICKIT_FOLLOW_SURFACE_ENABLED
        {
            NAME BRICKIT_FOLLOW_SURFACE_ENABLED;
            DEFAULT 1;
        }

        LINK BRICKIT_FOLLOW_SURFACE_SOURCE
        {
            NAME BRICKIT_FOLLOW_SURFACE_SOURCE;
            ACCEPT { Obase; }
        }

        LONG BRICKIT_FOLLOW_SURFACE_ORIENT_MODE
        {
            NAME BRICKIT_FOLLOW_SURFACE_ORIENT_MODE;
            DEFAULT 0;
            CYCLE
            {
                BRICKIT_FOLLOW_SURFACE_ORIENT_WORLD_UP;
                BRICKIT_FOLLOW_SURFACE_ORIENT_FOLLOW_NORMAL;
            }
        }

        REAL BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING
        {
            NAME BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING;
            CUSTOMGUI REALSLIDER;
            SCALE_H;
            MIN 0.0;
            MAX 1.0;
            STEP 0.01;
            DEFAULT 0.7;
        }

        BUTTON BRICKIT_FOLLOW_SURFACE_BAKE_BUTTON
        {
            NAME BRICKIT_FOLLOW_SURFACE_BAKE_BUTTON;
        }

        LONG BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY
        {
            NAME BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY;
            DEFAULT 2;
            CYCLE
            {
                BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY_DRAFT;
                BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY_STANDARD;
                BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY_HERO;
            }
        }

        BUTTON BRICKIT_FOLLOW_SURFACE_SWAP_HERO_BUTTON
        {
            NAME BRICKIT_FOLLOW_SURFACE_SWAP_HERO_BUTTON;
        }

        LINK BRICKIT_FOLLOW_SURFACE_BRICKIT_OP
        {
            NAME BRICKIT_FOLLOW_SURFACE_BRICKIT_OP;
            ACCEPT { Obase; }
            HIDDEN;
        }

        STRING BRICKIT_FOLLOW_SURFACE_RECORDS
        {
            NAME BRICKIT_FOLLOW_SURFACE_RECORDS;
            HIDDEN;
        }
    }
}
