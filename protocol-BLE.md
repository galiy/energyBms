# protocol-BLE.md — BLE-протокол BMS Enjie (EMU1101 / EMU1102 / EMU1103)

Единое описание протокола обмена BMS производства **Shanghai Enjie / N ENERGY**
(板 上海恩阶). Сведено из двух независимых источников:

- **приложение EN BMS 1.1.4** (Android, Flutter/Dart-AOT) — реверс кадров из `libapp.so`;
- **ПО «Upper Computer» `BatteryMonitor V2.1.13`** (RS-485) — карты `Agreement/*.xml`
  и реализация `BatteryMonitor.exe` (разбор .NET IL).

Оба пути ведут к **одному протоколу платы** (BLE-модуль BT2 — это BLE↔UART-мост,
через который виден тот же внутренний UART-протокол, что и по RS-485).
Детали разбора, инструменты и подводные камни — в `REVERSE_ENGINEERING.md`.

> Проверочные данные сняты с устройства **`BP00`**, MAC `28:xx:xx:xx:xx:xx`,
> пак 16S (16 ячеек, ~48/51.2 В).

## 1. Идентификация и семейство

Протокол — **бинарный вариант семейства «CID»** (`SOI = 0x7E`, `CID1 = 0x46`,
`EOI = 0x0D`), корень которого — китайский стандарт **YD/T 1363**. К этому же
семейству относятся публично описанные:

| Семейство | Формат | Особенности |
|---|---|---|
| **Pylontech RS-485**, **PACE / PbmsTools** | ASCII-hex: `7E 32 35 30 31 34 36 … 0D` | `CID1 = 0x4A/0x46`, `CKSUM` = 16-бит сумма-дополнение |
| **Gobel Power «RN BMS»** (`fancyui/Gobel-Power-RN-BMS-RS485-ModBus`) | **бинарный** V1.0 | `VER=0x10`, `CID1=0x46`, `LENGTH`, `INFO`, `CHKSUM`, `EOI=0x0D` — ближайший аналог |
| **Daren, Maiyou**, `syssi/esphome-pace-bms`, `nkinnan/esphome-pace-bms` | ASCII-hex PACE | проверка через `CID1/CID2` |
| **Enjie (наш)** | **бинарный** | `VER=0x10`, `CID1=0x46`, `LEN` с `LCHKSUM`, `EOI=0x0D` |

Ключевые параметры:

- `protocolName = BMS-16S`, `protocolVersion = 2.0` (файлы `…_V20_…`).
- Байт версии на линии `VER = 0x10`; `CID1 = 0x46` всегда; `EOI = 0x0D`.
- Транспорт «верхнего» канала: **RS-485, baud 19200**; тот же кадр виден по BLE.

## 2. Транспорт BLE (GATT)

| Роль | UUID | Handle (дамп) |
|---|---|---|
| Сервис | `0000ff00-0000-1000-8000-00805f9b34fb` | — |
| **Запись команд** (app→BMS) | `0000ff02-…` | `0x0014` |
| **Уведомления/ответы** (BMS→app) | `0000ff01-…` | `0x0011` |
| CCCD | `00002902-…` | — |

> В реальном HCI-дампе приложение **пишет в `ff02`**, **слушает `ff01`**.
> (`ff03`/`ff04` приложением не используются; ранние пробы ошибочно слушали `ff03`.)
> Ответы приходят **несколькими notify-фрагментами** (ограничение MTU) —
> их нужно склеивать в буфер до появления полного кадра `7E … 0D`.

## 3. Формат кадра

### 3.1. Структура

```
Запрос (app/хост → BMS):  7E | 10 | ADR | 46 | CID2 | LEN(2) | INFO | CHKSUM(2) | 0D
Ответ  (BMS → app/хост):  7E | 14 | ADR | CID2 | RTN | LEN(2) | INFO | CHKSUM(2) | 0D
```

| Поле | Байт | Значение |
|---|---|---|
| SOI | 1 | `0x7E` |
| VER | 1 | `0x10` (в запросе Версия-протокола `0x4F` — `0x20`); в ответе — `0x14` |
| ADR | 1 | адрес/индекс пакета (`0x01..0xFE`, `0xFF` — broadcast); в ответе `0x00` |
| CID1 | 1 | `0x46` — **только в запросе** (байт 3) |
| CID2 | 1 | код команды (§4); в ответе — эхо команды в байте 3 |
| RTN | 1 | **только в ответе** (байт 4): код возврата `0x00` (успех) |
| LEN | 2 | `LCHKSUM<<12 \| LENID`; `LENID` — число байт INFO (≤ 0x0FFF), big-endian |
| INFO | LENID | данные |
| CHKSUM | 2 | контрольная сумма (см. §3.3), big-endian |
| EOI | 1 | `0x0D` |

Суммарная длина кадра = `10 + LENID` (запрос и ответ; ответ на байт короче
запроса за счёт отсутствия CID1, но длиннее на байт RTN — итого та же
структура). В ответе `LENID = frame[5]<<8 | frame[6]`, `INFO` начинается с
байта 7.

> **Исправление (2026-09-30).** Ранее в этой таблице ответ был описан как
> `... ADR | (CID1) | CID2 | LEN(2) ...` с длиной `9 + LENID`, т.е. без байта
> RTN. Живой опрос устройства `BP00` (BlueZ/bleak, сервер `192.168.x.x`)
> показал у всех четырёх блоков (BasicInfo/Battery/ParallelBattery/ReadBMSParams)
> реальный заголовок `7E 14 00 CID2 00 LEN(2)` и полную длину `10 + LENID`;
> например, Battery — `7e 14 00 61 00 00 6a …` (LENID = `0x006a` = 106,
> длина кадра 116). CRC-16/CCITT этих кадров сходится. Восстановление байта RTN
> в кадрах из `DEVICE_SNAPSHOT.md` даёт CRC, совпадающий с живым захватом для
> BasicInfo (`b7 45`) и ReadBMSParams (`13 2b`), — это и подтверждает пропуск
> ровно одного байта RTN в прежних записях.

### 3.2. Длины `LEN` (из `DataFrame.getLengthCRC`, ПО Upper Computer)

```c
// LCHKSUM = инверсия + 1 от суммы нибблов LENID
crc = (LENID>>8 & 0xF) + (LENID>>4 & 0xF) + (LENID & 0xF);
crc = (~(crc % 16) + 1) & 0xF;      // 4-битное дополнение
LEN = ((LENID & 0x0FFF) | (crc << 12)) & 0xFFFF;
```

### 3.3. Контрольная сумма — два диалекта

**A. Устройство / приложение EN BMS (снято вживую)** — **CRC-16/CCITT**:
полином `0x1021`, init `0`, без отражения, старший бит первым. Считается по
байтам кадра **со 2-го по предпоследний** (`frame[1:-3]`, т.е. без `0x7E`,
CRC-поля и `0x0D`). Реализация:

```c
uint16_t crc16_ccitt(const uint8_t *buf, int len) {
    uint16_t crc = 0;
    for (int i = 0; i < len; i++) {
        uint8_t b = buf[i];
        for (int bit = 0; bit < 8; bit++) {
            if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
            else crc <<= 1;
            if (b & 0x80) crc ^= 0x1021;
            b <<= 1;
        }
        crc &= 0xffff;
    }
    return crc & 0xffff;
}
```

Проверено на кадрах: `BasicInfo 3a7f`, `Battery f7c1`, `ReadBMSParams e716`. ✅

**B. ПО «Upper Computer» (RS-485)** — **16-битная сумма-дополнение** (YD/T 1363):
`CHKSUM = ((~ (Σ frame[i], i=1..len-6)) & 0xFFFF) + 1`.

> ⚠️ Диалекты A и B различаются. Приложение EN BMS (BLE) шлёт бинарный кадр с
> CRC-16/CCITT; PC-инструмент «Upper Computer» (RS-485) шлёт кадр как
> **ASCII-hex** с суммой-дополнением.
>
> **РЕШЕНО (2026-10-04, живой RS-485 через шлюз `192.0.2.77:502`):** на RS485
> реально используется **диалект B в ASCII-виде** — кадр `~` + hex-поля
> (`VER ADR 46 CID2 LEN INFO CHK`) + `CR`, где `CHK` = сумма-дополнение
> **ASCII-кодов** символов от `VER` до конца `INFO`, а `LEN = LCHKSUM<<12|LENID`.
> host-RS485 отдаёт `0x42/0x44/0x4F/0x51/0x47/0x4D/0x4B/0xA4`; RM485 — только
> `0x42/0x44/0x4F/0x51`. Полное описание — [`protocol-485.md`](protocol-485.md).

## 4. Команды (CID2)

Коды из `ProtocolCommand..ctor` (ПО Upper Computer) и enum `CMD_TYPE` (приложение).

| CID2 | Имя | Назначение |
|---|---|---|
| `0x42` | `CID2_TeleMeter` | Телеметрия (ячейки, температуры, ток, SOC…) |
| `0x44` | `CID2_TeleState` | Состояние/защиты/предупреждения (битовая карта) |
| `0x45` | `CID2_TeleCtrlExt` | Управление реле/режимами |
| `0x47` | `CID2_GetAllParas` | Чтение всех параметров (169 Б) |
| `0x49` | `CID2_SetPara` | Запись одного параметра / битового флага |
| `0x4B` | `CID2_GetHistoryData` | История |
| `0x4D` | `CID2_GetTime` | Чтение времени BMS |
| `0x4E` | `CID2_SetTime` | Установка времени |
| `0x4F` | `CID2_ProtocolVer` | Версия протокола |
| `0x51` | `CID2_Manufacture` | Инфо производителя / имя протокола инвертора |
| `0x90` | `CID2_GetPacksNum` | Число параллельных пакетов |
| `0xA0` | `CID2_Adjust` | Калибровка |
| `0xA1` | `CID2_SetAllParas` | Запись всех параметров |
| `0xA2` | `CID2_ScheduleRecord` / `CID2_GetSN` | Запись расписания / чтение SN |
| `0xA3` | `CID2_SetSN` | Запись SN |
| `0xA4` | `CID2_GetBatSN` | Чтение SN батареи |
| `0xA5` | `CID2_SetBatSN` | Запись SN батареи |
| `0xA6` | `CID2_SetCanProtocol` | Выбор CAN-протокола |
| `0xA7` | `CID2_Set485Protocol` | Выбор 485-протокола |

### 4.1. Команды приложения EN BMS (реверс `BmsMsgUtil.dart`)

| Команда | `cmd1` | `cmd0` | LEN | payload |
|---|---|---|---|---|
| BasicInfo | `0x51` | `0x46` | 0 | `[]` |
| ReadBMSParams | `0x47` | `0x46` | 1 | `[0]` |
| SwitchCAN | `0x63` | `0x46` | 1 | `[PROTOCOL_CAN.value]` |
| Battery | `0x61` | `0x46` | 1 | `[0]` |
| ParallelBattery | `0x62` | `0x46` | 0 | `[]` |
| WriteBMSParams | `0xA1` | `0x46` | `0xA9` | 169 Б (§8.4) |

Проверено по `getCmd_*` в `BmsMsgUtil.dart`: `cmd1` **захардкожен** в каждой
функции, а enum `CMD_TYPE` (`baseInfo, aloneBattery, parallelBattery, packParams,
switchCAN, switch485, writeBMSParams`) имеет **внутренние** значения
`[0xA2, 0xC2, 0xC4, 0x8E, 0xC6, 0xC8, 0x142]` — это **не** байт `cmd1`
(и `0x142` физически не влезает в байт). Внутренние коды → `cmd1`:

| `CMD_TYPE` | значение | `cmd1` в кадре |
|---|---|---|
| `baseInfo` | `0xA2` | `0x51` |
| `aloneBattery` | `0xC2` | `0x61` |
| `parallelBattery` | `0xC4` | `0x62` |
| `packParams` | `0x8E` | `0x47` |
| `switchCAN` | `0xC6` | `0x63` |
| `switch485` | `0xC8` | (`switch485`) |
| `writeBMSParams` | `0x142` | `0xA1` |

**Соответствие диалектов:** `0x51 ≡ CID2_Manufacture`, `0x47 ≡ CID2_GetAllParas`,
`0xA1 ≡ CID2_SetAllParas`. Коды `0x61/0x62/0x63` в карте ПО отсутствуют —
вероятно, расширение протокола (см. §11).

**`SwitchCAN` payload** = `PROTOCOL_CAN.value` ∈ `{2,4,6,8,10,12,14}` для
`PN_GDLT, GRWT, VCTR, SMA_SF, GINL, STUD, MUST` (см. §9; в ПО Upper Computer
те же 7 протоколов, но нумеруются `1..7`).

### 4.2. Поля модели `Bms_Msg_Model` (смещения Dart-AOT)

| смещение | поле | содержимое |
|---|---|---|
| 0x0b | `field_b` | head `0x7E` |
| 0x13 | `field_13` | фикс. `0x10` |
| 0x1b | `field_1b` | ADR |
| 0x23 | `field_23` | CID1 `0x46` |
| 0x2b | `field_2b` | CID2 |
| 0x33 | `field_33` | длина payload (u16 be) |
| 0x3b | `field_3b` | массив payload (добивается нулями до `field_33`) |


### 4.3. BasicInfo (`0x51`) — формат ответа

**Запрос:** `CID2=0x51`, `INFO` пуст, `ADR` — адрес (в ответе `0x14`).

**Ответ `INFO`** (в живом срезе 36 байт):

| Смещение | Размер | Содержимое |
|---|---|---|
| 0 … 29 | 30 | ASCII-имя активного протокола инвертора, дополнено пробелами (`0x20`); префикс канала — `CAN:` или `485:` |
| 30 … 35 | 6 | служебные байты; приложение (`parseBody_BasicInfo`) читает их как отдельные поля по индексам 30–35 |

Пример (живое устройство):
```
43 41 4e 3a … 20 10 06 01 01 46 00
└─ ASCII "CAN:PNG_DYE_Luxp_TBB1101-XO17" ─┘└ служ. байты ┘
```
Здесь ASCII = `CAN:` (канал CAN) + `PNG_DYE_Luxp_TBB1101-XO17` — активный протокол
инвертора семейства **PN-GDLT** (Pylontech/Deye/Luxpower/TBB/Goodwe); модель
`TBB1101-XO17` совпадает с именем модуля `1101-XO17` из §8.
Служебные байты (`10 06 01 01 46 00`) производителем не документированы; `0x10`
похож на версию протокола.

> Модель `Bms_Basicinfo_Model` в приложении хранит строку протокола и карту типов
> батареи (LFP/NMP/LCO/LTO), т.е. BasicInfo используется для отображения
> активного протокола инвертора и типа АКБ.

## 5. Телеметрия — CID2 = 0x42 (`DataFrame.GetAllTeleMeter`)

Порядок полей строго по порядку ниже; многобайтовые — big-endian.
Блоки с `NumFieldEnable=True` предваряются байтом-счётчиком количества.

| # | Поле | Байт | Ед. | Масштаб |
|---|---|---|---|---|
| 1 | Cell01 | 2 | V | 0.001 |
| 2 | Cell02 | 2 | V | 0.001 |
| 3 | Cell03 | 2 | V | 0.001 |
| 4 | Cell04 | 2 | V | 0.001 |
| 5 | Cell05 | 2 | V | 0.001 |
| 6 | Cell06 | 2 | V | 0.001 |
| 7 | Cell07 | 2 | V | 0.001 |
| 8 | Cell08 | 2 | V | 0.001 |
| 9 | Cell09 | 2 | V | 0.001 |
| 10 | Cell10 | 2 | V | 0.001 |
| 11 | Cell11 | 2 | V | 0.001 |
| 12 | Cell12 | 2 | V | 0.001 |
| 13 | Cell13 | 2 | V | 0.001 |
| 14 | Cell14 | 2 | V | 0.001 |
| 15 | Cell15 | 2 | V | 0.001 |
| 16 | Cell16 | 2 | V | 0.001 |
| 17 | Battery temp1 | 2 | ℃ | 0.1 |
| 18 | Battery temp2 | 2 | ℃ | 0.1 |
| 19 | Battery temp3 | 2 | ℃ | 0.1 |
| 20 | Battery temp4 | 2 | ℃ | 0.1 |
| 21 | Ambient temp | 2 | ℃ | 0.1 |
| 22 | Power temp | 2 | ℃ | 0.1 |
| 23 | Current | 2 | A | 0.01 |
| 24 | Total voltage | 2 | V | 0.01 |
| 25 | Remaining capacity | 2 | Ah | 0.01 |
| 26 | Total capacity | 2 | Ah | 0.01 |
| 27 | SOC | 2 | % | 0.1 |
| 28 | Rated capacity | 2 | Ah | 0.01 |
| 29 | Battery cycles | 2 | times | 1 |
| 30 | SOH | 2 | % | 0.1 |
| 31 | Bus voltage | 2 | V | 0.01 |

Масштаб: `0.001` — мВ→В для ячеек; `0.1` — 0.1 K для температур;
`0.01` — ток/напряжение пакета/ёмкости; `SOC`/`SOH` — 0.1 %.

### 5.1. Формат payload `Battery (0x61)` приложения (модель `Bms_Recv_Model`)

Порядок полей — из `Bms_Recv_Model.toJson` (совпадает с порядком чтения
`parseBody_Battery`); многобайтовые — big-endian:

| # | Поле | Смысл |
|---|---|---|
| 1 | `dataflag` | флаг данных |
| 2 | `slaveNo` | адрес/индекс пакета |
| 3 | `batterynum` | число ячеек |
| 4 | `voltagelist` | напряжения ячеек (`batterynum` × u16) |
| 5 | `tempnum` | число датчиков температуры |
| 6 | `templist` | температуры (`tempnum` × u16) |
| 7 | `envtemp` | температура среды |
| 8 | `powertemp` | температура силовой части |
| 9 | `chargecurrent` | ток |
| 10 | `totalvoltage` | суммарное напряжение |
| 11 | `leftcapacity` | остаточная ёмкость |
| 12 | `customerp` | (польз. ёмкость) |
| 13 | `totalcapacity` | полная ёмкость |
| 14 | `soc` | заряд, % |
| 15 | `ratedcapacity` | номинальная ёмкость |
| 16 | `cycles` | число циклов |
| 17 | `soh` | износ, % |
| 18 | `portvoltage` | напряжение на клеммах |
| 19 | `reservelist1` | резерв |
| 20 | `batterywarnlist` | предупреждения (ячейки) |
| 21 | `tempwarnlist` | предупреждения (температура) |
| 22 | `envtempwarn` | предупреждение (среда) |
| 23 | `powertempwarn` | предупреждение (силовая часть) |
| 24 | `chargecurrentwarn` | предупреждение (ток) |
| 25 | `customerwarnp` | предупреждение (польз.) |
| 26 | `eventwarnlist` | события |
| 27 | `switchstate` | состояния ключей |
| 28 | `balancestatelist` | балансировка |
| 29 | `sysstate` | системное состояние |
| 30 | `brokenstatelist` | неисправности |

**Точная раскладка** (подтверждена живым кадром, `2026-09-30`):

| Поле | Тип | Масштаб |
|---|---|---|
| `dataflag` | u8 | — |
| `slaveNo` | u8 | индекс пакета |
| `batterynum` | u8 | число ячеек |
| `voltagelist` | `batterynum` × u16 | ×0.001 В (мВ) |
| `tempnum` | u8 | число датчиков |
| `templist` | `tempnum` × u16 | ×0.1 K, −273.1 → °C |
| `chargecurrent` | **s16** | ×0.01 А (минус = разряд) |
| `totalvoltage` | u16 | ×0.01 В |
| `leftcapacity` | u16 | ×0.01 А·ч |
| `customerp` | **u8** | (см. примечание) |
| `totalcapacity` | u16 | ×0.01 А·ч |
| `soc` | u16 | ×0.1 % |
| `ratedcapacity` | u16 | ×0.01 А·ч |
| `cycles` | u16 | ×1 |
| `soh` | u16 | ×0.1 % |
| `portvoltage` | u16 | ×0.01 В |
| далее | списки | предупреждения/статусы |

> ⚠️ `customerp` занимает **1 байт** (а не 2): только при таком выравнивании
> сходятся `totalcapacity`=314 А·ч, `soc`≈33 %, `soh`=100 %, `portvoltage`≈52 В.
> Масштабы (`parseBody_Battery`): ячейки `0.001` (мВ→В), ток/напряжение/ёмкости
> `0.01`, температуры `0.1` K, SOC/SOH `0.1`.

## 6. Управление — телеуправление (битовая карта)

| Поле | Byte | Bit | Тип |
|---|---|---|---|
| Discharge control | 0 | 0 | OnOff |
| Charge control | 0 | 1 | OnOff |
| Current limit control | 0 | 2 | OnOff |
| Temperature control | 0 | 3 | OnOff |
| System shutdown | 0 | 4 | Shutdown |
| Restore factory | 0 | 5 | Reset |

## 7. Состояние — CID2 = 0x44 (`CID2_TeleState`)

Порядок: 1) 16 ячеек (Protect, счётчик) 2) 6 температур 3) ток/напряжение пакета,
затем битовый блок `Ext_Bit` (ByteIndex от 0):

| Поле | Байт | Бит | Тип |
|---|---|---|---|
| Voltage sensor invalidation | 0 | 0 | Warn |
| Temperature sensor invalidation | 0 | 1 | Warn |
| Current sensor invalidation | 0 | 2 | Warn |
| Button switch invalidation | 0 | 3 | Warn |
| Cell differential voltage invalidation | 0 | 4 | Warn |
| Charge switch invalidation | 0 | 5 | Warn |
| Discharge switch invalidation | 0 | 6 | Warn |
| Current limit switch invalidation | 0 | 7 | Warn |
| Cell over voltage alarm | 1 | 0 | Warn |
| Cell over voltage protection | 1 | 1 | Protect |
| Cell under voltage alarm | 1 | 2 | Warn |
| Cell under voltage protection | 1 | 3 | Protect |
| Pack over voltage alarm | 1 | 4 | Warn |
| Pack over voltage protection | 1 | 5 | Protect |
| Pack under voltage alarm | 1 | 6 | Warn |
| Pack under voltage protection | 1 | 7 | Protect |
| Charging over temperature alarm | 2 | 0 | Warn |
| Charging over temperature protection | 2 | 1 | Protect |
| Charging under temperature alarm | 2 | 2 | Warn |
| Charging under temperature protection | 2 | 3 | Protect |
| Discharge over temperature alarm | 2 | 4 | Warn |
| Discharge over temperature protection | 2 | 5 | Protect |
| Discharge under temperature alarm | 2 | 6 | Warn |
| Discharge under temperature protection | 2 | 7 | Protect |
| Environmental over temperature alarm | 3 | 0 | Warn |
| Environmental over temperature protection | 3 | 1 | Protect |
| Environmental under temperature alarm | 3 | 2 | Warn |
| Environmental under temperature protection | 3 | 3 | Protect |
| Power over temperature protection | 3 | 4 | Protect |
| Power over temperature alarm | 3 | 5 | Warn |
| Cell low temperature heating | 3 | 6 | Warn |
| Secondary tripping protection | 3 | 7 | Warn |
| Charging overcurrent alarm | 4 | 0 | Warn |
| Charge overcurrent protection | 4 | 1 | Protect |
| Discharge overcurrent alarm | 4 | 2 | Warn |
| Discharge overcurrent protection | 4 | 3 | Protect |
| Transient current protection | 4 | 4 | Protect |
| Output short circuit protection | 4 | 5 | Protect |
| Transient protection lockout | 4 | 6 | Protect |
| Short circuit protection lockout | 4 | 7 | Protect |
| Charging high voltage protection | 5 | 0 | Protect |
| Intermittent power supply waiting | 5 | 1 | Warn |
| Remaining capacity alarm | 5 | 2 | Warn |
| Remaining capacity protection | 5 | 3 | Protect |
| Battery low voltage forbidden charging | 5 | 4 | Protect |
| Output reverse connection protection | 5 | 5 | Protect |
| Aerosol failure | 5 | 6 | Protect |
| Discharge switch | 6 | 0 | Normal |
| Charging switch | 6 | 1 | Normal |
| Current limit switch | 6 | 2 | Normal |
| Temperature control switch | 6 | 3 | Normal |
| Equalization1 | 7 | 0 | Normal |
| Equalization2 | 7 | 1 | Normal |
| Equalization3 | 7 | 2 | Normal |
| Equalization4 | 7 | 3 | Normal |
| Equalization5 | 7 | 4 | Normal |
| Equalization6 | 7 | 5 | Normal |
| Equalization7 | 7 | 6 | Normal |
| Equalization8 | 7 | 7 | Normal |
| Equalization9 | 8 | 0 | Normal |
| Equalization10 | 8 | 1 | Normal |
| Equalization11 | 8 | 2 | Normal |
| Equalization12 | 8 | 3 | Normal |
| Equalization13 | 8 | 4 | Normal |
| Equalization14 | 8 | 5 | Normal |
| Equalization15 | 8 | 6 | Normal |
| Equalization16 | 8 | 7 | Normal |
| Automatic charging waiting | 12 | 4 | Warn |
| Manual charging and waiting | 12 | 5 | Warn |
| EEPROM malfunction | 13 | 0 | Warn |
| RTC clock malfunction | 13 | 1 | Warn |
| Voltage calibration not done | 13 | 2 | Warn |
| Current calibration not done | 13 | 3 | Warn |
| Zero point calibration not done | 13 | 4 | Warn |
| Perpetual calendar is not synchronized | 13 | 5 | Warn |

Режим (`Mode_Byte`, последний блок): 1=Discharge, 2=Charge, 4=Float,
8=Fully charged, 0x10=Standby, 0x20=Shutdown.

## 8. Параметры — CID2 = 0x47 (чтение) / 0xA1 (запись), ~169 байт

### 8.1. Целочисленные параметры (`int_para`, по `ParaIndex`)

| ParaIndex | Смещение(байт) | Поле | Байт | Ед. | Масштаб |
|---|---|---|---|---|---|
| 0x0 | 0 | Cell over voltage alarm | 2 | V | 0.001 |
| 0x1 | 2 | Cell over voltage alarm recovery | 2 | V | 0.001 |
| 0x2 | 4 | Cell under voltage alarm | 2 | V | 0.001 |
| 0x3 | 6 | Cell under voltage alarm recovery | 2 | V | 0.001 |
| 0x4 | 8 | Cell over voltage protection | 2 | V | 0.001 |
| 0x5 | 10 | Cell over voltage protection recovery | 2 | V | 0.001 |
| 0x6 | 12 | Cell under voltage protection | 2 | V | 0.001 |
| 0x7 | 14 | Cell under voltage protection recovery | 2 | V | 0.001 |
| 0x8 | 16 | Balance turn-on voltage | 2 | V | 0.001 |
| 0x9 | 18 | Battery low voltage forbidden charging | 2 | V | 0.001 |
| 0xA | 20 | Pack over voltage alarm | 2 | V | 0.01 |
| 0xB | 22 | Pack over voltage alarm recovery | 2 | V | 0.01 |
| 0xC | 24 | Pack under voltage alarm | 2 | V | 0.01 |
| 0xD | 26 | Pack under voltage alarm recovery | 2 | V | 0.01 |
| 0xE | 28 | Pack over voltage protection | 2 | V | 0.01 |
| 0xF | 30 | Pack over voltage protection recovery | 2 | V | 0.01 |
| 0x10 | 32 | Pack under voltage protection | 2 | V | 0.01 |
| 0x11 | 34 | Pack under voltage protection recovery | 2 | V | 0.01 |
| 0x12 | 36 | Charging overvoltage protection | 2 | V | 0.01 |
| 0x13 | 38 | Charging overvoltage recovery | 2 | V | 0.01 |
| 0x14 | 40 | Charging over temperature alarm | 2 | ℃ | 0.1 |
| 0x15 | 42 | Charging over temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x16 | 44 | Charging under temperature alarm | 2 | ℃ | 0.1 |
| 0x17 | 46 | Charging under temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x18 | 48 | Charging over temperature protection | 2 | ℃ | 0.1 |
| 0x19 | 50 | Charging over temperature protection recovery | 2 | ℃ | 0.1 |
| 0x1A | 52 | Charging under temperature protection | 2 | ℃ | 0.1 |
| 0x1B | 54 | Charging under temperature protection recovery | 2 | ℃ | 0.1 |
| 0x1C | 56 | Discharge over temperature alarm | 2 | ℃ | 0.1 |
| 0x1D | 58 | Discharge over temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x1E | 60 | Discharge under temperature alarm | 2 | ℃ | 0.1 |
| 0x1F | 62 | Discharge under temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x20 | 64 | Discharge over temperature protection | 2 | ℃ | 0.1 |
| 0x21 | 66 | Discharge over temperature protection recovery | 2 | ℃ | 0.1 |
| 0x22 | 68 | Discharge under temperature protection | 2 | ℃ | 0.1 |
| 0x23 | 70 | Discharge under temperature protection recovery | 2 | ℃ | 0.1 |
| 0x24 | 72 | Cell low temperature heating | 2 | ℃ | 0.1 |
| 0x25 | 74 | Cell heating recovery | 2 | ℃ | 0.1 |
| 0x26 | 76 | Environmental over temperature alarm | 2 | ℃ | 0.1 |
| 0x27 | 78 | Environmental over temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x28 | 80 | Environmental under temperature alarm | 2 | ℃ | 0.1 |
| 0x29 | 82 | Environmental under temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x2A | 84 | Environmental over temperature protection | 2 | ℃ | 0.1 |
| 0x2B | 86 | Environmental over temperature protection recovery | 2 | ℃ | 0.1 |
| 0x2C | 88 | Environmental under temperature protection | 2 | ℃ | 0.1 |
| 0x2D | 90 | Environmental under temperature protection recovery | 2 | ℃ | 0.1 |
| 0x2E | 92 | Power over temperature alarm | 2 | ℃ | 0.1 |
| 0x2F | 94 | Power over temperature alarm recovery | 2 | ℃ | 0.1 |
| 0x30 | 96 | Power over temperature protection | 2 | ℃ | 0.1 |
| 0x31 | 98 | Power over temperature protection recovery | 2 | ℃ | 0.1 |
| 0x32 | 100 | Charging overcurrent alarm | 2 | A | 0.01 |
| 0x33 | 102 | Charging overcurrent recovery | 2 | A | 0.01 |
| 0x34 | 104 | Discharge overcurrent alarm | 2 | A | 0.01 |
| 0x35 | 106 | Discharge overcurrent recovery | 2 | A | 0.01 |
| 0x36 | 108 | Charge overcurrent protection | 2 | A | 0.01 |
| 0x37 | 110 | Discharge overcurrent protection | 2 | A | 0.01 |
| 0x38 | 112 | Transient overcurrent protection | 2 | A | 0.01 |
| 0x39 | 114 | Output soft start delay | 2 | mS | 1 |
| 0x3A | 116 | Battery rated capacity | 2 | Ah | 0.01 |
| 0x3B | 118 | Remaining capacity | 2 | Ah | 0.01 |
| 0x3C | 120 | Voltage differential start | 1 | V | 0.01 |
| 0x3D | 121 | Voltage differential stop | 1 | V | 0.01 |
| 0x3E | 122 | Balance start voltage difference | 1 | V | 0.001 |
| 0x3F | 123 | Balance stop voltage difference | 1 | V | 0.001 |
| 0x40 | 124 | Static equilibrium time | 1 | When | 1 |
| 0x41 | 125 | Cell number | 1 | String | 1 |
| 0x42 | 126 | Charge overcurrent delay | 1 | S | 1 |
| 0x43 | 127 | Discharge overcurrent delay | 1 | S | 1 |
| 0x44 | 128 | Transient overcurrent delay | 1 | mS | 1 |
| 0x45 | 129 | Overcurrent delay recovery | 1 | S | 1 |
| 0x46 | 130 | Overcurrent recovery times | 1 | times | 1 |
| 0x47 | 131 | Charge current limit delay | 1 | Minutes | 1 |
| 0x48 | 132 | Charge activation delay | 1 | Minutes | 1 |
| 0x49 | 133 | Charging activation interval | 1 | When | 1 |
| 0x4A | 134 | Charge activation times | 1 | times | 1 |
| 0x4B | 135 | Work record interval | 1 | Minutes | 1 |
| 0x4C | 136 | Standby recording interval | 1 | Minutes | 1 |
| 0x4D | 137 | Standby shutdown delay | 1 | When | 1 |
| 0x4E | 138 | Remaining capacity alarm | 1 | % | 1 |
| 0x4F | 139 | Remaining capacity protection | 1 | % | 1 |
| 0x50 | 140 | Interval charge capacity | 1 | % | 1 |
| 0x51 | 141 | Cycle cumulative capacity | 1 | % | 1 |
| 0x52 | 142 | Connection fault impedance | 1 | mΩ | 0.1 |
| 0x53 | 143 | Compensation point 1 position | 1 | String | 1 |
| 0x54 | 144 | Compensation point 1 impedance | 1 | mΩ | 0.1 |
| 0x55 | 145 | Compensation point 2 position | 1 | String | 1 |
| 0x56 | 146 | Compensation point 2 impedance | 1 | mΩ | 0.1 |

Итого `int_para` = **147 Б** (60 параметров по 2 Б + 27 по 1 Б).
Далее битовые параметры и калибровка:

### 8.2. Битовые параметры (`bit_para`)

| Поле | Byte | Bit |
|---|---|---|
| Voltage sensor invalidation | 0 | 0 |
| Temperature sensor invalidation | 0 | 1 |
| Current sensor invalidation | 0 | 2 |
| Button switch invalidation | 0 | 3 |
| Cell differential voltage invalidation | 0 | 4 |
| Charge switch invalidation | 0 | 5 |
| Discharge switch invalidation | 0 | 6 |
| Current limit switch invalidation | 0 | 7 |
| Cell over voltage alarm | 1 | 0 |
| Cell over voltage protection | 1 | 1 |
| Cell under voltage alarm | 1 | 2 |
| Cell under voltage protection | 1 | 3 |
| Pack over voltage alarm | 1 | 4 |
| Pack over voltage protection | 1 | 5 |
| Pack under voltage alarm | 1 | 6 |
| Pack under voltage protection | 1 | 7 |
| Charging over temperature alarm | 2 | 0 |
| Charging over temperature protection | 2 | 1 |
| Charging under temperature alarm | 2 | 2 |
| Charging under temperature protection | 2 | 3 |
| Discharge over temperature alarm | 2 | 4 |
| Discharge over temperature protection | 2 | 5 |
| Discharge under temperature alarm | 2 | 6 |
| Discharge under temperature protection | 2 | 7 |
| Environmental over temperature alarm | 3 | 0 |
| Environmental over temperature protection | 3 | 1 |
| Environmental under temperature alarm | 3 | 2 |
| Environmental under temperature protection | 3 | 3 |
| Power over temperature protection | 3 | 4 |
| Power over temperature alarm | 3 | 5 |
| Cell low temperature heating | 3 | 6 |
| Secondary tripping protection | 3 | 7 |
| Charging overcurrent alarm | 4 | 0 |
| Charge overcurrent protection | 4 | 1 |
| Discharge overcurrent alarm | 4 | 2 |
| Discharge overcurrent protection | 4 | 3 |
| Transient current protection | 4 | 4 |
| Output short circuit protection | 4 | 5 |
| Transient overcurrent lockout | 4 | 6 |
| Output short circuit locking | 4 | 7 |
| Charging high voltage protection | 5 | 0 |
| Intermittent charging function | 5 | 1 |
| Remaining capacity alarm | 5 | 2 |
| Remaining capacity protection | 5 | 3 |
| Battery low voltage forbidden charging | 5 | 4 |
| Output reverse connection protection | 5 | 5 |
| Aerosol failure | 5 | 6 |
| Output soft start function | 5 | 7 |
| Charge equalization function | 6 | 0 |
| Static equilibrium function | 6 | 1 |
| Timeout prohibits equalization | 6 | 2 |
| Over temperature prohibits equalization | 6 | 3 |
| Automatically activate charging | 6 | 4 |
| Manually activate charging | 6 | 5 |
| Take the initiative current limiting charging | 6 | 6 |
| Passive current limiting charging | 6 | 7 |
| Switch shut down function | 7 | 0 |
| Standby shutdown function | 7 | 1 |
| History record function | 7 | 2 |
| LCD display function | 7 | 3 |
| Bluetooth communication function | 7 | 4 |
| Automatic address coding | 7 | 5 |
| Parallel external polling | 7 | 6 |
| Single BMS 1.0C charging | 7 | 7 |

### 8.3. Калибровка (`adjust_para`, CID2 = 0xA0)

| ParaIndex | Поле | Ед. | Масштаб |
|---|---|---|---|
| 0x0 | Zero point calibration | A | 0.01 |
| 0x1 | Current calibration | A | 0.01 |
| 0x2 | Voltage calibration | V | 0.001 |

### 8.4. Форматы команд записи (из IL `Set*Frame` / `Req*Frame`)

`DataFrame(VER, CID2, ADR, fields[])`: `INFO` = конкатенация полей `fields`
в порядке массива, каждое поле — **big-endian**, длина = `ByteNum` байт
(для `ByteNum=2` — `hi,lo`; для 4 — `b3,b2,b1,b0`). `ADR` = индекс пакета
(`CurDispPackIndex` / `CurCommPackAdr`).

| Действие | CID2 | INFO (payload) |
|---|---|---|
| Чтение телеметрии | `0x42` | `[packIndex:1]` |
| Чтение состояния/защит | `0x44` | `[packIndex:1]` |
| Чтение всех параметров | `0x47` | `[packIndex:1]` |
| Версия протокола | `0x4F` | `[]` (в запросе `VER=0x20`) |
| Инфо производителя | `0x51` | `[]` |
| Число пакетов | `0x90` | `[]` |
| **Запись одного параметра** | `0x49` | `[packIndex:1][paraIndex:1][value:2 BE]` |
| **Запись битового параметра** | `0x49` | `[packIndex:1][byteParaIndex:1][byteValue:1]` |
| **Запись всех параметров** | `0xA1` | см. ниже (169 Б) |
| **Управление реле/режимом** | `0x45` | `[packIndex:1][bitNo:1][action:1]` |
| **Калибровка** | `0xA0` | `[paraIndex:1][value:2 BE]` |
| Чтение времени BMS | `0x4D` | `[]` |
| **Установка времени** | `0x4E` | `[year:2][month:1][day:1][hour:1][min:1][sec:1]` |
| **Выбор CAN-протокола** | `0xA6` | `[type:1]` (§9) |
| Выбор 485-протокола | `0xA7` | `[type:1]` |
| Чтение SN | `0xA2` | `[]` |
| **Запись SN** | `0xA3` | `[ASCII 30]` (пробелы) |
| Чтение SN батареи | `0xA4` | `[]` |
| **Запись SN батареи** | `0xA5` | `[ASCII 30]` (пробелы) |
| **Старт записи истории** | `0xA2` | `[0x10][start:Y2 dm hms][end:Y2 dm hms][interval:2]` |
| **Стоп записи истории** | `0xA2` | `[0x1F]` |

**Запись всех параметров (`0xA1`) — точная раскладка 169 Б:**

| Смещение | Размер | Поле |
|---|---|---|
| 0 | 1 | packIndex |
| 1 | 1 | IntParaCnt = `60` |
| 2 … 121 | 120 | 60 × `u16be` — параметры `ParaIndex 0x00…0x3B` (§8.1) |
| 122 | 1 | ByteParaCnt = `27` |
| 123 … 149 | 27 | 27 × `u8` — параметры `ParaIndex 0x3C…0x56` (§8.1) |
| 150 | 1 | BitGroupCnt = `8` |
| 151 … 158 | 8 | 8 × `u8` — битовые группы (§8.2) |
| 159 … 168 | 10 | ASCII-имя модуля (дополнено пробелами) |

Итого `1+1+120+1+27+1+8+10 = 169 Б` (совпадает с `0xA9` в живом дампе).
Ответ на чтение `0x47` имеет **тот же** формат (снятый payload начинался
`00 3C 0D B6 …`: packIndex=0, IntParaCnt=60, OVP≈3.510 В).

**Управление (`0x45`)**: `bitNo = ByteIndex·8 + BitIndex` из `teleControl` (§6)
— bit0 discharge, bit1 charge, bit2 current-limit, bit3 temperature,
bit4 shutdown, bit5 reset. `action`: для типа `OnOff` — `0x10` («Open»,
включить) если сейчас выключено, иначе `0x1F` («Close», выключить);
для `Shutdown`/`Reset` — `0x00`.

> Итог: блок 169 Б и все команды записи/режимов **полностью восстановлены** из IL.

## 9. Протоколы инвертора (CID2 = 0xA6 SetCanProtocol)

| Type | Имя | Бренды |
|---|---|---|
| 1 | PN-GDLT | PN-GDLT (Pylontech/Deye/Luxpower/TBB/Goodwe) |
| 2 | GRWT | Growatt (SPF/SPH) |
| 3 | VCTR | Victron |
| 4 | SMA-SF | SMA/SOFAR |
| 5 | GINL | Solis |
| 6 | STUD | Studer |
| 7 | MUST | MUST |

485-протокол «самоадаптируемый» (вручную не выбирается).

Приложение EN BMS адресует те же протоколы командой `SwitchCAN (0x63)` со
значениями `PROTOCOL_CAN` = `2, 4, 6, 8, 10, 12, 14` для
`PN_GDLT, GRWT, VCTR, SMA_SF, GINL, STUD, MUST` соответственно (нумерация
отличается от ПО Upper Computer, где те же имена имеют Type `1..7`).


## 10. Примеры кадров

**Запросы (write в `ff02`), addr = 0:**
```
BasicInfo       7e 10 00 46 51 00 00 3a 7f 0d
Battery         7e 10 00 46 61 00 01 00 f7 c1 0d
ReadBMSParams   7e 10 00 46 47 00 01 00 e7 16 0d
Write (0xA1)    7e 10 00 46 a1 00 a9 <169B payload> <crc> 0d
```

**Ответы (notify `ff01`):** заголовок `7E 14 ADR CID2 RTN LEN(2)` (ADR=`0x00`,
RTN=`0x00`; ранее `0x14` ошибочно называли ADR — это байт 1 заголовка):
```
BasicInfo (0x51):  7e 14 00 51 00 00 24 43 41 4e 3a ...  (ASCII "CAN:PN_G_DYE_Luxp_TBB1101-XO17")
Battery   (0x61):  7e 14 00 61 00 00 6a ...              (len=106, телеметрия, 4 notify-фрагмента)
ParallelBattery (0x62): 7e 14 00 62 00 00 28 ...         (len=40)
ReadBMSParams(0x47): 7e 14 00 47 00 00 a9 00 3c 0d b6 ... (len=169)
ACK записи (0xA1): 7e 14 00 a1 00 00 00 80 e7 0d         (LENID=0, кадр уже с RTN)
```
> В прежних записях кадров ответов байт `RTN` (`00`) был пропущен — см.
> исправление в §3.1 и примечание в `DEVICE_SNAPSHOT.md`.

**Декодированный `Battery (0x61)` (len=106, склейка фрагментов):**

| смещение | размер | поле |
|---|---|---|
| 0 | 1 | `dataflag` = `0x00` |
| 1 | 1 | `slaveNo` = `0x00` |
| 2 | 1 | `batterynum` = `0x10` (=16) |
| 3 | 32 | 16 напряжений ячеек, `u16be`, мВ (`0x0CBF` = 3263 → 3.263 В) |
| 35 | 1 | `tempnum` = `06` — число термодатчиков |
| 36 | 12 | 6 температур, `u16be`, ед. 0.1 K, офсет −2731 (2985 → 25.4 °C) |
| 48 | 58 | ток, напряжения/ёмкости, SOC/SOH, предупреждения, состояния (§5.1) |

**`BasicInfo (0x51)`**: payload = ASCII `CAN:PN_G_DYE_Luxp_TBB1101-XO17` +
служебные байты (`20 10 06 01 01 46 00`) — имя активного CAN-протокола инвертора.

## 11. Различия диалектов (BLE/приложение ↔ RS485/Upper Computer)

| Параметр | Приложение/устройство (HCI) | ПО Upper Computer (`Agreement`) |
|---|---|---|
| tail | `0x0D` | `0x0D` |
| control | CRC-16/CCITT | сумма-дополнение (YD/T 1363) |
| LEN | только длина (LCHKSUM=0) | `LCHKSUM<<12 \| LENID` |
| заголовок ответа | `7E 14 00 CID2 RTN LEN(2)`, длина `10+LENID` | — |

- Контроль: BLE-диалект — CRC-16/CCITT (подтверждено живьём); RS485 — сумма-дополнение
  ASCII + `LCHKSUM` в `LEN` (подтверждено живьём; см. `protocol-485.md` §2).
- Хвост кадра: **на проводе `0x0D`** (перепроверено по HCI-дампу дважды), хотя в
  asm `getSendMsg` фигурирует константа `0x1A` (внутренняя/легаси) — считать
  рабочим `0x0D`.
- Полная карта полей `0x61` получена по модели `Bms_Recv_Model` (§5.1) и
  **подтверждена** живым кадром (см. §12).
- Открытые пункты вынесены в бэклог (см. конец документа).

## 12. Проверено на живом устройстве (2026-09-30)

Опрос через сервер `192.168.x.x` (BlueZ/bleak), устройство **`BP00`**
(`28:xx:xx:xx:xx:xx`), сервис `ff00`, запись `ff02`, notify `ff01`.
Скрипты — в `tools/`. Только чтение; BT-адаптер не трогали.
Полный срез с сырыми кадрами, разделами и временем чтения — **`DEVICE_SNAPSHOT.md`**.

- **`BasicInfo (0x51)`** → CRC ok, payload = ASCII
  `CAN:PNG_DYE_Luxp_TBB1101-XO17` + `20 10 06 01 01 46 00`.
- **`Battery (0x61)`** → len = 106, CRC ok. Полностью декодирован (раскладка §5.1):
  ячейки ≈`3.256…3.262 В`; температуры `24.0…28.8 °C`; ток `−12.34 А` (разряд);
  напряжение сборки `52.14 В`; остаток `102.30 А·ч`; `customerp=6`; полная ёмкость
  `314.0 А·ч`; SOC `32.5 %`; SOH `100 %`; клеммы `52.17 В`; предупреждений нет.
- **`ParallelBattery (0x62)`** → len = 40, CRC ok: только `batterynum=16`,
  остальные поля нулевые (устройство одиночное).
- **`ReadBMSParams (0x47)`** → len = 169, CRC ok. ⚠️ Кадр содержит байты `0x0D`
  **внутри** payload — собирать кадр **по длине** (`total = 10 + LENID`), а не по
  `0x0D` (иначе кадр обрезается). Декодировано: `packIndex=0`, `IntParaCnt=60`,
  `ByteParaCnt=27`, `BitGroupCnt=8`, `module name = "1101-XO17"`.
  Ключевые пороги: Cell OVP `3.650 V`, OV-alarm `3.500`, UV-alarm `2.900`,
  UVP `2.700`; Pack OV-alarm `56.0`, UV-alarm `46.4`, OVP `57.6`, UVP `43.2 V`;
  charge OT alarm `50 °C`; charge OC alarm `200 A`; `Cell number = 16`;
  `Battery rated capacity = 314 Ah`, `Remaining capacity = 150 Ah`.
- **В BLE-диалекте применяются** `0x51/0x61/0x62/0x47`; команды
  `0x42/0x44/0x4F/0x90/0x4D/0xA2/0xA4` в этом диалекте не используются — их
  данные даёт RS485 (см. `protocol-485.md`).
  Время чтения блоков BLE: BasicInfo `0.253 с`, Battery `0.255 с`,
  ParallelBattery `0.253 с`, ReadBMSParams `1.414 с`.

**Вывод:** формат кадра, CRC-16/CCITT, сборка по длине, раскладка телеметрии
(§5.1) и формат блока 169 Б (§8.4) подтверждены на живом устройстве.

## Доступность TeleMeter (0x42)/TeleState (0x44) по интерфейсам

Приложение EN BMS в BLE-диалекте использует только `0x51/0x61/0x62/0x47`, поэтому
телеметрия/защиты в BLE-виде не читаются. По **RS485** (диалект PACE) доступны
телеметрия (`0x42`) и состояние/защиты (`0x44`), включая блок `Ext_Bit` (§7) —
разбор и карта: `protocol-485.md` §5/§6. Разметка `Ext_Bit` (byte/bit)
подтверждена по XML `16S_V20_ADDR_EN.xml` (`teleSignal`, совпадает с §7): байты 0..13.

## XML приложения: разметка телесигналов

`16S_V20_ADDR_EN.xml` (protocolConfig, `BMS-16S` v2.0) содержит:
- `teleMeter_Group` — раскладка телеметрии Battery (ячейки/температуры/ток/…);
- `teleSignal` — 126 сигналов `Ext_Bit` с `ByteIndex`/`BitIndex`/`Type`
  (`Warn`/`Protect`/`Normal`) — та же карта, что в §7;
- `int_para`/`bit_para` — параметры (пороги), соответствуют §8.

Пороги из `int_para` также выгружены в `tools/params_table.py`.

### 5.1.1. Точная раскладка ХВОСТА Battery из `parseBody_Battery` (APK, 2026-10-01)

Разобрана функция `parseBody_Battery` (`BmsMsgUtil.dart`, addr `0x3f3a18`,
размер `0x20f4`, blutter-дамп `/tmp/kilo/bms_out/.../BmsMsgUtil.dart`) и метод
`toJson` (`0x3def6c`), задающий **порядок имён** полей модели `Bms_Recv_Model`.

Порядок полей (из `toJson`, подтверждает §5.1):
`dataflag, slaveNo, batterynum, voltagelist, tempnum, templist, envtemp,
powertemp, chargecurrent, totalvoltage, leftcapacity, customerp, totalcapacity,
soc, ratedcapacity, cycles, soh, portvoltage, reservelist1, batterywarnlist,
tempwarnlist, envtempwarn, powertempwarn, chargecurrentwarn, customerwarnp,
eventwarnlist, switchstate, balancestatelist, sysstate, brokenstatelist`.

Как `parseBody_Battery` читает хвост (после `portvoltage`; смещения — от начала
39-байтного хвоста, наблюдаемого в живом кадре, INFO=106 Б, телеметрия=67 Б):

| Смещение | Байт | Как читается | Смысл (по порядку имён) |
|---|---|---|---|
| 0 | **16** (=`batterynum`) | цикл appends байт в отдельный список | первый warn-список (по ячейкам) |
| 16 | **`tempnum−2`** (=4) | цикл appends байт | warn-список по температурам (без ambient/power) |
| 20 | 1 | один байт | `envtempwarn` |
| 21 | 1 | один байт | `powertempwarn` |
| 22 | 1 | один байт | `chargecurrentwarn` |
| 23 | 1 | пропуск/скаляр | `customerwarnp` |
| 24 | 1 | `parseByte` | состояние (напр. `eventwarnlist`/`switchstate`) |
| 25 | 1 | `parseByte` | состояние |
| 26 | 1 | счётчик N | число блоков далее (в норме 3) |
| 27… | N×? | цикл: из байта раскладываются 8 бит в массив из 16 | `eventwarnlist`/`balancestatelist`/`sysstate`/`brokenstatelist` |

**Живой кадр (здоровая батарея):** хвост = `00`×25, затем `01 03 08`, затем `00`×11.
То есть **warn-область хвоста (смещения 0…23) вся нулевая**, а ненулевые байты
`01 03 08` (смещения 25…27) относятся к статусам (ключи/балансировка/режим), а не
к авариям. Это и было причиной ложных Warn/Protect при ошибочном смещении.

> ⚠️ Однозначное сопоставление первых двух списков с именами
> `reservelist1` / `batterywarnlist` (оба по `batterynum`-подобному счётчику)
> требует доп. проверки; практический вывод неизменен — warn-байты в начале хвоста,
> статусы — во второй половине.

**Практический вывод для декодера:** аварии Battery читать из warn-области
(смещения 0…22), а не из `Ext_Bit` XML `teleSignal_Group`.

### 5.1.2. Имена warn-битов ячейки Battery (APK, 2026-10-01)

`ble_data.dart` (blutter-дамп) содержит определения warn-битов ячейки в порядке:
`0 Cell high voltage warning`, `1 Cell over voltage protection`,
`2 Cell low voltage warning`, `3 Cell under voltage protection`.
В `sunReceiver` (`enbmsCellWarnBits`) байт предупреждения ячейки раскладывается по
этим битам; подтверждено живыми событиями: у ячеек 9 и 16 наблюдалось значение
`0x02` (бит 1 — защита от перенапряжения). Локализация строк — ru/en/zh в дашборде.

## 13. Переключение канала CAN/485 и коды RTN (живой BLE, 2026-10-02)

Проверено на живом EMU1101 через BLE-хост `gsrv` (`28:xx:xx:xx:xx:xx`, `BP00`),
кадры собраны по `BmsMsgUtil` / `device_data_provider` (blutter-дамп APK).

### 13.1. Формат ответа и поле RTN

Ответ: `7E | 14 | ADR | CID2 | RTN | LEN(2) | INFO | CHKSUM(2) | 0D`.
`RTN` — это **байт 4** (сразу после `CID2`):

| RTN | Значение |
|---|---|
| `0x00` | норма / SETSUCCESS |
| `0xE2` | **SETFAIL** («параметр не сохранён», ошибка) |

Строки приложения: `COMMON_DEVICE_SETTING_PARAM_SETSUCCESS` / `...SETFAIL`
(`device_setting_param_page.dart:0x3fe878`).

### 13.2. Канал **CAN** — CID2 `0x63` (работает)

- Запрос: `7E 10 ADR 46 63 00 01 <type> CHK 0D`
- Ответ: `7E 14 ADR 63 00 00 01 <type> CHK 0D` (`RTN=0x00`).

`type` трактуется устройством как тип из карты ПО (`canProtocol` в XML):
`1`=PN-GDLT, `2`=GRWT, `3`=VCTR, `4`=SMA-SF, `5`=GINL, `6`=STUD, `7`=MUST.

Проверено живьём (подтверждается строкой `BasicInfo`):

```
TX 7e 10 00 46 63 00 01 04 5a 2d 0d  -> RTN=0x00
BasicInfo -> CAN:SMA_SOFAR
TX 7e 10 00 46 63 00 01 01 0a 88 0d  -> RTN=0x00
BasicInfo -> CAN:PNG_DYE_Luxp_TBB1101-XO17   (исходный)
```

> Примечание: enum приложения `PROTOCOL_CAN_Ext.value` даёт значения `{2,4,6,…}`,
> но само устройство ожидает тип `1..7`. Ориентироваться на нумерацию карты (§9).

### 13.3. Канал **RS485** — CID2 `0x64` (инверторный канал)

- Запрос: `7E 10 ADR 46 64 <LEN> <payload> CHK 0D`
- Ответ этой платы: `7E 14 ADR 64 E2 00 01 <INFO> CHK 0D` — `RTN=0xE2` (SETFAIL)
  при любом payload (`LEN=0`, `0..6,8,10`). Пример: `7E 14 00 64 E2 00 01 14 6E 61 0D`.

`0x64` переключает **инверторный** канал (CAN/RM485) на 485; на этой плате он
отклоняется. К верхнему **host-RS485** (п. 10.2) это не относится: он работает по
диалекту PACE и используется верхним ПО (см. `protocol-485.md`).
Диспетчер ответов приложения: `0x63 → switchCANDataVN`,
`0x64 → switch485DataVN` (`device_data_provider.dart:0x3e8d54/0x3e8e30`).

### 13.4. Диалекты команд переключения

| Диалект | CAN | 485 |
|---|---|---|
| Приложение EN BMS | `0x63` (`getCmd_SwitchCAN`) | `0x64` (билдер в статике не найден) |
| ПО Upper Computer (карта) | `0xA6` SetCanProtocol `[type:1]` | `0xA7` Set485Protocol `[type:1]` |

На BLE-канале используется диалект приложения (`0x63`); CRC — CRC16/CCITT (§3.3).
Кадры `0xA6`/`0xA7` — диалект RS485/Upper Computer (`protocol-485.md`).

### 13.5. «CAN Verify Password»

Это **локальный пароль приложения** (Setting Password), а не команда BMS: хранится
в `shared_preferences` под ключом `app_user` (поле `password`), задаётся в
«My → Set Password» (`SetSpPassword`, `MY_SETPASSWORD`). В кадр переключения не
попадает и при прямом BLE-запросе не проверяется — на реверс-опрос не влияет.

## 14. Бэклог

- Коды `0x61/0x62/0x63` приложения отсутствуют в карте Upper Computer — установить
  их соответствие (или показать, что это уникальные команды BLE-диалекта).
- Подтвердить смысл байтов `Ext_Bit[14..18]` (за пределами XML Byte0..13) на живом
  изменении режима — см. `protocol-485.md` §6.
- Разобрать формат истории (`0x4B`) и точный формат даты/времени (`0x4D`).
- Проверить адресацию слейвов (`ADR=01..0F`) при параллельной сборке.
- Сверить значения параметров RS485 с BLE-эталоном (`DEVICE_SNAPSHOT.md` §4).
- Реализовать RS485-транспорт (host-RS485, PACE) в проекте sunReceiver (модуль
  `enBms`).
