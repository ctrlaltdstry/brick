#include "c4d.h"
#include "c4d_baseeffectordata.h"
#include "c4d_customgui/customgui_field.h"
#include "c4d_customgui/customgui_inexclude.h"
#include "c4d_gui.h"
#include "c4d_plugin.h"
#include "c4d_resource.h"
#include "description/obaseeffector.h"
#include "description/ofalloff_panel.h"
#include <algorithm>
#include <array>
#include <functional>
#include <vector>

using namespace cinema;

static const Int32 g_bricklibrary_panel_cmd_id = 1069996;
static const Int32 g_bricklibrary_customgui_id = 1070997;
static const Int32 g_brickhero_customgui_id = 1070998;
static const Int32 g_bricksources_customgui_id = 1070996;
static const Int32 g_brick_mograph_evaluator_tag_id = 1070999;
static const Int32 g_brick_mograph_evaluate_msg_id = 1071999;
static const Int32 g_brick_mograph_eval_count = 1000;
static const Int32 g_brick_mograph_eval_effectors = 1001;
static const Int32 g_brick_mograph_eval_ok = 1002;
static const Int32 g_brick_mograph_eval_generator = 1003;
static const Int32 g_brick_mograph_eval_color_changed = 1004;
static const Int32 g_brick_mograph_eval_field_color_applied = 1005;
static const Int32 g_brick_mograph_eval_field_color_mode_count = 1006;
static const Int32 g_brick_mograph_eval_skip_field_override = 1007;
static const Int32 g_brick_mograph_eval_effector_color_changed = 1008;
static const Int32 g_brick_mograph_eval_post_field_color_changed = 1009;
static const Int32 g_brick_mograph_eval_manual_field_skipped = 1010;
static const Int32 g_brick_mograph_eval_sample_count = 1011;
static const Int32 g_brick_mograph_eval_visibility_changed = 1012;
static const Int32 g_brick_mograph_eval_in_matrix_base = 200000;
static const Int32 g_brick_mograph_eval_in_color_base = 300000;
static const Int32 g_brick_mograph_eval_out_matrix_base = 400000;
static const Int32 g_brick_mograph_eval_out_color_base = 500000;
static const Int32 g_brick_mograph_eval_effector_color_sample_base = 600000;
static const Int32 g_brick_mograph_eval_field_color_sample_base = 601000;
static const Int32 g_brick_mograph_eval_out_visible_base = 700000;
static const Int32 g_brick_count = 15;
static const Int32 g_cols = 6;
static const Int32 g_userarea_id = 2000;
static const Int32 g_hero_userarea_id = 3000;
static const Int32 g_sources_userarea_id = 4000;
static const Int32 g_library_min_width = 420;
static const Int32 g_library_grid_height = 252;
static const Int32 g_sources_min_width = 240;
static const Int32 g_sources_min_height = 120;
static const Int32 g_sources_row_height = 22;
// Mode region holds the 16px icon plus the label text ("Intersect" is the
// widest at ~50px on default font). 96px gives the icon + 6px gap + label
// + a few px slack so the longest mode word doesn't truncate.
static const Int32 g_sources_mode_button_width = 96;
static const Int32 g_brickit_op_id = 1069998;
static const Int32 g_brick_source_mode_union = 0;
static const Int32 g_brick_source_mode_subtract = 1;
static const Int32 g_brick_source_mode_intersect = 2;
// Per-entry flag layout in InExcludeData.GetFlags() — bits 0-1 hold Mode,
// bit 2 holds AUTO_ADDED. See BrickGen/c4d_symbols.py for the canonical
// definition; these C++ constants must stay in sync.
static const Int32 g_brick_source_mode_mask = 3;
static const Int32 g_brick_source_flag_auto_added = 4;

// ---------------------------------------------------------------------------
// Design-system palette (see .claude/design-system.md). Applies to every
// custom-painted UserArea in this plugin. Don't introduce ad-hoc Vectors in
// DrawMsg — pull from these constants so the surfaces stay coherent and a
// single edit here propagates everywhere. C4D's DrawSetPen takes 0..1
// floats; values below match the hex tokens (#1F1F1F = 31/255 = 0.1216, etc).
//
// Only the tokens currently used by DrawMsg are listed. When you reach for a
// new role (surface-3 for an input bg, accent-hover for hover state, etc.),
// add it here from the design-system doc rather than inlining the literal.
// ---------------------------------------------------------------------------

static const Vector g_ds_surface_0      = Vector(0.1216, 0.1216, 0.1216); // #1F1F1F
static const Vector g_ds_surface_1      = Vector(0.1647, 0.1647, 0.1647); // #2A2A2A
static const Vector g_ds_surface_2      = Vector(0.2078, 0.2078, 0.2078); // #353535
static const Vector g_ds_accent         = Vector(0.1725, 0.4863, 0.8275); // #2C7CD3
static const Vector g_ds_text_primary   = Vector(0.8471, 0.8471, 0.8471); // #D8D8D8
static const Vector g_ds_text_secondary = Vector(0.5961, 0.5961, 0.5961); // #989898
static const Vector g_ds_divider        = Vector(0.1020, 0.1020, 0.1020); // #1A1A1A
static const Vector g_ds_border_subtle  = Vector(0.2510, 0.2510, 0.2510); // #404040

static const Char* g_brick_labels[g_brick_count] = {
	"1x1", "1x2", "1x3", "1x4", "1x6", "1x8",
	"2x2", "2x3", "2x4", "2x6", "2x8",
	"3x3", "3x4", "3x6", "3x8"
};
static const Char* g_brick_asset_names[g_brick_count] = {
	"brick_1x1", "brick_1x2", "brick_1x3", "brick_1x4", "brick_1x6", "brick_1x8",
	"brick_2x2", "brick_2x3", "brick_2x4", "brick_2x6", "brick_2x8",
	"brick_3x3", "brick_3x4", "brick_3x6", "brick_3x8"
};

class BrickLibraryCustomGui;

class BrickLibraryThumbUserArea : public GeUserArea
{
public:
	void SetOwner(BrickLibraryCustomGui* owner) { _owner = owner; }
	virtual Bool GetMinSize(Int32& w, Int32& h) override;
	virtual void DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg) override;
	virtual Bool InputEvent(const BaseContainer& msg) override;

private:
	BrickLibraryCustomGui* _owner = nullptr;
};

class BrickLibraryCustomGui : public iCustomGui
{
	INSTANCEOF(BrickLibraryCustomGui, iCustomGui)

public:
	BrickLibraryCustomGui(const BaseContainer& settings, CUSTOMGUIPLUGIN* plugin) : iCustomGui(settings, plugin)
	{
		_area.SetOwner(this);
		LoadThumbnails();
	}

	virtual ~BrickLibraryCustomGui()
	{
		for (Int32 i = 0; i < g_brick_count; ++i)
		{
			if (_thumbs[i] != nullptr)
			{
				BaseBitmap* bmp = _thumbs[i];
				BaseBitmap::Free(bmp);
				_thumbs[i] = nullptr;
			}
		}
	}

	virtual Bool CreateLayout() override
	{
		GroupBegin(1000, BFH_SCALEFIT | BFV_TOP, 1, 0, ""_s, 0);
		GroupBorderSpace(0, 0, 0, 0);
		C4DGadget* gadget = AddUserArea(g_userarea_id, BFH_SCALEFIT | BFV_TOP, g_library_min_width, g_library_grid_height);
		AttachUserArea(_area, gadget);
		GroupEnd();
		return SUPER::CreateLayout();
	}

	virtual Bool InitValues() override
	{
		_area.Redraw();
		return true;
	}

	virtual Bool SetData(const TriState<GeData>& tristate) override
	{
		_bitmask = tristate.GetValue().GetInt32();
		_tristate = tristate.GetTri();
		return InitValues();
	}

	virtual TriState<GeData> GetData() override
	{
		TriState<GeData> tri;
		tri.Add(GeData(_bitmask));
		return tri;
	}

	void ToggleIndex(Int32 idx)
	{
		if (idx < 0 || idx >= g_brick_count)
			return;

		_bitmask ^= (1 << idx);
		_tristate = false;
		InitValues();

		BaseContainer action(BFM_ACTION);
		action.SetInt32(BFM_ACTION_ID, GetId());
		action.SetData(BFM_ACTION_VALUE, GeData(_bitmask));
		SendParentMessage(action);
	}

	Bool IsEnabled(Int32 idx) const
	{
		if (idx < 0 || idx >= g_brick_count)
			return false;
		return (_bitmask & (1 << idx)) != 0;
	}

	BaseBitmap* GetThumbnail(Int32 idx) const
	{
		if (idx < 0 || idx >= g_brick_count)
			return nullptr;
		return _thumbs[idx];
	}

	Int32 GetHoverIndex() const
	{
		return _hoverIndex;
	}

	void SetHoverIndex(Int32 idx)
	{
		const Int32 clamped = (idx >= 0 && idx < g_brick_count) ? idx : -1;
		if (_hoverIndex == clamped)
			return;
		_hoverIndex = clamped;
		_area.Redraw();
	}

private:
	void LoadThumbnails()
	{
		const Filename pluginPath = GeGetPluginPath();
		const Filename pluginDir = pluginPath.GetDirectory();
		const Filename roots[4] = {
			pluginPath + Filename("res") + Filename("icons") + Filename("bricks"),
			pluginDir + Filename("res") + Filename("icons") + Filename("bricks"),
			pluginDir + Filename("Brick") + Filename("res") + Filename("icons") + Filename("bricks"),
			pluginDir + Filename("BrickGen") + Filename("res") + Filename("icons") + Filename("bricks"),
		};

		for (Int32 i = 0; i < g_brick_count; ++i)
		{
			BaseBitmap* bmp = nullptr;
			const String base = String(g_brick_asset_names[i]);
			const String candidates[3] = {
				base + String("@64.png"),
				base + String("@2x.png"),
				base + String(".png")
			};

			for (const Filename& root : roots)
			{
				for (const String& fileName : candidates)
				{
					const Filename filePath = root + Filename(fileName);
					if (!GeFExist(filePath, false))
						continue;

					BaseBitmap* tryBmp = BaseBitmap::Alloc();
					if (!tryBmp)
						continue;
					if (tryBmp->Init(filePath) == IMAGERESULT::OK && tryBmp->GetBw() > 0 && tryBmp->GetBh() > 0)
					{
						bmp = tryBmp;
						break;
					}
					BaseBitmap::Free(tryBmp);
				}
				if (bmp != nullptr)
					break;
			}

			_thumbs[i] = bmp;
		}
	}

	friend class BrickLibraryThumbUserArea;
	BrickLibraryThumbUserArea _area;
	std::array<BaseBitmap*, g_brick_count> _thumbs = {};
	Int32 _bitmask = 0;
	Int32 _hoverIndex = -1;
	Bool _tristate = false;
};

Bool BrickLibraryThumbUserArea::GetMinSize(Int32& w, Int32& h)
{
	w = 420;
	h = g_library_grid_height;
	return true;
}

void BrickLibraryThumbUserArea::DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg)
{
	OffScreenOn();

	Int32 w = GetWidth();
	Int32 h = GetHeight();
	if (w <= 0 || h <= 0)
		return;

	// Container surface = surface-0, matching the sources list and the
	// design-system rule that deepest content layers use surface-0.
	DrawSetPen(g_ds_surface_0);
	DrawRectangle(0, 0, w, h);

	const Int32 rows = (g_brick_count + g_cols - 1) / g_cols;
	const Int32 cellByWidth = (g_cols > 0) ? (w / g_cols) : 0;
	const Int32 cellByHeight = (rows > 0) ? (h / rows) : 0;
	const Int32 cellSize = (cellByWidth < cellByHeight) ? cellByWidth : cellByHeight;
	if (cellSize <= 0)
		return;
	const Int32 gridX = 0;
	const Int32 gridY = 0;
	const Int32 tileOuterPad = 2;
	const Int32 tileInnerPad = 0;

	for (Int32 i = 0; i < g_brick_count; ++i)
	{
		const Int32 col = i % g_cols;
		const Int32 row = i / g_cols;

		const Int32 xStart = gridX + col * cellSize + tileOuterPad;
		const Int32 yStart = gridY + row * cellSize + tileOuterPad;
		const Int32 xEnd = gridX + (col + 1) * cellSize - tileOuterPad - 1;
		const Int32 yEnd = gridY + (row + 1) * cellSize - tileOuterPad - 1;
		const Int32 innerX0 = xStart + tileInnerPad;
		const Int32 innerY0 = yStart + tileInnerPad;
		const Int32 innerX1 = xEnd - tileInnerPad;
		const Int32 innerY1 = yEnd - tileInnerPad;

		const Bool enabled = _owner && _owner->IsEnabled(i);

		// Tile background = surface-1 (one stop above the surface-0 grid).
		DrawSetPen(g_ds_surface_1);
		DrawRectangle(xStart, yStart, xEnd, yEnd);

		BaseBitmap* bmp = _owner ? _owner->GetThumbnail(i) : nullptr;
		if (bmp != nullptr)
		{
			const Int32 imgAreaX0 = innerX0;
			const Int32 imgAreaY0 = innerY0;
			const Int32 imgAreaX1 = innerX1;
			const Int32 imgAreaY1 = innerY1;
			const Int32 areaW = Max(1, imgAreaX1 - imgAreaX0 + 1);
			const Int32 areaH = Max(1, imgAreaY1 - imgAreaY0 + 1);

			const Int32 bw = Max(1, bmp->GetBw());
			const Int32 bh = Max(1, bmp->GetBh());
			const Float dstAspect = Float(areaW) / Float(areaH);
			const Float srcAspect = Float(bw) / Float(bh);
			Int32 srcX = 0;
			Int32 srcY = 0;
			Int32 srcW = bw;
			Int32 srcH = bh;

			// Center-crop cover: always fill the full thumbnail area edge-to-edge.
			if (srcAspect > dstAspect)
			{
				srcW = Max(1, Int32(Float(bh) * dstAspect));
				srcX = Max(0, (bw - srcW) / 2);
			}
			else if (srcAspect < dstAspect)
			{
				srcH = Max(1, Int32(Float(bw) / dstAspect));
				srcY = Max(0, (bh - srcH) / 2);
			}

			DrawBitmap(
				bmp,
				imgAreaX0, imgAreaY0,
				areaW, areaH,
				srcX, srcY, srcW, srcH,
				BMP_NORMALSCALED
			);
		}
		else
		{
			// No-thumbnail fallback: enabled = accent fill (this is the
			// "selected"/"active" cue per design system); disabled = surface-2
			// so the tile still reads as a clickable target.
			DrawSetPen(enabled ? g_ds_accent : g_ds_surface_2);
			DrawRectangle(innerX0, innerY0, innerX1, innerY1);
		}

		// Label is drawn last — keep it dark on the light-grey thumb backdrops without
		// the thick dark "subtitle bar" the light-on-dark pairing produced.
		DrawSetTextCol(g_ds_surface_0, g_ds_text_primary);
		DrawText(String(g_brick_labels[i]), innerX0 + 2, innerY0 + 1, DRAWTEXT_STD_ALIGN);

		// Selection chrome: enabled tiles get the accent ring (Maxon blue);
		// idle tiles get a subtle border. Double-frame on enabled to give the
		// selection more weight — same trick C4D's own selection rings use.
		DrawSetPen(enabled ? g_ds_accent : g_ds_border_subtle);
		DrawFrame(xStart, yStart, xEnd, yEnd);
		if (enabled)
			DrawFrame(xStart + 1, yStart + 1, xEnd - 1, yEnd - 1);
	}
}

Bool BrickLibraryThumbUserArea::InputEvent(const BaseContainer& msg)
{
	if (!_owner)
		return false;

	if (msg.GetInt32(BFM_INPUT_DEVICE) != BFM_INPUT_MOUSE)
		return false;

	Int32 mx = msg.GetInt32(BFM_INPUT_X);
	Int32 my = msg.GetInt32(BFM_INPUT_Y);
	Global2Local(&mx, &my);

	const Int32 w = GetWidth();
	const Int32 h = GetHeight();
	if (w <= 0 || h <= 0 || mx < 0 || my < 0 || mx >= w || my >= h)
	{
		_owner->SetHoverIndex(-1);
		return false;
	}

	const Int32 rows = (g_brick_count + g_cols - 1) / g_cols;
	const Int32 cellByWidth = (g_cols > 0) ? (w / g_cols) : 0;
	const Int32 cellByHeight = (rows > 0) ? (h / rows) : 0;
	const Int32 cellSize = (cellByWidth < cellByHeight) ? cellByWidth : cellByHeight;
	if (cellSize <= 0)
		return false;
	const Int32 gridW = cellSize * g_cols;
	const Int32 gridH = cellSize * rows;
	const Int32 gridX = 0;
	const Int32 gridY = 0;

	if (mx < gridX || my < gridY || mx >= (gridX + gridW) || my >= (gridY + gridH))
	{
		_owner->SetHoverIndex(-1);
		return false;
	}

	const Int32 col = (mx - gridX) / cellSize;
	const Int32 row = (my - gridY) / cellSize;
	const Int32 idx = row * g_cols + col;
	_owner->SetHoverIndex((idx >= 0 && idx < g_brick_count) ? idx : -1);

	if (
		idx >= 0 && idx < g_brick_count &&
		msg.GetInt32(BFM_INPUT_CHANNEL) == BFM_INPUT_MOUSELEFT &&
		msg.GetInt32(BFM_INPUT_VALUE) != 0
	)
	{
		_owner->ToggleIndex(idx);
		return true;
	}

	return false;
}

static Int32 g_brick_library_datatypes[] = { DTYPE_LONG };
static Int32 g_brick_hero_datatypes[] = { DTYPE_LONG };

static BaseBitmap* LoadHeroBitmap()
{
	const Filename pluginPath = GeGetPluginPath();
	const Filename pluginDir = pluginPath.GetDirectory();
	const Filename roots[4] = {
		pluginPath + Filename("res"),
		pluginDir + Filename("res"),
		pluginDir + Filename("Brick") + Filename("res"),
		pluginDir + Filename("BrickGen") + Filename("res"),
	};
	const String heroFile = "brickify_hero.png"_s;
	for (const Filename& root : roots)
	{
		const Filename heroPath = root + Filename(heroFile);
		if (!GeFExist(heroPath, false))
			continue;
		BaseBitmap* bmp = BaseBitmap::Alloc();
		if (!bmp)
			continue;
		if (bmp->Init(heroPath) == IMAGERESULT::OK && bmp->GetBw() > 0 && bmp->GetBh() > 0)
			return bmp;
		BaseBitmap::Free(bmp);
	}
	return nullptr;
}

class BrickHeroCustomGui;

class BrickHeroUserArea : public GeUserArea
{
public:
	void SetOwner(BrickHeroCustomGui* owner) { _owner = owner; }
	virtual Bool GetMinSize(Int32& w, Int32& h) override;
	virtual void DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg) override;

private:
	BrickHeroCustomGui* _owner = nullptr;
};

class BrickHeroCustomGui : public iCustomGui
{
	INSTANCEOF(BrickHeroCustomGui, iCustomGui)

public:
	BrickHeroCustomGui(const BaseContainer& settings, CUSTOMGUIPLUGIN* plugin) : iCustomGui(settings, plugin)
	{
		_area.SetOwner(this);
		_hero = LoadHeroBitmap();
	}

	virtual ~BrickHeroCustomGui()
	{
		if (_hero != nullptr)
		{
			BaseBitmap* bmp = _hero;
			BaseBitmap::Free(bmp);
			_hero = nullptr;
		}
	}

	virtual Bool CreateLayout() override
	{
		GroupBegin(5000, BFH_SCALEFIT | BFV_TOP, 1, 0, ""_s, 0);
		GroupBorderSpace(0, 0, 0, 0);
		C4DGadget* gadget = AddUserArea(g_hero_userarea_id, BFH_SCALEFIT | BFV_TOP, 320, 84);
		AttachUserArea(_area, gadget);
		GroupEnd();
		return SUPER::CreateLayout();
	}

	BaseBitmap* GetHero() const { return _hero; }

private:
	friend class BrickHeroUserArea;
	BrickHeroUserArea _area;
	BaseBitmap* _hero = nullptr;
};

Bool BrickHeroUserArea::GetMinSize(Int32& w, Int32& h)
{
	w = 320;
	h = 84;
	return true;
}

void BrickHeroUserArea::DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg)
{
	const Int32 w = GetWidth();
	const Int32 h = GetHeight();
	if (w <= 0 || h <= 0)
		return;

	// Letterbox area = surface-0 (the deepest content layer). The hero
	// bitmap sits on top via DrawBitmap below.
	DrawSetPen(g_ds_surface_0);
	DrawRectangle(0, 0, w, h);

	BaseBitmap* hero = _owner ? _owner->GetHero() : nullptr;
	if (hero == nullptr || hero->GetBw() <= 0 || hero->GetBh() <= 0)
		return;

	const Int32 bw = Max(1, hero->GetBw());
	const Int32 bh = Max(1, hero->GetBh());
	const Float dstAspect = Float(w) / Float(h);
	const Float srcAspect = Float(bw) / Float(bh);

	Int32 srcX = 0;
	Int32 srcY = 0;
	Int32 srcW = bw;
	Int32 srcH = bh;

	// Center-crop cover: uniformly scale from center so the hero always fills
	// the entire boundary without letterboxing as AM width changes.
	if (srcAspect > dstAspect)
	{
		srcW = Max(1, Int32(Float(bh) * dstAspect));
		srcX = Max(0, (bw - srcW) / 2);
	}
	else if (srcAspect < dstAspect)
	{
		srcH = Max(1, Int32(Float(bw) / dstAspect));
		srcY = Max(0, (bh - srcH) / 2);
	}

	DrawBitmap(
		hero,
		0, 0,
		w, h,
		srcX, srcY, srcW, srcH,
		BMP_NORMALSCALED
	);
}

// ---------------------------------------------------------------------------
// BrickSourcesCustomGui — Volume-Builder-style inset list of source meshes
// for a BrickIt op. The list is the source of truth (option B); scene-graph
// children of the host BrickIt auto-append to it as a convenience, but the
// list can also hold links to objects parented elsewhere in the scene.
//
// Add paths:  (a) parent an object under the BrickIt in the OM (auto-append
//                 on next CoreMessage(EVMSG_CHANGE)), or
//             (b) drag any object from the OM into the list area directly.
// Remove paths: select a row + Delete key, right-click "Remove from list",
//               or delete the object from the OM (entry self-prunes when
//               ObjectFromIndex returns nullptr on next draw).
//
// Cycle/self-reference filters (rejected at every entry point):
//   - Dropped/parented obj IsInstanceOf(BrickIt op type)  → reject + log
//   - Host BrickIt is an ancestor of the dropped object   → reject + log
//   - Dropped object IS the host                          → reject + log
// ---------------------------------------------------------------------------

static Int32 g_brick_sources_datatypes[] = { CUSTOMDATATYPE_INEXCLUDE_LIST };

// Right-click popup item IDs. Custom menu items must live in the range
// [FIRST_POPUP_ID (900000), 999999) — IDs below that get interpreted as
// either C4D command IDs or, for ID == 1 specifically, as the menu's own
// title (which renders the menu as an empty/tiny popup with no items).
static const Int32 g_sources_menu_remove = FIRST_POPUP_ID + 0;

class BrickSourcesCustomGui;

class BrickSourcesUserArea : public GeUserArea
{
public:
	void SetOwner(BrickSourcesCustomGui* owner) { _owner = owner; }
	virtual Bool GetMinSize(Int32& w, Int32& h) override;
	virtual void DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg) override;
	virtual Bool InputEvent(const BaseContainer& msg) override;

private:
	BrickSourcesCustomGui* _owner = nullptr;
};

class BrickSourcesCustomGui : public iCustomGui
{
	INSTANCEOF(BrickSourcesCustomGui, iCustomGui)

public:
	BrickSourcesCustomGui(const BaseContainer& settings, CUSTOMGUIPLUGIN* plugin) : iCustomGui(settings, plugin)
	{
		_area.SetOwner(this);
		LoadModeIcons();
	}

	virtual ~BrickSourcesCustomGui()
	{
		for (Int32 i = 0; i < 3; ++i)
		{
			if (_modeIcons[i] != nullptr)
			{
				BaseBitmap* bmp = _modeIcons[i];
				BaseBitmap::Free(bmp);
				_modeIcons[i] = nullptr;
			}
		}
	}

	BaseBitmap* GetModeIcon(Int32 mode) const
	{
		if (mode < 0 || mode > 2)
			return nullptr;
		return _modeIcons[mode];
	}

private:
	// Search the same plugin-root candidates the thumbnail loader uses so
	// the icons resolve whether the deploy script flattened the folder
	// layout or kept the BrickGen/res tree nested. Loaded once at
	// construction; freed in the destructor.
	void LoadModeIcons()
	{
		const Filename pluginPath = GeGetPluginPath();
		const Filename pluginDir = pluginPath.GetDirectory();
		const Filename roots[4] = {
			pluginPath + Filename("res") + Filename("icons") + Filename("modes"),
			pluginDir + Filename("res") + Filename("icons") + Filename("modes"),
			pluginDir + Filename("Brick") + Filename("res") + Filename("icons") + Filename("modes"),
			pluginDir + Filename("BrickGen") + Filename("res") + Filename("icons") + Filename("modes"),
		};
		const Char* baseNames[3] = { "Union", "Subtract", "Intersect" };

		for (Int32 i = 0; i < 3; ++i)
		{
			BaseBitmap* bmp = nullptr;
			const String base = String(baseNames[i]);
			// @2x first so HiDPI displays get the higher-res asset; .png
			// fallback is the 48px master.
			const String candidates[2] = {
				base + String("@2x.png"),
				base + String(".png"),
			};
			for (const Filename& root : roots)
			{
				for (const String& fileName : candidates)
				{
					const Filename filePath = root + Filename(fileName);
					if (!GeFExist(filePath, false))
						continue;
					BaseBitmap* tryBmp = BaseBitmap::Alloc();
					if (!tryBmp)
						continue;
					if (tryBmp->Init(filePath) == IMAGERESULT::OK && tryBmp->GetBw() > 0 && tryBmp->GetBh() > 0)
					{
						bmp = tryBmp;
						break;
					}
					BaseBitmap::Free(tryBmp);
				}
				if (bmp != nullptr)
					break;
			}
			_modeIcons[i] = bmp;
		}
	}

public:

	virtual Bool CreateLayout() override
	{
		GroupBegin(7000, BFH_SCALEFIT | BFV_TOP, 1, 0, ""_s, 0);
		GroupBorderSpace(0, 0, 0, 0);
		C4DGadget* gadget = AddUserArea(g_sources_userarea_id, BFH_SCALEFIT | BFV_TOP, g_sources_min_width, g_sources_min_height);
		AttachUserArea(_area, gadget);
		GroupEnd();
		return SUPER::CreateLayout();
	}

	virtual Bool InitValues() override
	{
		_area.Redraw();
		return true;
	}

	// Listen for scene-graph changes at the dialog level. GeUserArea doesn't
	// receive EVMSG_CHANGE reliably (the AM only routes core messages to the
	// hosting dialog), so the auto-append-from-children path lives here.
	// Pure-additive: never removes entries — option B keeps the list as the
	// source of truth, and OM-deleted entries self-prune via DrawMsg's
	// ObjectFromIndex == nullptr check.
	virtual Bool CoreMessage(Int32 id, const BaseContainer& msg) override
	{
		if (id == EVMSG_CHANGE || id == EVMSG_DOCUMENTRECALCULATED)
		{
			if (TryAutoAppendChildren())
			{
				// State changed — push to host so GVO sees the new entries.
				NotifyParentChanged();
			}
			_area.Redraw();
		}
		return iCustomGui::CoreMessage(id, msg);
	}

	// Walk the host BrickIt's direct children and append any that aren't
	// already in _value. Returns true iff at least one entry was added so
	// the caller can decide whether to NotifyParentChanged.
	//
	// Passes autoAdded=true so the appended entries are tagged as "live
	// connection" rows — un-parenting them later will drop the row and
	// fire the visibility-restore in _sync_source_visibility.
	Bool TryAutoAppendChildren()
	{
		BaseDocument* doc = nullptr;
		BaseObject* host = ResolveHostOp(doc);
		if (host == nullptr)
			return false;
		Bool anyAppended = false;
		for (BaseObject* child = host->GetDown(); child != nullptr; child = child->GetNext())
		{
			if (AppendIfValid(child, host, /*autoAdded=*/true))
				anyAppended = true;
		}
		return anyAppended;
	}

	virtual Bool SetData(const TriState<GeData>& tristate) override
	{
		_value = tristate.GetValue();
		_tristate = tristate.GetTri();
		// Run auto-append once at SetData time so a freshly-opened AM
		// reflects existing children immediately. Visibility flags are
		// managed by Python's _sync_source_visibility on every GVO so
		// hiding/restoring is post-bake, which keeps the source caches
		// populated for the bake step.
		if (TryAutoAppendChildren())
			NotifyParentChanged();
		_area.Redraw();
		return true;
	}

	virtual TriState<GeData> GetData() override
	{
		TriState<GeData> tri;
		tri.Add(_value);
		return tri;
	}

	// Drag-drop and keyboard: the AM routes BFM_DRAGRECEIVE and BFM_INPUT
	// (keyboard) to the iCustomGui's Message. Mouse input stays in the user
	// area's InputEvent. We hit-test drags against our user area's bounds,
	// validate the dragged obj against the cycle filters, and on
	// BFM_DRAG_FINISHED append it.
	virtual Int32 Message(const BaseContainer& msg, BaseContainer& result) override
	{
		if (msg.GetId() == BFM_INPUT &&
		    msg.GetInt32(BFM_INPUT_DEVICE) == BFM_INPUT_KEYBOARD)
		{
			const Int32 channel = msg.GetInt32(BFM_INPUT_CHANNEL);
			if (channel == KEY_DELETE || channel == KEY_BACKSPACE)
			{
				if (!_selectedRows.empty())
				{
					RemoveRows(_selectedRows);
					return true;
				}
			}
		}
		if (msg.GetId() == BFM_DRAGRECEIVE)
		{
			Int32 dx = 0, dy = 0;
			GetDragPosition(msg, &dx, &dy);
			Int32 ax = 0, ay = 0, aw = 0, ah = 0;
			GetItemDim(g_sources_userarea_id, &ax, &ay, &aw, &ah);
			const Bool overArea = (dx >= ax && dx < ax + aw && dy >= ay && dy < ay + ah);
			if (!overArea)
				return iCustomGui::Message(msg, result);

			Int32 dragType = 0;
			void* dragObject = nullptr;
			GetDragObject(msg, &dragType, &dragObject);
			if (dragType != DRAGTYPE_ATOMARRAY || dragObject == nullptr)
				return iCustomGui::Message(msg, result);
			AtomArray* arr = static_cast<AtomArray*>(dragObject);

			BaseDocument* doc = nullptr;
			BaseObject* host = ResolveHostOp(doc);
			// Validate every dragged item; if any one passes, accept the drop.
			Bool anyValid = false;
			for (Int32 i = 0; i < arr->GetCount(); ++i)
			{
				BaseList2D* item = static_cast<BaseList2D*>(arr->GetIndex(i));
				if (item == nullptr || !item->IsInstanceOf(Obase))
					continue;
				BaseObject* obj = static_cast<BaseObject*>(item);
				if (IsValidSourceCandidate(obj, host))
				{
					anyValid = true;
					break;
				}
			}
			if (!anyValid)
				return iCustomGui::Message(msg, result);

			// While hovering, just signal "accept" via the cursor.
			if (!msg.GetInt32(BFM_DRAG_FINISHED))
				return SetDragDestination(MOUSE_POINT_HAND);

			// On drop: append every valid object, log + skip the rest.
			// autoAdded=false so drag-dropped entries persist across
			// un-parent — they're standalone references, not live
			// child-of-host connections.
			for (Int32 i = 0; i < arr->GetCount(); ++i)
			{
				BaseList2D* item = static_cast<BaseList2D*>(arr->GetIndex(i));
				if (item == nullptr || !item->IsInstanceOf(Obase))
					continue;
				BaseObject* obj = static_cast<BaseObject*>(item);
				AppendIfValid(obj, host, /*autoAdded=*/false);
			}
			NotifyParentChanged();
			_area.Redraw();
			return SetDragDestination(MOUSE_POINT_HAND);
		}
		return iCustomGui::Message(msg, result);
	}

	// Push the current _value back to the host parameter so the BrickIt op
	// re-runs GetVirtualObjects with the updated InExcludeData. Mirrors how
	// BrickLibraryCustomGui::ToggleIndex notifies the parent.
	void NotifyParentChanged()
	{
		_tristate = false;
		BaseContainer action(BFM_ACTION);
		action.SetInt32(BFM_ACTION_ID, GetId());
		action.SetData(BFM_ACTION_VALUE, _value);
		SendParentMessage(action);
	}

	// Resolve the BrickIt object whose parameter we represent. The active
	// document's selected object is the one being shown in the AM, so its
	// BRICKIFYASSEMBLY_SOURCES parameter is the one driving us.
	BaseObject* ResolveHostOp(BaseDocument*& outDoc) const
	{
		outDoc = GetActiveDocument();
		if (outDoc == nullptr)
			return nullptr;
		BaseObject* active = outDoc->GetActiveObject();
		if (active == nullptr || !active->IsInstanceOf(g_brickit_op_id))
			return nullptr;
		return active;
	}

	// Cycle/self-reference filter shared by drag-drop accept and the
	// auto-append-from-children path. Logs the rejection reason once via
	// GePrint so the user understands why their drag didn't take.
	Bool IsValidSourceCandidate(BaseObject* obj, BaseObject* host) const
	{
		if (obj == nullptr || host == nullptr)
			return false;
		if (obj == host)
		{
			GePrint(cinema::String("[brick] Source rejected: cannot use BrickIt as its own source ('") + obj->GetName() + cinema::String("')."));
			return false;
		}
		if (obj->IsInstanceOf(g_brickit_op_id))
		{
			GePrint(cinema::String("[brick] Source rejected: BrickIt cannot be a source of another BrickIt ('") + obj->GetName() + cinema::String("')."));
			return false;
		}
		// Cycle hazard: the freeze case is when `obj` is an ancestor of the
		// host BrickIt. Baking obj would CSTO its entire subtree (which
		// contains the host), re-trigger the host's GVO, and recurse. The
		// reverse — obj being inside the host's subtree (e.g. a direct
		// child, the *intended* auto-append path) — is fine: the bake step
		// only walks each source independently, never recursing into the
		// host's own GVO.
		for (BaseObject* a = host->GetUp(); a != nullptr; a = a->GetUp())
		{
			if (a == obj)
			{
				GePrint(cinema::String("[brick] Source rejected: '") + obj->GetName() + cinema::String("' is an ancestor of this BrickIt (would cycle on bake)."));
				return false;
			}
		}
		return true;
	}

	// Walk _value entries in stored order, dropping nulls (OM-deleted) and
	// returning live objects. The list is the source of truth; this is the
	// canonical iteration for both DrawMsg and InputEvent.
	//
	// outFlags carries the full per-entry flags (mode bits 0-1 + AUTO_ADDED
	// bit 2) so callers like RebuildFromEntries can preserve AUTO_ADDED
	// across rewrites. Display callers should mask with
	// g_brick_source_mode_mask to extract just the mode.
	void CollectRowEntries(std::vector<BaseObject*>& outObjects, std::vector<Int32>& outFlags) const
	{
		outObjects.clear();
		outFlags.clear();
		const InExcludeData* data = _value.GetCustomDataType<InExcludeData>();
		BaseDocument* doc = GetActiveDocument();
		if (data == nullptr || doc == nullptr)
			return;
		const Int32 count = data->GetObjectCount();
		for (Int32 i = 0; i < count; ++i)
		{
			BaseList2D* item = data->ObjectFromIndex(doc, i);
			if (item == nullptr || !item->IsInstanceOf(Obase))
				continue;
			BaseObject* obj = static_cast<BaseObject*>(item);
			Int32 flags = data->GetFlags(i);
			outObjects.push_back(obj);
			outFlags.push_back(flags);
		}
	}

	// Helper to extract just the mode bits for display.
	static Int32 ModeOfFlags(Int32 flags)
	{
		const Int32 m = flags & g_brick_source_mode_mask;
		if (m != g_brick_source_mode_union &&
		    m != g_brick_source_mode_subtract &&
		    m != g_brick_source_mode_intersect)
			return g_brick_source_mode_union;
		return m;
	}

	// Helper: rebuild _value from the current row entries plus an optional
	// mutation. Used by every mutator (cycle mode, append, remove) so the
	// data plumbing is in one place.
	//
	// Side-effect: diff old vs new entry sets and toggle visibility flags
	// accordingly. Newly-added objects get hidden in editor + render
	// (Volume Builder convention — the source mesh "becomes" the
	// generator's output). Newly-removed get reset to MODE_UNDEF so they
	// re-appear at their default visibility. Skipped on the very first
	// SetData from C4D's deserialization (controlled by `_initialSyncDone`)
	// so opening a saved scene doesn't unhide things the user wanted hidden.
	//
	// `excludeFromDiff` is for callers that immediately scene-delete some
	// of the removed objects (RemoveRows' Volume-Builder semantics path) —
	// passing those objects here keeps us from setting flags or AddUndo
	// entries on objects that are about to be freed.
	void RebuildFromEntries(const std::vector<BaseObject*>& objects,
	                        const std::vector<Int32>& modes,
	                        const std::vector<BaseObject*>& excludeFromDiff = {})
	{
		// Snapshot the previous entry set BEFORE mutating _value.
		std::vector<BaseObject*> prev;
		{
			const InExcludeData* old = _value.GetCustomDataType<InExcludeData>();
			BaseDocument* doc = GetActiveDocument();
			if (old != nullptr && doc != nullptr)
			{
				const Int32 oc = old->GetObjectCount();
				for (Int32 i = 0; i < oc; ++i)
				{
					BaseList2D* item = old->ObjectFromIndex(doc, i);
					if (item != nullptr && item->IsInstanceOf(Obase))
						prev.push_back(static_cast<BaseObject*>(item));
				}
			}
		}

		GeData fresh(CUSTOMDATATYPE_INEXCLUDE_LIST, DEFAULTVALUE);
		InExcludeData* sink = fresh.GetCustomDataTypeWritable<InExcludeData>();
		if (sink == nullptr)
			return;
		const Int32 count = (Int32)objects.size();
		for (Int32 i = 0; i < count; ++i)
		{
			if (objects[i] == nullptr)
				continue;
			sink->InsertObject(objects[i], (i < (Int32)modes.size()) ? modes[i] : g_brick_source_mode_union);
		}
		_value = fresh;
		// Visibility diff lives in Python's _sync_source_visibility (runs
		// every GVO, after the bake reads the source caches). Doing it
		// here would hide the cube BEFORE the next GVO bakes it, which
		// invalidates GetCache() and breaks the brick render for the
		// drag-drop path specifically.
		(void)prev;
		(void)excludeFromDiff;
	}

	// Append a candidate to _value if it passes the cycle filter and isn't
	// already in the list. `autoAdded` controls bit 2 of the entry's flags:
	// true when the row is added because the object was parented under the
	// BrickIt (the row is a "live connection" — un-parenting drops it),
	// false for drag-dropped entries (those persist across un-parent).
	// No notify here — caller batches with NotifyParentChanged() so a
	// multi-drop is one update.
	Bool AppendIfValid(BaseObject* obj, BaseObject* host, Bool autoAdded)
	{
		if (!IsValidSourceCandidate(obj, host))
			return false;
		// Dedup against current _value.
		BaseDocument* doc = GetActiveDocument();
		const InExcludeData* current = _value.GetCustomDataType<InExcludeData>();
		if (current != nullptr && doc != nullptr && current->GetObjectIndex(doc, obj) != NOTOK)
			return false;
		std::vector<BaseObject*> objects;
		std::vector<Int32> flags;
		CollectRowEntries(objects, flags);
		objects.push_back(obj);
		const Int32 newFlags = g_brick_source_mode_union |
		                       (autoAdded ? g_brick_source_flag_auto_added : 0);
		flags.push_back(newFlags);
		RebuildFromEntries(objects, flags);
		return true;
	}

	Int32 RowCount() const
	{
		std::vector<BaseObject*> objects;
		std::vector<Int32> modes;
		CollectRowEntries(objects, modes);
		return (Int32)objects.size();
	}

	void CycleModeForRow(Int32 rowIndex)
	{
		std::vector<BaseObject*> objects;
		std::vector<Int32> flags;
		CollectRowEntries(objects, flags);
		if (rowIndex < 0 || rowIndex >= (Int32)objects.size())
			return;
		// Cycle just the mode bits; preserve the AUTO_ADDED bit so a row's
		// origin (auto-from-children vs drag-dropped) survives mode edits.
		const Int32 currentFlags = flags[rowIndex];
		const Int32 currentMode = currentFlags & g_brick_source_mode_mask;
		Int32 nextMode = g_brick_source_mode_union;
		switch (currentMode)
		{
			case g_brick_source_mode_union:     nextMode = g_brick_source_mode_subtract;  break;
			case g_brick_source_mode_subtract:  nextMode = g_brick_source_mode_intersect; break;
			default:                             nextMode = g_brick_source_mode_union;     break;
		}
		flags[rowIndex] = (currentFlags & ~g_brick_source_mode_mask) | nextMode;
		RebuildFromEntries(objects, flags);
		NotifyParentChanged();
		_area.Redraw();
	}

	// Remove every row in `rowIndices` (descending order so erasing from
	// the entry vector doesn't shift indices we still need to remove).
	// Volume Builder semantics: any row whose object is a direct child of
	// the host BrickIt also deletes the scene object; entries pointing
	// elsewhere are list-only removals. All scene deletions roll into one
	// undo step so Ctrl-Z restores everything.
	void RemoveRows(std::vector<Int32> rowIndices)
	{
		if (rowIndices.empty())
			return;
		std::vector<BaseObject*> objects;
		std::vector<Int32> modes;
		CollectRowEntries(objects, modes);

		BaseDocument* doc = nullptr;
		BaseObject* host = ResolveHostOp(doc);

		// Sort descending so erasing keeps remaining indices valid.
		std::sort(rowIndices.begin(), rowIndices.end(), std::greater<Int32>());

		std::vector<BaseObject*> toDeleteFromScene;
		for (Int32 rowIndex : rowIndices)
		{
			if (rowIndex < 0 || rowIndex >= (Int32)objects.size())
				continue;
			BaseObject* obj = objects[rowIndex];
			if (obj != nullptr && host != nullptr && doc != nullptr &&
			    obj->GetUp() == host)
			{
				toDeleteFromScene.push_back(obj);
			}
			objects.erase(objects.begin() + rowIndex);
			modes.erase(modes.begin() + rowIndex);
		}
		// `toDeleteFromScene` is excluded from the visibility diff so we
		// don't add UNDOTYPE::BITS entries for objects that are about to
		// be freed in the loop below — those undo entries would dangle
		// after BaseObject::Free.
		RebuildFromEntries(objects, modes, toDeleteFromScene);
		_selectedRows.clear();
		_selectionAnchor = -1;
		NotifyParentChanged();

		if (!toDeleteFromScene.empty() && doc != nullptr)
		{
			doc->StartUndo();
			for (BaseObject* obj : toDeleteFromScene)
			{
				doc->AddUndo(UNDOTYPE::DELETEOBJ, obj);
				obj->Remove();
				BaseObject::Free(obj);
			}
			doc->EndUndo();
			EventAdd();
		}

		_area.Redraw();
	}

	// Selection helpers — _selectedRows is kept sorted ascending and
	// duplicate-free, treated as a set. The anchor is the row a future
	// shift-click will measure from (set on every plain or ctrl click).
	Bool IsRowSelected(Int32 rowIndex) const
	{
		return std::binary_search(_selectedRows.begin(), _selectedRows.end(), rowIndex);
	}

	void ClearSelection()
	{
		if (_selectedRows.empty() && _selectionAnchor < 0)
			return;
		_selectedRows.clear();
		_selectionAnchor = -1;
		_area.Redraw();
	}

	void SelectSingle(Int32 rowIndex)
	{
		const Int32 total = RowCount();
		if (rowIndex < 0 || rowIndex >= total)
		{
			ClearSelection();
			return;
		}
		_selectedRows.clear();
		_selectedRows.push_back(rowIndex);
		_selectionAnchor = rowIndex;
		_area.Redraw();
	}

	void ToggleRow(Int32 rowIndex)
	{
		const Int32 total = RowCount();
		if (rowIndex < 0 || rowIndex >= total)
			return;
		auto it = std::lower_bound(_selectedRows.begin(), _selectedRows.end(), rowIndex);
		if (it != _selectedRows.end() && *it == rowIndex)
			_selectedRows.erase(it);
		else
			_selectedRows.insert(it, rowIndex);
		_selectionAnchor = rowIndex;
		_area.Redraw();
	}

	// Range select from anchor to rowIndex (inclusive). If no anchor, this
	// behaves like SelectSingle. The selection replaces any current set —
	// mirrors the OM/Finder convention where shift-click defines a fresh
	// contiguous run rather than extending the existing scattered selection.
	void SelectRange(Int32 rowIndex)
	{
		const Int32 total = RowCount();
		if (rowIndex < 0 || rowIndex >= total)
			return;
		if (_selectionAnchor < 0 || _selectionAnchor >= total)
		{
			SelectSingle(rowIndex);
			return;
		}
		const Int32 lo = (_selectionAnchor < rowIndex) ? _selectionAnchor : rowIndex;
		const Int32 hi = (_selectionAnchor < rowIndex) ? rowIndex : _selectionAnchor;
		_selectedRows.clear();
		for (Int32 i = lo; i <= hi; ++i)
			_selectedRows.push_back(i);
		// Anchor stays put so further shift-clicks measure from the same
		// origin — also matches OM/Finder behavior.
		_area.Redraw();
	}

	const std::vector<Int32>& GetSelectedRows() const { return _selectedRows; }

private:
	friend class BrickSourcesUserArea;
	BrickSourcesUserArea _area;
	GeData _value{ CUSTOMDATATYPE_INEXCLUDE_LIST, DEFAULTVALUE };
	Bool _tristate = false;
	std::vector<Int32> _selectedRows;   // sorted ascending, no dups
	Int32 _selectionAnchor = -1;        // origin for shift-range clicks
	BaseBitmap* _modeIcons[3] = { nullptr, nullptr, nullptr };
};


Bool BrickSourcesUserArea::GetMinSize(Int32& w, Int32& h)
{
	w = g_sources_min_width;
	h = g_sources_min_height;
	return true;
}

static const Char* ModeShortLabel(Int32 mode)
{
	switch (mode)
	{
		case g_brick_source_mode_subtract:  return "Subtract";
		case g_brick_source_mode_intersect: return "Intersect";
		default:                             return "Union";
	}
}

void BrickSourcesUserArea::DrawMsg(Int32 x1, Int32 y1, Int32 x2, Int32 y2, const BaseContainer& msg)
{
	OffScreenOn();

	const Int32 w = GetWidth();
	const Int32 h = GetHeight();
	if (w <= 0 || h <= 0)
		return;

	// Container surface = surface-0 (deepest layer per design system, like
	// a viewport area embedded in the AM). Frame uses `divider` (#1A1A1A) —
	// per the design system this token is intentionally darker than the
	// darkest surface for an etched-inset look, so the box reads as set
	// INTO the panel rather than ON it.
	DrawSetPen(g_ds_surface_0);
	DrawRectangle(0, 0, w, h);
	DrawSetPen(g_ds_divider);
	DrawFrame(0, 0, w - 1, h - 1);

	if (_owner == nullptr)
		return;

	std::vector<BaseObject*> objects;
	std::vector<Int32> modes;
	_owner->CollectRowEntries(objects, modes);
	const Int32 rowCount = (Int32)objects.size();
	if (rowCount <= 0)
	{
		// Empty state: secondary text on surface-0.
		DrawSetTextCol(g_ds_text_secondary, g_ds_surface_0);
		DrawText("Drop meshes here or parent under BrickIt."_s, 8, (h / 2) - 7, DRAWTEXT_STD_ALIGN);
		return;
	}

	const Int32 rowH = g_sources_row_height;
	const Int32 modeW = g_sources_mode_button_width;
	const Int32 iconSize = 16;          // C4D OM icon native size
	const Int32 treeGutter = 14;        // Width of the left gutter that holds the tree connector
	const Int32 iconLeftPad = 4;        // Gap between tree connector and icon
	const Int32 nameLeftGap = 6;        // Gap between icon and name
	// Mode icon position: 30% inset from the right edge of the container,
	// i.e. icon's right edge sits at ~70% of the container width. Sits
	// to the right of the name column with breathing room before the
	// container's right edge.
	const Int32 modeRightInset = (w * 30) / 100;
	const Int32 vertInset = 4;          // Top + bottom breathing room inside the container
	const Int32 horzInset = 4;          // Left + right breathing room so rows don't clip the frame

	for (Int32 i = 0; i < rowCount; ++i)
	{
		// Rows are inset on all four sides so they don't visually overlap
		// the container's etched border. Stripes still feel "list-like"
		// because the inset is uniform across all rows.
		const Int32 rowY = vertInset + i * rowH;
		if (rowY + rowH > h - vertInset)
			break;
		const Int32 rowX0 = horzInset;
		const Int32 rowX1 = w - 1 - horzInset;
		const Int32 rowY1 = rowY + rowH - 1;
		const Bool isSelected = _owner->IsRowSelected(i);
		const Bool isLastRow = (i == rowCount - 1);

		// Alternating row backgrounds (surface-1 / surface-2) — one-stop
		// difference per the design system's "adjacent surfaces differ by
		// one stop" rule. Selection is conveyed via text recolor only, so
		// the row bg here is independent of selected state.
		const Vector rowBg = (i & 1) ? g_ds_surface_2 : g_ds_surface_1;
		DrawSetPen(rowBg);
		DrawRectangle(rowX0, rowY, rowX1, rowY1);

		// Tree connector (left gutter): a vertical line down the gutter
		// plus a short horizontal stub at row mid-height, mimicking the
		// OM's "├─" / "└─" idiom. Our list is flat — every row is a
		// top-level source — so the connector is purely visual scaffolding
		// to echo the OM's hierarchy aesthetic, not a real tree.
		const Int32 treeX = rowX0 + treeGutter / 2;
		const Int32 treeY0 = rowY;
		// Last row gets the "└─" form: vertical stops at row midline. All
		// other rows get the "├─" form: vertical continues through.
		const Int32 verticalEndY = isLastRow ? (rowY + rowH / 2) : rowY1;
		DrawSetPen(g_ds_border_subtle);
		DrawLine(treeX, treeY0, treeX, verticalEndY);
		DrawLine(treeX, rowY + rowH / 2, treeX + treeGutter / 2, rowY + rowH / 2);

		// Object icon (right of the gutter). IconData carries a BaseBitmap
		// atlas plus a sub-rect; bitmap is owned by C4D, we just blit the
		// slice. BMP_ALLOWALPHA blends transparent pixels in the icon with
		// whatever DrawSetPen color is active — set it to rowBg first so
		// the OM atlas's transparent corners pick up the row's stripe
		// color instead of bleeding the AM's default backdrop.
		const Int32 iconX = rowX0 + treeGutter + iconLeftPad;
		const Int32 iconY = rowY + (rowH - iconSize) / 2 - 1;
		Int32 nameX0 = iconX + iconSize + nameLeftGap;
		if (objects[i] != nullptr)
		{
			IconData icon;
			objects[i]->GetIcon(&icon);
			if (icon.bmp != nullptr && icon.w > 0 && icon.h > 0)
			{
				DrawSetPen(rowBg);
				DrawBitmap(
					icon.bmp,
					iconX, iconY, iconSize, iconSize,
					icon.x, icon.y, icon.w, icon.h,
					BMP_ALLOWALPHA | BMP_NORMALSCALED
				);
			}
		}

		// Name column to the right of the icon. Selected name recolors to
		// accent blue (the "active/interactive" cue) on the unchanged row
		// background — quieter than a full-row fill.
		DrawSetTextCol(isSelected ? g_ds_accent : g_ds_text_primary, rowBg);
		const String name = (objects[i] != nullptr) ? objects[i]->GetName() : "(missing)"_s;
		DrawText(name, nameX0, rowY + 3, DRAWTEXT_STD_ALIGN);

		// Mode control: icon glyph + text label drawn side-by-side on the
		// row background (no pill — the icons carry their own brand colors
		// via alpha, and a colored backdrop would camouflage them). The
		// glyph is left-anchored within the mode region; the label sits
		// immediately to its right. The whole region is the click target.
		const Int32 btnX1 = rowX1 - modeRightInset;
		const Int32 btnX0 = btnX1 - modeW;
		const Int32 btnY0 = rowY + 2;
		const Int32 btnY1 = rowY1 - 1;
		const Int32 glyphSize = 16;
		const Int32 glyphX = btnX0;
		const Int32 glyphY = btnY0 + ((btnY1 - btnY0) - glyphSize) / 2;
		const Int32 labelX = glyphX + glyphSize + 6;

		const Int32 displayMode = BrickSourcesCustomGui::ModeOfFlags(modes[i]);
		BaseBitmap* iconBmp = _owner->GetModeIcon(displayMode);
		if (iconBmp != nullptr && iconBmp->GetBw() > 0 && iconBmp->GetBh() > 0)
		{
			// BMP_ALLOWALPHA blends transparent icon pixels with the current
			// pen color — set it to the row's stripe color so the icon's
			// transparent regions match the row.
			DrawSetPen(rowBg);
			DrawBitmap(
				iconBmp,
				glyphX, glyphY, glyphSize, glyphSize,
				0, 0, iconBmp->GetBw(), iconBmp->GetBh(),
				BMP_ALLOWALPHA | BMP_NORMALSCALED
			);
		}

		// Label always rendered (with or without icon). Sits to the right
		// of the glyph slot so the label position is stable as the mode
		// cycles even if the icon load fails.
		DrawSetTextCol(g_ds_text_primary, rowBg);
		DrawText(String(ModeShortLabel(displayMode)), labelX, rowY + 3, DRAWTEXT_STD_ALIGN);
	}
}

// Hit-test helper: which row index does (mx, my) fall in, or -1 if none.
// `topInset` is the top vertical inset matching DrawMsg's vertInset.
static Int32 HitTestRow(Int32 my, Int32 totalRows, Int32 topInset, Int32 rowH)
{
	const Int32 rel = my - topInset;
	if (rel < 0)
		return -1;
	const Int32 idx = rel / rowH;
	return (idx >= 0 && idx < totalRows) ? idx : -1;
}

Bool BrickSourcesUserArea::InputEvent(const BaseContainer& msg)
{
	if (_owner == nullptr)
		return false;
	if (msg.GetInt32(BFM_INPUT_DEVICE) != BFM_INPUT_MOUSE)
		return false;
	if (msg.GetInt32(BFM_INPUT_VALUE) == 0)
		return false;

	const Int32 channel = msg.GetInt32(BFM_INPUT_CHANNEL);
	const Bool isLeft = (channel == BFM_INPUT_MOUSELEFT);
	const Bool isRight = (channel == BFM_INPUT_MOUSERIGHT);
	if (!isLeft && !isRight)
		return false;

	Int32 mx = msg.GetInt32(BFM_INPUT_X);
	Int32 my = msg.GetInt32(BFM_INPUT_Y);
	Global2Local(&mx, &my);

	const Int32 w = GetWidth();
	const Int32 h = GetHeight();
	if (w <= 0 || h <= 0 || mx < 0 || my < 0 || mx >= w || my >= h)
		return false;

	const Int32 rowH = g_sources_row_height;
	const Int32 modeW = g_sources_mode_button_width;
	const Int32 modeRightInset = (w * 30) / 100;  // Must match DrawMsg.
	const Int32 vertInset = 4;                    // Must match DrawMsg.
	const Int32 horzInset = 4;                    // Must match DrawMsg.

	std::vector<BaseObject*> objects;
	std::vector<Int32> modes;
	_owner->CollectRowEntries(objects, modes);
	const Int32 rowCount = (Int32)objects.size();
	const Int32 rowIndex = HitTestRow(my, rowCount, vertInset, rowH);

	// Click outside any row clears the selection (same convention as the OM).
	if (rowIndex < 0)
	{
		if (isLeft)
		{
			_owner->ClearSelection();
			return true;
		}
		return false;
	}

	const Int32 rowX1 = w - 1 - horzInset;  // Must match DrawMsg row right edge.
	const Int32 btnX1 = rowX1 - modeRightInset;
	const Int32 btnX0 = btnX1 - modeW;
	const Bool overModePill = (mx >= btnX0 && mx <= btnX1);

	const Int32 qualifiers = msg.GetInt32(BFM_INPUT_QUALIFIER);
	const Bool shiftHeld = (qualifiers & QSHIFT) != 0;
	const Bool ctrlHeld = (qualifiers & QCTRL) != 0;

	if (isLeft)
	{
		// Click on Mode icon cycles the mode (mode never participates in
		// selection — it's a per-row action button). Otherwise the click
		// updates the selection per Shift/Ctrl conventions.
		if (overModePill)
		{
			_owner->CycleModeForRow(rowIndex);
		}
		else if (shiftHeld)
		{
			_owner->SelectRange(rowIndex);
		}
		else if (ctrlHeld)
		{
			_owner->ToggleRow(rowIndex);
		}
		else
		{
			_owner->SelectSingle(rowIndex);
		}
		return true;
	}

	if (isRight)
	{
		// Right-click respects an existing multi-selection: if the clicked
		// row is already selected, the menu acts on the whole selection;
		// otherwise it switches to single-select on the clicked row first.
		std::vector<Int32> targetRows;
		if (_owner->IsRowSelected(rowIndex))
		{
			targetRows = _owner->GetSelectedRows();
		}
		else
		{
			_owner->SelectSingle(rowIndex);
			targetRows.push_back(rowIndex);
		}

		BaseContainer menu;
		const String label = (targetRows.size() > 1)
			? cinema::String("Remove from list (") + String::IntToString((Int32)targetRows.size()) + cinema::String(")")
			: cinema::String("Remove from list");
		menu.SetString(g_sources_menu_remove, label);
		const Int32 picked = ShowPopupMenu(nullptr, MOUSEPOS, MOUSEPOS, menu);
		if (picked == g_sources_menu_remove)
			_owner->RemoveRows(targetRows);
		return true;
	}

	return false;
}

class BrickSourcesCustomGuiData : public CustomGuiData
{
public:
	virtual Int32 GetId() override { return g_bricksources_customgui_id; }

	virtual CDialog* Alloc(const BaseContainer& settings) override
	{
		BrickSourcesCustomGui* dlg = NewObjClear(BrickSourcesCustomGui, settings, GetPlugin());
		if (!dlg)
			return nullptr;
		return dlg->Get();
	}

	virtual void Free(CDialog* dlg, void* userdata) override
	{
		if (!dlg || !userdata)
			return;
		BrickSourcesCustomGui* subDialog = static_cast<BrickSourcesCustomGui*>(userdata);
		DeleteObj(subDialog);
	}

	virtual const Char* GetResourceSym() override { return "CUSTOMGUIBRICKSOURCES"; }

	virtual CustomProperty* GetProperties() override { return nullptr; }

	virtual Int32 GetResourceDataType(Int32*& table) override
	{
		table = g_brick_sources_datatypes;
		return sizeof(g_brick_sources_datatypes) / sizeof(Int32);
	}
};

Bool RegisterBrickSourcesCustomGUI()
{
	static BaseCustomGuiLib customGuiLib;
	ClearMem(&customGuiLib, sizeof(customGuiLib));
	FillBaseCustomGui(customGuiLib);

	if (!InstallLibrary(g_bricksources_customgui_id, &customGuiLib, 1000, sizeof(customGuiLib)))
		return false;

	if (!RegisterCustomGuiPlugin("Brick Sources List GUI"_s, 0, NewObjClear(BrickSourcesCustomGuiData)))
		return false;

	return true;
}

class BrickLibraryCustomGuiData : public CustomGuiData
{
public:
	virtual Int32 GetId() override { return g_bricklibrary_customgui_id; }

	virtual CDialog* Alloc(const BaseContainer& settings) override
	{
		BrickLibraryCustomGui* dlg = NewObjClear(BrickLibraryCustomGui, settings, GetPlugin());
		if (!dlg)
			return nullptr;
		return dlg->Get();
	}

	virtual void Free(CDialog* dlg, void* userdata) override
	{
		if (!dlg || !userdata)
			return;
		BrickLibraryCustomGui* subDialog = static_cast<BrickLibraryCustomGui*>(userdata);
		DeleteObj(subDialog);
	}

	virtual const Char* GetResourceSym() override { return "CUSTOMGUIBRICKLIBRARY"; }

	virtual CustomProperty* GetProperties() override { return nullptr; }

	virtual Int32 GetResourceDataType(Int32*& table) override
	{
		table = g_brick_library_datatypes;
		return sizeof(g_brick_library_datatypes) / sizeof(Int32);
	}
};

class BrickHeroCustomGuiData : public CustomGuiData
{
public:
	virtual Int32 GetId() override { return g_brickhero_customgui_id; }

	virtual CDialog* Alloc(const BaseContainer& settings) override
	{
		BrickHeroCustomGui* dlg = NewObjClear(BrickHeroCustomGui, settings, GetPlugin());
		if (!dlg)
			return nullptr;
		return dlg->Get();
	}

	virtual void Free(CDialog* dlg, void* userdata) override
	{
		if (!dlg || !userdata)
			return;
		BrickHeroCustomGui* subDialog = static_cast<BrickHeroCustomGui*>(userdata);
		DeleteObj(subDialog);
	}

	virtual const Char* GetResourceSym() override { return "CUSTOMGUIBRICKHERO"; }

	virtual CustomProperty* GetProperties() override { return nullptr; }

	virtual Int32 GetResourceDataType(Int32*& table) override
	{
		table = g_brick_hero_datatypes;
		return sizeof(g_brick_hero_datatypes) / sizeof(Int32);
	}
};

Bool RegisterBrickLibraryCustomGUI()
{
	static BaseCustomGuiLib customGuiLib;
	ClearMem(&customGuiLib, sizeof(customGuiLib));
	FillBaseCustomGui(customGuiLib);

	if (!InstallLibrary(g_bricklibrary_customgui_id, &customGuiLib, 1000, sizeof(customGuiLib)))
		return false;

	if (!RegisterCustomGuiPlugin("Brick Library Thumbnail GUI"_s, 0, NewObjClear(BrickLibraryCustomGuiData)))
		return false;

	return true;
}

Bool RegisterBrickHeroCustomGUI()
{
	static BaseCustomGuiLib customGuiLib;
	ClearMem(&customGuiLib, sizeof(customGuiLib));
	FillBaseCustomGui(customGuiLib);

	if (!InstallLibrary(g_brickhero_customgui_id, &customGuiLib, 1000, sizeof(customGuiLib)))
		return false;

	if (!RegisterCustomGuiPlugin("Brick Hero Banner GUI"_s, 0, NewObjClear(BrickHeroCustomGuiData)))
		return false;

	return true;
}

class BrickLibraryPanelDialog : public GeDialog
{
public:
	virtual Bool CreateLayout() override
	{
		SetTitle("Brick Library Inline GUI (WIP)"_s);
		GroupBegin(1000, BFH_SCALEFIT | BFV_SCALEFIT, 1, 0, ""_s, BFV_SCALEFIT);
		GroupBorderSpace(12, 12, 12, 12);
		AddStaticText(1001, BFH_LEFT, 0, 0,
			"Native SDK module scaffold is active."_s, BORDER_NONE);
		AddStaticText(1002, BFH_LEFT, 0, 0,
			"Next step: implement custom AM GUI thumbnail control."_s, BORDER_NONE);
		GroupEnd();
		return true;
	}
};

class BrickLibraryPanelCommand : public CommandData
{
public:
	virtual Bool Execute(BaseDocument* doc, GeDialog* parentManager) override
	{
		return _dialog.Open(DLG_TYPE::ASYNC, g_bricklibrary_panel_cmd_id, -1, -1, 460, 120);
	}

	virtual Bool RestoreLayout(void* secret) override
	{
		return _dialog.RestoreLayout(g_bricklibrary_panel_cmd_id, 0, secret);
	}

private:
	BrickLibraryPanelDialog _dialog;
};

Bool RegisterBrickLibraryPanelCommand()
{
	// PLUGINFLAG_HIDEPLUGINMENU keeps this internal scaffold panel out
	// of the Extensions menu — it's only meant to be invoked through
	// BrickIt's UI hooks, not directly by the user.
	return RegisterCommandPlugin(
		g_bricklibrary_panel_cmd_id,
		"Brick Library Inline GUI (WIP)"_s,
		PLUGINFLAG_HIDEPLUGINMENU,
		nullptr,
		"Open Brick Library native scaffold panel."_s,
		NewObjClear(BrickLibraryPanelCommand));
}

static Bool BrickColorsDiffer(const Vector& a, const Vector& b)
{
	const Float eps = 0.0001;
	return Abs(a.x - b.x) > eps || Abs(a.y - b.y) > eps || Abs(a.z - b.z) > eps;
}

static Int32 CountChangedMoDataColors(MoData* md, const BaseContainer& bc, Int32 count)
{
	if (md == nullptr || count <= 0)
		return 0;

	AutoLocker lock(md->GetAutoLock());
	MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
	if (!colors)
		return 0;

	Int32 changed = 0;
	for (Int32 i = 0; i < count; ++i)
	{
		const Vector inColor = bc.GetVector(g_brick_mograph_eval_in_color_base + i, Vector(1.0));
		if (BrickColorsDiffer(colors[i], inColor))
			++changed;
	}
	return changed;
}

static void SetMoDataColorSamples(BaseContainer& bc, Int32 baseId, MoData* md, Int32 count)
{
	if (md == nullptr || count <= 0)
		return;

	AutoLocker lock(md->GetAutoLock());
	MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
	if (!colors)
		return;

	const Int32 sampleCount = Min<Int32>(count, 5);
	bc.SetInt32(g_brick_mograph_eval_sample_count, sampleCount);
	for (Int32 i = 0; i < sampleCount; ++i)
		bc.SetVector(baseId + i, colors[i]);
}

static Int32 ApplyFieldListColors(BaseObject* effector, BaseObject* generator, MoData* md, Int32 count)
{
	if (effector == nullptr || md == nullptr || count <= 0)
		return 0;

	BaseContainer* effectorData = effector->GetDataInstance();
	if (effectorData == nullptr)
		return 0;
	if (effectorData->GetInt32(ID_MG_BASEEFFECTOR_COLOR_MODE, ID_MG_BASEEFFECTOR_COLOR_MODE_OFF) != ID_MG_BASEEFFECTOR_COLOR_MODE_FIELD)
		return 0;

	const FieldList* fields = effectorData->GetCustomDataType<FieldList>(FIELDS);
	if (fields == nullptr || !fields->HasContent())
		return 0;

	std::vector<Vector> positions;
	positions.resize(count);
	{
		AutoLocker lock(md->GetAutoLock());
		MDArray<Matrix> matrices = md->GetMatrixArray(MODATA_MATRIX);
		if (!matrices)
			return 0;
		for (Int32 i = 0; i < count; ++i)
			positions[i] = matrices[i].off;
	}

	const Matrix fieldTransform = generator != nullptr ? generator->GetMg() : Matrix();
	const FieldInput input(positions.data(), count, fieldTransform);
	iferr (FieldOutput sampled = fields->SampleListSimple(*effector, input, FIELDSAMPLE_FLAG::COLOR))
	{
		return 0;
	}
	else
	{
		ConstFieldOutputBlock block = sampled.GetBlock();
		if (block.GetCount() <= 0 || block._color.GetCount() <= 0)
			return 0;

		AutoLocker lock(md->GetAutoLock());
		MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
		if (!colors)
			return 0;

		Int32 applied = 0;
		const Int32 sampleCount = Min<Int32>(count, (Int32)block._color.GetCount());
		for (Int32 i = 0; i < sampleCount; ++i)
		{
			const Vector sampledColor = block._color[i];
			if (BrickColorsDiffer(colors[i], sampledColor))
			{
				colors[i] = sampledColor;
				++applied;
			}
		}
		return applied;
	}
}

class BrickMoGraphEvaluatorTag : public TagData
{
	INSTANCEOF(BrickMoGraphEvaluatorTag, TagData)

public:
	static NodeData* Alloc() { return NewObjClear(BrickMoGraphEvaluatorTag); }

	virtual Bool Message(GeListNode* node, Int32 type, void* data) override
	{
		if (type != g_brick_mograph_evaluate_msg_id)
			return SUPER::Message(node, type, data);

		BaseTag* tag = static_cast<BaseTag*>(node);
		if (tag == nullptr)
			return false;

		BaseContainer& bc = tag->GetDataInstanceRef();
		const Int32 count = bc.GetInt32(g_brick_mograph_eval_count, 0);
		const Bool skipFieldOverride = bc.GetBool(g_brick_mograph_eval_skip_field_override, false);
		bc.SetBool(g_brick_mograph_eval_ok, false);
		bc.SetInt32(g_brick_mograph_eval_color_changed, 0);
		bc.SetInt32(g_brick_mograph_eval_field_color_applied, 0);
		bc.SetInt32(g_brick_mograph_eval_field_color_mode_count, 0);
		bc.SetInt32(g_brick_mograph_eval_effector_color_changed, 0);
		bc.SetInt32(g_brick_mograph_eval_post_field_color_changed, 0);
		bc.SetBool(g_brick_mograph_eval_manual_field_skipped, skipFieldOverride);
		bc.SetInt32(g_brick_mograph_eval_sample_count, 0);
		if (count <= 0)
			return true;

		MoData* md = MoData::Alloc();
		if (md == nullptr)
			return false;

		Bool ok = true;
		if (md->AddArray(MODATA_MATRIX, DTYPE_MATRIX, "Matrix"_s, MOGENFLAG_MODATASET) == NOTOK)
			ok = false;
		if (md->AddArray(MODATA_COLOR, DTYPE_COLOR, "Color"_s, MOGENFLAG_COLORSET) == NOTOK)
			ok = false;
		if (md->AddArray(MODATA_FLAGS, DTYPE_LONG, "Flags"_s, 0) == NOTOK)
			ok = false;
		if (md->AddArray(MODATA_WEIGHT, DTYPE_REAL, "Weight"_s, 0) == NOTOK)
			ok = false;
		if (ok && !md->SetCount(count))
			ok = false;

		if (ok)
		{
			AutoLocker lock(md->GetAutoLock());
			MDArray<Matrix> matrices = md->GetMatrixArray(MODATA_MATRIX);
			MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
			MDArray<Int32> flags = md->GetLongArray(MODATA_FLAGS);
			MDArray<Float> weights = md->GetRealArray(MODATA_WEIGHT);
			if (!matrices || !colors || !flags || !weights)
			{
				ok = false;
			}
			else
			{
				for (Int32 i = 0; i < count; ++i)
				{
					matrices[i] = bc.GetMatrix(g_brick_mograph_eval_in_matrix_base + i, Matrix());
					colors[i] = bc.GetVector(g_brick_mograph_eval_in_color_base + i, Vector(1.0));
					flags[i] = MOGENFLAG_CLONE_ON | MOGENFLAG_MODATASET | MOGENFLAG_COLORSET;
					weights[i] = 1.0;
				}
			}
		}

		BaseObject* owner = tag->GetObject();
		BaseObject* generator = owner;
		BaseDocument* doc = owner != nullptr ? owner->GetDocument() : nullptr;
		if (doc == nullptr)
			doc = GetActiveDocument();
		const BaseList2D* linkedGenerator = bc.GetObjectLink(g_brick_mograph_eval_generator, doc);
		if (linkedGenerator != nullptr && linkedGenerator->IsInstanceOf(Obase))
		{
			generator = const_cast<BaseObject*>(static_cast<const BaseObject*>(linkedGenerator));
			if (doc == nullptr)
				doc = generator->GetDocument();
		}

		const InExcludeData* effectors = bc.GetCustomDataType<InExcludeData>(g_brick_mograph_eval_effectors);
		if (ok && effectors != nullptr)
		{
			Int32 fieldColorApplied = 0;
			Int32 fieldColorModeCount = 0;
			std::vector<BaseObject*> fieldColorEffectors;
			const Int32 effectorCount = effectors->GetObjectCount();
			for (Int32 i = 0; i < effectorCount; ++i)
			{
				BaseList2D* linked = effectors->ObjectFromIndex(doc, i);
				if (linked == nullptr || !linked->IsInstanceOf(Obase))
					continue;
				BaseObject* effector = static_cast<BaseObject*>(linked);
				Effector_PassData pass;
				pass.op = generator;
				pass.md = md;
				pass.weight = 1.0;
				pass.thread = nullptr;
				effector->Message(MSG_EXECUTE_EFFECTOR, &pass);
				BaseContainer* effectorData = effector->GetDataInstance();
				if (effectorData != nullptr && effectorData->GetInt32(ID_MG_BASEEFFECTOR_COLOR_MODE, ID_MG_BASEEFFECTOR_COLOR_MODE_OFF) == ID_MG_BASEEFFECTOR_COLOR_MODE_FIELD)
				{
					++fieldColorModeCount;
					fieldColorEffectors.push_back(effector);
				}
			}
			const Int32 effectorColorChanged = CountChangedMoDataColors(md, bc, count);
			bc.SetInt32(g_brick_mograph_eval_effector_color_changed, effectorColorChanged);
			SetMoDataColorSamples(bc, g_brick_mograph_eval_effector_color_sample_base, md, count);
			if (!skipFieldOverride)
			{
				for (BaseObject* fieldEffector : fieldColorEffectors)
					fieldColorApplied += ApplyFieldListColors(fieldEffector, generator, md, count);
			}
			bc.SetInt32(g_brick_mograph_eval_field_color_applied, fieldColorApplied);
			bc.SetInt32(g_brick_mograph_eval_field_color_mode_count, fieldColorModeCount);
			const Int32 postFieldColorChanged = CountChangedMoDataColors(md, bc, count);
			bc.SetInt32(g_brick_mograph_eval_post_field_color_changed, postFieldColorChanged);
			SetMoDataColorSamples(bc, g_brick_mograph_eval_field_color_sample_base, md, count);
		}

		Int32 visibilityChanged = 0;
		if (ok)
		{
			AutoLocker lock(md->GetAutoLock());
			MDArray<Matrix> matrices = md->GetMatrixArray(MODATA_MATRIX);
			MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
			MDArray<Int32> flags = md->GetLongArray(MODATA_FLAGS);
			if (!matrices || !colors || !flags)
			{
				ok = false;
			}
			else
			{
				for (Int32 i = 0; i < count; ++i)
				{
					bc.SetMatrix(g_brick_mograph_eval_out_matrix_base + i, matrices[i]);
					bc.SetVector(g_brick_mograph_eval_out_color_base + i, colors[i]);
					const Bool visible = (flags[i] & MOGENFLAG_CLONE_ON) != 0;
					bc.SetBool(g_brick_mograph_eval_out_visible_base + i, visible);
					if (!visible)
						++visibilityChanged;
				}
			}
		}

		bc.SetInt32(g_brick_mograph_eval_color_changed, bc.GetInt32(g_brick_mograph_eval_post_field_color_changed, 0));
		bc.SetInt32(g_brick_mograph_eval_visibility_changed, visibilityChanged);
		bc.SetBool(g_brick_mograph_eval_ok, ok);
		MoData::Free(md);
		return true;
	}
};

Bool RegisterBrickMoGraphEvaluatorTag()
{
	// PLUGINFLAG_HIDEPLUGINMENU + PLUGINFLAG_HIDE keep this internal
	// message-passing tag out of the OM right-click "Add Tag" menu. The
	// tag is instantiated programmatically by brickit_mograph_generator
	// and is never user-addable.
	return RegisterTagPlugin(
		g_brick_mograph_evaluator_tag_id,
		"Brick MoGraph Evaluator"_s,
		TAG_MULTIPLE | PLUGINFLAG_HIDEPLUGINMENU | PLUGINFLAG_HIDE,
		BrickMoGraphEvaluatorTag::Alloc,
		""_s,
		nullptr,
		0);
}


cinema::Bool cinema::PluginStart()
{
	if (!RegisterBrickLibraryCustomGUI())
		return false;
	if (!RegisterBrickHeroCustomGUI())
		return false;
	if (!RegisterBrickSourcesCustomGUI())
		return false;
	if (!RegisterBrickMoGraphEvaluatorTag())
		return false;

	if (!RegisterBrickLibraryPanelCommand())
		return false;
	return true;
}

void cinema::PluginEnd()
{
}

cinema::Bool cinema::PluginMessage(cinema::Int32 id, void* data)
{
	switch (id)
	{
		case C4DPL_INIT_SYS:
		{
			if (!g_resource.Init())
				return false;
			return true;
		}
	}
	return false;
}
