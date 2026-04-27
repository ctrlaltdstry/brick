#include "c4d.h"
#include "c4d_gui.h"
#include "c4d_plugin.h"
#include "c4d_resource.h"
#include <array>

using namespace cinema;

static const Int32 g_bricklibrary_panel_cmd_id = 1069996;
static const Int32 g_bricklibrary_customgui_id = 1070997;
static const Int32 g_brick_count = 22;
static const Int32 g_cols = 6;
static const Int32 g_userarea_id = 2000;
static const Int32 g_status_text_id = 2001;

static const Char* g_brick_labels[g_brick_count] = {
	"1x1", "1x2", "1x3", "1x4", "1x6", "1x8", "2x2", "2x3", "2x4", "2x6", "2x8",
	"1x1p", "1x2p", "1x3p", "1x4p", "1x6p", "1x8p", "2x2p", "2x3p", "2x4p", "2x6p", "2x8p"
};
static const Char* g_brick_asset_names[g_brick_count] = {
	"brick_1x1", "brick_1x2", "brick_1x3", "brick_1x4", "brick_1x6", "brick_1x8",
	"brick_2x2", "brick_2x3", "brick_2x4", "brick_2x6", "brick_2x8",
	"plate_1x1", "plate_1x2", "plate_1x3", "plate_1x4", "plate_1x6", "plate_1x8",
	"plate_2x2", "plate_2x3", "plate_2x4", "plate_2x6", "plate_2x8"
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
		GroupBegin(1000, BFH_SCALEFIT | BFV_SCALEFIT, 1, 0, ""_s, 0);
		GroupBorderSpace(4, 4, 4, 4);
		C4DGadget* gadget = AddUserArea(g_userarea_id, BFH_SCALEFIT | BFV_SCALEFIT, 420, 230);
		AttachUserArea(_area, gadget);
		AddStaticText(g_status_text_id, BFH_LEFT, 0, 0, ""_s, BORDER_NONE);
		GroupEnd();
		return SUPER::CreateLayout();
	}

	virtual Bool InitValues() override
	{
		if (_tristate)
			SetString(g_status_text_id, "Mixed Selection"_s);
		else
			SetString(g_status_text_id, FormatString("Enabled bricks: @", CountEnabled(_bitmask)));

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
	static Int32 CountEnabled(Int32 bitmask)
	{
		Int32 count = 0;
		for (Int32 i = 0; i < g_brick_count; ++i)
		{
			if ((bitmask & (1 << i)) != 0)
				++count;
		}
		return count;
	}

	void LoadThumbnails()
	{
		const Filename pluginPath = GeGetPluginPath();
		const Filename pluginDir = pluginPath.GetDirectory();
		const Filename roots[3] = {
			pluginPath + Filename("res") + Filename("icons") + Filename("bricks"),
			pluginDir + Filename("res") + Filename("icons") + Filename("bricks"),
			pluginDir + Filename("BrickGenerator") + Filename("res") + Filename("icons") + Filename("bricks"),
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
	h = 230;
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
	const Int32 cellW = w / g_cols;
	const Int32 cellH = h / rows;
	const Int32 tileOuterPad = 2;
	const Int32 tileInnerPad = 2;
	const Int32 labelHeight = 14;

	for (Int32 i = 0; i < g_brick_count; ++i)
	{
		const Int32 col = i % g_cols;
		const Int32 row = i / g_cols;

		const Int32 xStart = col * cellW + tileOuterPad;
		const Int32 yStart = row * cellH + tileOuterPad;
		const Int32 xEnd = (col + 1) * cellW - tileOuterPad - 1;
		const Int32 yEnd = (row + 1) * cellH - tileOuterPad - 1;
		const Int32 innerX0 = xStart + tileInnerPad;
		const Int32 innerY0 = yStart + tileInnerPad;
		const Int32 innerX1 = xEnd - tileInnerPad;
		const Int32 innerY1 = yEnd - tileInnerPad;

		const Bool enabled = _owner && _owner->IsEnabled(i);

		DrawSetPen(Vector(0.15, 0.15, 0.15));
		DrawRectangle(xStart, yStart, xEnd, yEnd);
		DrawSetPen(enabled ? Vector(0.85, 0.24, 0.24) : Vector(0.35, 0.35, 0.35));
		DrawFrame(xStart, yStart, xEnd, yEnd);

		BaseBitmap* bmp = _owner ? _owner->GetThumbnail(i) : nullptr;
		if (bmp != nullptr)
		{
			const Int32 imgAreaX0 = innerX0;
			const Int32 imgAreaY0 = innerY0 + labelHeight;
			const Int32 imgAreaX1 = innerX1;
			const Int32 imgAreaY1 = innerY1;
			const Int32 areaW = Max(1, imgAreaX1 - imgAreaX0 + 1);
			const Int32 areaH = Max(1, imgAreaY1 - imgAreaY0 + 1);

			const Int32 bw = Max(1, bmp->GetBw());
			const Int32 bh = Max(1, bmp->GetBh());
			const Float sx = Float(areaW) / Float(bw);
			const Float sy = Float(areaH) / Float(bh);
			const Float s = sx < sy ? sx : sy;
			const Int32 drawW = Max(1, Int32(Float(bw) * s));
			const Int32 drawH = Max(1, Int32(Float(bh) * s));
			const Int32 drawX = imgAreaX0 + (areaW - drawW) / 2;
			const Int32 drawY = imgAreaY0 + (areaH - drawH) / 2;

			DrawBitmap(
				bmp,
				drawX, drawY,
				drawW, drawH,
				0, 0, bmp->GetBw(), bmp->GetBh(),
				BMP_NORMALSCALED
			);
		}
		else
		{
			DrawSetPen(enabled ? Vector(0.72, 0.18, 0.18) : Vector(0.24, 0.24, 0.24));
			DrawRectangle(innerX0, innerY0 + labelHeight, innerX1, innerY1);
		}

		// Draw label last with explicit text colors for readability.
		DrawSetTextCol(Vector(0.96, 0.96, 0.96), Vector(0.15, 0.15, 0.15));
		DrawText(String(g_brick_labels[i]), innerX0, innerY0 - 1, DRAWTEXT_STD_ALIGN);
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
	const Int32 cellW = w / g_cols;
	const Int32 cellH = h / rows;
	if (cellW <= 0 || cellH <= 0)
		return false;

	const Int32 col = mx / cellW;
	const Int32 row = my / cellH;
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

cinema::Bool cinema::PluginStart()
{
	if (!RegisterBrickLibraryCustomGUI())
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
