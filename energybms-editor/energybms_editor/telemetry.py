"""Декодеры читаемых блоков: TeleMeter 0x42, TeleState 0x44, Battery 0x61,
Manufacture 0x51, Time 0x4D. Возвращают структуры для отображения в UI."""


def _u16(b, o):
    return (b[o] << 8) | b[o + 1]


def _s16(b, o):
    v = (b[o] << 8) | b[o + 1]
    return v - 0x10000 if v & 0x8000 else v


def decode_telemetry(info):
    """0x42, 75 байт -> список строк (секция, имя, значение, ед.)."""
    if len(info) < 67:
        return [["Телеметрия", "Блок", "неполный ответ (%d Б)" % len(info), ""]]
    n = info[2]
    o = 3
    rows = [["Ячейки", "Cell %02d" % (i + 1), "%.3f" % (_u16(info, o + 2 * i) * 0.001), "В"]
            for i in range(n)]
    o += 2 * n
    tn = info[o]
    o += 1
    labels = ["Temp1", "Temp2", "Temp3", "Temp4", "Ambient", "Power"]
    for i in range(tn):
        name = labels[i] if i < len(labels) else "Temp%d" % (i + 1)
        rows.append(["Температуры", name, "%.1f" % (_u16(info, o + 2 * i) * 0.1 - 273.1), "°C"])
    o += 2 * tn
    rows.append(["Сборка", "Current (ток)", "%.2f" % (_s16(info, o) * 0.01), "А"]); o += 2
    rows.append(["Сборка", "Total voltage", "%.2f" % (_u16(info, o) * 0.01), "В"]); o += 2
    rows.append(["Сборка", "Remaining capacity", "%.2f" % (_u16(info, o) * 0.01), "А·ч"]); o += 2
    o += 1  # field_count
    rows.append(["Сборка", "Total capacity", "%.2f" % (_u16(info, o) * 0.01), "А·ч"]); o += 2
    rows.append(["Сборка", "SOC", "%.1f" % (_u16(info, o) * 0.1), "%"]); o += 2
    rows.append(["Сборка", "Rated capacity", "%.2f" % (_u16(info, o) * 0.01), "А·ч"]); o += 2
    rows.append(["Сборка", "Battery cycles", "%d" % _u16(info, o), ""]); o += 2
    rows.append(["Сборка", "SOH", "%.1f" % (_u16(info, o) * 0.1), "%"]); o += 2
    rows.append(["Сборка", "Bus voltage", "%.2f" % (_u16(info, o) * 0.01), "В"]); o += 2
    rows.append(["Прочее", "temp-drift current", "%.3f" % (_u16(info, o) * 0.001), "А"]); o += 2
    rows.append(["Прочее", "zero-point current", "%.3f" % (_u16(info, o) * 0.001), "А"]); o += 2
    rows.append(["Прочее", "charge energy", "%.1f" % (_u16(info, o) * 0.1), "кВт·ч"]); o += 2
    rows.append(["Прочее", "discharge energy", "%.1f" % (_u16(info, o) * 0.1), "кВт·ч"]); o += 2
    return rows


def decode_state(info):
    """0x44, 49 байт -> {rows, active, mode}."""
    return _decode_state_impl(info)


_EXT_BITS = {
    0: ["Отказ датчика напряжения", "Отказ датчика температуры", "Отказ датчика тока",
        "Отказ кнопки", "Отказ контроля разброса", "Отказ зарядного ключа",
        "Отказ разрядного ключа", "Отказ ключа огр. тока"],
    1: ["Авария перенапр. ячейки", "Защита перенапр. ячейки", "Авария недонапр. ячейки",
        "Защита недонапр. ячейки", "Авария перенапр. сборки", "Защита перенапр. сборки",
        "Авария недонапр. сборки", "Защита недонапр. сборки"],
    2: ["Авария перегрева заряда", "Защита перегрева заряда", "Авария переохл. заряда",
        "Защита переохл. заряда", "Авария перегрева разряда", "Защита перегрева разряда",
        "Авария переохл. разряда", "Защита переохл. разряда"],
    3: ["Авария перегрева среды", "Защита перегрева среды", "Авария переохл. среды",
        "Защита переохл. среды", "Защита перегрева силовой", "Авария перегрева силовой",
        "Подогрев ячеек", "Вторичная защита"],
    4: ["Авария перетока заряда", "Защита перетока заряда", "Авария перетока разряда",
        "Защита перетока разряда", "Импульсная защита", "Защита КЗ выхода",
        "Блокировка импульса", "Блокировка КЗ"],
    5: ["Защита повыш. U заряда", "Прерывистый заряд", "Авария по остатку",
        "Защита по остатку", "Запрет заряда при низком U", "Защита от обратного подкл.",
        "Аэрозоль", "Плавный пуск"],
    6: ["Ключ разряда вкл.", "Ключ заряда вкл.", "Ключ огр. тока вкл.", "Ключ термо вкл.",
        "", "", "", ""],
    7: ["Балансировка 1", "Балансировка 2", "Балансировка 3", "Балансировка 4",
        "Балансировка 5", "Балансировка 6", "Балансировка 7", "Балансировка 8"],
    8: ["Балансировка 9", "Балансировка 10", "Балансировка 11", "Балансировка 12",
        "Балансировка 13", "Балансировка 14", "Балансировка 15", "Балансировка 16"],
    12: ["Авто ожидание заряда (4)", "Ручное ожидание заряда (5)", "", "", "", "", "", ""],
    13: ["Ошибка EEPROM", "Ошибка RTC", "Ошибка калибровки U", "Ошибка калибровки I",
         "Ошибка нуля", "Ошибка синхр. календаря", "", ""],
}
_MODE = {0x00: "Idle/ожидание", 0x01: "Discharge (разряд)", 0x02: "Charge (заряд)",
         0x04: "Float (поддержание)", 0x08: "Fully charged (полный заряд)",
         0x10: "Standby (ожидание)", 0x20: "Shutdown (выключение)"}


def _decode_state_impl(info):
    if len(info) < 3:
        return {"rows": [["Состояние", "Блок", "неполный ответ (%d Б)" % len(info), ""]],
                "active": [], "mode": "?"}
    n = info[2]
    o = 3
    cell_flags = list(info[o:o + n]); o += n
    tn = info[o] if o < len(info) else 0; o += 1
    temp_flags = list(info[o:o + tn]); o += tn
    o += 2  # current/voltage GB
    ext_cnt = info[o] if o < len(info) else 0; o += 1
    # Устройство передаёт Ext_Bit на 1 байт меньше счётчика (ByteNumAdjust=-1 в XML);
    # при ext_cnt<=1 ничего не читаем, чтобы не сдвинуть Mode.
    ext_len = max(ext_cnt - 1, 0)
    ext = list(info[o:o + ext_len]); o += ext_len
    mode = info[o] if o < len(info) else 0

    rows = [["Заголовок", "Число ячеек", str(n), ""]]
    active = []
    for i, b in enumerate(cell_flags):
        if b:
            active.append("Ячейка %d: 0x%02X" % (i + 1, b))
    for i, b in enumerate(temp_flags):
        if b:
            active.append("Температура %d: 0x%02X" % (i + 1, b))
    for gi, byte in enumerate(ext):
        names = _EXT_BITS.get(gi)
        if not names:
            continue
        for bit in range(8):
            if byte & (1 << bit):
                label = names[bit] or ("бит %d" % bit)
                active.append("Ext_Bit[%d].%d: %s" % (gi, bit, label))
    rows.append(["Режим", "Mode", _MODE.get(mode, "0x%02X" % mode), ""])
    return {"rows": rows, "active": active, "mode": _MODE.get(mode, "0x%02X" % mode)}


def _ascii_printable(data):
    return "".join(chr(b) if 32 <= b < 127 else " " for b in data).rstrip()


def decode_manufacture(info, ble=False):
    """0x51. Диалекты различаются: RS485 — [имя 10Б][служ. 2Б][протокол 20Б];
    BLE — ASCII-строка вида 'CAN:...' со служебными хвостовыми байтами."""
    if ble:
        return [["Модуль", "BasicInfo (BLE)", _ascii_printable(info), ""]]
    module = info[0:10].decode("latin-1", "replace").rstrip(" ")
    service = info[10:12].hex(" ").upper() if len(info) >= 12 else ""
    proto = info[12:32].decode("latin-1", "replace").rstrip(" ") if len(info) >= 32 else ""
    return [["Модуль", "module name", module, ""],
            ["Служебное", "service", service, ""],
            ["Инвертор", "inverter protocol", proto, ""]]


def decode_time(info):
    if len(info) < 7:
        return [["Время BMS", "Дата/время", "неполный ответ (%d Б)" % len(info), ""]]
    y = _u16(info, 0)
    return [["Время BMS", "Дата/время",
             "%04d-%02d-%02d %02d:%02d:%02d" % (y, info[2], info[3], info[4], info[5], info[6]), ""]]


def decode_sn(info):
    return [["Батарея", "Serial number", info.decode("latin-1", "replace").rstrip(" "), ""]]


def decode_battery_ble(info):
    """0x61 BLE: ячейки/температуры + остаток сырым блоком."""
    if len(info) < 4:
        return [["Батарея", "Блок", "неполный ответ (%d Б)" % len(info), ""]], []
    n = info[2]
    o = 3
    rows = [["Ячейки", "Cell %02d" % (i + 1),
             "%.3f" % (_u16(info, o + 2 * i) * 0.001), "В"] for i in range(n)]
    o += 2 * n
    if o < len(info):
        tn = info[o]; o += 1
        for i in range(tn):
            if o + 1 >= len(info):
                break
            rows.append(["Температуры", "Temp%d" % (i + 1),
                         "%.1f" % (_u16(info, o) * 0.1 - 273.1), "°C"])
            o += 2
    return rows, list(info[o:])
