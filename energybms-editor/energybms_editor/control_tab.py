"""Вкладка «Управление»: команды управления BMS.

Каждая кнопка формирует callable(link) и передаёт его в главное окно, которое
показывает подтверждение, выполняет команду и перечитывает данные.
"""
from datetime import datetime

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDateTimeEdit, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget
)

CAN_TYPES = [
    (1, "PN-GDLT — Pylontech / Deye / Luxpower / TBB / Goodwe"),
    (2, "GRWT — Growatt (SPF/SPH)"),
    (3, "VCTR — Victron"),
    (4, "SMA-SF — SMA / SOFAR"),
    (5, "GINL — Solis (Ginlong)"),
    (6, "STUD — Studer"),
    (7, "MUST — MUST"),
]
# ключи коммутационных функций 0x45
SWITCHES = [
    (0, "Разрядный ключ"),
    (1, "Зарядный ключ"),
    (2, "Ключ ограничения тока"),
    (3, "Ключ термоконтроля (нагрев)"),
]
ACTION_ON = 0x10
ACTION_OFF = 0x1F


class ControlTab(QWidget):
    run = Signal(str, str, object)  # title, description, callable(link)

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- коммутационные ключи
        switches = QGroupBox("Коммутационные ключи (0x45 TeleCtrl)")
        sv = QVBoxLayout(switches)
        self._sw_labels = {}
        for bit, name in SWITCHES:
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            row.addStretch(1)
            state = QLabel("—")
            state.setMinimumWidth(70)
            self._sw_labels[bit] = state
            on = QPushButton("Включить")
            off = QPushButton("Выключить")
            on.clicked.connect(self._mk_switch(bit, name, ACTION_ON))
            off.clicked.connect(self._mk_switch(bit, name, ACTION_OFF))
            row.addWidget(QLabel("Состояние:"))
            row.addWidget(state)
            row.addWidget(on)
            row.addWidget(off)
            w = QWidget(); w.setLayout(row)
            sv.addWidget(w)

        # --- питание
        power = QGroupBox("Питание (0x45 TeleCtrl)")
        pv = QHBoxLayout(power)
        shutdown = QPushButton("Выключить BMS")
        reset = QPushButton("Сбросить BMS")
        shutdown.clicked.connect(lambda: self.run.emit(
            "Выключить BMS", "Команда 0x45: выключение BMS.", lambda link: link.send_control(4, 0x00)))
        reset.clicked.connect(lambda: self.run.emit(
            "Сбросить BMS", "Команда 0x45: сброс/перезапуск BMS.", lambda link: link.send_control(5, 0x00)))
        pv.addWidget(shutdown)
        pv.addWidget(reset)

        # --- протокол инвертора
        proto = QGroupBox("Протокол инвертора (CAN 0xA6/0x63, 485 0xA7/0x64)")
        f = QVBoxLayout(proto)
        self.can_combo = QComboBox()
        for t, name in CAN_TYPES:
            self.can_combo.addItem("%d — %s" % (t, name), t)
        can_apply = QPushButton("Применить CAN-протокол")
        can_apply.clicked.connect(self._apply_can)
        row_can = QHBoxLayout(); row_can.addWidget(self.can_combo); row_can.addWidget(can_apply)
        wc = QWidget(); wc.setLayout(row_can)
        f.addWidget(QLabel("CAN-протокол инвертора:"))
        f.addWidget(wc)

        self.p485_combo = QComboBox()
        for t in range(1, 8):
            self.p485_combo.addItem("type %d" % t, t)
        p485_apply = QPushButton("Применить 485-протокол")
        p485_apply.clicked.connect(self._apply_485)
        # Смена 485-протокола запрещена: значения не документированы/непонятны.
        # Виджеты оставлены на форме «на будущее», но заблокированы.
        tip = ("Смена 485-протокола недоступна: значения не документированы "
               "и не проверены. Оставлено на будущее.")
        self.p485_combo.setEnabled(False)
        p485_apply.setEnabled(False)
        self.p485_combo.setToolTip(tip)
        p485_apply.setToolTip(tip)
        row_485 = QHBoxLayout(); row_485.addWidget(self.p485_combo); row_485.addWidget(p485_apply)
        w4 = QWidget(); w4.setLayout(row_485)
        f.addWidget(QLabel("485-протокол (недоступно — значения неизвестны):"))
        f.addWidget(w4)

        # --- время
        tbox = QGroupBox("Время BMS (0x4E SetTime)")
        tv = QHBoxLayout(tbox)
        self.dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        set_time = QPushButton("Установить время")
        set_time.clicked.connect(self._apply_time)
        tv.addWidget(self.dt); tv.addWidget(set_time)

        # --- SN
        snbox = QGroupBox("Серийные номера (0xA5 / 0xA3)")
        snv = QVBoxLayout(snbox)
        self.bat_sn = QLineEdit(); self.bat_sn.setMaxLength(30)
        self.bat_sn.setPlaceholderText("SN батареи (до 30 символов)")
        b1 = QPushButton("Записать SN батареи")
        b1.clicked.connect(self._write_bat_sn)
        self.dev_sn = QLineEdit(); self.dev_sn.setMaxLength(30)
        self.dev_sn.setPlaceholderText("SN устройства (до 30 символов)")
        b2 = QPushButton("Записать SN устройства")
        b2.clicked.connect(self._write_dev_sn)
        snv.addWidget(self.bat_sn); snv.addWidget(b1)
        snv.addWidget(self.dev_sn); snv.addWidget(b2)

        note = QLabel("Любая команда выполняется только после подтверждения и затем "
                      "данные перечитываются из BMS.")
        note.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(switches)
        lay.addWidget(power)
        lay.addWidget(proto)
        lay.addWidget(tbox)
        lay.addWidget(snbox)
        lay.addWidget(note)
        lay.addStretch(1)

    def set_serial_numbers(self, bat=None, dev=None):
        """Заполняет поля SN прочитанными из BMS значениями (пустые — не трогаем)."""
        if bat:
            self.bat_sn.setText(bat)
        if dev:
            self.dev_sn.setText(dev)

    def set_switch_states(self, states):
        """states: {bit: True/False} или пусто — состояние ключей из Ext_Bit[6]."""
        color_on = QColor("#3c9d3c")
        color_off = QColor("#8a8a8a")
        for bit, label in self._sw_labels.items():
            if bit not in states:
                label.setText("—")
                label.setStyleSheet("")
                continue
            on = states[bit]
            label.setText("Вкл" if on else "Выкл")
            label.setStyleSheet("color:%s; font-weight:bold;" % (color_on.name() if on else color_off.name()))

    def _mk_switch(self, bit, name, action):
        word = "включить" if action == ACTION_ON else "выключить"
        return lambda: self.run.emit(
            "%s: %s" % ("Включить" if action == ACTION_ON else "Выключить", name),
            "Команда 0x45: %s «%s»." % (word, name),
            lambda link: link.send_control(bit, action))

    def _write_bat_sn(self):
        text = self.bat_sn.text()  # читаем виджет в GUI-потоке
        self.run.emit("Запись SN батареи",
                      "Команда 0xA5: серийный номер батареи будет перезаписан:\n\n«%s»" % text,
                      lambda link: link.set_bat_sn(text))

    def _write_dev_sn(self):
        text = self.dev_sn.text()
        self.run.emit("Запись SN устройства",
                      "Команда 0xA3: серийный номер устройства будет перезаписан:\n\n«%s»" % text,
                      lambda link: link.set_dev_sn(text))

    def _apply_can(self):
        t = self.can_combo.currentData()
        name = self.can_combo.currentText()
        self.run.emit("Выбор CAN-протокола",
                      "Установить CAN-протокол инвертора:\n\n%s" % name,
                      lambda link: link.set_can_protocol(t))

    def _apply_485(self):
        t = self.p485_combo.currentData()
        self.run.emit("Выбор 485-протокола",
                      "Установить 485-протокол: type %d." % t,
                      lambda link: link.set_485_protocol(t))

    def _apply_time(self):
        # конвертируем QDateTime -> datetime здесь, в GUI-потоке
        q = self.dt.dateTime()
        d, t = q.date(), q.time()
        dt = datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second())
        self.run.emit("Установка времени",
                      "Установить время BMS: %s" % dt.strftime("%Y-%m-%d %H:%M:%S"),
                      lambda link: link.set_time(dt))
