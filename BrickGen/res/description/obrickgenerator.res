CONTAINER obrickgenerator
{
    NAME BRICKGENERATOR;
    INCLUDE Obase;

    GROUP ID_OBJECTPROPERTIES
    {
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
                BRICKGENERATOR_QUALITY_DRAFT;
                BRICKGENERATOR_QUALITY_STANDARD;
                BRICKGENERATOR_QUALITY_HERO;
            }
        }
    }
}
