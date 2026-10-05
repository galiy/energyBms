"""Декодеры читаемых блоков: TeleMeter 0x42, TeleState 0x44, Battery 0x61,
Manufacture 0x51, Time 0x4D, SN 0xA4.

Строки для UI — [секция, имя, значение, ед., описание]. Описание (может быть
пустым) показывается кнопкой «?».
"""
from .descriptions import BIT_DESC

# --------------------------------------------------------------- описания из доков
def _u16(b, o):
    return (b[o] << 8) | b[o + 1]


def _s16(b, o):
    v = (b[o] << 8) | b[o + 1]
    return v - 0x10000 if v & 0x8000 else v


def _row(section, name, value, unit="", desc=""):
    return [section, name, value, unit, desc]


# биты статуса ячейки (protocol-BLE.md §12.1: enbmsCellWarnBits)
CELL_BITS = [
    (0, "Предупреждение о повышенном напряжении ячейки", "Warn"),
    (1, "Защита от перенапряжения ячейки", "Protect"),
    (2, "Предупреждение о пониженном напряжении ячейки", "Warn"),
    (3, "Защита от недонапряжения ячейки", "Protect"),
]
# биты статуса датчика температуры (трактовка по аналогии, в доке не детализировано)
TEMP_BITS = [
    (0, "Предупреждение перегрева", "Warn"),
    (1, "Защита от перегрева", "Protect"),
    (2, "Предупреждение переохлаждения", "Warn"),
    (3, "Защита от переохлаждения", "Protect"),
]

# группы Ext_Bit: name -> [(bit, RU-имя, тип), ...]  (protocol-BLE.md §7)
EXT_GROUPS = {
    0: ("Неисправности датчиков и ключей", [
        (0, "Отказ датчика напряжения", "Warn"),
        (1, "Отказ датчика температуры", "Warn"),
        (2, "Отказ датчика тока", "Warn"),
        (3, "Отказ кнопки", "Warn"),
        (4, "Отказ контроля разброса ячеек", "Warn"),
        (5, "Отказ зарядного ключа", "Warn"),
        (6, "Отказ разрядного ключа", "Warn"),
        (7, "Отказ ключа ограничения тока", "Warn")]),
    1: ("Напряжение ячеек и сборки", [
        (0, "Авария перенапряжения ячейки", "Warn"),
        (1, "Защита от перенапряжения ячейки", "Protect"),
        (2, "Авария недонапряжения ячейки", "Warn"),
        (3, "Защита от недонапряжения ячейки", "Protect"),
        (4, "Авария перенапряжения сборки", "Warn"),
        (5, "Защита от перенапряжения сборки", "Protect"),
        (6, "Авария недонапряжения сборки", "Warn"),
        (7, "Защита от недонапряжения сборки", "Protect")]),
    2: ("Температура заряда/разряда", [
        (0, "Авария перегрева при заряде", "Warn"),
        (1, "Защита от перегрева при заряде", "Protect"),
        (2, "Авария переохлаждения при заряде", "Warn"),
        (3, "Защита от переохлаждения при заряде", "Protect"),
        (4, "Авария перегрева при разряде", "Warn"),
        (5, "Защита от перегрева при разряде", "Protect"),
        (6, "Авария переохлаждения при разряде", "Warn"),
        (7, "Защита от переохлаждения при разряде", "Protect")]),
    3: ("Среда, силовая часть, нагрев", [
        (0, "Авария перегрева среды", "Warn"),
        (1, "Защита от перегрева среды", "Protect"),
        (2, "Авария переохлаждения среды", "Warn"),
        (3, "Защита от переохлаждения среды", "Protect"),
        (4, "Защита от перегрева силовой части", "Protect"),
        (5, "Авария перегрева силовой части", "Warn"),
        (6, "Подогрев ячеек при низкой температуре", "Warn"),
        (7, "Вторичная (резервная) защита", "Warn")]),
    4: ("Токовые защиты", [
        (0, "Авария перетока при заряде", "Warn"),
        (1, "Защита от перетока при заряде", "Protect"),
        (2, "Авария перетока при разряде", "Warn"),
        (3, "Защита от перетока при разряде", "Protect"),
        (4, "Защита от импульсного тока", "Protect"),
        (5, "Защита от короткого замыкания выхода", "Protect"),
        (6, "Блокировка при импульсном токе", "Protect"),
        (7, "Блокировка при КЗ выхода", "Protect")]),
    5: ("Напряжение заряда, остаток, выход", [
        (0, "Защита от повышенного напряжения заряда", "Protect"),
        (1, "Прерывистый заряд", "Warn"),
        (2, "Авария по остаточной ёмкости", "Warn"),
        (3, "Защита по остаточной ёмкости", "Protect"),
        (4, "Запрет заряда при низком напряжении", "Protect"),
        (5, "Защита от обратного подключения выхода", "Protect"),
        (6, "Срабатывание аэрозольного пожаротушения", "Protect"),
        (7, "Функция плавного пуска выхода", "Protect")]),
    6: ("Состояние ключей (Normal)", [
        (0, "Разрядный ключ включён", "Normal"),
        (1, "Зарядный ключ включён", "Normal"),
        (2, "Ключ ограничения тока включён", "Normal"),
        (3, "Ключ термоконтроля включён", "Normal")]),
    7: ("Балансировка ячеек 1–8 (Normal)",
        [(b, "Балансировка ячейки %d" % (b + 1), "Normal") for b in range(8)]),
    8: ("Балансировка ячеек 9–16 (Normal)",
        [(b, "Балансировка ячейки %d" % (b + 9), "Normal") for b in range(8)]),
    12: ("Ожидание заряда", [
        (4, "Автоматическое ожидание заряда", "Warn"),
        (5, "Ручное ожидание заряда", "Warn")]),
    13: ("Системные ошибки", [
        (0, "Ошибка EEPROM", "Warn"),
        (1, "Ошибка часов RTC", "Warn"),
        (2, "Калибровка напряжения не выполнена", "Warn"),
        (3, "Калибровка тока не выполнена", "Warn"),
        (4, "Калибровка нуля не выполнена", "Warn"),
        (5, "Календарь не синхронизирован", "Warn")]),
}

_MODE = {0x00: "Idle/ожидание", 0x01: "Discharge (разряд)", 0x02: "Charge (заряд)",
         0x04: "Float (поддержание)", 0x08: "Fully charged (полный заряд)",
         0x10: "Standby (ожидание)", 0x20: "Shutdown (выключение)"}


def _decode_bits(byte, table):
    """byte -> список 'Флаг (тип)' для установленных известных бит."""
    out = []
    for bit, name, typ in table:
        if byte & (1 << bit):
            out.append("%s (%s)" % (name, typ))
    known = {b for b, _, _ in table}
    for bit in range(8):
        if byte & (1 << bit) and bit not in known:
            out.append("Неизвестный бит %d" % bit)
    return out


def decode_state(info):
    """0x44, 49 байт -> структура для вкладок Ячейки/Датчики/Флаги."""
    if len(info) < 3:
        return {"mode": "?", "cells": [], "temps": [], "ext": [], "summary": [],
                "error": "неполный ответ (%d Б)" % len(info)}
    n = info[2]
    o = 3
    cell_flags = list(info[o:o + n]); o += n
    tn = info[o] if o < len(info) else 0; o += 1
    temp_flags = list(info[o:o + tn]); o += tn
    gb_current = info[o] if o < len(info) else 0
    gb_voltage = info[o + 1] if o + 1 < len(info) else 0
    o += 2  # current/voltage GB
    ext_cnt = info[o] if o < len(info) else 0; o += 1
    ext_len = max(ext_cnt - 1, 0)
    ext = list(info[o:o + ext_len]); o += ext_len
    mode = info[o] if o < len(info) else 0

    cells = []
    for i, b in enumerate(cell_flags):
        cells.append({"n": i + 1, "byte": b, "flags": _decode_bits(b, CELL_BITS)})
    temps = []
    for i, b in enumerate(temp_flags):
        temps.append({"n": i + 1, "byte": b, "flags": _decode_bits(b, TEMP_BITS)})
    # разворачиваем ВСЕ принятые байты Ext_Bit, включая недокументированные
    ext_out = []
    for g in range(len(ext)):
        byte = ext[g]
        name, bits = EXT_GROUPS.get(g, ("Ext_Bit[%d] (не документировано)" % g, []))
        defined = {b for b, _, _ in bits}
        rows = []
        for bit, bname, typ in bits:
            rows.append({"bit": bit, "name": bname, "type": typ,
                         "on": bool(byte & (1 << bit)),
                         "desc": BIT_DESC.get((g, bit), "")})
        for bit in range(8):
            if bit not in defined:
                rows.append({"bit": bit, "name": "бит %d" % bit, "type": "?",
                             "on": bool(byte & (1 << bit)), "desc": ""})
        ext_out.append({"group": g, "name": name, "byte": byte, "rows": rows})
    mode_txt = _MODE.get(mode, "0x%02X (неизвестный режим)" % mode)

    def _gb_text(byte):
        if byte == 0:
            return "0x00 — норма"
        bits = ", ".join(str(b) for b in range(8) if byte & (1 << b))
        return "0x%02X (установлены биты: %s)" % (byte, bits)

    summary = [
        ["Число ячеек", str(n), "Сообщено устройством в блоке состояния (0x44)."],
        ["Число датчиков температуры", str(tn), "Сообщено устройством в блоке состояния (0x44)."],
        ["Статус измерения тока", _gb_text(gb_current),
         "Байт-маска состояния канала измерения тока (GB). 0x00 — норма; "
         "при ненулевом значении перечислены установленные биты. "
         "Точная семантика битов в документации не детализирована."],
        ["Статус измерения напряжения", _gb_text(gb_voltage),
         "Байт-маска состояния канала измерения напряжения (GB). 0x00 — норма; "
         "при ненулевом значении перечислены установленные биты. "
         "Точная семантика битов в документации не детализирована."],
        ["Байт Ext_Bit", "%d (счётчик заявляет %d; передано count−1)"
         % (ext_len, ext_cnt),
         "Расширенный блок флагов/защит. Устройство заявляет счётчик %d, но "
         "передаёт на 1 байт меньше (XML ByteNumAdjust=−1). Побитная расшифровка "
         "всех байт — на вкладке «Флаги (Ext_Bit)»." % ext_cnt],
        ["Режим работы", mode_txt, "Текущий режим работы BMS."],
    ]
    return {"mode": mode_txt, "cells": cells, "temps": temps, "ext": ext_out,
            "summary": summary, "error": ""}


# ----------------------------------------------------------------- TeleMeter
_TEMP_NAMES = {0: "Температура ячейки 1", 1: "Температура ячейки 2",
               2: "Температура ячейки 3", 3: "Температура ячейки 4",
               4: "Температура среды", 5: "Температура силовой части"}


def decode_telemetry(info):
    """0x42, 75 байт."""
    from .descriptions import TELE_DESC
    if len(info) < 67:
        return [_row("Телеметрия", "Блок", "неполный ответ (%d Б)" % len(info))]
    rows = []
    n = info[2]
    o = 3
    for i in range(n):
        rows.append(_row("Напряжение ячеек", "Ячейка %d" % (i + 1),
                         "%.3f" % (_u16(info, o) * 0.001), "В"))
        o += 2
    tn = info[o] if o < len(info) else 0
    o += 1
    for i in range(tn):
        rows.append(_row("Температуры", _TEMP_NAMES.get(i, "Датчик %d" % (i + 1)),
                         "%.1f" % (_u16(info, o) * 0.1 - 273.1), "°C"))
        o += 2
    rows.append(_row("Сборка", "Ток", "%.2f" % (_s16(info, o) * 0.01), "А")); o += 2
    rows.append(_row("Сборка", "Напряжение сборки", "%.2f" % (_u16(info, o) * 0.01),
                     "В", TELE_DESC.get(50, ""))); o += 2
    rows.append(_row("Сборка", "Остаточная ёмкость", "%.2f" % (_u16(info, o) * 0.01), "А·ч")); o += 2
    o += 1  # field_count
    rows.append(_row("Сборка", "Полная ёмкость", "%.2f" % (_u16(info, o) * 0.01), "А·ч")); o += 2
    rows.append(_row("Сборка", "Уровень заряда (SOC)", "%.1f" % (_u16(info, o) * 0.1), "%")); o += 2
    rows.append(_row("Сборка", "Номинальная ёмкость", "%.2f" % (_u16(info, o) * 0.01), "А·ч")); o += 2
    rows.append(_row("Сборка", "Число циклов", "%d" % _u16(info, o), "")); o += 2
    rows.append(_row("Сборка", "Здоровье (SOH)", "%.1f" % (_u16(info, o) * 0.1), "%")); o += 2
    rows.append(_row("Сборка", "Напряжение на клеммах", "%.2f" % (_u16(info, o) * 0.01), "В")); o += 2
    rows.append(_row("Прочее", "Ток температурного дрейфа", "%.3f" % (_u16(info, o) * 0.001),
                     "А", TELE_DESC.get(67, ""))); o += 2
    rows.append(_row("Прочее", "Ток нулевой точки", "%.3f" % (_u16(info, o) * 0.001),
                     "А", TELE_DESC.get(69, ""))); o += 2
    rows.append(_row("Прочее", "Энергия заряда", "%.1f" % (_u16(info, o) * 0.1),
                     "кВт·ч", TELE_DESC.get(71, ""))); o += 2
    rows.append(_row("Прочее", "Энергия разряда", "%.1f" % (_u16(info, o) * 0.1),
                     "кВт·ч", TELE_DESC.get(73, ""))); o += 2
    return rows


# ----------------------------------------------------------------- прочее
def _ascii_printable(data):
    return "".join(chr(b) if 32 <= b < 127 else " " for b in data).rstrip()


def decode_manufacture(info, ble=False):
    if ble:
        return [_row("Модуль", "BasicInfo (BLE)", _ascii_printable(info))]
    module = info[0:10].decode("latin-1", "replace").rstrip(" ")
    service = info[10:12].hex(" ").upper() if len(info) >= 12 else ""
    proto = info[12:32].decode("latin-1", "replace").rstrip(" ") if len(info) >= 32 else ""
    return [_row("Модуль", "Имя модуля", module),
            _row("Служебное", "service", service),
            _row("Инвертор", "Протокол инвертора", proto)]


def decode_time(info):
    if len(info) < 7:
        return [_row("Время BMS", "Дата/время", "неполный ответ (%d Б)" % len(info))]
    y = _u16(info, 0)
    return [_row("Время BMS", "Дата/время (локальное)",
                 "%04d-%02d-%02d %02d:%02d:%02d" % (y, info[2], info[3], info[4], info[5], info[6]))]


def sn_text(info):
    return info.decode("latin-1", "replace").rstrip(" \x00")


def decode_sn(info, section="Батарея", name="Серийный номер"):
    return [_row(section, name, sn_text(info))]


def decode_battery_ble(info):
    """0x61 BLE: ячейки/температуры + остаток сырым блоком."""
    if len(info) < 4:
        return [_row("Батарея", "Блок", "неполный ответ (%d Б)" % len(info))], []
    n = info[2]
    o = 3
    rows = [_row("Напряжение ячеек", "Ячейка %d" % (i + 1),
                 "%.3f" % (_u16(info, o + 2 * i) * 0.001), "В") for i in range(n)]
    o += 2 * n
    if o < len(info):
        tn = info[o]; o += 1
        for i in range(tn):
            if o + 1 >= len(info):
                break
            rows.append(_row("Температуры", _TEMP_NAMES.get(i, "Датчик %d" % (i + 1)),
                             "%.1f" % (_u16(info, o) * 0.1 - 273.1), "°C"))
            o += 2
    return rows, list(info[o:])
