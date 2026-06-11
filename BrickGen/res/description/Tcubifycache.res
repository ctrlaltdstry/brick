CONTAINER Tcubifycache
{
    NAME Tcubifycache;

    INCLUDE Texpression;

    GROUP ID_TAGPROPERTIES
    {
        DEFAULT 1;
        COLUMNS 1;

        // When enabled, the Cubify object plays the cached per-frame fit
        // stored on this tag. Disable to fall back to normal behavior.
        BOOL CUBIFY_CACHE_ENABLED
        {
            NAME CUBIFY_CACHE_ENABLED;
            DEFAULT 1;
        }

        // Read-only status (frame count etc.), filled in by the bake.
        STRING CUBIFY_CACHE_INFO
        {
            NAME CUBIFY_CACHE_INFO;
            CUSTOMGUI STATICTEXT;
        }

        // Hidden: serialized per-frame fit cache, saved with the scene.
        STRING CUBIFY_CACHE_BLOB
        {
            NAME CUBIFY_CACHE_BLOB;
            HIDDEN;
        }
    }
}
