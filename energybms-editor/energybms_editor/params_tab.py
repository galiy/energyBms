"""Вкладки редактирования: числовые параметры и биты-флаги.

Параметры и биты разделены по закладкам, но редактирование общее: кнопки
«Редактировать/Сохранить/Отменить» живут в главном окне и управляют обеими.
"""
import copy
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)

from . import params as P
from .descriptions import BIT_DESC, GROUP_NAMES_RU, PARAM_DESC

DEC_BY_SCALE = {"0.001": 3, "0.01": 2, "0.1": 1, "1": 0}
INVALID_BG = QColor(255, 205, 205)
MISSING_BG = QColor(235, 235, 235)


def _fmt(idx, raw):
    if raw is None:
        return "нет данных"
    p = P.PARAM_BY_INDEX[idx]
    val = P.to_value(idx, raw)
    dec = DEC_BY_SCALE.get(p[4], 2)
    return ("%.*f" % (dec, val))


class ParamsTab(QWidget):
    """Числовые параметры (0x00..0x56). Режим правки задаётся извне."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.original = None
        self.editing = False
        self._loading = False
        self._invalid = set()
        self._missing = set()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["№", "Параметр", "Значение", "Ед.", "?"])
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 56)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 30)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        self._build_rows()

    def _build_rows(self):
        self.table.setRowCount(len(P.PARAMS))
        for row, p in enumerate(P.PARAMS):
            idx = p[0]
            it_idx = QTableWidgetItem("0x%02X" % idx)
            it_idx.setData(Qt.UserRole, idx)
            it_name = QTableWidgetItem("%s — %s" % (p[2], p[3]))
            it_name.setToolTip(p[3])
            it_val = QTableWidgetItem("–")
            it_val.setData(Qt.UserRole, idx)
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_unit = QTableWidgetItem(p[5])
            for it in (it_idx, it_name, it_val, it_unit):
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, it_idx)
            self.table.setItem(row, 1, it_name)
            self.table.setItem(row, 2, it_val)
            self.table.setItem(row, 3, it_unit)
            desc = PARAM_DESC.get(idx, "")
            if desc:
                from PySide6.QtWidgets import QToolButton
                btn = QToolButton()
                btn.setText("?")
                btn.setAutoRaise(True)
                btn.setToolTip(desc)
                btn.clicked.connect(lambda _=False, n=p[3], d=desc: _show_desc(self, n, d))
                self.table.setCellWidget(row, 4, btn)

    def _rows_with_values(self):
        for row in range(self.table.rowCount()):
            yield row, self.table.item(row, 2).data(Qt.UserRole)

    # ------------------------------------------------------------------ модель
    def set_model(self, model):
        self.model = copy.deepcopy(model)
        self.original = copy.deepcopy(model)
        self._loading = True
        raw = self.model.get("raw", {})
        for row, idx in self._rows_with_values():
            text = _fmt(idx, raw.get(idx, 0)) if idx in raw else "–"
            item = self.table.item(row, 2)
            item.setText(text)
            self._paint(item, "valid" if idx in raw else "missing")
        self._loading = False
        self._invalid = set()
        self._missing = {idx for _, idx in self._rows_with_values() if idx not in raw}

    @staticmethod
    def _paint(item, kind):
        if kind == "valid":
            item.setBackground(QBrush())
            item.setForeground(QBrush())
        elif kind == "missing":
            item.setBackground(MISSING_BG)
            item.setForeground(QColor("black"))
        else:
            item.setBackground(INVALID_BG)
            item.setForeground(QColor("black"))

    def set_editing(self, editing):
        self.editing = editing
        for row, _ in self._rows_with_values():
            item = self.table.item(row, 2)
            flags = item.flags()
            item.setFlags(flags | Qt.ItemIsEditable if editing else flags & ~Qt.ItemIsEditable)

    # --------------------------------------------------------------- сбор/проверка
    def collect(self):
        raw = {}
        invalid = set()
        missing = set()
        for row, idx in self._rows_with_values():
            text = self.table.item(row, 2).text().strip().replace(",", ".")
            if text in ("", "–", "-"):
                missing.add(idx)
                continue
            try:
                val = float(text)
                if not math.isfinite(val):
                    raise ValueError
                r = P.to_raw(idx, val)
                lo, hi = P.raw_range(idx)
                if r < lo or r > hi:
                    raise ValueError
                raw[idx] = r
            except (ValueError, TypeError, OverflowError):
                invalid.add(idx)
        return raw, invalid, missing

    def numeric_changes(self, raw):
        orig = self.original.get("raw", {})
        out = []
        for idx in sorted(raw):
            if idx not in orig:
                out.append(("param", idx, None, raw[idx]))
            elif raw[idx] != orig.get(idx):
                out.append(("param", idx, orig.get(idx), raw[idx]))
        return out

    def apply_filter(self, text):
        q = (text or "").strip().lower()
        for row, p in enumerate(P.PARAMS):
            hay = ("0x%02x" % p[0]) + " " + p[2] + " " + p[3] + " " + p[5]
            self.table.setRowHidden(row, bool(q) and q not in hay.lower())

    def _on_item_changed(self, item):
        if self._loading or not self.editing or item.column() != 2:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        text = item.text().strip().replace(",", ".")
        if text in ("", "–", "-"):
            self._paint(item, "missing")
            self._missing.add(idx)
            self._invalid.discard(idx)
            return
        try:
            val = float(text)
            ok = math.isfinite(val)
            if ok:
                r = P.to_raw(idx, val)
                lo, hi = P.raw_range(idx)
                ok = lo <= r <= hi
        except (ValueError, TypeError, OverflowError):
            ok = False
        if ok:
            self._paint(item, "valid")
            self._invalid.discard(idx)
            self._missing.discard(idx)
        else:
            self._paint(item, "invalid")
            self._invalid.add(idx)
        self.changed.emit()


class BitFlagsTab(QWidget):
    """Биты-флаги (8 групп × 8 бит) вертикальной таблицей, побитно."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.original = None
        self.editing = False
        self._loading = False
        self._rows = []  # (group, bit)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Группа", "Бит", "Флаг", "Вкл", "?"])
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 40)
        self.table.setColumnWidth(3, 40)
        self.table.setColumnWidth(4, 30)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        self._build_rows()

    def _build_rows(self):
        from PySide6.QtWidgets import QToolButton
        prev = None
        for g in range(8):
            for b in range(8):
                name = P.BITGROUPS[g][b][1] if b < len(P.BITGROUPS[g]) else ""
                self._rows.append((g, b))
                r = len(self._rows) - 1
                self.table.insertRow(r)
                grp = GROUP_NAMES_RU.get(g, "group%d" % g) if g != prev else ""
                prev = g
                it_g = QTableWidgetItem(grp)
                it_b = QTableWidgetItem(str(b))
                it_n = QTableWidgetItem(name)
                it_c = QTableWidgetItem()
                for it in (it_g, it_b, it_n, it_c):
                    it.setFlags(Qt.ItemIsEnabled)
                it_c.setCheckState(Qt.Unchecked)
                self.table.setItem(r, 0, it_g)
                self.table.setItem(r, 1, it_b)
                self.table.setItem(r, 2, it_n)
                self.table.setItem(r, 3, it_c)
                desc = BIT_DESC.get((g, b), "")
                if desc:
                    btn = QToolButton()
                    btn.setText("?")
                    btn.setAutoRaise(True)
                    btn.setToolTip(desc)
                    btn.clicked.connect(lambda _=False, n=name, d=desc: _show_desc(self, n, d))
                    self.table.setCellWidget(r, 4, btn)

    def set_model(self, model):
        self.model = copy.deepcopy(model)
        self.original = copy.deepcopy(model)
        groups = self.model.get("bitgroups", [0] * 8)
        self._loading = True
        for r, (g, b) in enumerate(self._rows):
            byte = groups[g] if g < len(groups) else 0
            item = self.table.item(r, 3)
            item.setCheckState(Qt.Checked if (byte >> b) & 1 else Qt.Unchecked)
        self._loading = False

    def set_editing(self, editing):
        self.editing = editing
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 3)
            flags = item.flags()
            item.setFlags(flags | Qt.ItemIsUserCheckable if editing
                          else flags & ~Qt.ItemIsUserCheckable)

    def group_values(self):
        groups = [0] * 8
        for r, (g, b) in enumerate(self._rows):
            if self.table.item(r, 3).checkState() == Qt.Checked:
                groups[g] |= (1 << b)
        return groups

    def group_changes(self, groups):
        orig = self.original.get("bitgroups", [0] * 8)
        out = []
        for g in range(8):
            o = orig[g] if g < len(orig) else 0
            if groups[g] != o:
                out.append(("group", g, o, groups[g]))
        return out

    def apply_filter(self, text):
        q = (text or "").strip().lower()
        last_group = None
        for r, (g, b) in enumerate(self._rows):
            en, ru = P.BITGROUPS[g][b]
            hay = (GROUP_NAMES_RU.get(g, "") + " " + en + " " + ru + " " + str(b)).lower()
            hidden = bool(q) and q not in hay
            self.table.setRowHidden(r, hidden)
            if hidden:
                continue
            if g != last_group:
                self.table.item(r, 0).setText(GROUP_NAMES_RU.get(g, "group%d" % g))
                last_group = g
            else:
                self.table.item(r, 0).setText("")

    def _on_item_changed(self, item):
        if self._loading or not self.editing or item.column() != 3:
            return
        self.changed.emit()


def _show_desc(parent, name, desc):
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information(parent, name or "Описание", desc)


class ConfirmDialog(QDialog):
    def __init__(self, changes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Подтверждение изменений")
        table = QTableWidget(len(changes), 3)
        table.setHorizontalHeaderLabels(["Параметр", "Было", "Новое"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, (kind, key, old, new) in enumerate(changes):
            if kind == "param":
                p = P.PARAM_BY_INDEX[key]
                name = "0x%02X %s" % (key, p[3])
                old_s = _fmt(key, old)
                new_s = _fmt(key, new)
                unit = p[5]
            else:
                name = GROUP_NAMES_RU.get(key, "group%d" % key)
                bitnames = P.BITGROUPS[key] if key < len(P.BITGROUPS) else []
                diff = old ^ new
                on = ", ".join(bitnames[b][1] for b in range(8)
                               if (diff >> b) & 1 and b < len(bitnames))
                old_s = "0x%02X" % old
                new_s = "0x%02X" % new
                if on:
                    new_s += " (%s)" % on
                unit = ""
            table.setItem(i, 0, QTableWidgetItem(name))
            table.setItem(i, 1, QTableWidgetItem("%s %s" % (old_s, unit)))
            item_new = QTableWidgetItem("%s %s" % (new_s, unit))
            item_new.setForeground(QColor("#1e9e1e"))
            table.setItem(i, 2, item_new)
        table.resizeColumnsToContents()

        from PySide6.QtWidgets import QLabel
        warn = QLabel("<b>Внимание:</b> значения будут записаны в BMS командой 0xA1 "
                      "и сохранены в энергонезависимой памяти устройства.")
        warn.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Записать в BMS")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(warn)
        lay.addWidget(table)
        lay.addWidget(buttons)
        self.resize(640, min(120 + len(changes) * 26, 520))
