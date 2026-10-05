"""Диалог настройки соединения (все варианты: TCP-шлюз, COM, BLE)."""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget
)

from .transports import BleTransport, list_serial_ports


class ScanWorker(QThread):
    """Сканирование BLE вне GUI-потока, чтобы не морозить окно."""
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, timeout=12.0, parent=None):
        super().__init__(parent)
        self.timeout = timeout

    def run(self):
        try:
            self.done.emit(BleTransport.scan(self.timeout))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ConnectDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка соединения")
        self.cfg = dict(cfg)

        self.transport = QComboBox()
        self.transport.addItem("TCP (прозрачный RS485/RS232-шлюз)", "tcp")
        self.transport.addItem("Serial (COM / tty)", "serial")
        self.transport.addItem("BLE (Bluetooth Low Energy)", "ble")
        idx = self.transport.findData(cfg.get("transport", "tcp"))
        self.transport.setCurrentIndex(max(0, idx))

        # TCP
        self.tcp_host = QLineEdit(cfg.get("tcp_host", ""))
        self.tcp_port = QSpinBox(); self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(int(cfg.get("tcp_port", 502)))
        self.port_type = QComboBox()
        self.port_type.addItem("host-RS485 (19200, параметры)", "host")
        self.port_type.addItem("RM485 (9600, только чтение телеметрии)", "rm485")
        self.port_type.setCurrentIndex(max(0, self.port_type.findData(cfg.get("port_type", "host"))))
        tcp = QWidget(); f = QFormLayout(tcp)
        f.addRow("Host:", self.tcp_host)
        f.addRow("Port:", self.tcp_port)
        f.addRow("Порт BMS:", self.port_type)

        # Serial
        self.serial_port = QComboBox(); self.serial_port.setEditable(True)
        self.serial_port.addItems(list_serial_ports())
        self.serial_port.setCurrentText(cfg.get("serial_port", ""))
        self.baud = QComboBox(); self.baud.setEditable(True)
        self.baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud.setCurrentText(str(cfg.get("baud", 19200)))
        ser = QWidget(); f2 = QFormLayout(ser)
        f2.addRow("Порт:", self.serial_port)
        f2.addRow("Baud:", self.baud)

        # BLE
        self.ble_name = QLineEdit(cfg.get("ble_name", "BP00"))
        self.ble_address = QLineEdit(cfg.get("ble_address", ""))
        self.ble_scan = QPushButton("Сканировать…")
        self.ble_scan.clicked.connect(self._scan)
        self.ble_list = QComboBox()
        self.ble_list.currentIndexChanged.connect(self._pick_ble)
        ble = QWidget(); f3 = QFormLayout(ble)
        row = QHBoxLayout(); row.addWidget(self.ble_name); row.addWidget(self.ble_scan)
        w = QWidget(); w.setLayout(row)
        f3.addRow("Имя:", w)
        f3.addRow("Адрес:", self.ble_address)
        f3.addRow("Найденные:", self.ble_list)

        self.adr = QSpinBox(); self.adr.setRange(0, 15)
        self.adr.setValue(int(cfg.get("adr", 0)))



        self._pages = [tcp, ser, ble]  # держим ссылки (иначе GC удалит страницы)
        self.stack = QStackedWidget()
        self.stack.addWidget(tcp)
        self.stack.addWidget(ser)
        self.stack.addWidget(ble)

        form = QFormLayout()
        form.addRow("Транспорт:", self.transport)
        form.addRow("Адрес устройства:", self.adr)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.stack)
        lay.addWidget(buttons)

        self.transport.currentIndexChanged.connect(self._switch)
        self._switch()

    def _switch(self):
        self.stack.setCurrentIndex(self.transport.currentIndex())

    def _scan(self):
        self.ble_scan.setEnabled(False)
        self.ble_scan.setText("Сканирование…")
        self._scanner = ScanWorker(12.0, self)
        self._scanner.done.connect(self._on_scan_done)
        self._scanner.failed.connect(self._on_scan_failed)
        self._scanner.finished.connect(self._on_scan_finished)
        self._scanner.start()

    def _on_scan_done(self, items):
        self.ble_list.clear()
        for addr, name in items:
            self.ble_list.addItem("%s  %s" % (name or "(no name)", addr), (addr, name))

    def _on_scan_failed(self, msg):
        self.ble_list.clear()
        self.ble_list.addItem("ошибка: %s" % msg, None)

    def _on_scan_finished(self):
        self.ble_scan.setEnabled(True)
        self.ble_scan.setText("Сканировать…")

    def _pick_ble(self):
        data = self.ble_list.currentData()
        if isinstance(data, tuple):
            addr, name = data
            self.ble_address.setText(addr)
            if name:
                self.ble_name.setText(name)

    def result_config(self):
        kind = self.transport.currentData()
        try:
            baud = int((self.baud.currentText() or "").strip() or "19200")
        except ValueError:
            baud = int(self.cfg.get("baud", 19200))
        self.cfg.update({
            "transport": kind,
            "tcp_host": self.tcp_host.text().strip(),
            "tcp_port": self.tcp_port.value(),
            "port_type": self.port_type.currentData(),
            "serial_port": self.serial_port.currentText().strip(),
            "baud": baud,
            "ble_name": self.ble_name.text().strip(),
            "ble_address": self.ble_address.text().strip(),
            "adr": self.adr.value(),
        })
        return self.cfg
