# Cinema 4D 2026 — gotchas and conventions

Hard-won knowledge from this project that the official docs don't surface.
Authoritative API reference: <https://developers.maxon.net/docs/py/2026_2_0/index.html>.
Native SDK headers live under `C:/Dev/c4d_sdk_2026/frameworks/`.

Add a new entry every time we burn time on a non-obvious C4D quirk. Each entry:
**what we tried → what actually works → why** (so future-us doesn't have to
re-derive it).

---

## Description-resource (`.res`) grammar — different from dialog `.res`

Description files (under `res/description/o*.res`) and dialog files (under
`res/dialogs/`) **share the file extension but use different grammars**.
Keywords valid in one are silently/loudly rejected in the other.

When a description-resource parse fails, `LoadDescription(ID)` returns False
and the entire Attribute Manager goes blank for that object — no popup, no
console error unless your plugin logs one.

### What works in description `.res`

- `GROUP { DEFAULT 1; COLUMNS N; ... }` — N-column flow
- `SCALE_H;` on the parent — fill the AM width
- `IN_EXCLUDE PARAM_ID { NAME ...; CUSTOMGUI X; ACCEPT { Obase; } }` —
  declare an InExcludeData parameter; the `CUSTOMGUI` *attribute inside the
  block* swaps the renderer to a custom GUI plugin
- `STATICTEXT PARAM_ID { NAME ...; }` — works as an empty-column spacer
  inside a multi-column parent **as long as the parent is a flat
  COLUMNS N group** (see next section).

### Justified responsive 2-column layout — flat is the only structure that works

This is the canonical pattern (lifted from Maxon's `ohairsdkgen.res`):

```
GROUP MY_GROUP
{
    COLUMNS 2;
    DEFAULT 1;
    SCALE_H;

    LONG  PARAM_A { ... SCALE_H; CYCLE { ... } }   // row 1, col 1
    BUTTON PARAM_B { ... SCALE_H; }                // row 1, col 2

    REAL  PARAM_C { ... SCALE_H; }                 // row 2, col 1
    BOOL  PARAM_D { ... }                          // row 2, col 2

    BOOL  PARAM_E { ... }                          // row 3, col 1
    STATICTEXT SPACER_1 { NAME SPACER_1; }         // row 3, col 2 (empty)
}
```

Widgets stream directly into the parent row-by-row, alternating columns.
Empty cells use a `STATICTEXT` placeholder with an empty NAME string in
the `.str` file.

**What does NOT work:** wrapping each column's contents in its own
`GROUP { COLUMNS 1; SCALE_H; ... }`. Tried every combination of
`LAYOUTGROUP`, `SCALE_H` on parent + inner groups + individual gadgets —
the layout engine treats each inner group as a single cell, sizes it to
its widest child, and the result is a left-aligned non-responsive block.
LAYOUTGROUP makes COLUMNS N flow nested groups across columns, but
those columns refuse to claim half the AM width regardless.

**The takeaway:** for a real 50/50 justified layout, flatten the structure
and stream widgets row-by-row into a flat `COLUMNS N` parent. If the rows
need different widget counts (e.g. left col has 4 widgets, right col has
2), pad the right column with `STATICTEXT` empty-name spacers.

**Booleans need SCALE_H too.** Easy to forget on `BOOL` widgets because
they're "just a checkbox", but without `SCALE_H` they pin to their label
and the cell collapses around the checkbox — leaving a wide gap before
the next column. Apply `SCALE_H` to *every* widget in a 2-column group
that should claim its half of the AM width.

### Multi-button row inline with a field — doesn't fit cleanly

Wanted: `Field | [Button1] [Button2] [Button3]` on one row. C4D's
description grammar makes this hard because:

- Putting the buttons in a `GROUP { COLUMNS 3; ... }` as a single cell
  of a flat `COLUMNS 2` parent → the sub-group overflows to a full-width
  row UNDERNEATH the field instead of staying in the right cell.
- Adding `LAYOUTGROUP` to the buttons sub-group → the buttons VANISH
  entirely (the engine treats LAYOUTGROUP as making the group truly
  inline, but apparently with zero width allocation in this case).
- Streaming the buttons as direct cells of a `COLUMNS 2` parent → they
  break across rows (B1 col2 row1, B2 col1 row2, B3 col2 row2) which
  isn't what we want.
- Restructuring the whole parent as `COLUMNS 4` to fit field-plus-3-buttons
  in one row → conflicts with other rows in the group that expect 2 cells.

Conclusion: when you have a multi-button preset row, **keep it as a
full-width row beneath its field** (the 1-column parent + COLUMNS 3
sub-group pattern, which is what C4D's own examples do). The
right-of-the-field placement isn't worth the layout-engine fight.

### `LAYOUTGROUP` in description `.res`

Useful when nested groups DO need to flow across columns instead of
stacking vertically — e.g. a `COLUMNS 3` parent containing three inner
GROUPs that each hold a stacked sub-form, and you want the three GROUPs
side by side. But this still gives left-aligned columns, not justified
50/50 columns.

**Don't** combine `LAYOUTGROUP` with the flat-columns layout above —
flat already flows correctly without it.

### What does NOT work in description `.res`

- `SPACE H, V;` — dialog-only. In a description file this kills the parse
  and blanks the AM.
- `CUSTOMGUI BLOCK_TYPE { ... }` as a top-level declaration. There's no
  such top-level keyword. To plug in a custom GUI for an InExcludeData
  parameter, declare it as `IN_EXCLUDE PARAM_ID { CUSTOMGUI XYZ; ... }`.
- Using a `STATICTEXT` parameter slot as an "empty middle column" spacer
  with a declared-but-otherwise-unused ID (e.g. `BRICKIFYASSEMBLY_SPACER_1`)
  *also* killed the parse — the description grammar wants every referenced
  parameter ID to be a real usable slot, not a placeholder. So there's no
  clean inline-grammar way to add a column gap. Accept C4D's natural
  column spacing or, if you really need separation, allocate a real
  `STATICTEXT` parameter with an empty NAME string in `obrickifyassembly.str`.

### Where to find the truth

The C4D SDK ships description-resource examples under
`C:/Dev/c4d_sdk_2026/plugins/example.main/res/description/`. Dialog
examples live next door under `res/dialogs/`. **Don't copy a syntax pattern
from a dialog example into a description file** without checking it works
in description grammar first.

---

## `iCustomGui` and `GeUserArea` — message routing

`iCustomGui` inherits `GeDialog` (via `SubDialog`). `GeUserArea` is a
canvas attached to a gadget inside a dialog. They get different messages.

| Message | Routes to |
|---|---|
| `BFM_INPUT` mouse | `GeUserArea::InputEvent` (the area the cursor is over) |
| `BFM_INPUT` keyboard | `GeDialog::Message` / `iCustomGui::Message`, only when the dialog has focus |
| `BFM_DRAGRECEIVE` (drag-drop) | `GeDialog::Message` / `iCustomGui::Message`, NOT `GeUserArea` directly |
| `EVMSG_CHANGE`, `EVMSG_DOCUMENTRECALCULATED` | `GeDialog::CoreMessage` / `iCustomGui::CoreMessage`. **`GeUserArea::CoreMessage` does NOT reliably receive these** — the AM only forwards core messages to the hosting dialog |

Practical: scene-graph reactions (auto-append on parent-under-host, redraw
on scene change, etc.) belong on `iCustomGui::CoreMessage`, not on the
user area's own `CoreMessage`.

### `GeUserArea` does not get keyboard focus from clicks

There's no `SetFocus()` on `GeUserArea`. To handle Delete/Backspace etc.
inside a custom user area, intercept `BFM_INPUT` with
`device == BFM_INPUT_KEYBOARD` in the parent `iCustomGui::Message` and
inspect `_selectedRow` / your own selection state. Don't try to make the
user area itself focusable.

### Drag-drop accept pattern

Override `iCustomGui::Message`. On `BFM_DRAGRECEIVE`:

1. `GetDragPosition(msg, &dx, &dy)` and hit-test against your gadget's
   bounds via `GetItemDim(gadget_id, &x, &y, &w, &h)`.
2. `GetDragObject(msg, &type, &object)` — for OM objects, `type ==
   DRAGTYPE_ATOMARRAY`, `object` casts to `AtomArray*`.
3. While hovering (no `BFM_DRAG_FINISHED` flag): return
   `SetDragDestination(MOUSE_POINT_HAND)` to show "accept" cursor; return
   `false` to show "reject."
4. On `BFM_DRAG_FINISHED`: do the actual append/insert, then return
   `SetDragDestination(MOUSE_POINT_HAND)`.

---

## Popup menus (`ShowPopupMenu`)

The menu's `BaseContainer` keys have grammar:

| ID range | Meaning |
|---|---|
| `0` | Menu's empty string (skip) |
| `1` | The menu's *own title* (for sub-menus) — **NOT a menu item** |
| `2` to `899999` | Cinema 4D command IDs (existing commands) |
| `900000` to `999999` (`FIRST_POPUP_ID` and up) | **Custom user items — use this range** |
| `1000000+` | Plugin command IDs |

Symptom of getting this wrong: putting your "do thing" item at ID `1`
makes the popup render as a tiny black square because there's no real
item — the "Remove from list" string was eaten as the menu's title.

Sub-menus go in via `mainmenu.SetContainer(submenu_id, submenu_bc)`.

---

## String types — `cinema::String` vs. `maxon::String`

The C++ SDK has two `String` types in different namespaces. Literal
suffix `"text"_s` produces a `maxon::String`. C4D method returns
(`obj->GetName()`, `String::IntToString(...)`) produce `cinema::String`.
Mixing them in one `+` chain throws `error C2666: 'maxon::operator +':
overloaded functions have similar conversions`.

Fix: wrap each literal in `cinema::String("...")` so the whole expression
stays in one namespace:

```cpp
GePrint(cinema::String("[brick] Source rejected: '") + obj->GetName() + cinema::String("')"));
```

---

## Cycle filter for "object as source of generator"

Pattern: a generator that bakes its inputs (Volume Builder, BrickIt,
anything walking `obj->GetDown()` and CSTOing the result) freezes if its
input list contains:

- The generator itself
- Another generator of the same type (each one's GVO triggers the other's,
  ad infinitum)
- An ANCESTOR of the generator. Baking `obj` walks `obj`'s entire subtree,
  which contains the generator, which re-triggers the generator's GVO

The cycle direction matters: an object being *inside* the generator's
subtree (e.g. a direct child) is NOT a cycle — that's the intended
auto-append path. The freeze case is the **reverse**: the input would
CSTO through the generator on its way down.

Filter implementation:

```cpp
// Reject if obj is host, is another instance of host's type, or is an
// ancestor of host. Walk from host UP looking for obj.
for (BaseObject* a = host->GetUp(); a != nullptr; a = a->GetUp())
    if (a == obj) return /* reject */;
```

Same logic mirrored in Python: walk `host.GetUp()` up the chain.

---

## `BMP_ALLOWALPHA` blends with the current pen color

`DrawBitmap(..., BMP_ALLOWALPHA | BMP_NORMALSCALED)` blends the bitmap's
transparent pixels against whatever color was last set with `DrawSetPen`.
Set the pen to your row/cell background **just before** the bitmap blit so
alpha-transparent corners pick up the row color rather than the AM's
default backdrop:

```cpp
DrawSetPen(rowBg);
DrawBitmap(icon, x, y, w, h, srcX, srcY, srcW, srcH,
           BMP_ALLOWALPHA | BMP_NORMALSCALED);
```

Atlas-baked icon backdrops (some C4D OM icons have a solid background
baked into the bitmap) won't be removed by this — that's a property of
the source bitmap, not the blit flag.

---

## Plugin ID conventions

| ID | What |
|---|---|
| `1069998` | `ID_BRICKIFYASSEMBLY` — BrickIt object |
| `1069999` | `ID_BRICKGENERATOR` — Brick generator |
| `1069997` | `ID_BRICKLIBRARYPANEL` — Brick library panel |
| `1069996` | `g_bricksources_customgui_id` — sources list custom GUI |
| `1069995` | `ID_BRICKIT_EFFECTORS_AUTOHOOK` |
| `1069994` | `ID_BRICKIT_FOLLOW_SURFACE_TAG` |
| `1070996` | (custom GUI) — also bricksources, native registration |
| `1070997` | `g_bricklibrary_customgui_id` — library thumbnail GUI |
| `1070998` | `g_brickhero_customgui_id` — hero banner GUI |
| `1070999` | `g_brick_mograph_evaluator_tag_id` |

Plugin IDs must be registered with Maxon to avoid collisions across
plugins. The `1069994..1070999` block is ours.
