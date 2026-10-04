"""Вкладка параметров: блокировка, режим редактирования, валидация, сохранение."""
import copy
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from . import params as P

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
    saveRequested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.original = None
        self.editing = False
        self._loading = False
        self._invalid = set()
        self._missing = set()

        self.status = QLabel("Параметры не прочитаны")
        self.status.setStyleSheet("color:#555")

        self.btn_edit = QPushButton("Редактировать")
        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отменить изменения")
        self.btn_save.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_edit.clicked.connect(self._toggle_edit)
        self.btn_save.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self._cancel_edit)

        bar = QHBoxLayout()
        bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_cancel)
        bar.addStretch(1)
        bar.addWidget(self.status)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["№", "Параметр", "Значение", "Ед."])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        flags_box = QGroupBox("Бит-группы (маски функций и защит)")
        self.groups = QTableWidget(8, 9)
        self.groups.setHorizontalHeaderLabels(
            ["Группа"] + ["%d" % b for b in range(8)])
        self.groups.verticalHeader().setVisible(False)
        for g in range(8):
            item = QTableWidgetItem("group%d" % g)
            item.setFlags(Qt.ItemIsEnabled)
            self.groups.setItem(g, 0, item)
            for b in range(8):
                cb = QTableWidgetItem()
                cb.setFlags(Qt.ItemIsEnabled)
                self.groups.setItem(g, b + 1, cb)
        self.groups.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.groups.verticalHeader().setDefaultSectionSize(26)
        self.groups.itemChanged.connect(self._on_item_changed)
        gv = QVBoxLayout(flags_box)
        gv.addWidget(self.groups)

        lay = QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addWidget(self.table)
        lay.addWidget(flags_box)

        self._build_rows()

    # ------------------------------------------------------------- построение
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
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(3)

    def _rows_with_values(self):
        for row in range(self.table.rowCount()):
            idx = self.table.item(row, 2).data(Qt.UserRole)
            yield row, idx

    # ------------------------------------------------------------- модель
    def set_model(self, model, keep_original=False):
        self.model = copy.deepcopy(model)
        if not keep_original:
            self.original = copy.deepcopy(model)
        self._loading = True
        raw = self.model.get("raw", {})
        for row, idx in self._rows_with_values():
            text = _fmt(idx, raw.get(idx, 0)) if idx in raw else "–"
            item = self.table.item(row, 2)
            item.setText(text)
            item.setBackground(QColor("white") if idx in raw else MISSING_BG)
        self._set_groups(self.model.get("bitgroups", [0] * 8))
        self._loading = False
        self._invalid = set()
        self._missing = {idx for _, idx in self._rows_with_values() if idx not in raw}
        self.status.setText("Прочитано параметров: %d%s" %
                            (len(raw), "" if not self._missing else " (нет данных: %d)" % len(self._missing)))
        self._apply_edit_state()

    def _set_groups(self, groups):
        for g in range(8):
            byte = groups[g] if g < len(groups) else 0
            for b in range(8):
                cb = self.groups.item(g, b + 1)
                cb.setCheckState(Qt.Checked if (byte >> b) & 1 else Qt.Unchecked)

    # ------------------------------------------------------------- редактирование
    def _toggle_edit(self):
        if self.model is None:
            return
        if self.editing:
            raw, groups, _inv, _miss = self._collect()
            if self._changes(raw, groups):
                ans = QMessageBox.question(
                    self, "Несохранённые изменения",
                    "Есть несохранённые изменения. Выйти из режима редактирования "
                    "без сохранения?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ans != QMessageBox.Yes:
                    return
        self.editing = not self.editing
        self._apply_edit_state()

    def _cancel_edit(self):
        self.editing = False
        self.set_model(self.model, keep_original=True)

    def _apply_edit_state(self):
        edit = self.editing
        self.btn_edit.setText("Готово" if edit else "Редактировать")
        for row, _ in self._rows_with_values():
            item = self.table.item(row, 2)
            flags = item.flags()
            if edit:
                flags |= Qt.ItemIsEditable
            else:
                flags &= ~Qt.ItemIsEditable
            item.setFlags(flags)
        for g in range(8):
            for b in range(8):
                cb = self.groups.item(g, b + 1)
                flags = cb.flags()
                if edit:
                    flags |= Qt.ItemIsUserCheckable
                else:
                    flags &= ~Qt.ItemIsUserCheckable
                cb.setFlags(flags)
        self.btn_cancel.setEnabled(edit)
        self._refresh_save()

    def _collect(self):
        """Собирает текущие raw/bitgroups. Возвращает (raw, groups, invalid, missing)."""
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
        groups = []
        for g in range(8):
            byte = 0
            for b in range(8):
                if self.groups.item(g, b + 1).checkState() == Qt.Checked:
                    byte |= (1 << b)
            groups.append(byte)
        return raw, groups, invalid, missing

    def _refresh_save(self):
        if self.model is None:
            self.btn_save.setEnabled(False)
            return
        raw, groups, invalid, missing = self._collect()
        changed = self._changes(raw, groups)
        # Запись идёт всем блоком 169 Б: без данных хоть по одному параметру
        # записывать нельзя (риск обнулить поле), поэтому missing блокирует.
        ok = bool(self.editing and changed and not invalid and not missing)
        self.btn_save.setEnabled(ok)
        if invalid:
            tip = "Есть невалидные параметры"
        elif missing:
            tip = "Есть параметры без данных — перечитайте перед сохранением"
        elif not changed:
            tip = "Нет изменений"
        else:
            tip = "Записать изменения в BMS"
        self.btn_save.setToolTip(tip)

    def _changes(self, raw, groups):
        orig_raw = self.original.get("raw", {})
        changed = []
        for idx in sorted(raw):
            if idx not in orig_raw:
                # параметр не был прочитан, старое значение неизвестно
                changed.append(("param", idx, None, raw[idx]))
            elif raw[idx] != orig_raw.get(idx):
                changed.append(("param", idx, orig_raw.get(idx), raw[idx]))
        orig_g = self.original.get("bitgroups", [0] * 8)
        for g in range(8):
            if groups[g] != (orig_g[g] if g < len(orig_g) else 0):
                changed.append(("group", g, orig_g[g] if g < len(orig_g) else 0, groups[g]))
        return changed

    def _on_item_changed(self, item):
        if self._loading or not self.editing:
            return
        if item.column() == 2 and item.data(Qt.UserRole) is not None:
            idx = item.data(Qt.UserRole)
            text = item.text().strip().replace(",", ".")
            if text in ("", "–", "-"):
                item.setBackground(MISSING_BG)
                self._missing.add(idx)
                self._invalid.discard(idx)
            else:
                try:
                    val = float(text)
                    ok = math.isfinite(val)
                    if ok:
                        r = P.to_raw(idx, val)
                        lo, hi = P.raw_range(idx)
                        ok = lo <= r <= hi
                except (ValueError, TypeError, OverflowError):
                    ok = False
                item.setBackground(QColor("white") if ok else INVALID_BG)
                if ok:
                    self._invalid.discard(idx)
                    self._missing.discard(idx)
                else:
                    self._invalid.add(idx)
        self._refresh_save()

    # ------------------------------------------------------------- сохранение
    def _save(self):
        raw, groups, invalid, missing = self._collect()
        if invalid or missing:
            if missing:
                QMessageBox.warning(
                    self, "Нет данных",
                    "Часть параметров не прочитана — запись всего блока 169 Б "
                    "может обнулить эти поля. Перечитайте параметры и повторите.")
            return
        changes = self._changes(raw, groups)
        if not changes:
            return
        dlg = ConfirmDialog(changes, self)
        if dlg.exec() != QDialog.Accepted:
            return
        model = copy.deepcopy(self.original)
        model["raw"].update(raw)
        model["bitgroups"] = groups
        self.editing = False
        self._apply_edit_state()
        self.saveRequested.emit(model)


class ConfirmDialog(QDialog):
    def __init__(self, changes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Подтверждение изменений")
        rows = len(changes)
        table = QTableWidget(rows, 3)
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
                name = "group%d" % key
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
            item_new.setForeground(QColor("#0a7d00"))
            table.setItem(i, 2, item_new)
        table.resizeColumnsToContents()

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
        self.resize(640, min(120 + rows * 26, 520))
