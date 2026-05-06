CONTAINER obrickgenerator
{
    NAME BRICKGENERATOR;
    INCLUDE Obase;

    GROUP ID_OBJECTPROPERTIES
    {
        BUTTON BRICKGENERATOR_OPEN_USER_MANUAL
        {
            NAME BRICKGENERATOR_OPEN_USER_MANUAL;
        }

        LONG BRICKGENERATOR_TYPE
        {
            NAME BRICKGENERATOR_TYPE;
            DEFAULT 0;
            CYCLE
            {
                BRICKGENERATOR_TYPE_BRICK;
                BRICKGENERATOR_TYPE_PLATE;
            }
        }

        LONG BRICKGENERATOR_WIDTH
        {
            NAME BRICKGENERATOR_WIDTH;
            MIN 1;
            MAX 32;
            STEP 1;
            DEFAULT 2;
            CUSTOMGUI LONGSLIDER;
        }

        LONG BRICKGENERATOR_DEPTH
        {
            NAME BRICKGENERATOR_DEPTH;
            MIN 1;
            MAX 32;
            STEP 1;
            DEFAULT 4;
            CUSTOMGUI LONGSLIDER;
        }

        LONG BRICKGENERATOR_HEIGHT
        {
            NAME BRICKGENERATOR_HEIGHT;
            MIN 1;
            MAX 24;
            STEP 1;
            DEFAULT 3;
            CUSTOMGUI LONGSLIDER;
        }

        LONG BRICKGENERATOR_QUALITY
        {
            NAME BRICKGENERATOR_QUALITY;
            DEFAULT 1;
            CYCLE
            {
                BRICKGENERATOR_QUALITY_PROXY;
                BRICKGENERATOR_QUALITY_DRAFT;
                BRICKGENERATOR_QUALITY_STANDARD;
                BRICKGENERATOR_QUALITY_HERO;
            }
        }

        GROUP BRICKGENERATOR_GROUP_LOGO
        {
            DEFAULT 1;
            COLUMNS 1;

            BOOL BRICKGENERATOR_ENABLE_LOGO
            {
                NAME BRICKGENERATOR_ENABLE_LOGO;
                DEFAULT 0;
            }

            LINK BRICKGENERATOR_LOGO_SOURCE
            {
                NAME BRICKGENERATOR_LOGO_SOURCE;
                ACCEPT { Obase; }
            }

            REAL BRICKGENERATOR_LOGO_ROTATION
            {
                NAME BRICKGENERATOR_LOGO_ROTATION;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 360.0;
                STEP 1.0;
                DEFAULT 0.0;
            }

            REAL BRICKGENERATOR_LOGO_DIAMETER
            {
                NAME BRICKGENERATOR_LOGO_DIAMETER;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 100.0;
                STEP 1.0;
                DEFAULT 0.0;
            }

            REAL BRICKGENERATOR_LOGO_HEIGHT
            {
                NAME BRICKGENERATOR_LOGO_HEIGHT;
                CUSTOMGUI REALSLIDER;
                MIN 0.02;
                MAX 0.25;
                STEP 0.01;
                DEFAULT 0.06;
            }

            REAL BRICKGENERATOR_LOGO_BLEND
            {
                NAME BRICKGENERATOR_LOGO_BLEND;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 1.0;
                STEP 0.05;
                DEFAULT 1.0;
            }

            REAL BRICKGENERATOR_LOGO_SINK
            {
                NAME BRICKGENERATOR_LOGO_SINK;
                CUSTOMGUI REALSLIDER;
                MIN 0.0;
                MAX 0.05;
                STEP 0.001;
                DEFAULT 0.015;
            }
        }
    }
}
