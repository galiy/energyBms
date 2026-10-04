"""Главное окно приложения: соединение, чтение, вкладки."""
import queue

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget
)

from . import config, telemetry
from .connect_dialog import ConnectDialog
from .link import BmsLink
from .params_tab import ParamsTab
from .protocol import CID_RU, rtn_text


class IoWorker(QThread):
    done = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._q = queue.Queue()
        self.link = None

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
        return cfg

    def do_read(self):
        if not self.link:
            raise RuntimeError("нет соединения")
        return self.link.read_all()

    def do_write(self, model):
        if not self.link:
            raise RuntimeError("нет соединения")
        return self.link.write_params(model)

    def do_close(self):
        if self.link:
            self.link.close()
            self.link = None
        return True


def _table(cols):
    t = QTableWidget(0, cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionMode(QTableWidget.NoSelection)
    t.setAlternatingRowColors(True)
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

        self.conn_label = QLabel()
        self._update_conn_label()

        self.btn_conn = QPushButton("Соединение…")
        self.btn_read = QPushButton("Чтение")
        self.btn_conn.clicked.connect(self._open_conn)
        self.btn_read.clicked.connect(self._read)

        bar = QHBoxLayout()
        bar.addWidget(self.btn_conn)
        bar.addWidget(self.btn_read)
        bar.addStretch(1)
        bar.addWidget(self.conn_label)

        self.tabs = QTabWidget()
        self.tab_tele = _table(4)
        self.tab_tele.setHorizontalHeaderLabels(["Секция", "Параметр", "Значение", "Ед."])
        self.tab_tele.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.tab_state = _table(3)
        self.tab_state.setHorizontalHeaderLabels(["Секция", "Параметр", "Значение"])
        self.tab_state.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.state_active = QTextEdit()
        self.state_active.setReadOnly(True)
        self.state_active.setPlaceholderText("Активные предупреждения/защиты появятся после чтения.")
        self.state_active.setFont(QFont("Monospace", 9))
        state_w = QWidget()
        self._state_w = state_w  # держим ссылку (иначе GC удалит контейнер)
        sv = QVBoxLayout(state_w)
        sv.addWidget(self.tab_state)
        sv.addWidget(QLabel("Активные флаги:"))
        sv.addWidget(self.state_active)

        self.params_tab = ParamsTab()
        self.params_tab.saveRequested.connect(self._write_params)

        self.tab_info = _table(4)
        self.tab_info.setHorizontalHeaderLabels(["Секция", "Параметр", "Значение", "Ед."])
        self.tab_info.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.tabs.addTab(self.tab_tele, "Телеметрия")
        self.tabs.addTab(self.tab_state, "Состояние/защиты")
        self.tabs.addTab(self.params_tab, "Параметры")
        self.tabs.addTab(self.tab_info, "Инфо / SN")

        central = QWidget()
        self._central = central  # держим ссылку (иначе GC удалит контейнер)
        lay = QVBoxLayout(central)
        lay.addLayout(bar)
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Готово. Настройте соединение и нажмите «Чтение».")

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
                data = telemetry.decode_state(state.info)
                self._fill_simple(self.tab_state, data["rows"])
                self.state_active.setPlainText("\n".join(data["active"]) or "Нет активных флагов")
        except Exception as exc:  # noqa: BLE001
            dec_err.append("состояние: %s" % exc)

        if params_block and params_block.success:
            from . import params as P
            try:
                self.params_tab.set_model(P.decode_params(params_block.info))
            except ValueError as exc:
                dec_err.append("параметры: %s" % exc)

        try:
            info_rows = []
            if manuf and manuf.success:
                info_rows += telemetry.decode_manufacture(
                    manuf.info, ble=(self.cfg.get("transport") == "ble"))
            if proto and proto.success:
                info_rows.append(["Протокол", "ProtocolVer", proto.info.hex(" ").upper() or "—", ""])
            if tm and tm.success:
                info_rows += telemetry.decode_time(tm.info)
            if sn and sn.success:
                info_rows += telemetry.decode_sn(sn.info)
            if info_rows:
                self._fill_simple(self.tab_info, info_rows)
        except Exception as exc:  # noqa: BLE001
            dec_err.append("инфо: %s" % exc)

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

    @staticmethod
    def _fill_simple(table, rows):
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row[:table.columnCount()]):
                item = QTableWidgetItem(str(val))
                if c >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, c, item)
        table.resizeColumnToContents(0)
        if table.columnCount() >= 4:
            table.resizeColumnToContents(3)

    def _write_params(self, model):
        self.statusBar().showMessage("Запись параметров в BMS…")
        self.worker.submit("write", lambda: self.worker.do_write(model))

    def closeEvent(self, event):
        try:
            # закрытие выполняем в рабочем потоке (не читаем worker.link из UI-потока)
            self.worker.submit("close", self.worker.do_close)
            self.worker.stop()
        finally:
            super().closeEvent(event)
