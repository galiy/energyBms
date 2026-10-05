"""Главное окно приложения: соединение, чтение, вкладки."""
import copy
import queue

from PySide6.QtCore import QByteArray, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
    QVBoxLayout, QWidget
)

from . import config, telemetry
from .connect_dialog import ConnectDialog
from .link import BmsLink
from .control_tab import ControlTab
from .params_tab import BitFlagsTab, ConfirmDialog, ParamsTab
from .protocol import CID_RU, rtn_text


class IoWorker(QThread):
    done = Signal(str, object)
    failed = Signal(str, str)
    notice = Signal(str)

    def __init__(self):
        super().__init__()
        self._q = queue.Queue()
        self.link = None
        self.cfg = None

    def submit(self, op, fn):
        self._q.put((op, fn))
        if not self.isRunning():
            self.start()

    def stop(self):
        self._q.put(None)
        # дожидаемся текущей операции (BLE-чтение блока может длиться до 6 с)
        self.wait(25000)

    def run(self):
        while True:
            job = self._q.get()
            if job is None:
                break
            op, fn = job
            try:
                self.done.emit(op, fn())
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(op, str(exc))

    # операции (выполняются в рабочем потоке)
    def do_connect(self, cfg):
        if self.link:
            self.link.close()
        self.link = BmsLink.create(cfg)
        self.link.connect()
        self.cfg = cfg
        return cfg

    def _reconnect(self):
        try:
            if self.link:
                self.link.close()
        except Exception:
            pass
        self.link = None
        self.notice.emit("Соединение потеряно — переподключение…")
        self.link = BmsLink.create(self.cfg)
        self.link.connect()
        self.notice.emit("Соединение восстановлено — повтор операции…")

    def _guarded(self, fn):
        """Выполняет операцию; при разрыве связи переподключается и повторяет."""
        try:
            return fn()
        except Exception:  # noqa: BLE001 — разрыв связи/ошибка ввода-вывода
            if not self.cfg:
                raise
            self._reconnect()
            return fn()

    def do_read(self):
        if not self.link:
            raise RuntimeError("нет соединения")
        res = self._guarded(lambda: self.link.read_all())
        # «полуоткрытое» соединение: сокет жив, но ответов нет — пробуем
        # переподключиться и повторить чтение один раз
        if self.cfg and res and not any(r.ok for r in res.values()):
            try:
                self._reconnect()
                res2 = self.link.read_all()
                if any(r.ok for r in res2.values()):
                    return res2
            except Exception:  # noqa: BLE001
                pass
        return res

    def do_write(self, model):
        if not self.link:
            raise RuntimeError("нет соединения")
        return self._guarded(lambda: self.link.write_params(model))

    def do_close(self):
        if self.link:
            self.link.close()
            self.link = None
        return True

    def do_call(self, fn):
        if not self.link:
            raise RuntimeError("нет соединения")
        return self._guarded(lambda: fn(self.link))


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionMode(QTableWidget.NoSelection)
    t.setAlternatingRowColors(True)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Interactive)
    h.setStretchLastSection(False)
    n = len(headers)
    if n >= 2:
        h.setSectionResizeMode(1, QHeaderView.Stretch)
    t.setColumnWidth(0, 150)
    if n >= 3:
        t.setColumnWidth(2, 200)
    if n >= 5:                      # таблицы с колонкой «Ед.» и «?»
        t.setColumnWidth(2, 120)
        t.setColumnWidth(3, 70)
        t.setColumnWidth(4, 30)
    return t


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EnergyBMS Editor")
        self.resize(980, 720)
        self.cfg = config.load()
        self._connected_cfg = None
        self._auto_read = False

        self.worker = IoWorker()
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.notice.connect(self.statusBar().showMessage)

        self.conn_label = QLabel()
        self._update_conn_label()

        self.btn_conn = QPushButton("Настройки соединения")
        self.btn_read = QPushButton("Обновить (чтение)")
        self.btn_conn.clicked.connect(self._open_conn)
        self.btn_read.clicked.connect(self._read)

        self.btn_edit = QPushButton("Редактировать")
        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отменить изменения")
        self.btn_save.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_edit.clicked.connect(self._toggle_edit)
        self.btn_save.clicked.connect(self._save_params)
        self.btn_cancel.clicked.connect(self._cancel_edit)

        bar = QHBoxLayout()
        bar.addWidget(self.btn_conn)
        bar.addWidget(self.btn_read)
        bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_cancel)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по таблице…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(240)
        self.search_edit.hide()
        self.search_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search_edit)
        bar.addStretch(1)
        bar.addWidget(self.conn_label)

        self.tabs = QTabWidget()
        cols = ["Секция", "Параметр", "Значение", "Ед.", "?"]
        self.tab_tele = _table(cols)

        # --- вкладка «Сводка»: общие поля блока состояния
        self.tab_summary = _table(["Показатель", "Значение", "?"])
        sh = self.tab_summary.horizontalHeader()
        sh.setSectionResizeMode(1, QHeaderView.Stretch)
        sh.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tab_summary.setColumnWidth(2, 30)

        # --- вкладка «Ячейки»: по ячейке — понятные флаги, не hex
        self.tab_cells = QTableWidget(0, 3)
        self.tab_cells.setHorizontalHeaderLabels(["Ячейка", "Состояние", "Активные флаги"])
        self.tab_cells.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tab_cells.setColumnWidth(0, 80)
        self.tab_cells.setColumnWidth(1, 110)
        self._prep_status_table(self.tab_cells)

        # --- вкладка «Датчики»
        self.tab_temps = QTableWidget(0, 3)
        self.tab_temps.setHorizontalHeaderLabels(["Датчик", "Состояние", "Активные флаги"])
        self.tab_temps.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tab_temps.setColumnWidth(0, 80)
        self.tab_temps.setColumnWidth(1, 110)
        self._prep_status_table(self.tab_temps)

        # --- вкладка «Флаги»: побитно по группам Ext_Bit, с описанием
        self.tab_flags = QTableWidget(0, 6)
        self.tab_flags.setHorizontalHeaderLabels(
            ["Группа", "Бит", "Флаг", "Тип", "Состояние", "?"])
        fh = self.tab_flags.horizontalHeader()
        fh.setSectionResizeMode(QHeaderView.Interactive)
        fh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tab_flags.setColumnWidth(0, 250)
        self.tab_flags.setColumnWidth(1, 40)
        self.tab_flags.setColumnWidth(3, 80)
        self.tab_flags.setColumnWidth(4, 110)
        self.tab_flags.setColumnWidth(5, 30)
        self._prep_status_table(self.tab_flags)

        self.params_tab = ParamsTab()
        self.flags_tab = BitFlagsTab()
        self._edit_mode = False
        self._read_model = None
        self.params_tab.changed.connect(self._refresh_save)
        self.flags_tab.changed.connect(self._refresh_save)

        self.tab_info = _table(["Секция", "Параметр", "Значение"])
        ih = self.tab_info.horizontalHeader()
        ih.setSectionResizeMode(1, QHeaderView.Stretch)
        ih.setSectionResizeMode(2, QHeaderView.Stretch)

        self.tabs.addTab(self.tab_tele, "Телеметрия")
        self.tabs.addTab(self.tab_summary, "Сводка")
        self.tabs.addTab(self.tab_cells, "Ячейки")
        self.tabs.addTab(self.tab_temps, "Датчики")
        self.tabs.addTab(self.tab_flags, "Флаги (Ext_Bit)")
        self.tabs.addTab(self.params_tab, "Параметры")
        self.tabs.addTab(self.flags_tab, "Биты (флаги)")
        self.tabs.addTab(self.tab_info, "Инфо / SN")

        self.control_tab = ControlTab()
        self.control_tab.run.connect(self._run_control)
        self.tabs.addTab(self.control_tab, "Управление")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tabs.currentIndex())

        central = QWidget()
        self._central = central  # держим ссылку (иначе GC удалит контейнер)
        lay = QVBoxLayout(central)
        lay.addLayout(bar)
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)

        self._restore_ui_state()
        if config.has_saved():
            self.statusBar().showMessage("Запуск: автоматическое чтение…")
            QTimer.singleShot(400, self._read)
        else:
            self.statusBar().showMessage("Готово. Настройте соединение и нажмите «Обновить (чтение)».")

    # ---------------------------------------------------------------- поиск
    def _on_tab_changed(self, index):
        w = self.tabs.widget(index)
        has_search = w in (self.params_tab, self.flags_tab)
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        # сброс фильтра обеих таблиц
        self.params_tab.apply_filter("")
        self.flags_tab.apply_filter("")
        self.search_edit.setVisible(has_search)

    def _apply_filter(self, text):
        cur = self.tabs.currentWidget()
        if cur is self.params_tab:
            self.params_tab.apply_filter(text)
        elif cur is self.flags_tab:
            self.flags_tab.apply_filter(text)

    # ---------------------------------------------------------------- UI-состояние
    def _ui_tables(self):
        return {
            "tele": self.tab_tele,
            "summary": self.tab_summary,
            "cells": self.tab_cells,
            "temps": self.tab_temps,
            "flags": self.tab_flags,
            "info": self.tab_info,
            "params": self.params_tab.table,
            "flags": self.flags_tab.table,
        }

    def _restore_ui_state(self):
        ui = self.cfg.get("ui") or {}
        geo = ui.get("geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:
                pass
        headers = ui.get("headers") or {}
        for name, table in self._ui_tables().items():
            entry = headers.get(name)
            if not entry:
                continue
            # формат: {"state": <b64>, "cols": <int>}; пропускаем состояния
            # от другой версии (изменилось число колонок)
            if isinstance(entry, dict):
                state, cols = entry.get("state"), entry.get("cols")
                if cols is not None and cols != table.columnCount():
                    continue
            else:
                continue
            if state:
                try:
                    table.horizontalHeader().restoreState(
                        QByteArray.fromBase64(state.encode("ascii")))
                except Exception:
                    pass

    def _save_ui_state(self):
        self.cfg["ui"] = {
            "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "headers": {
                name: {"state": bytes(t.horizontalHeader().saveState().toBase64()).decode("ascii"),
                       "cols": t.columnCount()}
                for name, t in self._ui_tables().items()
            },
        }

    # ---------------------------------------------------------------- соединение
    def _update_conn_label(self):
        c = self.cfg
        if c["transport"] == "tcp":
            desc = "TCP %s:%s (%s)" % (c["tcp_host"], c["tcp_port"], c["port_type"])
        elif c["transport"] == "serial":
            desc = "Serial %s @ %s (%s)" % (c["serial_port"], c["baud"], c["port_type"])
        else:
            desc = "BLE %s %s" % (c["ble_name"], c["ble_address"])
        self.conn_label.setText(desc)

    def _open_conn(self):
        dlg = ConnectDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = dlg.result_config()
            _path, err = config.save(self.cfg)
            self._update_conn_label()
            self._connected_cfg = None
            if err:
                self.statusBar().showMessage("Не удалось сохранить настройки: %s" % err)
                QMessageBox.warning(self, "Настройки",
                                    "Не удалось сохранить настройки в %s:\n%s" % (_path, err))
            else:
                self.statusBar().showMessage("Настройки сохранены в %s" % _path)

    def _read(self):
        self.btn_read.setEnabled(False)
        self.statusBar().showMessage("Чтение…")
        if self._connected_cfg is None:
            self._auto_read = True
            self.worker.submit("connect", lambda: self.worker.do_connect(self.cfg))
        else:
            self.worker.submit("read", self.worker.do_read)

    def _on_done(self, op, payload):
        if op == "connect":
            self._connected_cfg = payload
            self.statusBar().showMessage("Подключено: %s" % self.conn_label.text())
            if self._auto_read:
                self._auto_read = False
                self.worker.submit("read", self.worker.do_read)
            else:
                self.btn_read.setEnabled(True)
        elif op == "read":
            self._apply_read(payload)
            self.btn_read.setEnabled(True)
            self.statusBar().showMessage("Чтение завершено")
        elif op == "write":
            res = payload
            if res is not None and res.success:
                self.statusBar().showMessage("Запись 0xA1: успешно")
            else:
                detail = "нет ответа" if (res is None or res.rtn is None) else rtn_text(res.rtn)
                self.statusBar().showMessage("Запись 0xA1: ошибка (%s)" % detail)
                QMessageBox.warning(
                    self, "Запись не выполнена",
                    "BMS не подтвердила запись параметров (%s).\n"
                    "Значения перечитаются из устройства." % detail)
            # при любом исходе перечитываем, чтобы показать реальное состояние BMS
            self.worker.submit("read", self.worker.do_read)
        elif op == "control":
            res = payload
            if res is not None and res.success:
                self.statusBar().showMessage("Команда выполнена (RTN=00), перечитываю…")
            else:
                detail = "нет ответа" if (res is None or res.rtn is None) else rtn_text(res.rtn)
                self.statusBar().showMessage("Команда: ошибка (%s)" % detail)
                QMessageBox.warning(self, "Команда не выполнена",
                                    "BMS отклонила команду (%s)." % detail)
            self.worker.submit("read", self.worker.do_read)

    def _on_failed(self, op, msg):
        self.btn_read.setEnabled(True)
        if op == "connect":
            self._auto_read = False
            self._connected_cfg = None
        self.statusBar().showMessage("Ошибка (%s): %s" % (op, msg))
        QMessageBox.warning(self, "Ошибка", "Операция «%s» не удалась:\n%s" % (op, msg))

    # ---------------------------------------------------------------- заполнение
    def _apply_read(self, blocks):
        tele = blocks.get(0x42)
        state = blocks.get(0x44)
        batt = blocks.get(0x61)
        params_block = blocks.get(0x47)
        manuf = blocks.get(0x51)
        proto = blocks.get(0x4F)
        tm = blocks.get(0x4D)
        sn = blocks.get(0xA4)
        dev_sn = blocks.get(0xA2)
        dec_err = []

        try:
            if tele and tele.success:
                self._fill_simple(self.tab_tele, telemetry.decode_telemetry(tele.info))
            elif batt and batt.success:
                rows, _ = telemetry.decode_battery_ble(batt.info)
                self._fill_simple(self.tab_tele, rows)
        except Exception as exc:  # noqa: BLE001
            dec_err.append("телеметрия: %s" % exc)

        try:
            if state and state.success:
                self._fill_state(telemetry.decode_state(state.info))
        except Exception as exc:  # noqa: BLE001
            dec_err.append("состояние: %s" % exc)

        if params_block and params_block.success:
            from . import params as P
            try:
                model = P.decode_params(params_block.info)
                self._read_model = model
                self.params_tab.set_model(model)
                self.flags_tab.set_model(model)
                if self._edit_mode:
                    self.params_tab.set_editing(True)
                    self.flags_tab.set_editing(True)
            except ValueError as exc:
                dec_err.append("параметры: %s" % exc)

        try:
            info_rows = []
            if manuf and manuf.success:
                info_rows += telemetry.decode_manufacture(
                    manuf.info, ble=(self.cfg.get("transport") == "ble"))
            if proto and proto.success:
                data = proto.info.hex(" ").upper()
                info_rows.append(["Протокол", "Версия протокола (0x4F)",
                                  data if data else "команда поддержана (полезных данных нет)"])
            elif proto:
                info_rows.append(["Протокол", "Версия протокола (0x4F)",
                                  "нет ответа / не поддержано"] + ([] if proto.rtn is None else []))
            if tm and tm.success:
                info_rows += telemetry.decode_time(tm.info)
            if sn and sn.success:
                info_rows += telemetry.decode_sn(sn.info, "Батарея", "Серийный номер батареи")
            if dev_sn and dev_sn.success:
                info_rows += telemetry.decode_sn(dev_sn.info, "Устройство",
                                                 "Серийный номер устройства")
            if info_rows:
                self._fill_simple(self.tab_info, info_rows)
        except Exception as exc:  # noqa: BLE001
            dec_err.append("инфо: %s" % exc)

        # заполняем поля ввода SN на вкладке «Управление» прочитанными значениями
        bat_sn_txt = telemetry.sn_text(sn.info) if (sn and sn.success) else ""
        dev_sn_txt = telemetry.sn_text(dev_sn.info) if (dev_sn and dev_sn.success) else ""
        self.control_tab.set_serial_numbers(bat_sn_txt, dev_sn_txt)

        # диагностический дамп сырого ответа (локально, только чтение)
        dump_path = config.dump_last_read(blocks)
        if dump_path:
            self._last_dump = dump_path

        self._report_errors(blocks, dec_err)

    def _report_errors(self, blocks, dec_err=None):
        errs = list(dec_err or [])
        for cid, res in blocks.items():
            if not res.ok:
                errs.append("%s (0x%02X): нет ответа" % (CID_RU.get(cid, "?"), cid))
            elif res.rtn != 0:
                errs.append("%s (0x%02X): %s" % (CID_RU.get(cid, "?"), cid, rtn_text(res.rtn)))
        if errs:
            self.statusBar().showMessage("Чтение завершено с замечаниями: " + "; ".join(errs))

    def _show_desc(self, name, desc):
        QMessageBox.information(self, name or "Описание", desc)

    def _fill_simple(self, table, rows):
        ncols = table.columnCount()
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c in range(min(4, ncols)):
                val = row[c] if c < len(row) else ""
                item = QTableWidgetItem(str(val))
                if c == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, c, item)
            if ncols >= 5:
                desc = row[4] if len(row) > 4 else ""
                if desc:
                    btn = QToolButton()
                    btn.setText("?")
                    btn.setAutoRaise(True)
                    btn.setToolTip(desc)
                    btn.clicked.connect(lambda _=False, n=row[1], d=desc: self._show_desc(n, d))
                    table.setCellWidget(r, 4, btn)
                else:
                    table.setCellWidget(r, 4, None)

    # ------------------------------------------------------------ состояние/защиты
    @staticmethod
    def _prep_status_table(t):
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionMode(QTableWidget.NoSelection)
        t.setAlternatingRowColors(True)

    @staticmethod
    def _put(table, r, c, text, color=None):
        item = QTableWidgetItem(str(text))
        if color is not None:
            item.setForeground(color)
        table.setItem(r, c, item)

    def _fill_summary(self, rows):
        self.tab_summary.setRowCount(len(rows))
        for r, row in enumerate(rows):
            name = row[0] if len(row) > 0 else ""
            val = row[1] if len(row) > 1 else ""
            desc = row[2] if len(row) > 2 else ""
            self._put(self.tab_summary, r, 0, name)
            self._put(self.tab_summary, r, 1, val)
            if desc:
                btn = QToolButton()
                btn.setText("?")
                btn.setAutoRaise(True)
                btn.setToolTip(desc)
                btn.clicked.connect(lambda _=False, n=name, d=desc: self._show_desc(n, d))
                self.tab_summary.setCellWidget(r, 2, btn)
            else:
                self.tab_summary.setCellWidget(r, 2, None)

    def _fill_state(self, data):
        if data.get("error"):
            self._fill_summary([["Состояние", data["error"], ""]])
            self.control_tab.set_switch_states({})
            self.tab_cells.setRowCount(1)
            for c, t in enumerate(["—", "—", data["error"]]):
                self._put(self.tab_cells, 0, c, t)
            self.tab_temps.setRowCount(0)
            self.tab_flags.setRowCount(0)
            return

        self._fill_summary(data.get("summary", []))
        # состояние ключей — из группы Ext_Bit[6] (биты 0..3)
        sw = {}
        for g in data.get("ext", []):
            if g["group"] == 6:
                for br in g["rows"]:
                    if br["bit"] <= 3:
                        sw[br["bit"]] = br["on"]
        self.control_tab.set_switch_states(sw)
        warn = QColor("#d9534f")
        ok = QColor("#8a8a8a")
        # ячейки
        self.tab_cells.setRowCount(len(data["cells"]))
        for r, c in enumerate(data["cells"]):
            on = bool(c["flags"])
            self._put(self.tab_cells, r, 0, "Ячейка %d" % c["n"])
            self._put(self.tab_cells, r, 1, "АВАРИЯ/ЗАЩИТА" if on else "норма", warn if on else ok)
            self._put(self.tab_cells, r, 2, "; ".join(c["flags"]) if c["flags"] else "—", warn if on else None)
        # датчики
        self.tab_temps.setRowCount(len(data["temps"]))
        for r, c in enumerate(data["temps"]):
            on = bool(c["flags"])
            self._put(self.tab_temps, r, 0, "Датчик %d" % c["n"])
            self._put(self.tab_temps, r, 1, "АВАРИЯ/ЗАЩИТА" if on else "норма", warn if on else ok)
            self._put(self.tab_temps, r, 2, "; ".join(c["flags"]) if c["flags"] else "—", warn if on else None)
        # флаги (побитно)
        rows = []
        for g in data["ext"]:
            for br in g["rows"]:
                rows.append((g, br))
        self.tab_flags.setRowCount(len(rows))
        green = QColor("#3c9d3c")
        prev_group = None
        for r, (g, br) in enumerate(rows):
            if g["group"] != prev_group:
                self._put(self.tab_flags, r, 0,
                          "%s (байт %d: 0x%02X)" % (g["name"], g["group"], g["byte"]))
                prev_group = g["group"]
            else:
                self._put(self.tab_flags, r, 0, "")
            self._put(self.tab_flags, r, 1, br["bit"])
            self._put(self.tab_flags, r, 2, br["name"])
            self._put(self.tab_flags, r, 3, br["type"])
            on = br["on"]
            self._put(self.tab_flags, r, 4, "1 — активен" if on else "0")
            if on:
                color = green if br["type"] == "Normal" else warn
                for c in range(5):
                    it = self.tab_flags.item(r, c)
                    if it:
                        it.setForeground(color)
            if br.get("desc"):
                btn = QToolButton()
                btn.setText("?")
                btn.setAutoRaise(True)
                btn.setToolTip(br["desc"])
                btn.clicked.connect(lambda _=False, n=br["name"], d=br["desc"]: self._show_desc(n, d))
                self.tab_flags.setCellWidget(r, 5, btn)
            else:
                self.tab_flags.setCellWidget(r, 5, None)
        self.statusBar().showMessage("Режим работы: %s" % data.get("mode", "?"))

    # ------------------------------------------------------------ редактирование
    def _collect_all(self):
        raw, invalid, missing = self.params_tab.collect()
        groups = self.flags_tab.group_values()
        return raw, groups, invalid, missing

    def _pending_changes(self):
        raw, groups, _inv, _miss = self._collect_all()
        return (self.params_tab.numeric_changes(raw)
                + self.flags_tab.group_changes(groups))

    def _toggle_edit(self):
        if self.params_tab.model is None:
            QMessageBox.information(self, "Редактирование", "Сначала прочитайте параметры.")
            return
        if self._edit_mode and self._pending_changes():
            ans = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Выйти из режима редактирования без сохранения?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        self._edit_mode = not self._edit_mode
        self.params_tab.set_editing(self._edit_mode)
        self.flags_tab.set_editing(self._edit_mode)
        self.btn_edit.setText("Готово" if self._edit_mode else "Редактировать")
        self.btn_cancel.setEnabled(self._edit_mode)
        self._refresh_save()

    def _cancel_edit(self):
        if self._read_model is None:
            return
        self._edit_mode = False
        self.params_tab.set_editing(False)
        self.flags_tab.set_editing(False)
        self.btn_edit.setText("Редактировать")
        self.btn_cancel.setEnabled(False)
        self.params_tab.set_model(self._read_model)
        self.flags_tab.set_model(self._read_model)
        self._refresh_save()

    def _refresh_save(self):
        if self.params_tab.model is None:
            self.btn_save.setEnabled(False)
            return
        raw, groups, invalid, missing = self._collect_all()
        changes = (self.params_tab.numeric_changes(raw)
                   + self.flags_tab.group_changes(groups))
        self.btn_save.setEnabled(
            bool(self._edit_mode and changes and not invalid and not missing))
        if invalid:
            tip = "Есть невалидные параметры"
        elif missing:
            tip = "Есть параметры без данных — перечитайте перед сохранением"
        elif not changes:
            tip = "Нет изменений"
        elif not self._edit_mode:
            tip = "Нажмите «Редактировать»"
        else:
            tip = "Записать изменения в BMS"
        self.btn_save.setToolTip(tip)

    def _save_params(self):
        raw, groups, invalid, missing = self._collect_all()
        if invalid or missing:
            if missing:
                QMessageBox.warning(self, "Нет данных",
                    "Часть параметров не прочитана — запись всего блока 169 Б может "
                    "обнулить эти поля. Перечитайте параметры и повторите.")
            return
        changes = (self.params_tab.numeric_changes(raw)
                   + self.flags_tab.group_changes(groups))
        if not changes:
            return
        if ConfirmDialog(changes, self).exec() != QDialog.Accepted:
            return
        model = copy.deepcopy(self._read_model)
        model["raw"].update(raw)
        model["bitgroups"] = groups
        self._edit_mode = False
        self.params_tab.set_editing(False)
        self.flags_tab.set_editing(False)
        self.btn_edit.setText("Редактировать")
        self.btn_cancel.setEnabled(False)
        self.btn_save.setEnabled(False)
        self._write_params(model)

    def _write_params(self, model):
        self.statusBar().showMessage("Запись параметров в BMS…")
        self.worker.submit("write", lambda: self.worker.do_write(model))

    def _run_control(self, title, desc, fn):
        """Команда управления: подтверждение → выполнение → перечитывание."""
        try:
            if self._connected_cfg is None:
                QMessageBox.information(self, "Управление",
                                        "Сначала выполните чтение (нужно соединение).")
                return
            if QMessageBox.question(self, title, desc + "\n\nВыполнить команду?",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) != QMessageBox.Yes:
                return
            self.statusBar().showMessage("Команда: %s…" % title)
            self.worker.submit("control", lambda: self.worker.do_call(fn))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Управление", "Ошибка команды «%s»:\n%s" % (title, exc))

    def closeEvent(self, event):
        try:
            # геометрию окна и состояние колонок сохраняем при закрытии
            self._save_ui_state()
            config.save(self.cfg)
            # закрытие выполняем в рабочем потоке (не читаем worker.link из UI-потока)
            self.worker.submit("close", self.worker.do_close)
            self.worker.stop()
        finally:
            super().closeEvent(event)
