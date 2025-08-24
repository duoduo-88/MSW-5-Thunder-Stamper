#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import io
import time
import mmap
import struct
import traceback
from pathlib import Path
from dataclasses import dataclass

from PySide6 import QtCore, QtWidgets, QtGui

# -------------------- 常量 & 預設 --------------------
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
DEFAULT_EXTS = [
    ".mod",
]
SCAN_INTERVAL_SEC = 1.5  # 監看輪詢間隔

# -------------------- 圖像封包（記憶體，不落地） --------------------
@dataclass
class ImageBlob:
    source_file: str
    source_path: str
    label: str
    png_bytes: bytes
    width: int = 0
    height: int = 0
    def qpixmap(self) -> QtGui.QPixmap:
        pix = QtGui.QPixmap(); pix.loadFromData(self.png_bytes, "PNG"); return pix

# -------------------- 抽取：位元組掃描 PNG --------------------
def bytescan_pngs(file_path: Path):
    imgs, errs = [], []
    try:
        size = file_path.stat().st_size
        if size < 16: return imgs, errs
        with open(file_path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                search_pos = 0
                base = file_path.stem
                idx = 0
                while True:
                    start = mm.find(PNG_MAGIC, search_pos)
                    if start == -1: break
                    pos = start + len(PNG_MAGIC)
                    try:
                        while True:
                            if pos + 8 > size: raise ValueError("EOF @hdr")
                            length = struct.unpack(">I", mm[pos:pos+4])[0]
                            ctype  = mm[pos+4:pos+8]; pos += 8
                            if pos + length + 4 > size: raise ValueError("EOF @data")
                            if ctype == b"IEND":
                                pos += 4
                                raw = bytes(mm[start:pos])
                                idx += 1
                                label = f"{base}_{idx:03d}.png"
                                w, h = sniff_png_size(raw)
                                imgs.append(ImageBlob(file_path.name, str(file_path), label, raw, w, h))
                                search_pos = pos
                                break
                            else:
                                pos += length + 4
                    except Exception as e:
                        errs.append(f"bytescan fail @{start}: {e}")
                        search_pos = start + 1
                        continue
            finally:
                mm.close()
    except Exception as e:
        errs.append(f"{file_path.name}: {e}")
    return imgs, errs

def sniff_png_size(png_bytes: bytes) -> tuple[int,int]:
    try:
        if not png_bytes.startswith(PNG_MAGIC): return 0,0
        length = struct.unpack(">I", png_bytes[8:12])[0]
        if png_bytes[12:16] != b"IHDR" or length != 13: return 0,0
        w = struct.unpack(">I", png_bytes[16:20])[0]
        h = struct.unpack(">I", png_bytes[20:24])[0]
        return int(w), int(h)
    except Exception:
        return 0,0

# -------------------- 抽取：UnityPy 解析 Texture2D（選用） --------------------
def unitypy_textures(file_path: Path):
    imgs, errs = [], []
    try:
        try:
            import UnityPy  # type: ignore
        except Exception as e:
            return [], [f"UnityPy not available: {e}"]
        env = UnityPy.load(str(file_path))
        base = file_path.stem
        idx = 0
        for obj in env.objects:
            if obj.type.name != "Texture2D": continue
            try:
                data = obj.read()
                image = data.image
                if image is None: continue
                idx += 1
                bio = io.BytesIO(); image.save(bio, format="PNG"); raw = bio.getvalue()
                w, h = image.size
                label = f"{base}_tex2d_{idx:03d}.png"
                imgs.append(ImageBlob(file_path.name, str(file_path), label, raw, w, h))
            except Exception as e:
                errs.append(f"Texture2D export failed: {e}")
    except Exception as e:
        errs.append(f"UnityPy load failed: {e}")
    return imgs, errs

# -------------------- 監看工作者 --------------------
class WatchWorker(QtCore.QObject):
    imageFound = QtCore.Signal(object)   # ImageBlob
    fileLog    = QtCore.Signal(str)
    statMsg    = QtCore.Signal(str)
    finished   = QtCore.Signal()
    def __init__(self, root_dir: Path, recurse: bool, exts, min_size_bytes: int,
                 use_unitypy: bool, stop_flag):
        super().__init__()
        self.root_dir = root_dir
        self.recurse = recurse
        self.exts = [e.lower() for e in exts] if exts else []
        self.min_size_bytes = max(0, int(min_size_bytes))
        self.use_unitypy = bool(use_unitypy)
        self.stop_flag = stop_flag
        self._seen = {}  # path -> (size, mtime)
    def run(self):
        try:
            while not self.stop_flag.is_set():
                files = self._enumerate_files()
                for p in files:
                    if self.stop_flag.is_set(): break
                    try:
                        st = p.stat(); key = str(p); sig = (st.st_size, st.st_mtime)
                        if self._seen.get(key) == sig: continue
                        self._seen[key] = sig
                        self.statMsg.emit("監看中…")
                        imgs, errs = bytescan_pngs(p)
                        if not imgs and self.use_unitypy:
                            up_imgs, up_errs = unitypy_textures(p)
                            imgs += up_imgs; errs += up_errs
                        for e in errs: self.fileLog.emit("⚠ " + e)
                        if imgs:
                            self.fileLog.emit(f"✅ {p.name} → 解析出 {len(imgs)} 張")
                            for im in imgs: self.imageFound.emit(im)
                        else:
                            self.fileLog.emit(f"— {p.name} 沒有解析出圖片")
                    except Exception as e:
                        self.fileLog.emit(f"❌ {p.name}: {e}")
                self.statMsg.emit("監看中…")
                self._sleep_intervals(SCAN_INTERVAL_SEC, check_every=10)
        finally:
            self.finished.emit()
    def _sleep_intervals(self, total_sec: float, check_every: int = 10):
        slices = int(total_sec * check_every) or 1
        step = total_sec / slices
        for _ in range(slices):
            if self.stop_flag.is_set(): break
            time.sleep(step)
    def _enumerate_files(self):
        root = self.root_dir; res = []
        it = root.rglob("*") if self.recurse else root.glob("*")
        for p in it:
            if not p.is_file(): continue
            try:
                if self.min_size_bytes > 0 and p.stat().st_size < self.min_size_bytes:
                    continue
            except Exception:
                continue
            if p.suffix.lower() == ".png": continue
            if self.exts:
                if p.suffix.lower() in self.exts: res.append(p)
            else:
                res.append(p)
        return res

# -------------------- 自訂 Delegate：縮圖右側/下方自動排版（右側改為多行換行填滿） --------------------
class ThumbTextDelegate(QtWidgets.QStyledItemDelegate):
    GAP = 8
    PAD = 8
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PE_PanelItemViewItem, opt, painter, opt.widget)

        icon = opt.icon
        text = opt.text or ""

        view = opt.widget
        mode_right = getattr(view, "_mode_right", False)
        icon_size = view.iconSize()
        iw, ih = icon_size.width(), icon_size.height()

        r = QtCore.QRect(opt.rect).marginsRemoved(QtCore.QMargins(self.PAD, self.PAD, self.PAD, self.PAD))

        # Icon 區
        icon_rect = QtCore.QRect(r.left(), r.top(), iw, ih)
        actual = icon.pixmap(iw, ih, QtGui.QIcon.Normal if opt.state & QtWidgets.QStyle.State_Enabled else QtGui.QIcon.Disabled)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(icon_rect, actual)
        painter.restore()

        fm = opt.fontMetrics
        if mode_right:
            # 右側文字：改成「多行換行」佔滿整個右側高度（盡量填滿紅框區）
            tx = icon_rect.right() + self.GAP
            text_rect = QtCore.QRect(tx, r.top(), r.right() - tx, ih)
            painter.drawText(text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap, text)
        else:
            # 下方單行/兩行
            ty = icon_rect.bottom() + self.GAP
            text_rect = QtCore.QRect(r.left(), ty, r.width(), fm.height() * 2)
            painter.drawText(text_rect, QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter | QtCore.Qt.TextWordWrap, text)

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        view = option.widget
        icon_size = view.iconSize()
        fm = option.fontMetrics
        if getattr(view, "_mode_right", False):
            h = max(icon_size.height(), fm.height()) + self.PAD * 2
        else:
            h = icon_size.height() + self.GAP + fm.height() * 2 + self.PAD * 2
        return QtCore.QSize(icon_size.width() + 300, h)

# -------------------- 客製 QListWidget：自適應 gridSize & 模式切換 --------------------
class ThumbListWidget(QtWidgets.QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._thumb = 96
        self._mode_right_threshold = 160
        self._mode_right = False
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setFlow(QtWidgets.QListView.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QtWidgets.QListView.Static)
        self.setSpacing(6)
        self.setItemDelegate(ThumbTextDelegate())
        self.updateMetrics()

    def setThumb(self, s: int):
        self._thumb = max(32, int(s))
        self.updateMetrics()

    def updateMetrics(self):
        iw = ih = self._thumb
        self.setIconSize(QtCore.QSize(iw, ih))
        available_text = max(0, self.viewport().width() - (iw + ThumbTextDelegate.GAP + ThumbTextDelegate.PAD * 2))
        self._mode_right = available_text >= self._mode_right_threshold
        self._mode_right_prop_to_children()
        if self._mode_right:
            fm = self.fontMetrics()
            h = max(ih, fm.height()) + ThumbTextDelegate.PAD * 2
        else:
            fm = self.fontMetrics()
            h = ih + ThumbTextDelegate.GAP + fm.height() * 2 + ThumbTextDelegate.PAD * 2
        w = self.viewport().width() or (iw + 180)
        self.setGridSize(QtCore.QSize(w, h))
        self.viewport().update()

    def _mode_right_prop_to_children(self):
        self.setProperty("_mode_right", bool(self._mode_right))

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e)
        self.updateMetrics()

# -------------------- 進度條（中央白字疊印） --------------------
class StatusProgressBar(QtWidgets.QProgressBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._overlay = ""
        self.setTextVisible(False)
    def setOverlayText(self, text: str):
        self._overlay = text or ""
        self.update()
    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._overlay:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF")))
        f = self.font(); f.setBold(True); p.setFont(f)
        p.drawText(self.rect(), QtCore.Qt.AlignCenter, self._overlay)
        p.end()

# -------------------- 可縮放/拖移預覽（含 HUD） --------------------
class ImagePreview(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self._item = None
        self._hud = QtWidgets.QLabel(self)
        self._hud.setText("")
        self._hud.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._hud.setStyleSheet("QLabel{background-color: rgba(0,0,0,120); color: #EEE; padding: 4px 8px; border-radius: 6px; font-size: 12px;}")
        self._hud.hide()
        self._empty = QtWidgets.QGraphicsTextItem("尚無預覽")
        self._empty.setDefaultTextColor(QtGui.QColor("#AAAAAA"))
        f = QtGui.QFont(); f.setPointSize(14); self._empty.setFont(f)
        self.scene().addItem(self._empty)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform | QtGui.QPainter.TextAntialiasing)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self._min_zoom, self._max_zoom = 0.05, 50.0
        self._hud_margin = 8
    def clear_image(self, text="尚無預覽"):
        self.scene().clear(); self._item = None
        self._empty = QtWidgets.QGraphicsTextItem(text)
        self._empty.setDefaultTextColor(QtGui.QColor("#AAAAAA"))
        f = QtGui.QFont(); f.setPointSize(14); self._empty.setFont(f)
        self.scene().addItem(self._empty)
        self.resetTransform()
        self._hud.hide()
    def set_image_bytes(self, png_bytes: bytes):
        pix = QtGui.QPixmap()
        if not pix.loadFromData(png_bytes, "PNG"):
            self.clear_image("預覽失敗"); return
        self.scene().clear()
        self._item = self.scene().addPixmap(pix)
        self.scene().setSceneRect(self._item.boundingRect())
        self._fit()
    def _fit(self):
        if not self._item: return
        self.resetTransform()
        br = self._item.boundingRect()
        if not br.isEmpty():
            self.fitInView(br.marginsAdded(QtCore.QMarginsF(4,4,4,4)), QtCore.Qt.KeepAspectRatio)
        self._reposition_hud()
    def wheelEvent(self, e: QtGui.QWheelEvent):
        if not self._item: return super().wheelEvent(e)
        factor = 1.15 if e.angleDelta().y() > 0 else 1/1.15
        cur = self.transform().m11()
        target = cur * factor
        if target < self._min_zoom: factor = self._min_zoom / cur
        elif target > self._max_zoom: factor = self._max_zoom / cur
        self.scale(factor, factor); self._reposition_hud()
    def mouseDoubleClickEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            cur = self.transform().m11()
            if abs(cur - 1.0) < 0.05: self._fit()
            else: self.resetTransform(); self._reposition_hud()
        else:
            super().mouseDoubleClickEvent(e)
    def resizeEvent(self, e):
        super().resizeEvent(e); self._reposition_hud()
    def set_overlay_text(self, text: str):
        if text:
            self._hud.setText(text); self._hud.adjustSize(); self._hud.show(); self._reposition_hud()
        else:
            self._hud.hide()
    def _reposition_hud(self):
        if not self._hud.isVisible(): return
        m = self._hud_margin
        x = m
        y = self.viewport().height() - self._hud.height() - m
        self._hud.move(x, y)

# -------------------- 主視窗 --------------------
class LivePreviewWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MSW碎片檢查工具 MSW Fragment Viewer v1.0.0")
        self.setFixedSize(1600, 900)

        import threading
        self.stop_flag = threading.Event()
        self.images: list[ImageBlob] = []
        self.max_cache = 500
        self.auto_preview_latest = True

        # ---- 上方控制列 ----
        self.src_edit = QtWidgets.QLineEdit(); self.src_btn  = QtWidgets.QPushButton("來源資料夾…")
        self.out_edit = QtWidgets.QLineEdit(); self.out_btn  = QtWidgets.QPushButton("匯出資料夾…")
        self.recurse_chk = QtWidgets.QCheckBox("包含子資料夾"); self.recurse_chk.setChecked(True)
        self.group_chk   = QtWidgets.QCheckBox("匯出時依來源檔名建立子資料夾"); self.group_chk.setChecked(True)
        self.ext_hint = QtWidgets.QLabel("副檔名清單（逗號分隔；留空=所有檔案）")
        self.ext_edit = QtWidgets.QLineEdit(", ".join(DEFAULT_EXTS))
        self.size_lbl = QtWidgets.QLabel("檔案尺寸下限 (MB)    ")
        self.size_spin = QtWidgets.QDoubleSpinBox(); self.size_spin.setDecimals(1); self.size_spin.setRange(0.0, 10240.0); self.size_spin.setSingleStep(1.0)
        self.use_unitypy_chk = QtWidgets.QCheckBox("啟用 UnityPy 解析（Texture2D→PNG）"); self.use_unitypy_chk.setChecked(True)
        self.auto_prev_chk   = QtWidgets.QCheckBox("自動預覽最新"); self.auto_prev_chk.setChecked(True); self.auto_prev_chk.toggled.connect(self._set_auto_preview)
        self.max_cache_lbl = QtWidgets.QLabel("最大快取張數              ")
        self.max_cache_spin = QtWidgets.QSpinBox(); self.max_cache_spin.setRange(10, 10000); self.max_cache_spin.setValue(self.max_cache); self.max_cache_spin.valueChanged.connect(self._set_max_cache)
        self.start_btn = QtWidgets.QPushButton("開始監看")
        self.stop_btn  = QtWidgets.QPushButton("停止"); self.stop_btn.setEnabled(False)

        # ---- 左側：自訂清單 + 縮圖尺寸滑桿 ----
        self.list = ThumbListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list.currentRowChanged.connect(self.show_selected)

        self.thumb_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.thumb_slider.setRange(48, 256)
        self.thumb_slider.setValue(self.list._thumb)
        self.thumb_slider.setSingleStep(8)
        self.thumb_slider.valueChanged.connect(self._on_thumb_changed)
        self.thumb_lbl = QtWidgets.QLabel(f"縮圖：{self.list._thumb}px")

        # ---- 中間預覽與右側日誌 ----
        self.preview = ImagePreview(); self.preview.setMinimumSize(400, 400); self.preview.setStyleSheet("background:#222; color:#aaa;")
        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True)
        try:
            fixed = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
            self.log.setFont(fixed)
        except Exception:
            pass

        # ---- 底部：進度與匯出 ----
        self.progress = StatusProgressBar(); self.progress.setRange(0, 0); self.progress.setVisible(False)
        self.progress.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.progress.setMinimumHeight(18)
        self.progress.setStyleSheet("""
            QProgressBar { border: 0px; padding: 0px; background: rgba(255,255,255,0.08); }
            QProgressBar::chunk { margin: 0px; background: #ff9a2e; }
        """)
        self.export_sel_btn  = QtWidgets.QPushButton("匯出選取")
        self.export_all_btn  = QtWidgets.QPushButton("匯出全部 (目前快取)")
        self.clear_btn       = QtWidgets.QPushButton("清空快取")

        # ====== 版面：上—中—下 ======
        root = QtWidgets.QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(10)

        # 上方控制列（Grid）
        ctl = QtWidgets.QGridLayout(); ctl.setHorizontalSpacing(8); ctl.setVerticalSpacing(6)
        ctl.setColumnStretch(0, 1); ctl.setColumnStretch(1, 6); ctl.setColumnStretch(2, 2)
        r = 0
        ctl.addWidget(QtWidgets.QLabel("來源資料夾"), r, 0); ctl.addWidget(self.src_edit, r, 1); ctl.addWidget(self.src_btn,  r, 2); r += 1
        ctl.addWidget(QtWidgets.QLabel("匯出資料夾（選取匯出時使用）"), r, 0); ctl.addWidget(self.out_edit, r, 1); ctl.addWidget(self.out_btn,  r, 2); r += 1
        h1 = QtWidgets.QHBoxLayout(); h1.addWidget(self.recurse_chk); h1.addSpacing(12); h1.addWidget(self.group_chk); h1.addStretch(1); ctl.addLayout(h1, r, 0, 1, 3); r += 1
        ctl.addWidget(self.ext_hint, r, 0, 1, 3); r += 1
        ctl.addWidget(self.ext_edit, r, 0, 1, 3); r += 1
        h2 = QtWidgets.QHBoxLayout(); h2.addWidget(self.size_lbl); self.size_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed); h2.addWidget(self.size_spin); ctl.addLayout(h2, r, 0, 1, 3); r += 1
        h3 = QtWidgets.QHBoxLayout(); h3.addWidget(self.max_cache_lbl); self.max_cache_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed); h3.addWidget(self.max_cache_spin); ctl.addLayout(h3, r, 0, 1, 3); r += 1
        h4 = QtWidgets.QHBoxLayout(); h4.addWidget(self.use_unitypy_chk); h4.addSpacing(12); h4.addWidget(self.auto_prev_chk); h4.addStretch(1); ctl.addLayout(h4, r, 0, 1, 3); r += 1
        h5 = QtWidgets.QHBoxLayout()
        for b in (self.start_btn, self.stop_btn):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        h5.addWidget(self.start_btn, 1); h5.addSpacing(12); h5.addWidget(self.stop_btn, 1)
        ctl.addLayout(h5, r, 0, 1, 3); r += 1
        root.addLayout(ctl)

        # 中間三分割
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # 左：縮圖尺寸條 + 清單
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(0,0,0,0); lv.setSpacing(6)
        slider_row = QtWidgets.QHBoxLayout(); slider_row.addWidget(self.thumb_lbl); slider_row.addWidget(self.thumb_slider)
        lv.addLayout(slider_row); lv.addWidget(self.list, 1)

        # 中：預覽
        mid  = QtWidgets.QWidget(); mv = QtWidgets.QVBoxLayout(mid);  mv.setContentsMargins(0,0,0,0); mv.setSpacing(0); mv.addWidget(self.preview, 1)

        # 右：日誌
        right = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(right); rv.setContentsMargins(0,0,0,0); rv.setSpacing(0); rv.addWidget(self.log, 1)

        splitter.addWidget(left); splitter.addWidget(mid); splitter.addWidget(right)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 5); splitter.setStretchFactor(2, 3)
        root.addWidget(splitter, 1)

        # 進度條
        root.addWidget(self.progress)

        # 底部：匯出三鍵（等寬）
        export_row = QtWidgets.QHBoxLayout()
        for b in (self.export_sel_btn, self.export_all_btn, self.clear_btn):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        export_row.addWidget(self.export_sel_btn, 1); export_row.addSpacing(12)
        export_row.addWidget(self.export_all_btn, 1); export_row.addSpacing(12)
        export_row.addWidget(self.clear_btn, 1)
        root.addLayout(export_row)

        # 事件
        self.src_btn.clicked.connect(self.choose_src)
        self.out_btn.clicked.connect(self.choose_out)
        self.start_btn.clicked.connect(self.start_watch)
        self.stop_btn.clicked.connect(self.stop_watch)
        self.export_sel_btn.clicked.connect(self.export_selected)
        self.export_all_btn.clicked.connect(self.export_all)
        self.clear_btn.clicked.connect(self.clear_cache)

        self.thread = None
        self.worker = None

    # ---- 縮圖尺寸控制 ----
    def _on_thumb_changed(self, v: int):
        self.list.setThumb(v)
        self.thumb_lbl.setText(f"縮圖：{v}px")

    # -------- 控制邏輯 --------
    def start_watch(self):
        src = self.src_edit.text().strip()
        if not src or not os.path.isdir(src):
            QtWidgets.QMessageBox.warning(self, "錯誤", "請選擇正確的來源資料夾"); return
        exts_text = self.ext_edit.text().strip()
        exts_list = [s.strip().lower() for s in exts_text.split(",") if s.strip()]
        exts = [x if x.startswith(".") else "." + x for x in exts_list] if exts_list else []
        min_size_bytes = int(float(self.size_spin.value()) * 1024 * 1024)
        self.log.clear()
        if min_size_bytes > 0: self.append_log(f"將忽略小於 {self.size_spin.value():.1f} MB 的檔案")
        self.stop_flag.clear(); self.set_running(True)

        self.thread = QtCore.QThread(self)
        self.worker = WatchWorker(
            root_dir=Path(src),
            recurse=self.recurse_chk.isChecked(),
            exts=exts,
            min_size_bytes=min_size_bytes,
            use_unitypy=self.use_unitypy_chk.isChecked(),
            stop_flag=self.stop_flag
        )
        self.worker.moveToThread(self.thread)
        self.worker.imageFound.connect(self.on_image_found)
        self.worker.fileLog.connect(self.append_log)
        self.worker.statMsg.connect(self.set_status)
        self.worker.finished.connect(self.on_worker_done)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def stop_watch(self):
        self.set_status("停止中…")
        self.append_log("🛑 停止中…將在本輪掃描結束後停止。"); self.stop_flag.set()

    def on_worker_done(self):
        self.set_running(False)
        if self.thread:
            self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        self.set_status("已停止")

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        for w in (self.src_btn, self.recurse_chk, self.ext_edit, self.size_spin,
                  self.use_unitypy_chk, self.auto_prev_chk, self.max_cache_spin,
                  self.src_edit, self.out_btn, self.out_edit):
            w.setEnabled(not running)
        self.progress.setVisible(running)
        if running: self.progress.setOverlayText("監看中…")
        else:       self.progress.setOverlayText("")

    # -------- 預覽 & 清單 --------
    @QtCore.Slot(object)
    def on_image_found(self, img: ImageBlob):
        # 最新加入頂部（index 0），清單也插入在最上面
        self.images.insert(0, img)
        # 控制快取大小（從尾端移除舊的）
        if len(self.images) > self.max_cache:
            drop = len(self.images) - self.max_cache
            del self.images[-drop:]
            for _ in range(min(drop, self.list.count())):
                self.list.takeItem(self.list.count()-1)

        item = QtWidgets.QListWidgetItem(f"{img.label}  [{img.width}x{img.height}]  <{Path(img.source_path).name}>")
        pm = img.qpixmap().scaled(self.list._thumb, self.list._thumb, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        item.setIcon(QtGui.QIcon(pm))
        self.list.insertItem(0, item)

        if self.auto_preview_latest:
            self.list.setCurrentRow(0)

    def show_selected(self, row: int):
        if row < 0 or row >= len(self.images):
            self.preview.clear_image("尚無預覽"); self.preview.set_overlay_text(""); return
        img = self.images[row]
        self.preview.set_image_bytes(img.png_bytes)
        self.preview.set_overlay_text(f"{img.label}   {img.width}x{img.height}   來源：{img.source_file}")

    def resizeEvent(self, ev):
        super().resizeEvent(ev); self.show_selected(self.list.currentRow())

    def _set_auto_preview(self, checked: bool): self.auto_preview_latest = checked
    def _set_max_cache(self, v: int): self.max_cache = v

    def clear_cache(self):
        self.images.clear(); self.list.clear(); self.preview.clear_image("尚無預覽"); self.preview.set_overlay_text("")
        self.append_log("🧹 已清空快取")

    # -------- 匯出 --------
    def choose_src(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "選擇來源資料夾")
        if d: self.src_edit.setText(d)
    def choose_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "選擇匯出資料夾")
        if d: self.out_edit.setText(d)
    def _ensure_out_dir(self) -> Path | None:
        out = self.out_edit.text().strip()
        if not out:
            QtWidgets.QMessageBox.warning(self, "提醒", "請先選擇匯出資料夾。"); return None
        p = Path(out)
        try: p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "錯誤", f"建立匯出資料夾失敗：\n{e}"); return None
        return p
    def export_selected(self):
        outdir = self._ensure_out_dir()
        if outdir is None: return
        rows = sorted({i.row() for i in self.list.selectedIndexes()})
        if not rows and self.list.currentRow() >= 0:
            rows = [self.list.currentRow()]
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "尚未選取任何圖片。"); return
        cnt = 0
        for r in rows:
            if r < 0 or r >= len(self.images): continue
            img = self.images[r]; sub = outdir
            if self.group_chk.isChecked():
                sub = outdir / Path(img.source_file).stem; sub.mkdir(parents=True, exist_ok=True)
            try:
                with open(sub / img.label, "wb") as f: f.write(img.png_bytes)
                cnt += 1
            except Exception as e:
                self.append_log(f"❌ 匯出失敗 {img.label}: {e}")
        QtWidgets.QMessageBox.information(self, "完成", f"已匯出 {cnt} 張。")
    def export_all(self):
        outdir = self._ensure_out_dir()
        if outdir is None: return
        cnt = 0
        for img in self.images:
            sub = outdir
            if self.group_chk.isChecked():
                sub = outdir / Path(img.source_file).stem; sub.mkdir(parents=True, exist_ok=True)
            try:
                with open(sub / img.label, "wb") as f: f.write(img.png_bytes)
                cnt += 1
            except Exception as e:
                self.append_log(f"❌ 匯出失敗 {img.label}: {e}")
        QtWidgets.QMessageBox.information(self, "完成", f"已匯出 {cnt} 張（目前快取）。")

    # -------- 狀態（顯示在進度條中央） --------
    @QtCore.Slot(str)
    def set_status(self, text: str):
        if text.startswith("分析："):
            self.progress.setOverlayText("解析中…")
        else:
            self.progress.setOverlayText(text)

    @QtCore.Slot(str)
    def append_log(self, line: str):
        self.log.appendPlainText(line)

# -------------------- 入口 --------------------
def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    w = LivePreviewWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        try:
            QtWidgets.QMessageBox.critical(None, "啟動失敗", msg)
        except Exception:
            pass
        raise
