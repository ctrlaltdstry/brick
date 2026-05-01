#include "c4d.h"
#include "c4d_baseeffectordata.h"
#include "c4d_customgui/customgui_field.h"
#include "c4d_customgui/customgui_inexclude.h"
#include "c4d_gui.h"
#include "c4d_plugin.h"
#include "c4d_resource.h"
#include "description/obaseeffector.h"
#include "description/ofalloff_panel.h"
#include <array>
#include <vector>

using namespace cinema;

static const Int32 g_bricklibrary_panel_cmd_id = 1069996;
static const Int32 g_bricklibrary_customgui_id = 1070997;
static const Int32 g_brickhero_customgui_id = 1070998;
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
static const Int32 g_brick_mograph_eval_in_matrix_base = 200000;
static const Int32 g_brick_mograph_eval_in_color_base = 300000;
static const Int32 g_brick_mograph_eval_out_matrix_base = 400000;
static const Int32 g_brick_mograph_eval_out_color_base = 500000;
static const Int32 g_brick_mograph_eval_effector_color_sample_base = 600000;
static const Int32 g_brick_mograph_eval_field_color_sample_base = 601000;
static const Int32 g_brick_count = 15;
static const Int32 g_cols = 6;
static const Int32 g_userarea_id = 2000;
static const Int32 g_hero_userarea_id = 3000;
static const Int32 g_library_min_width = 420;
static const Int32 g_library_grid_height = 252;

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

	DrawSetPen(Vector(0.12, 0.12, 0.12));
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

		DrawSetPen(Vector(0.15, 0.15, 0.15));
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
			DrawSetPen(enabled ? Vector(0.72, 0.18, 0.18) : Vector(0.24, 0.24, 0.24));
			DrawRectangle(innerX0, innerY0, innerX1, innerY1);
		}

		// Label is drawn last — keep it dark on the light-grey thumb backdrops without
		// the thick dark "subtitle bar" the light-on-dark pairing produced.
		DrawSetTextCol(Vector(0.05, 0.05, 0.08), Vector(0.93, 0.93, 0.93));
		DrawText(String(g_brick_labels[i]), innerX0 + 2, innerY0 + 1, DRAWTEXT_STD_ALIGN);

		// Full-bleed thumbnails cover the tile, so draw selection chrome last.
		DrawSetPen(enabled ? Vector(0.85, 0.24, 0.24) : Vector(0.35, 0.35, 0.35));
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

	DrawSetPen(Vector(0.08, 0.08, 0.08));
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
	return RegisterCommandPlugin(
		g_bricklibrary_panel_cmd_id,
		"Brick Library Inline GUI (WIP)"_s,
		0,
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

		if (ok)
		{
			AutoLocker lock(md->GetAutoLock());
			MDArray<Matrix> matrices = md->GetMatrixArray(MODATA_MATRIX);
			MDArray<Vector> colors = md->GetVectorArray(MODATA_COLOR);
			if (!matrices || !colors)
			{
				ok = false;
			}
			else
			{
				for (Int32 i = 0; i < count; ++i)
				{
					bc.SetMatrix(g_brick_mograph_eval_out_matrix_base + i, matrices[i]);
					bc.SetVector(g_brick_mograph_eval_out_color_base + i, colors[i]);
				}
			}
		}

		bc.SetInt32(g_brick_mograph_eval_color_changed, bc.GetInt32(g_brick_mograph_eval_post_field_color_changed, 0));
		bc.SetBool(g_brick_mograph_eval_ok, ok);
		MoData::Free(md);
		return true;
	}
};

Bool RegisterBrickMoGraphEvaluatorTag()
{
	return RegisterTagPlugin(
		g_brick_mograph_evaluator_tag_id,
		"Brick MoGraph Evaluator"_s,
		TAG_MULTIPLE,
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
