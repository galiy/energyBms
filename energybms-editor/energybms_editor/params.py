"""Таблица параметров BMS Enjie EMU110x (CID2 0x47 / запись 0xA1).

Источник: protocol-485.md §8 (RW-колонка), tools/params_table.py.
Значения хранятся как СЫРЫЕ целые (u16/u8); преобразование в инженерные
единицы выполняют to_value()/to_raw().
"""

# (index, size(1|2), EN name, RU name, scale, unit)
PARAMS = [
    (0x00, 2, "Cell over voltage alarm", "Авария перенапряжения ячейки", "0.001", "V"),
    (0x01, 2, "Cell over voltage alarm recovery", "Восстановление аварии перенапряжения ячейки", "0.001", "V"),
    (0x02, 2, "Cell under voltage alarm", "Авария недонапряжения ячейки", "0.001", "V"),
    (0x03, 2, "Cell under voltage alarm recovery", "Восстановление аварии недонапряжения ячейки", "0.001", "V"),
    (0x04, 2, "Cell over voltage protection", "Защита от перенапряжения ячейки", "0.001", "V"),
    (0x05, 2, "Cell over voltage protection recovery", "Восстановление защиты от перенапряжения ячейки", "0.001", "V"),
    (0x06, 2, "Cell under voltage protection", "Защита от недонапряжения ячейки", "0.001", "V"),
    (0x07, 2, "Cell under voltage protection recovery", "Восстановление защиты от недонапряжения ячейки", "0.001", "V"),
    (0x08, 2, "Balance turn-on voltage", "Напряжение включения балансировки", "0.001", "V"),
    (0x09, 2, "Battery low voltage forbidden charging", "Запрет заряда при низком напряжении", "0.001", "V"),
    (0x0A, 2, "Pack over voltage alarm", "Авария перенапряжения сборки", "0.01", "V"),
    (0x0B, 2, "Pack over voltage alarm recovery", "Восстановление аварии перенапряжения сборки", "0.01", "V"),
    (0x0C, 2, "Pack under voltage alarm", "Авария недонапряжения сборки", "0.01", "V"),
    (0x0D, 2, "Pack under voltage alarm recovery", "Восстановление аварии недонапряжения сборки", "0.01", "V"),
    (0x0E, 2, "Pack over voltage protection", "Защита от перенапряжения сборки", "0.01", "V"),
    (0x0F, 2, "Pack over voltage protection recovery", "Восстановление защиты от перенапряжения сборки", "0.01", "V"),
    (0x10, 2, "Pack under voltage protection", "Защита от недонапряжения сборки", "0.01", "V"),
    (0x11, 2, "Pack under voltage protection recovery", "Восстановление защиты от недонапряжения сборки", "0.01", "V"),
    (0x12, 2, "Charging overvoltage protection", "Защита от перенапряжения при заряде", "0.01", "V"),
    (0x13, 2, "Charging overvoltage recovery", "Восстановление после перенапряжения при заряде", "0.01", "V"),
    (0x14, 2, "Charging over temperature alarm", "Авария перегрева при заряде", "0.1", "℃"),
    (0x15, 2, "Charging over temperature alarm recovery", "Восстановление аварии перегрева при заряде", "0.1", "℃"),
    (0x16, 2, "Charging under temperature alarm", "Авария переохлаждения при заряде", "0.1", "℃"),
    (0x17, 2, "Charging under temperature alarm recovery", "Восстановление аварии переохлаждения при заряде", "0.1", "℃"),
    (0x18, 2, "Charging over temperature protection", "Защита от перегрева при заряде", "0.1", "℃"),
    (0x19, 2, "Charging over temperature protection recovery", "Восстановление защиты от перегрева при заряде", "0.1", "℃"),
    (0x1A, 2, "Charging under temperature protection", "Защита от переохлаждения при заряде", "0.1", "℃"),
    (0x1B, 2, "Charging under temperature protection recovery", "Восстановление защиты от переохлаждения при заряде", "0.1", "℃"),
    (0x1C, 2, "Discharge over temperature alarm", "Авария перегрева при разряде", "0.1", "℃"),
    (0x1D, 2, "Discharge over temperature alarm recovery", "Восстановление аварии перегрева при разряде", "0.1", "℃"),
    (0x1E, 2, "Discharge under temperature alarm", "Авария переохлаждения при разряде", "0.1", "℃"),
    (0x1F, 2, "Discharge under temperature alarm recovery", "Восстановление аварии переохлаждения при разряде", "0.1", "℃"),
    (0x20, 2, "Discharge over temperature protection", "Защита от перегрева при разряде", "0.1", "℃"),
    (0x21, 2, "Discharge over temperature protection recovery", "Восстановление защиты от перегрева при разряде", "0.1", "℃"),
    (0x22, 2, "Discharge under temperature protection", "Защита от переохлаждения при разряде", "0.1", "℃"),
    (0x23, 2, "Discharge under temperature protection recovery", "Восстановление защиты от переохлаждения при разряде", "0.1", "℃"),
    (0x24, 2, "Cell low temperature heating", "Подогрев ячеек при низкой температуре", "0.1", "℃"),
    (0x25, 2, "Cell heating recovery", "Восстановление подогрева ячеек", "0.1", "℃"),
    (0x26, 2, "Environmental over temperature alarm", "Авария перегрева среды", "0.1", "℃"),
    (0x27, 2, "Environmental over temperature alarm recovery", "Восстановление аварии перегрева среды", "0.1", "℃"),
    (0x28, 2, "Environmental under temperature alarm", "Авария переохлаждения среды", "0.1", "℃"),
    (0x29, 2, "Environmental under temperature alarm recovery", "Восстановление аварии переохлаждения среды", "0.1", "℃"),
    (0x2A, 2, "Environmental over temperature protection", "Защита от перегрева среды", "0.1", "℃"),
    (0x2B, 2, "Environmental over temperature protection recovery", "Восстановление защиты от перегрева среды", "0.1", "℃"),
    (0x2C, 2, "Environmental under temperature protection", "Защита от переохлаждения среды", "0.1", "℃"),
    (0x2D, 2, "Environmental under temperature protection recovery", "Восстановление защиты от переохлаждения среды", "0.1", "℃"),
    (0x2E, 2, "Power over temperature alarm", "Авария перегрева силовой части", "0.1", "℃"),
    (0x2F, 2, "Power over temperature alarm recovery", "Восстановление аварии перегрева силовой части", "0.1", "℃"),
    (0x30, 2, "Power over temperature protection", "Защита от перегрева силовой части", "0.1", "℃"),
    (0x31, 2, "Power over temperature protection recovery", "Восстановление защиты от перегрева силовой части", "0.1", "℃"),
    (0x32, 2, "Charging overcurrent alarm", "Авария перетока при заряде", "0.01", "A"),
    (0x33, 2, "Charging overcurrent recovery", "Восстановление после перетока при заряде", "0.01", "A"),
    (0x34, 2, "Discharge overcurrent alarm", "Авария перетока при разряде", "0.01", "A"),
    (0x35, 2, "Discharge overcurrent recovery", "Восстановление после перетока при разряде", "0.01", "A"),
    (0x36, 2, "Charge overcurrent protection", "Защита от перетока при заряде", "0.01", "A"),
    (0x37, 2, "Discharge overcurrent protection", "Защита от перетока при разряде", "0.01", "A"),
    (0x38, 2, "Transient overcurrent protection", "Защита от импульсного перетока", "0.01", "A"),
    (0x39, 2, "Output soft start delay", "Задержка плавного пуска выхода", "1", "mS"),
    (0x3A, 2, "Battery rated capacity", "Номинальная ёмкость батареи", "0.01", "Ah"),
    (0x3B, 2, "Remaining capacity", "Остаточная ёмкость", "0.01", "Ah"),
    (0x3C, 1, "Voltage differential start", "Порог пуска по разнице напряжений", "0.01", "V"),
    (0x3D, 1, "Voltage differential stop", "Порог останова по разнице напряжений", "0.01", "V"),
    (0x3E, 1, "Balance start voltage difference", "Разница напряжений включения балансировки", "0.001", "V"),
    (0x3F, 1, "Balance stop voltage difference", "Разница напряжений выключения балансировки", "0.001", "V"),
    (0x40, 1, "Static equilibrium time", "Время статической балансировки", "1", "мин"),
    (0x41, 1, "Cell number", "Число ячеек", "1", "шт"),
    (0x42, 1, "Charge overcurrent delay", "Задержка защиты от перетока при заряде", "1", "с"),
    (0x43, 1, "Discharge overcurrent delay", "Задержка защиты от перетока при разряде", "1", "с"),
    (0x44, 1, "Transient overcurrent delay", "Задержка защиты от импульсного перетока", "1", "мс"),
    (0x45, 1, "Overcurrent delay recovery", "Задержка восстановления после перетока", "1", "с"),
    (0x46, 1, "Overcurrent recovery times", "Число восстановлений после перетока", "1", "раз"),
    (0x47, 1, "Charge current limit delay", "Задержка ограничения тока заряда", "1", "мин"),
    (0x48, 1, "Charge activation delay", "Задержка активации заряда", "1", "мин"),
    (0x49, 1, "Charging activation interval", "Интервал активации заряда", "1", "мин"),
    (0x4A, 1, "Charge activation times", "Число активаций заряда", "1", "раз"),
    (0x4B, 1, "Work record interval", "Интервал записи при работе", "1", "мин"),
    (0x4C, 1, "Standby recording interval", "Интервал записи в режиме ожидания", "1", "мин"),
    (0x4D, 1, "Standby shutdown delay", "Задержка выключения в режиме ожидания", "1", "мин"),
    (0x4E, 1, "Remaining capacity alarm", "Авария по остаточной ёмкости", "1", "%"),
    (0x4F, 1, "Remaining capacity protection", "Защита по остаточной ёмкости", "1", "%"),
    (0x50, 1, "Interval charge capacity", "Ёмкость интервального заряда", "1", "%"),
    (0x51, 1, "Cycle cumulative capacity", "Накопленная ёмкость цикла", "1", "%"),
    (0x52, 1, "Connection fault impedance", "Сопротивление неисправности соединения", "0.1", "мОм"),
    (0x53, 1, "Compensation point 1 position", "Позиция точки компенсации 1", "1", "№"),
    (0x54, 1, "Compensation point 1 impedance", "Сопротивление точки компенсации 1", "0.1", "мОм"),
    (0x55, 1, "Compensation point 2 position", "Позиция точки компенсации 2", "1", "№"),
    (0x56, 1, "Compensation point 2 impedance", "Сопротивление точки компенсации 2", "0.1", "мОм"),
]

PARAM_BY_INDEX = {p[0]: p for p in PARAMS}
INT_COUNT = 60            # 0x00..0x3B
BYTE_START = 0x3C
BYTE_COUNT = 27           # 0x3C..0x56

# Бит-группы 0..7: список (EN, RU) по битам 0..7
BITGROUPS = [
    [  # group0 — маски игнорирования датчиков/ключей
        ("Voltage sensor invalidation", "Игнорирование датчика напряжения"),
        ("Temperature sensor invalidation", "Игнорирование датчика температуры"),
        ("Current sensor invalidation", "Игнорирование датчика тока"),
        ("Button switch invalidation", "Игнорирование кнопки"),
        ("Cell differential voltage invalidation", "Игнорирование контроля разброса ячеек"),
        ("Charge switch invalidation", "Игнорирование зарядного ключа"),
        ("Discharge switch invalidation", "Игнорирование разрядного ключа"),
        ("Current limit switch invalidation", "Игнорирование ключа ограничения тока"),
    ],
    [  # group1 — аварии/защиты по напряжению
        ("Cell over voltage alarm", "Авария перенапряжения ячейки"),
        ("Cell over voltage protection", "Защита от перенапряжения ячейки"),
        ("Cell under voltage alarm", "Авария недонапряжения ячейки"),
        ("Cell under voltage protection", "Защита от недонапряжения ячейки"),
        ("Pack over voltage alarm", "Авария перенапряжения сборки"),
        ("Pack over voltage protection", "Защита от перенапряжения сборки"),
        ("Pack under voltage alarm", "Авария недонапряжения сборки"),
        ("Pack under voltage protection", "Защита от недонапряжения сборки"),
    ],
    [  # group2 — температура заряда/разряда
        ("Charging over temperature alarm", "Авария перегрева при заряде"),
        ("Charging over temperature protection", "Защита от перегрева при заряде"),
        ("Charging under temperature alarm", "Авария переохлаждения при заряде"),
        ("Charging under temperature protection", "Защита от переохлаждения при заряде"),
        ("Discharge over temperature alarm", "Авария перегрева при разряде"),
        ("Discharge over temperature protection", "Защита от перегрева при разряде"),
        ("Discharge under temperature alarm", "Авария переохлаждения при разряде"),
        ("Discharge under temperature protection", "Защита от переохлаждения при разряде"),
    ],
    [  # group3 — среда/силовая часть/нагрев
        ("Environmental over temperature alarm", "Авария перегрева среды"),
        ("Environmental over temperature protection", "Защита от перегрева среды"),
        ("Environmental under temperature alarm", "Авария переохлаждения среды"),
        ("Environmental under temperature protection", "Защита от переохлаждения среды"),
        ("Power over temperature protection", "Защита от перегрева силовой части"),
        ("Power over temperature alarm", "Авария перегрева силовой части"),
        ("Cell low temperature heating", "Подогрев ячеек при низкой температуре"),
        ("Secondary tripping protection", "Вторичная (резервная) защита"),
    ],
    [  # group4 — токовые защиты
        ("Charging overcurrent alarm", "Авария перетока при заряде"),
        ("Charge overcurrent protection", "Защита от перетока при заряде"),
        ("Discharge overcurrent alarm", "Авария перетока при разряде"),
        ("Discharge overcurrent protection", "Защита от перетока при разряде"),
        ("Transient current protection", "Защита от импульсного (броскового) тока"),
        ("Output short circuit protection", "Защита от КЗ на выходе"),
        ("Transient overcurrent lockout", "Блокировка при импульсном перетоке"),
        ("Output short circuit locking", "Блокировка при КЗ на выходе"),
    ],
    [  # group5 — повышенное напряжение/остаток/выход
        ("Charging high voltage protection", "Защита от повышенного напряжения заряда"),
        ("Intermittent charging function", "Функция прерывистого заряда"),
        ("Remaining capacity alarm", "Авария по остаточной ёмкости"),
        ("Remaining capacity protection", "Защита по остаточной ёмкости"),
        ("Battery low voltage forbidden charging", "Запрет заряда при низком напряжении"),
        ("Output reverse connection protection", "Защита от обратного подключения выхода"),
        ("Aerosol failure", "Срабатывание аэрозольного пожаротушения"),
        ("Output soft start function", "Функция плавного пуска выхода"),
    ],
    [  # group6 — балансировка/активация заряда
        ("Charge equalization function", "Функция балансировки при заряде"),
        ("Static equilibrium function", "Функция статической балансировки"),
        ("Timeout prohibits equalization", "Запрет балансировки по таймауту"),
        ("Over temperature prohibits equalization", "Запрет балансировки при перегреве"),
        ("Automatically activate charging", "Автоактивация заряда"),
        ("Manually activate charging", "Ручная активация заряда"),
        ("Take the initiative current limiting charging", "Активное ограничение тока заряда"),
        ("Passive current limiting charging", "Пассивное ограничение тока заряда"),
    ],
    [  # group7 — сервисные функции
        ("Switch shut down function", "Выключение по кнопке"),
        ("Standby shutdown function", "Автоотключение в режиме ожидания"),
        ("History record function", "Ведение истории"),
        ("LCD display function", "Дисплей LCD"),
        ("Bluetooth communication function", "Bluetooth-связь"),
        ("Automatic address coding", "Автоадресация"),
        ("Parallel external polling", "Внешний опрос при параллельном включении"),
        ("Single BMS 1.0C charging", "Одиночный BMS: заряд 1.0C"),
    ],
]


def to_value(idx, raw):
    """Сырое целое -> инженерное значение (float)."""
    p = PARAM_BY_INDEX.get(idx)
    scale = float(p[4]) if p else 1.0
    if p and p[5] == "℃":
        return raw * 0.1 - 273.1
    return raw * scale


def to_raw(idx, value):
    """Инженерное значение -> сырое целое (округление)."""
    p = PARAM_BY_INDEX.get(idx)
    if p and p[5] == "℃":
        return int(round((float(value) + 273.1) / 0.1))
    scale = float(p[4]) if p else 1.0
    return int(round(float(value) / scale))


def raw_range(idx):
    """Допустимый диапазон сырого значения для параметра."""
    p = PARAM_BY_INDEX.get(idx)
    size = p[1] if p else 1
    return (0, 0xFFFF if size == 2 else 0xFF)


def value_range(idx):
    """Допустимый диапазон инженерного значения."""
    p = PARAM_BY_INDEX.get(idx)
    lo, hi = raw_range(idx)
    if p and p[5] == "℃":
        return (lo * 0.1 - 273.1, hi * 0.1 - 273.1)
    scale = float(p[4]) if p else 1.0
    return (lo * scale, hi * scale)


def decode_params(info):
    """169-байтный INFO -> dict с сырыми значениями.

    Возвращает {pack_index, raw:{idx:raw}, bitgroups:[u8 x8], module_name}.
    """
    if len(info) < 169:
        raise ValueError("INFO параметров короче 169 байт: %d" % len(info))
    pack = info[0]
    int_cnt = info[1]
    off = 2
    raw = {}
    for i in range(int_cnt):
        raw[i] = (info[off] << 8) | info[off + 1]
        off += 2
    byte_cnt = info[off]
    off += 1
    for j in range(byte_cnt):
        raw[BYTE_START + j] = info[off]
        off += 1
    bit_cnt = info[off]
    off += 1
    groups = list(info[off:off + bit_cnt])
    off += bit_cnt
    module = info[off:off + 10].decode("latin-1", "replace").rstrip(" ")
    return {"pack_index": pack, "raw": raw, "bitgroups": groups, "module_name": module}


def encode_params(model):
    """dict из decode_params (с изменёнными raw/bitgroups) -> 169 байт."""
    raw = model["raw"]
    groups = model["bitgroups"]
    buf = bytearray(169)
    buf[0] = model.get("pack_index", 0)
    buf[1] = INT_COUNT
    off = 2
    for i in range(INT_COUNT):
        v = int(raw.get(i, 0)) & 0xFFFF
        buf[off] = (v >> 8) & 0xFF
        buf[off + 1] = v & 0xFF
        off += 2
    buf[122] = BYTE_COUNT
    off = 123
    for j in range(BYTE_COUNT):
        buf[off] = int(raw.get(BYTE_START + j, 0)) & 0xFF
        off += 1
    buf[150] = 8
    for g in range(8):
        buf[151 + g] = int(groups[g]) & 0xFF if g < len(groups) else 0
    name = (model.get("module_name", "") or "").encode("latin-1", "replace")[:10]
    name = name + b" " * (10 - len(name))
    buf[159:169] = name
    return bytes(buf)


def empty_model():
    """Заготовка модели параметров для случая, если чтение не удалось."""
    return {"pack_index": 0, "raw": {p[0]: 0 for p in PARAMS},
            "bitgroups": [0, 0, 0, 0, 0, 0, 0, 0], "module_name": ""}
