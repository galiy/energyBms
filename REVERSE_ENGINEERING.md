# REVERSE_ENGINEERING.md — детали разбора и узкие места

Технический дневник: как восстановлен протокол Enjie, какие инструменты и
приёмы использовались, какие грабли встретились. Написан так, чтобы **другая
сессия могла продолжить работу** без повторного «изобретения» методов.
Результаты (сам протокол) вынесены в `protocol-BLE.md`.

## Содержание

1. Инвентарь артефактов, доступы и правила
2. Реверс BLE-кадров из APK (Dart-AOT, blutter)
3. Живой BLE-опрос и HCI-дамп
4. Анализ APK EN BMS 1.1.4 (манифест, OSINT, безопасность)
5. Разбор ПО «Upper Computer» (.NET) — первоисточник протокола
6. Узкие места, грабли и полезные приёмы
7. Статус, инфраструктура и команды (архив)

## 1. Инвентарь артефактов, доступы и правила

| Артефакт | Путь / доступ | Примечание |
|---|---|---|
| APK приложения | `./BMS_1.1.4.apk` (копия; ориг. `/home/<user>/Загрузки/`) | SHA-256 `584230df…273c21`, debug-сборка |
| Распаковка apktool | `/tmp/kilo/bms_full`, `/tmp/kilo/bms` | **в `/tmp` — не переживёт перезагрузку** |
| Даташит | `emu1101-24v-24100-1101-10e-08s-v1-0-en.pdf` | в репозитории |
| Dart-AOT декомпиляция | `/tmp/kilo/bms_out` (blutter) | ключевой файл `asm/bms_flutter/common/ble/BmsMsgUtil.dart`; **`/tmp` — непостоянно** |
| ПО «Upper Computer» | `/tmp/kilo/upper` (после распаковки) | скачано с cnshenergy; **`/tmp` — непостоянно** |
| Карта протокола (копия) | `16S_V20_ADDR_EN.xml` | в репозитории |
| HCI-дампы телефона | `./btlogs/` (в `.gitignore`) | BTSnoop v1 / H4 |
| Сервер для BLE-опроса | `192.168.x.x`, root | bleak 3.0.2, bluetoothctl, gatttool |
| Телефон | IIIIF150 B3, Android 14 | ADB по Wi-Fi, HCI snoop |

**Правила (не нарушать):**
- **BT-адаптер сервера не трогать** (никаких `systemctl restart bluetooth`,
  `hciconfig reset/up`, `btmgmt power`, очистки сопряжений) — только пассивный
  скан и подключение к рекламирующимся устройствам.
- Приватные данные — только в `.kilo/`; sudo-пароль — в связке ключей
  (`secret-tool lookup service sudo username <user>`), не логировать.
- Язык ответов — русский.
- **Не редактировать `.kilo/agent-manager.json`**.

## 2. Реверс BLE-кадров из APK (Dart-AOT, blutter)

Источник: дайджест Dart-AOT `libapp.so` приложения **EN BMS** (Shanghai Enjie, N ENERGY,
上海恩阶电子科技有限公司, ICP 沪ICP备2021016577号-2A), пакет отладки `com.example.bms_flutter`
(versionName 1.1.4), Flutter ~3.3.x, Dart 2.18.6 (snapshot hash `b6d0a1f034d158b0d37b51d559379697`,
arm64, compressed-pointers, null-safety).

### Контекст реверс-инжиниринга

- Описание устройства (сайт производителя): [EMU1101-V1.6 Smart BMS 100A/150A/200A 8S-16S LFP NCM](https://www.cnshenergy.com/products/emu1101-v16-smart-bms-100a-150a-200a-8s-16s-lfp-ncm/)
- APK: `/home/<user>/Загрузки/BMS_1.1.4.apk`, распакован в `/tmp/kilo/bms_full` (apktool) и `/tmp/kilo/bms`.
- Декомпиляция: `blutter` (`/tmp/kilo/blutter`, репозиторий `worawit/blutter`), выводится в `/tmp/kilo/bms_out`.
- Ключевой файл: `/tmp/kilo/bms_out/asm/bms_flutter/common/ble/BmsMsgUtil.dart`
  (классы `BmsMsgUtil`, `Bms_Msg_Model`). Дополнительно: `common/ble/ble_data.dart`.

### BLE-профиль (GATT)

| Роль | UUID |
|---|---|
| сервис | `0000ff00-…` |
| запись (write) | `0000ff02-…` |
| уведомления (notify) | `0000ff01-…` |
| CCCD | `00002902-…` |

### HTTP-эндпоинты (из приложения)

- `https://wxcrm.vsites.cn/enbmsapi/config`
- `http://kyplatform.vsites.cn/kyplatform/bms/saveLog` (cleartext, разрешён через `network_security_config`)

### Формат кадра (подтверждён, обе стороны)

`getSendMsg` (0x3d0648) собирает итоговый список = заголовок + payload + CRC + хвост.
Приёмная функция (0x3f66xx) проверяет длину кадра `len + 7 + 3` — совпадает.

| смещение | размер | поле | значение |
|---|---|---|---|
| 0 | 1 | head | `0x7E` |
| 1 | 1 | fix | `0x10` (константа) |
| 2 | 1 | addr | адрес/индекс устройства |
| 3 | 1 | cmd0 | `0x46` (`'F'`) |
| 4 | 1 | cmd1 | код команды (см. ниже) |
| 5 | 2 | len | длина payload, big-endian (`hi<<8 \| lo`) |
| 7 | len | payload | данные (дополняются нулями до `len`) |
| 7+len | 2 | crc16 | CRC-16/CCITT (полином `0x1021`, init 0), big-endian |
| 9+len | 1 | tail | `0x1A` |

Суммарная длина кадра = `9 + len`.

#### Поля модели `Bms_Msg_Model` (смещения через compressed-pointer)

| смещение | поле | содержимое |
|---|---|---|
| 0x0b | `field_b` | head = `0x7E` |
| 0x13 | `field_13` | фикс. = `0x10` |
| 0x1b | `field_1b` | addr (аргумент команды) |
| 0x23 | `field_23` | cmd0 = `0x46` |
| 0x2b | `field_2b` | cmd1 = код команды |
| 0x33 | `field_33` | **длина payload** (16 бит, big-endian) |
| 0x3b | `field_3b` | массив данных payload |

`field_33` — это длина (а не «флаг»). Данные из `field_3b` добиваются нулями до `field_33`.

### Таблица команд (геттеры `getCmd_*`)

CMD = `0x46` + cmd1. Параметры: header `0x7E`, len `0x10`, addr — аргумент.

| Команда | cmd1 | cmd0 | | длина (`field_33`) | payload (`field_3b`) |
|---|---|---|---|---|
| BasicInfo | `0x51` | `0x46` | `getCmd_BasicInfo` | 0 | `[]` |
| ReadBMSParams | `0x47` | `0x46` | `getCmd_ReadBMSParams` | 1 | `[0]` |
| SwitchCAN | `0x63` | `0x46` | `getCmd_SwitchCAN` | 1 | `[CAN]` |
| Battery | `0x61` | `0x46` | `getCmd_Battery` | 1 | `[0]` |
| ParallelBattery | `0x62` | `0x46` | `getCmd_ParallelBattery` | 0 | `[]` |

#### enum `CMD_TYPE` (имена `cmd1`)
- `baseInfo` = `0x51`
- `aloneBattery` = `0x61`
- `parallelBattery` = `0x62`
- `packParams` (ReadBMSParams) = `0x47`
- `switchCAN` = `0x63`
- `switch485` = `0xc6`-ing (см. исходник), `writeBMSParams`
- полный список opcodes в исходнике: `[162,194,196,142,198,200,322]` = `0xA2,0xC2,0xC4,0x8E,0xC6,0xC8,0x142`

### Обработчики ответов (`parseBody_*`)
- `parseBody_PackParams` (0x3e91b8) → модель `Bms_PackParamter_Model`
- `parseBody_Msg` (0x3f6524) — общий разбор тела.

### Контрольная сумма: CRC-16/CCITT

- Полином: `0x1021`
- Инициализация: `0`
- Без отражения, старший бит первым (цикл проверяет бит `0x8000`)
- Порядок байт в кадре: big-endian (сначала старший байт)
- Вычисленное значение печатается в консоль как `======计算得crc16=:` — удобно сверять любую команду.

Реализация (псевдокод логики из ассемблера):

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

> Открытый вопрос: CRC считается по заголовку+payload (стандартно) или по payload.
> Проверяется по логу `======计算得crc16=:` на реальном кадре.

### Примеры команд (Big-endian)

```
Battery:          7E 10 <addr> 46 61 00 01 00 <crcHi> <crcLo> 1A
ParallelBattery:  7E 10 <addr> 46 62 00 00 <crcHi> <crcLo> 1A
SwitchCAN:        7E 10 <addr> 46 63 00 01 <CAN> <crcHi> <crcLo> 1A
ReadBMSParams:    7E 10 <addr> 46 47 00 01 00 <crcHi> <crcLo> 1A
BasicInfo:        7E 10 <addr> 46 51 00 00 <crcHi> <crcLo> 1A
```

### Уточнения по APK (сверка с ПО «Upper Computer», 2026-09-30)

После получения протокола производителя (`protocol-BLE.md`) `BmsMsgUtil.dart`
перечитан заново. Что уточнилось:

- **`cmd1` захардкожен** в `getCmd_*`: `BasicInfo 0x51`, `Battery 0x61`,
  `ParallelBattery 0x62`, `ReadBMSParams 0x47`, `SwitchCAN 0x63`,
  `WriteBMSParams 0xA1`.
- **enum `CMD_TYPE`** имеет **внутренние** значения
  `[0xA2, 0xC2, 0xC4, 0x8E, 0xC6, 0xC8, 0x142]` (для `baseInfo, aloneBattery,
  parallelBattery, packParams, switchCAN, switch485, writeBMSParams`) — это
  **не** байт `cmd1` (значение `0x142` вообще не влезает в байт). Ранее (в
  прежнем документе по реверсу APK) они ошибочно приравнивались к `cmd1`.
- **`PROTOCOL_CAN`**: имена `[PN_GDLT, GRWT, VCTR, SMA_SF, GINL, STUD, MUST]`,
  значения `[2, 4, 6, 8, 10, 12, 14]`; payload команды `SwitchCAN (0x63)` =
  `PROTOCOL_CAN.value`. В ПО Upper Computer те же 7 протоколов нумеруются `1..7`.
- **`Bms_Recv_Model`** (payload `0x61`) — 30 полей в порядке:
  `dataflag, slaveNo, batterynum, voltagelist, tempnum, templist, envtemp,
  powertemp, chargecurrent, totalvoltage, leftcapacity, customerp, totalcapacity,
  soc, ratedcapacity, cycles, soh, portvoltage, reservelist1, batterywarnlist,
  tempwarnlist, envtempwarn, powertempwarn, chargecurrentwarn, customerwarnp,
  eventwarnlist, switchstate, balancestatelist, sysstate, brokenstatelist`
  (полная таблица — `protocol-BLE.md` §5.1). «Заголовок» `00 00 10` в живом кадре —
  это `dataflag=0`, `slaveNo=0`, `batterynum=16`.
- **Хвост кадра:** в asm `getSendMsg` (0x3d0648) фигурирует константа `0x1A`,
  но фактический кадр на проводе — `7e1000465100003a7f0d` (заканчивается
  `0x0D`); подтверждено повторным разбором `btlogs/btsnoop_hci.log`. Считать
  рабочим `0x0D`.
- CRC-16/CCITT по `frame[1:-3]` перепроверен на живых кадрах: `3a7f/f7c1/e716`.
- **`customerp` в `Bms_Recv_Model` — 1 байт (u8)**, а не u16: только при таком
  выравнивании в живом кадре `0x61` сходятся `totalcapacity`=314 А·ч, `soc`≈33 %,
  `soh`=100 %, `portvoltage`≈52 В (см. `protocol-BLE.md` §5.1).
- В BLE-диалекте используются `0x51, 0x61, 0x62, 0x47`; команды
  `0x42, 0x44, 0x4F, 0x90, 0x4D, 0xA2, 0xA4` доступны по RS485 (`protocol-485.md`).
- `ParallelBattery (0x62)` возвращает 40 Б (при одиночном устройстве — нули).
- **Серийного номера в чтении нет:** рекламный пакет пуст (нет manufacturer/service data,
  только `ff00`), сервис Device Information (`180A`/`2A25`) не выставляется, `GetSN (0xA2)` и
  `GetBatSN (0xA4)` ответа не дают. Идентификация — только по BLE-MAC (`28:xx:xx:xx:xx:xx`).
- **Характеристика `ff04` читаемая** и отдаёт последнюю записанную команду (кэш): при опросе
  содержала `7e 10 00 46 51 00 00 8c 96 1a` — кадр BasicInfo, но с хвостом **`0x1A`** и иной
  контрольной суммой, чем наши кадры (`0x0D`/`3a 7f`). Т.е. хвост `0x1A` в asm `getSendMsg`
  не «мёртвый»: им пользуется какой-то вариант ПО/клиента. Плата принимает оба (`0x0D` и, видимо, `0x1A`).

### 2.1. Хвост `parseBody_Battery` (0x61) — точная раскладка (2026-10-01)

- Функция `parseBody_Battery` (`BmsMsgUtil.dart`, `0x3f3a18`, size `0x20f4`);
  порядок имён полей — из `toJson` (`0x3def6c`), см. `protocol-BLE.md` §5.1.1.
- После `portvoltage` идёт 39-байтный хвост: список `batterynum`(=16) байт, затем
  список `tempnum−2`(=4) байт, затем 3 одиночных warn-байта, скаляры и блоки
  состояний (см. таблицу в PROTOCOL §5.1.1).
- Живой кадр: warn-область (смещения 0…23) **нулевая**; ненулевые `01 03 08`
  на смещениях 25…27 — это статусы (ключи/баланс/режим), не аварии.
- Грабли: попытка декодировать аварии из `Ext_Bit` XML `teleSignal_Group`
  (смещение tail[24:38]) даёт ложные Warn/Protect — ошибочно.
- blutter-дамп лежит в `/tmp/kilo/bms_out` (**в /tmp — не переживёт перезагрузку**;
  при утере пересобрать blutter'ом).

## 3. Живой BLE-опрос и HCI-дамп

Документ фиксирует результаты **реального опроса** BMS по Bluetooth через сервер
`192.168.x.x` (Ubuntu, BlueZ), полученные 2026-09-28. Дополняет
`REVERSE_ENGINEERING.md (раздел 2)` (реверс из APK `libapp.so`, приложение EN BMS 1.1.4)
сверкой с работающим устройством.

Все операции выполнены **только чтение/запись BLE-характеристик**.
Правило: **BT-адаптер не трогать** (никаких `systemctl restart bluetooth`,
`hciconfig reset/up`, `btmgmt power`, очистки сопряжений и т.п.) —
только пассивное сканирование и подключение уже к рекламирующимся устройствам.

### 1. Поиск устройства

Сканированием с сервера обнаружено единственное устройство BMS:

| Параметр | Значение |
|---|---|
| MAC (public) | `28:xx:xx:xx:xx:xx` |
| Имя (local name) | **`BP00`** |
| UUID сервиса | `0000ff00-0000-1000-8000-00805f9b34fb` |
| RSSI | −88 … −102 dBm (слабый, устройство вне стабильного радиуса) |
| Paired / Connected | нет / нет (на момент осмотра) |

Дополнительно в эфире: группа `22:DD:65:..` (`BMS-ANT22AAUB-0001/0002`,
`ANT-BLE22AAUB-0001/0002`) — это **НЕ** наша BMS (нет сервиса `0000ff00`),
а также CE308/CE208 (принтеры), MacBook, прочие устройства.

> ВАЖНО: `BP00` **не рекламируется постоянно** — появляется периодически
> и уходит. Попытка подключения в момент отсутствия даёт `Device not available`
> / `NOT FOUND`.

### 2. GATT-характеристики сервиса `0000ff00`

Реальные свойства характеристик (из `bluetoothctl info` / bleak `client.services`):

| Характеристика | Properties | Наблюдаемое поведение |
|---|---|---|
| `0000ff01-…` | notyfy | подписка ок, но **данных не приходит** |
| `0000ff02-…` | write / write-without-response | **канал записи команд** (работает) |
| `0000ff03-…` | write / write-without-response / notify | **рабочий канал ответов** (notify приходит сюда) |
| `0000ff04-…` | read / write / notify | **эхо** записанного кадра (возвращает отправленный кадр) |

#### Расхождение с `REVERSE_ENGINEERING.md (раздел 2)`

В документе (`:20-23`) указано: сервис `ff00`, запись `ff01`, уведомления `ff02`.
Реально:

- **notify-канал ответа = `ff03`**, а не `ff02`;
- `ff01` — только notify, но без данных;
- `ff02` — запись (совпадает по смыслу с «write»);
- `ff04` — read/write/notify, отдаёт эхо отправленного кадра.

Итог по ролям (проверено на устройстве): **писать в `ff02`, слушать на `ff03`**.

### 3. Отправляемые команды (формат кадра)

Кадр (отправка) — как в документе:
`7E 10 <addr> 46 <cmd1> <len:u16be> <payload> <crc:u16be> 1A`

CRC-16/CCITT (полином `0x1021`, init `0`, big-endian) — подтверждено по
`getSendMsg` (`0x3d0c58`, `0x3d0cb0`) и сверено (совпадает с документом).

Проверенные кадры (addr = 0):

```
BasicInfo (0x51):      7e1000465100008c961a
Battery   (0x61):      7e10004661000100d9dc1a
ParallelBattery(0x62): 7e10004662000010631a
ReadBMSParams (0x47):  7e10004647000100c90b1a
```

> ПРИМЕЧАНИЕ: в одном из промежуточных скриптов была ошибка маски CRC
> (`& 0x1fff` вместо `& 0xffff`), из-за чего там CRC получался заниженным
> (например `..0c961a`, `..19dc1a` вместо `..8c961a`, `..d9dc1a`).
> Корректные значения — с маской `0xffff` (приведены выше).

### 4. Ответы устройства

При подключении и после команд на `ff03` приходят короткие пакеты:

```
при подключении:       020202   010a
после любой команды:   0101
```

`0101` приходит **на все команды** (BasicInfo / Battery / ParallelBattery /
ReadBMSParams) — выглядит как **статус/ACK**, а **не** данные телеметрии.

### 5. Разбор ответа в приложении (`parseBody_Msg`, 0x3f6524)

Из декомпиляции `BmsMsgUtil.dart` (0x3f6524), подтверждено вживую, что
приложение НЕ рассматривает `0101` как данные — проверки:

- длина тела ответа `len + 7`;
- **`CRC` кадра** = `body[len-3] << 8 | body[len-2]` (два предпоследних байта);
- **последний байт** `body[len-1]` (поле `field_47`) должен быть **`0x0D`**;
- допустимо, если `field_47 == 0x0D && crc16(без 3 последних байт) == CRC`.

#### Расхождение по хвосту кадра

- **Отправка** (getSendMsg, `0x3d0e40`): хвост кадра = **`0x1A`**.
- **Приём/проверка** (parseBody_Msg, `0x3f69d0`): хвост должен быть **`0x0D`**.

То есть tail `0x1A` установлен только на отправку, а на приёме ожидается
`0x0D` (либо это раздельные протокольные константы).

### 6. Решение (заменяет разделы 5–7)

Полный ответный кадр получен. Рабочие параметры: канал ответов — notify **`ff01`**
(write `ff02`), хвост `0x0D`, CRC-16/CCITT по `frame[1:-3]`, `addr` в ответе `0x14`.
Детали и живой трафик — в §10.

### 10. ПОДТВЕРЖДЕНО HCI-snoop-дампом с телефона (2026-09-30)

> Раздел 10 **заменяет** выводы разделов 5–7 там, где есть расхождения.
> Источник — реальный HCI-дамп с телефона IIIIF150 B3 (Android 14) через
> `adb bugreport` → `btsnoop_hci.log` (папка `./btlogs/`). Полный живой
> трафик приложения EN BMS: подключение, чтение (BasicInfo/Battery/
> ReadBMSParams) и **две операции записи** (команда `0xA1`).

#### 10.1. Реальные роли характеристик (по handle)

| Handle | UUID | Роль | Направление |
|---|---|---|---|
| `0x0011` | `ff01` | **notify** | BMS → приложение (ответы) |
| `0x0014` | `ff02` | **write** | приложение → BMS (команды) |

Приложение **пишет в `ff02` (handle `0x0014`)** и **получает ответы по
notify `ff01` (handle `0x0011`)**. Это совпадает с исходником
(`writeCharacteristicUUID=ff02`, `notifyCharacteristicUUID=ff01`).

> ⚠️ В разделе 2 ошибочно указано слушать `ff03`. Правильный канал ответов —
> **`ff01`**. `ff03`/`ff04` приложением не используются.

#### 10.2. Реальный формат кадра (подтверждён обе стороны)

Запрос (приложение → BMS):
```
7E | 10 | 00 | 46 | <cmd1> | <len:u16be> | <payload> | <crc:u16be> | 0D
```
Ответ (BMS → приложение):
```
7E | 14 | 00 | <cmd1> | <len:u16be> | <payload> | <crc:u16be> | 0D
```

Отличия от `REVERSE_ENGINEERING.md (раздел 2)` — **критичны**:

| Параметр | Документ | Реально (дамп) |
|---|---|---|
| хвост кадра (tail) | `0x1A` | **`0x0D`** (в обе стороны) |
| CRC-диапазон | «заголовок+payload» (открытый вопрос) | **всё, кроме первого байта `0x7E`** |
| `addr` в ответе | — | **`0x14`** (20) — идентификатор пакета/устройства |
| канал ответов | `ff02` | **`ff01`** |

**CRC — точная формула:** CRC-16/CCITT (полином `0x1021`, init `0`, без
отражения, big-endian) по байтам кадра **начиная со второго** (fix `0x10`),
исключая ведущий `0x7E`. Проверено на трёх кадрах:

| команда | кадр (hex) | CRC в кадре | CRC по формуле |
|---|---|---|---|
| BasicInfo `0x51` | `7e100046510000` | `3a7f` | `3a7f` ✅ |
| Battery `0x61` | `7e10004661000100` | `f7c1` | `f7c1` ✅ |
| ReadBMSParams `0x47` | `7e10004647000100` | `e716` | `e716` ✅ |

> Именно поэтому наши ручные кадры (`…8c961a`, `…d9dc1a`) не совпадали и
> устройство отвечало только `0101`: были неверны и CRC (считался от `7E`),
> и tail (`1A` вместо `0D`), и канал прослушивания.

#### 10.3. Наблюдённые команды и ответы

**Запросы (write в `ff02`):**
```
BasicInfo      7e1000465100003a7f0d
Battery        7e10004661000100f7c10d
ReadBMSParams  7e10004647000100e7160d
Запись (0xA1)  7e100046a100a9<169 байт payload><crc>0d
```

**Ответы (notify `ff01`, addr=`0x14`):**
- `BasicInfo (0x51)` — ASCII-строка конфигурации:
  `7e140051000024 43414e3a504e475f4459455f4c7578705f544242313130312d584f313720...`
  payload = `CAN:PN_G_DYE_Luxp_TBB1101-XO17` + служебные байты
  (`10 06 01 01 46 00 …`) — **имя/код протокола инвертора** (см. `PN_GDLT`,
  Deye/Luxpower/TBB из раздела 11 datasheet).
- `Battery (0x61)` — большой кадр телеметрии (напряжения ячеек и пр.),
  приходит **несколькими notify-фрагментами** (MTU), напр.
  `7e14006100006a0000100cbf0cbd…` (len=`0x006a`=106).
- `ReadBMSParams (0x47)` — ответ len=`0x00a9` (169), `7e1400470000a9003c0d…`.
- **ACK на запись**: `7e1400a100000080e70d`.

#### 10.4. Две операции записи

Обе операции — команда **`0xA1`** (в `REVERSE_ENGINEERING.md (раздел 2)` не описана):
```
7e 10 00 46 a1 00 a9 <payload 169 байт> <crc> 0d
```
Payload у двух записей почти идентичен; различается байтами состояния
(в одном — `…0d b6…`, в другом — `…0d ac…`) и CRC. BMS отвечает ACK
`7e1400a100000080e70d`. Похоже, `0xA1` = запись параметров/команд управления
(сравнить с `writeBMSParams`/switch-командами из реверса APK).

#### 10.5. Важное про приём ответов

Ответы **фрагментированы** на несколько ATT-нотификаций (ограничение MTU).
Пример Battery: 4 последовательных notify:
`7e14006100006a…` + `…` + `…` + `…95cb0d`. Их нужно **склеивать** в буфер
до появления полного кадра (`7E … 0D`), как `msgQueue` в приложении.

### 8. Инфраструктура опроса

- **Сервер**: `192.168.x.x`, root (пароль — в связке ключей, правило см.
  `AGENTS.md`).
- **BT-контроллер**: Realtek BT 5.0 USB (`RTK_BT_5.0`, HCI 5.1), интерфейс
  `hci0`/`hci1` (переиндексируется), powered + LE.
- bluez: `bluetoothctl`, есть `gatttool`, python `bleak` 3.0.2 (с ним работаем).
- **ВАЖНО (инфраструктура)**: пароль для SSH через `background_process`
  не передаётся (`secret-tool` там отдаёт пустую строку → SSH `Permission
  denied`). Рабочее решение — длинный блокирующий `bash`-вызов с
  `secret-tool lookup` в том же процессе (не `background_process`), либо
  файл пароля вне `.kilo/`.
- Скрипты опроса: `/tmp/ble_scan_connect.py`, `/tmp/ble_accum.py` (лежат на
  сервере в `/tmp`).

### 9. Чек-лист сверки с документом (что по итогам подтверждено / опровергнуто)

Обновлено после разбора HCI-дампа (раздел 10):

| Утверждение `REVERSE_ENGINEERING.md (раздел 2)` | Статус (по дампу) |
|---|---|
| Сервис GATT `0000ff00` | ✅ подтверждено |
| Запись `ff01` / уведомления `ff02` | ❌ иначе: **запись `ff02` (handle 0x14), ответы `ff01` (handle 0x11)** |
| Кадр `7E 10 addr 46 cmd1 len crc 1A` | ⚠️ структура верна, но **tail = `0x0D`**, а не `0x1A` |
| CRC-16/CCITT `0x1021`, init 0, big-endian | ⚠️ полином/порядок верны, но **CRC считается БЕЗ ведущего `0x7E`** |
| Команды `0x51/0x61/0x62/0x47/0x63` | ✅ подтверждены; плюс обнаружена команда **`0xA1`** (запись) |
| Поле `addr` = 0 в запросе | ✅ так и есть; в ответе байт 2 = `0x00` (эхо ADR). **Байт 1 ответа = `0x14`, а не ADR**, и после `CID2` идёт байт `RTN` (`00`) — уточнено живым захватом (см. §11.1 и `protocol-BLE.md` §3.1) |

### 11. Углублённый разбор кадров (декодирование payload)

Кадры пересобраны из notify-фрагментов (склейка по полю длины) и проверены
по CRC — все валидны.

#### 11.1. `BasicInfo` (`0x51`), ответ, len = 36
```
7e 14 00 51 00 00 24 | 43 41 4e 3a 50 4e 47 5f 44 59 45 5f 4c 75 78 70 5f
                       54 42 42 31 31 30 31 2d 58 4f 31 37 20 10 06 01 01 46 00 | b7 45 | 0d
```
> Заголовок ответа: `7E 14 ADR CID2 RTN LEN(2)`; здесь `RTN = 00` (ранее в записи
> пропущен). Длина = `10 + LENID = 46`. CRC `b7 45` совпадает с живым захватом.
payload (ASCII): **`CAN:PNG_DYE_Luxp_TBB1101-XO17`** + хвостовые байты
(`20 10 06 01 01 46 00`) — имя активного протокола инвертора (CAN) и
доп. флаги. См. раздел 12 (`PN-GDLT`).

#### 11.2. `Battery` (`0x61`), ответ, len = 106
Структура payload:
| смещение | размер | поле |
|---|---|---|
| 0 | 3 | заголовок (`00 00 10`) |
| 3 | 32 | **16 напряжений ячеек**, `u16be`, мВ (0x0CBF = 3263) |
| 35 | 1 | = `06` (число термодатчиков) |
| 36 | 12 | **6 температур**, `u16be`, ед. 0.1 K, офсет −2731 (2985 → 25.4 °C) |
| 48 | … | ток, SOC/SOH, ёмкость, статусы/защиты (остаток 58 байт) |

Факт: данный пак — **16S** (16 ячеек ~3.26 В), т.е. 48/51.2 В, хотя модель
в даташите помечена как «24V» (EMU1101 поддерживает 8–16S). Приходит
**несколькими notify-фрагментами** (MTU), их надо склеивать.

#### 11.2a. Сверка с декомпиляцией APK (`parseBody_*`)

Payload'ы декодируются не «на глаз», а штатными парсерами приложения
(`BmsMsgUtil.dart`, blutter-дамп `/tmp/kilo/bms_out/asm/...`):

- `parseBody_BasicInfo` (0x3f610c) → `Bms_Basicinfo_Model` (0x34);
- `parseBody_Battery` (0x3f3a18) → **`Bms_Recv_Model`** (0xd0 = 208 Б);
- `parseBody_PackParams` (0x3e91b8) → `Bms_PackParamter_Model`;
- `parseBody_ParallelBattery`, `parseBody_WriteBMSParams`.

**Масштабы из `parseBody_Battery`**: используются `0.001`, `0.1`, `0.01`.
`0.001` применяется к напряжениям ячеек → **мВ/1000 = В** (совпадает с нашим
разбором: 0x0CBF=3263 мВ → 3.263 В). Остальные поля Recv-модели масштабируются
`0.1` / `0.01` (токи/ёмкости/температуры). Парсер читает payload
последовательно в набор полей (`field_b, field_f, field_13, field_1b, 1f,
23, 27, 2b … c7`); полная по-полевая карта Recv-модели требует трассировки
цикла ячеек в asm.

#### 11.3. `ReadBMSParams` (`0x47`) / запись `0xA1`, len = 169
`0x47` читает, `0xA1` пишет тот же блок 169 байт (payload записи = байт `0x00`
+ прочитанный блок с изменённым значением). Это **блок параметров/настроек**
(пороги защит, конфигурация). В обеих записях (f548/f554) отличается один
байт — именно та настройка, которую меняли через приложение. BMS отвечает ACK
`7e1400a100000080e70d`.

### 12. Производитель и сопоставление с открытыми источниками (OSINT, 2026-09-30)

Метод: веб-поиск (Brave/DuckDuckGo/Bing), GitHub (репозитории), сайт
производителя. DuckDuckGo/Google/Yandex/Ecosia/Marginalia блокировали бота;
рабочие — **Brave** и **GitHub repositories**.

#### 12.1. Производитель и модель (подтверждено официальным сайтом)

- **Shanghai Energy Electronic Technology Co., Ltd.** / 上海恩阶电子科技有限公司
  (бренд **Enjie** / EN / **N ENERGY**), сайты: `cnshenergy.com` (EN),
  `energyborn.com` (中文), `enjiebms.com`.
- Продукт — **EMU1101 V16 Smart BMS**: 8S–16S, 24–51.2 В, 100/150/200/300 A,
  LFP/NCM/LTO, CAN/RS485, **Bluetooth/WiFi — опция**. На странице продукта
  лежит ровно наш даташит `emu1101-…-10e-08s-v1-0-en.pdf`.
- Семейство: EMU1101 (LV), EMU1102 (LTO/Na-ion), EMU1103(D), серия 1202/1203/
  1204/1205 (12V), HV BCU/BMU EHVS500.
- Совпадает с реверсом APK (`REVERSE_ENGINEERING.md (раздел 4)`): бренд N ENERGY,
  上海恩阶, ICP 沪ICP备2021016577号-2A, `wxcrm.vsites.cn` и т.д.

#### 12.2. Роль Bluetooth-модуля и «верхнего» протокола

- Официальный **BT2 module** (`bt2-module-product-specification-en.pdf`) —
  это BLE-адаптер, который подключается к **UART/LCD-порту** платы EMU1101
  (пины GND/TX/RX/3.3V) и **мостит BLE ↔ внутренний UART-протокол BMS**.
  Отсюда: кадры `7E … 0D`, которые мы сняли по BLE, — это **внутренний
  «host/upper-computer» протокол** платы, а не отдельный BLE-протокол.
- Тот же протокол плата отдаёт по **RS485** для ПО «Upper Computer»
  (`upper-computer-download.rar`, есть на сайте) и по WiFi-stick (Tuya,
  spec `TSW-T111`), который тоже общается по RS485 (baud **9600/19200**).
- Вывод: через BLE (BT2) и через RS485 «верхний компьютер» видит **одни и
  те же кадры** `7E 10 … 46 <cmd> … CRC 0D`. Это фирменный протокол Enjie.

#### 12.3. Протоколы инверторов (из раздела 11 даташита и сайта)

- Строка из `BasicInfo` — **`CAN:PNG_DYE_Luxp_TBB1101-XO17`**. Поиск
  подтвердил: **`PN-GDLT`** — это CAN-протокол, применяемый для
  **Luxpower/Deye/Sol-Ark/Growatt/Sunsynk** и совместимый с Pylontech
  (в списках протоколов: «Luxpower or PN-GDLT», «switch to PN-GDLT»).
- Даташит перечисляет ~40 инверторных протоколов (Goodwe, Solis, Sungrow,
  Pylontech/PYLON, Growatt, Deye, Victron, SMA …) — переключение через
  «верхний компьютер».

#### 12.4. Сравнение с известными открытыми протоколами BMS

| BMS/семейство | Транспорт/фрейминг | Наш EMU1101 (Enjie) |
|---|---|---|
| **Pylontech** LV (популярный «PYLON»/`PN-GDLT`) | CAN 500k, ID `0x351,0x355,0x356,0x359,0x35C,0x35E` | Использует его как **исходящий** к инвертору (строка протокола) |
| **Seplos / PACE** (в дат. упомянут для `srne`) | **Modbus-RTU**, 19200 8N1, блоки PIA/PIB/PIC/SPA/SFA/SCA | Совпадает по *набору* (телеметрия + блок параметров ~0x6A/0xA9), но **фрейминг иной** |
| JBD / Xiaoxiang | UART, старт `0xDD` | иное |
| JK BMS | UART/BLE, `0x55 0xAA` | иное |
| Daly | UART, `0xA5` | иное |
| **Наш BLE/UART** | `7E | 10/14 | … | 46 <cmd> | len | payload | CRC16-CCITT | 0D` | фирменный; в открытых источниках **точного описания нет** |

Ключевое: наш кадровый протокол — **не** Modbus и не совпадает с публичными
JBD/JK/Daly; это **собственный формат Enjie**. Его структурно близкие соседи —
«блочные» протоколы Seplos/PACE (чтение телеметрии + отдельный блок
настроек), но синтаксис отличается. Публичного описания именно кадров
`7E…0D`/`0x46` в открытых источниках не найдено — реверс уникален.

#### 12.5. Полезные первоисточники (найдены)

- `cnshenergy.com/downloads/` — все даташиты (EMU1101/1102/1103, 12V, HV,
  LCD, активные балансиры).
- `cnshenergy.com/software-download/` — ПО: ENBMS Android/iOS, BMS BW/CW,
  **Upper Computer** (RS485 host).
- `cnshenergy.com/uploads/file/20250427/bt2-module-product-specification-en.pdf`
  — Bluetooth-модуль BT2.
- `…/specification-for-connecting-wifi-stick-and-bmsv1-0-en.pdf` — WiFi-stick.
- `cnshenergy.com/uploads/Types-of-Inverter-Protocols-1.pdf` — список
  инверторных протоколов (индексируется поиском; прямой URL отдаёт 404).
- GitHub: `ai-republic/bms-to-inverter` (много BMS/инвертор-биндингов),
  `marcelrv/seplosBMSv3` (Seplos/PACE Modbus), `ul-gh/pylon_bms_diagnostics`
  (Pylontech CAN).

#### 12.6. Что осталось неизвестным

- Полная карта полей блока `0x47`/`0xA1` (169 байт) — пороги/настройки.
- Остаток payload `0x61` (ток, SOC/SOH, флаги защит) — смещения.
- Точные значения `addr` при обращении к конкретному модулю в параллельной
  сборке (в дампе addr запроса = 0, ответа = `0x14`).
- Возможен язык команд «верхнего компьютера» (в ПО Upper Computer) — при
  необходимости можно установить и снять его трафик по RS485.

### 13. НАЙДЕНО точное описание протокола (ПО «Upper Computer», 2026-09-30)

Выполнен повторный поиск в открытых источниках и найден **первоисточник**:
официальное ПО Enjie «Upper Computer» (`BatteryMonitor V2.1.13`,
`cnshenergy.com/software-download/`). Внутри — `Agreement/*.xml` (карты протокола,
`protocolName=BMS-16S`, `protocolVersion=2.0`) и реализация `BatteryMonitor.exe`.
Подробный разбор — в `protocol-BLE.md`, копия карты — `16S_V20_ADDR_EN.xml`.

#### 13.1. Семейство (ответ на «похожие протоколы»)

Кадр Enjie `7E | 10 | ADR | 46 | CID2 | LEN(2) | INFO | CHKSUM(2) | 0D` — это
**бинарный вариант семейства «CID»** (`SOI=0x7E`, `CID1=0x46`, `EOI=0x0D`),
корень которого — китайский стандарт **YD/T 1363**. К этому же семейству
относятся публично описанные:

- **Pylontech RS-485** и **PACE / PbmsTools** (ASCII-hex вариант той же
  структуры: `CID1=0x4A/0x46`, `CHKSUM` = 16-битная сумма-дополнение);
- **Gobel Power «RN BMS»** (`fancyui/Gobel-Power-RN-BMS-RS485-ModBus`) —
  **бинарный** V1.0: `SOI`, `VER=0x10`, `CID1=0x46`, `CID2`, `LENGTH`, `INFO`,
  `CHKSUM`, `EOI=0x0D` — ближайший структурный аналог протокола Enjie;
- Daren, Maiyou и др. «PACE-совместимые» (DIY Solar Forum, GitHub `syssi/esphome-pace-bms`,
  `nkinnan/esphome-pace-bms`).

#### 13.2. Что даёт первоисточник

- Полный формат кадра, коды `CID2`, алгоритмы `LCHKSUM` и `CHKSUM`
  (разобраны из IL `DataFrame.getLengthCRC` / `getFrameCRC`).
- Карта телеметрии (CID2=0x42), битовые защиты (0x44), блок параметров
  (0x47 чтение / 0xA1 запись): пороги, защиты, калибровка — см. §4–7
  в `protocol-BLE.md`.
- Список CAN-протоколов инвертора (PN-GDLT, Growatt, Victron, SMA/SOFAR,
  Solis, Studer, MUST).

#### 13.3. Открытое расхождение

Контрольная сумма: по `BatteryMonitor.exe` это **16-битная сумма-дополнение**
(YD/T 1363), а снятые BLE-кадры приложения EN BMS 1.1.4 сходятся с
**CRC-16/CCITT** (`3a7f/f7c1/e716`). Требуется проверка на живом RS-485:
какой контроль реально требует плата (возможны разные ревизии протокола).

## 4. Анализ APK EN BMS 1.1.4 (манифест, OSINT, безопасность)

Дата анализа: 2026-09-28. Машина: `<host>`.
Исходный файл: `/home/<user>/Загрузки/BMS_1.1.4.apk`.

### Краткий итог

Штатное Android-приложение (Flutter) китайской разработки для управления
аккумуляторной батареей (BMS — Battery Management System) по Bluetooth Low
Energy. Бренд — логотип «N ENERGY» (`assets/.../bmslogo.png`).

Это **не опубликованная сборка**: package name шаблонный `com.example.*`,
подпись — Android Debug. Вредоносных признаков не найдено, но из-за отладочной
подписи и разрешённого открытого HTTP трафика доверять файлу из случайного
источника не следует.

### Файл

| Параметр | Значение |
|---|---|
| Имя | `BMS_1.1.4.apk` |
| Размер | 34 048 427 байт (≈32.5 МиБ) |
| Тип | Android package (APK), zipflinger |
| Дата файла | 2026-09-28 21:33:35 +03:00 |
| Записей в архиве | 122 |
| SHA-256 | `584230df7c222f2c8ac445599caec9757ad9e6b218dc1a7e3079fb8570273c21` |
| MD5 | `0fc75efdbc3a6f2005e9209b966b3dc6` |

### Сборка и подпись

- Путь сборки (из бинарника `libapp.so`):
  `file:///E:/ENBMS/ENBMSPGY/bms_flutter/.dart_tool/flutter_build/dart_plugin_registrant.dart`
  — Windows-машина разработчика, проект `bms_flutter`, каталог `ENBMS`.
- Package name: `com.example.bms_flutter` (шаблонный `com.example`).
- versionName `1.1.4`, versionCode `1`, minSdk 19, targetSdk 31, compileSdk 32,
  codename 12.
- Подпись: `CN=Android Debug, O=Android, C=US`, серийный номер `1`,
  действительна 2024-03-26 … 2054-03-19, алгоритм **SHA1withRSA** (слабая,
  отладочная).
  - SHA-1 отпечаток: `<ssh-fingerprint>`
  - SHA-256 отпечаток: `<ssh-fingerprint>`

### Технологии

- Flutter / Dart (AOT-компиляция), нативные библиотеки:
  `lib/{arm64-v8a,armeabi-v7a,x86_64}/libflutter.so` и `libapp.so`.
- Kotlin/Java: `classes.dex` (~7.6 МБ, ~1081 класс), в основном обвязка Flutter.
- Android `MainActivity`: `com.example.bms_flutter.MainActivity`, `exported=true`,
  запуск с `LAUNCHER`.

Dart-пакеты (ключевые):

- `flutter_blue_plus` — Bluetooth Low Energy (связь с батареей по BLE)
- `dio`, `http_parser` — HTTP-клиент
- `webview_flutter` + собственный JS-мост (`ezfast_flutter_base`) — WebView
  со взаимным вызовом JS ↔ native
- `shared_preferences`, `path_provider`, `package_info_plus`,
  `device_info_plus`, `get`, `flutter_screenutil`, `bot_toast`, `gif_view`,
  `protobuf`, `rxdart`

### Функциональность (по строкам бинарника)

- Вход по логину/паролю (`app_login_page`, `HINT_INPUT_PASSWORD`,
  `LOGIN_HINT_ACCOUNT_PASSWORD_INCORRECT`).
- Поиск и подключение устройства по BLE (`flutterblueplus.proto`,
  `androidAutoConnect`, `BluetoothDevice/Service/Characteristic`).
- Страницы устройства: `device_index_page`, `device_detail_page`,
  `device_info_page`, `device_alarm_page`, `device_protection_page`,
  `device_setting_param_page`, `device_setting_switch_page`.
- Пароль настройки/«CAN verify password» (`SetSpPassword`,
  `DEVICE_INFO_CAN_VERIFY_PASSWORD`).
- Телеметрия BMS: напряжение/ток/заряд (SOC), температуры, ячейки, MOS,
  предупреждения и защиты (напр. «Battery over voltage protection»,
  «Ambient high temperature warning», «Battery low voltage charging prohibited»).
- Многоязычный интерфейс (`app_language`, `Locale`, локализация).

### Разрешения (`AndroidManifest.xml`)

`INTERNET`, `CAMERA`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`,
`BLUETOOTH` / `BLUETOOTH_ADMIN` (только до Android 11, `maxSdkVersion=30`),
`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `ACCESS_FINE_LOCATION`,
`ACCESS_COARSE_LOCATION`.

### Сеть (жёстко зашитые адреса в `libapp.so`)

- `https://wxcrm.vsites.cn/enbmsapi/config` — конфиг/API.
- `http://kyplatform.vsites.cn/kyplatform/bms/saveLog` — **отправка логов по
  открытому HTTP**.
- `https://enagreement-1318815394.cos.ap-shanghai.myqcloud.com/agreement.html`
  — пользовательское соглашение.
- `https://enprivacy-1318815394.cos.ap-shanghai.myqcloud.com/privacy.html`
  — политика конфиденциальности.
- `https://www.baidu.com/`, `https://iconfont.alicdn.com/...` — служебные.

### Углублённый разбор (apktool / aapt, 2026-09-28)

После установки `apktool` и `aapt` сделан полный разбор
(`apktool d -f -o /tmp/kilo/bms_full`, `aapt dump badging|permissions|xmltree`).
Дополнительно к первичному анализу выяснено:

**Манифест (декодирован apktool)** — детали, невидимые в сырых строках:
- `android.permission.BLUETOOTH_SCAN` объявлен с
  `usesPermissionFlags="neverForLocation"` (0x10000) — приложение заявляет,
  что результаты BLE-сканирования не используются для определения геолокации;
  при этом `ACCESS_FINE_LOCATION` всё равно запрошен (нужен для BLE на Android
  ≤ 11).
- `MainActivity`: `launchMode="singleTop"`, `exported=true`,
  `windowSoftInputMode="adjustResize"`, тема `@style/LaunchTheme`.
- `application`: `appComponentFactory=androidx.core.app.CoreComponentFactory`,
  `icon=@mipmap/ic_launcher`, `label="BMS"`,
  `networkSecurityConfig=@xml/network_security_config`.
- Собственного нативного кода нет: `MainActivity.smali` — стандартный
  `FlutterActivity` (только пустой конструктор).
- Поддерживаемые ABI: `arm64-v8a`, `armeabi-v7a`, `x86_64`.
- 85 локалей (в основном переводы AndroidX; метка приложения везде `BMS`).

**Нативные плагины (по smali в `classes.dex`)** — Android-часть:
`com.boskokg.flutter_blue_plus`, `com.tekartik.sqflite` (в `libapp.so`
не используется — вероятно, транзитивный/неиспользуемый),
`de.appgewaltig.disk_space`, `dev.fluttercommunity.plus.device_info`,
`dev.fluttercommunity.plus.packageinfo`, плюс `com.google.protobuf` и Guava.

**BLE-профиль (из `libapp.so`)**: GATT-сервис `0000ff00-0000-1000-8000-00805f9b34fb`,
характеристики `0000ff01-…` и `0000ff02-…` (запись/уведомления,
`writeCharacteristicUUID` / `notifyCharacteristicUUID`), стандартный CCCD
`00002902-…`. В APK лежит `unknown/flutterblueplus.proto` с моделью
AdvertisementData/ScanResult/BluetoothDevice и др.

**Протокол связи с батареей**: типы `PROTOCOL_CAN` и `PROTOCOL_485`
(«Inverter CAN»), перечисление `CMD_TYPE` — то есть BMS общается по CAN или
RS-485, а телефон — по BLE, с трансляцией команд.

### Модель устройства и протоколы мониторинга

#### Модель BMS

По коду (`BmsMsgUtil`, модели `Bms_Basicinfo_Model`, `Bms_PackParamter_Model`,
`Bms_ParallelBattery_Model`, `Bms_Recv_Model`, `COMMON_DEVICE_DETAIL_MODEL`)
и открытым данным — это **многопакетная (параллельная) батарейная система**
серии EN (бренд N ENERGY), платы типа «48100» (48 В / 100 А·ч, 16S).

Собираемые/отображаемые параметры пакета (`DEVICE_INFO_*`):

- состояние батареи: заряд (`BATSTATE_CHARGE`), float-заряд
  (`CHARGING_FLOAT`), разряд (`DISCHARGE`), ожидание (`STANDBY`), резерв
  (`RESERVER`), отключение (`SHUTDOWN`);
- `Battery_Capacity` (ёмкость), `Battery_type`, `Rated_Capacity`, `Number_of_cycles`,
  `Number_strings`, `Remaining_capacity`;
- `Port_voltage`, `Power_Temperature`, `Max/Min_Voltage`, `Max/Min_Temperature`;
- `Online_quantity`, `parallel_machines` — число параллельных модулей (并机);
- телеметрия по каждой ячейке / MOS и перечень защит и тревог
  (over/under voltage, over/under temperature, ток, и т.п.).

Возможности управления: чтение/запись параметров пакета, чтение данных
параллельного модуля, переключение линии связи CAN ↔ RS-485.

#### Транспорт (BLE) — слой между телефоном и адаптером BMS

- GATT-сервис `0000ff00-0000-1000-8000-00805f9b34fb`;
- характеристика записи `0000ff01-…` (`writeCharacteristicUUID`,
  `writeCharCode`), поддержка записи `writeWithoutResponse` (write-no-response);
- характеристика уведомлений `0000ff02-…` (`notifyCharacteristicUUID`)
  + стандартный CCCD `00002902-…`;
- телефо́н подключается к Bluetooth-адаптеру, который физически сидит на
  CAN/RS-485 шине батареи и транслирует команды.

#### Прикладной протокол (поверх BLE)

Запрос/ответ через команды `getCmd_*`:

- `getCmd_BasicInfo` — базовая информация устройства;
- `getCmd_Battery` — основные данные (SOC, напряжения, токи, температура);
- `getCmd_ParallelBattery` — данные параллельного модуля (`_buildDatasParallel`,
  `_getHanlderData_ParallelBattery`, `ParallelBatteryDataListener`);
- `getCmd_ReadBMSParams` / `getCmd_WriteBMSParams` — чтение/запись параметров
  пакета;
- `getCmd_SwitchCAN` — переключение на CAN (с подтверждением «CAN Verify
  Password» / «Success switching CAN», «Success switching 485»).

Целостность кадра — **CRC-16** (`get:_checkSum`, `crc_16`, строки `CRC Fail` /
`======CRC Fail`). Есть поле `CMD_TYPE` (тип команды) и `checkSum`. Точный
маппинг кадров (порядок байт/смещения) в статике недоступен — требуется
декодирование Dart-AOT.

#### Подчинённые полевые протоколы

- `PROTOCOL_CAN` (в т.ч. «Inverter CAN» — обмен с инвертором по CAN);
- `PROTOCOL_485` (RS-485, вероятно Modbus-RTU, учитывая CRC-16);
- переключение между ними — программное (команды `Success switching CAN/485`),
  что характерно для BMS-плат (например, общий CAN-протокол Pylontech/стандарт
  для инверторов + собственный RS-485).

**Ограничение**: логика приложения написана на Dart и скомпилирована AOT в
`lib/…/libapp.so`; ни `apktool`, ни `aapt` её не декомпилируют — они дают
только манифест, ресурсы и smali нативной обвязки. Для анализа Dart-логики
нужен отдельный инструмент (например, `blutter` для снапшота Dart AOT);
также `apktool` не покрывает восстановление исходного Dart-кода.

### Замечания по безопасности

1. **Разрешён весь cleartext-HTTP.** В `res/xml/network_security_config.xml`
   для `base-config` стоит `cleartextTrafficPermitted=true`. Любой незашифрованный
   трафик (в т.ч. `saveLog` по `http://`) не защищён.
2. **Отладочная подпись + `com.example`** — тестовая/внутренняя сборка, не
   официальный релиз; в таком APK подпись/обновление не гарантируют
   целостность и авторство.
3. **WebView с JS-мостом** (`ef_init_js_bridge.js`: каналы `EfWebViewJsBridgeChannel`,
   `EfWebViewJsLogChannel`) в сочетании с разрешённым cleartext расширяет
   поверхность атаки, если грузится внешний контент.
4. Отдельно упомянут домен `android.bugly.qq.com` (Tencent Bugly) в
   network-security-config; сам SDK Bugly в бинарнике не обнаружен.
5. Хардкод-секретов (ключи/токены/API-ключи) в ресурсах и `libapp.so` **не
   найдено**; явных рекламных/трекерных SDK тоже.
6. Разрешения камеры, геолокации и файлов — типичны для BLE-приложений, но
   стоит убедиться, что они не используются избыточно.

### Идентификация в открытых источниках (OSINT, 2026-09-28)

Приложение опознано по опубликованным версиям и связям в APK:

| Признак | Значение |
|---|---|
| Название в сторах | **EN BMS** |
| Android package (публичная версия) | `com.energybms.bms_flutter` |
| Наш файл | `com.example.bms_flutter` — отладочная/переименованная сборка той же программы |
| Android 1.1.1 (APKPure) | 2024-03-28, 19.2 МБ |
| iOS (App Store, id1661065493) | 1.1.2 — 2025-11-19; 1.1.1 — 2025-05-15; 1.1.0 — 2024-03-26 |
| Разработчик (Apple) | частное лицо (имя/ID не публикуем); у него же приложение **Higee** |
| Копирайт | © **上海恩阶电子科技有限公司** (Shanghai Enjie Electronic Technology Co., Ltd.) |
| ICP-备案 | **沪ICP备2021016577号-2A** (Шанхай) |
| Политика конфиденциальности | `https://wxcrm.vsites.cn/enbms/privacy.html` — домен `vsites.cn` совпадает с зашитым в APK |

Продукция компании (поиск по «上海恩阶»): плата защиты литиевых аккумуляторов
**«上海恩阶BMS 16串 锂电池保护板 48100-1101-1»** (48 В / 100 А·ч, 16
последовательных ячеек; Taobao «询价» = цена по запросу). То есть производитель —
BMS-плат для литиевых батарей.

Описание в сторах: «интеллектуальная система управления питанием» —
по Bluetooth управляет батарейным блоком, в реальном времени показывает
состояние и базовые параметры. Языки: китайский, английский, **вьетнамский**
(совпадает с `app_language`/`currentLanguageVn` в APK). По Apple Privacy Label
приложение собирает для «функций приложения» **номер телефона** (контактные
данные) — согласуется с входом по логину/паролю из `app_login_page`.

Связь с находками в бинарнике:
- `ENBMS` в пути сборки `E:/ENBMS/…` = «EN BMS» / «En Energy» (бренд **N ENERGY**,
  логотип `bmslogo.png`);
- серверы `wxcrm.vsites.cn` / `kyplatform.vsites.cn` — официальная облачная
  платформа (WeChat-CRM «wx-crm») этой же компании;
- BMS общается по CAN / RS-485, телефон — по BLE, сервис `0xFF00`.

Вывод OSINT: готовое коммерческое приложение китайской компании
Shanghai Enjie Electronics (бренд EN / N ENERGY). Наш `BMS_1.1.4.apk` —
**внутренняя отладочная сборка разработчика (новость версиями 1.1.1 в сторах),
подписанная debug-ключом**, скорее всего предоставлена напрямую производителем.

### Вывод и рекомендация

Это **EN BMS** — официальное приложение китайской компании
**上海恩阶电子科技有限公司** (Shanghai Enjie Electronic Technology Co., Ltd.,
бренд EN / N ENERGY) для мониторинга и настройки BMS-аккумулятора через
Bluetooth. Наш файл — **внутренняя отладочная сборка** (package `com.example`,
debug-подпись, версия 1.1.4 новее релиза 1.1.1), т.е. это разработческая копия,
а не сторонний/вредоносный модифицированный APK. Признаков вредоносности не
найдено; остаётся риск, связанный с разрешённым в конфиге открытым HTTP.

Рекомендации:
- уточнить источник файла; при необходимости проверить SHA-256 на VirusTotal;
- не устанавливать, если цель устройства — конфиденциальные данные;
- при установке ограничить сетевые разрешения и не вводить чужие учётные данные.

### Как воспроизвести анализ

```bash
## Базовое
file BMS_1.1.4.apk
sha256sum BMS_1.1.4.apk
md5sum BMS_1.1.4.apk
keytool -printcert -jarfile BMS_1.1.4.apk

## Распаковка
mkdir -p /tmp/kilo/bms && cd /tmp/kilo/bms
unzip -o /home/<user>/Загрузки/BMS_1.1.4.apk

## AndroidManifest.xml — бинарный AXML, разбирается скриптом /tmp/kilo/axml.py

## Строки и адреса
strings -n 8 lib/arm64-v8a/libapp.so \
  | grep -Eio 'https?://[^ "]+' | sort -u
strings lib/arm64-v8a/libapp.so | grep -Eo 'package:[a-z0-9_]+/'
```

Инструменты в системе: `unzip`, `keytool`, `file`, `strings`, `python3`.

Во время первичного разбора `apktool`/`aapt`/`jadx` отсутствовали — манифест
разобран собственным скриптом `axml.py`. 2026-09-28 доустановлены:

```bash
sudo apt-get install -y apktool aapt   # aapt 1:14~beta1-2build3, apktool 2.7.0
## проверка:
aapt dump badging BMS_1.1.4.apk
apktool d -s -f -o /tmp/apktest BMS_1.1.4.apk
```

`apktool` в системе распаковывает и ресурсы, и smali (`jadx` не ставился).

## 5. Разбор ПО «Upper Computer» (.NET) — первоисточник протокола

**Откуда:** `https://www.cnshenergy.com/uploads/file/20250427/upper-computer-download.rar`
(19 095 530 Б). Внутри — **вложенный** RAR:
`BatteryMonitor V2.1.13_NULL_VER_2025.rar` → каталог
`BatteryMonitor V2.1.13_20并_中性_20250111/`.

```bash
cd /tmp/kilo
curl -sL -o upper-computer.rar "https://www.cnshenergy.com/uploads/file/20250427/upper-computer-download.rar"
mkdir -p upper && unrar x -o+ upper-computer.rar upper/
unrar x -o+ "upper/05-Upper Computer Download/BatteryMonitor V2.1.13_NULL_VER_2025.rar" upper/out/
```

**Что внутри:**
- `Agreement/*.xml` — **карты протокола** по числу ячеек (`16S_V20_ADDR[_EN].xml`
  и др.); схема: `basicConfig`, `teleMeter_Group`, `teleControl_Group`,
  `teleSignal_Group`, `int_para_Group`, `bit_para_Group`, `adjust_para_Group`,
  `warnHistory`, `canProtocol`.
- `BatteryMonitor.exe` — .NET (PE32, Mono/.NET) — **реализация**.
- `Instruction/*.pdf` — инструкция (baud **19200**, логин/пароль веб-интерфейса — в `.kilo/`).

**Разбор XML:** `xml.etree.ElementTree`; таблицы полей (телеметрия, защиты,
параметры) сгенерированы скриптом прямо из XML → см. `protocol-BLE.md`.

**Разбор `BatteryMonitor.exe` (IL):**
- `monodis` (`mono-utils`) **падает с segfault** на полном дампе этой сборки;
  выборочные дампы работают: `monodis --typedef|--method|--fields|--constant`.
- Рабочий путь — Python `dnfile` + `dncil`
  (`pip install --user --break-system-packages dnfile dncil`).
- Скрипт: `dnfile.dnPE(path)` → найти `TypeDef` `BatteryMonitor.DataFrame`
  / `ProtocolCommand` / `StudioCtrl` / `MainWindow` / `ParaManageDialog`;
  для каждого метода взять `MethodDefRow.Rva` → `pe.get_offset_from_rva()` →
  срез `pe.__data__` → `dncil.cil.body.reader.read_method_body_from_bytes(data)`.
- Токены операндов резолвятся вручную: `token(0xTT00RRRR)` → table `TT`
  (0x04 Field, 0x06 MethodDef, 0x0A MemberRef, 0x70 UserString), `RID`.
- **Что извлекается:**
  - `ProtocolCommand..ctor` → коды `CID2` (`protocol-BLE.md` §4);
  - `DataFrame.getLengthCRC` → алгоритм `LCHKSUM`;
  - `DataFrame.getFrameCRC` → 16-битная сумма-дополнение;
  - `DataFrame..ctor` → сборка `INFO` (поля big-endian, `ByteNum` байт);
  - `MainWindow.Req*Frame`, `ParaManageDialog.Set*Frame`, `AdjustDialog.*`,
    `SNSettingDialog.*`, `RemoteScheduleDialog.*` → форматы payload
    чтения/записи (`protocol-BLE.md` §8.4).

**Прочие находки:** `canProtocol` Type 1..7 (PN-GDLT, GRWT, VCTR, SMA-SF,
GINL, STUD, MUST); 485-протокол самоадаптируемый.

### 5.1. IL-факты, добытые для RS485 (2026-10-04)

Дамп методов через `dnfile`+`dncil` (`ildump.py`; поле-таблица `Field=0x04`,
`Method=0x06` — иначе имена токенов путаются):

- `MainWindow.ReqParamFrame` строит `DataFrame(VER, CID2_GetAllParas=0x47, ADR=packIndex, INFO=[packIndex:1])`.
- `MainWindow.ReqTelemeterFrame` → `CID2_TeleMeter=0x42`; `ReqTeleStateFrame` → `0x44`.
- Последовательность опроса в `TreatRcvFrame`: после ответа `ProtocolVer (0x4F)`
  в очередь ставятся `ReqManufactureFrame (0x51)`, `ReqTeleStateFrame (0x44)`,
  `ReqTelemeterFrame (0x42)`.
- `getFrameCRC`: **сумма ASCII-кодов** символов от `VER` до конца `INFO`, затем
  дополнение до 0 (`((~Σ)&0xFFFF)+1`); `getLengthCRC`: `LCHKSUM<<12|LENID`.
- `GetReturnMessage`: таблица `RTN`: 0 Normal, 1 ProtocolVer, 2 DataCheck,
  3 LenCheck, **4 CommandNoSupport**, 5 DataFormat, 6 DataInvalid, 7 Address,
  8 Flash, 0x80..0xEF User, иначе Undefined.
- `TreatRcvFrame` TeleState: блок `Ext_Bit` (`NumFieldEnable=True`,
  `ByteNumAdjust=-1`) читается как `count−1` байт; наблюдён count `0x14` → 19 байт.
- `TreatRcvFrame` TeleMeter: последний блок `NumFieldEnable=True`, count `0x0A`=10
  полей × u16; в **EN**-карте 4 поля потеряны, в **CN** `16S_V20_ADDR.xml` они есть:
  `温漂电流` (×0.001 A), `零点电流` (×0.001 A), `充电能量`/`放电能量` (×0.1 кВт·ч).

Итог и подтверждение на живой RS485 — [`protocol-485.md`](protocol-485.md).

## 6. Узкие места, грабли и полезные приёмы

- **`monodis` segfault** на полной сборке → `dnfile`+`dncil` либо выборочные
  `monodis --таблица`.
- **PEP 668 (`externally-managed-environment`)** при `pip install` →
  `--break-system-packages` (или venv).
- **`secret-tool` в `background_process` отдаёт пустую строку** → SSH-пароль не
  проходит; использовать блокирующий `bash`-вызов с `secret-tool` в том же процессе.
- **`/tmp/kilo` не персистентен** — декомпиляция `bms_out`, распакованное ПО
  Upper Computer, скрипты исчезнут после перезагрузки; критичное копировать в репозиторий.
- **BLE: канал ответов.** Ранние пробы слушали `ff03` и получали только `0101`.
  Реально приложение пишет в **`ff02`**, слушает **`ff01`**; `ff03`/`ff04` не используются.
- **BLE-кадры фрагментируются** notify-ами по MTU — склеивать буфер до полного
  кадра `7E … 0D`.
- **`0x0D` может встречаться ВНУТРИ payload** (особенно `ReadBMSParams`) —
  собирать кадр **по длине** (`total = 10 + LENID`, где `LENID = bytes[5..6]`),
  а не по первому `0x0D`. Иначе кадр обрезается и CRC «не сходится».
- **Устройство `BP00` рекламируется непостоянно** — иначе `Device not available`.
- **Две контрольные суммы:** приложение — CRC-16/CCITT, ПО Upper Computer —
  сумма-дополнение (см. `protocol-BLE.md` §3.3, §11).
- **Адрес ответа** в HCI-дампе — `0x14`, в запросе — `0`.
- **Поисковики блокируют бота:** рабочие — **Brave** и **GitHub**; DuckDuckGo/
  Google/Yandex/Ecosia/Marginalia/Mojeek отдают капчу/429.
- **RAR вложенный** — распаковывать в два прохода (пакет `unrar`).
- **Dart-AOT** `apktool`/`aapt` не берут — нужен `blutter`.

## 7. Статус, инфраструктура и команды (архив)

Обновлено: 2026-09-30. Кратко: что сделано, что известно достоверно, что
делать дальше, какие инструменты/доступы нужны. Подробности — в
`REVERSE_ENGINEERING.md (раздел 2)` (реверс из APK), `REVERSE_ENGINEERING.md (раздел 4)` (анализ APK/OSINT),
`REVERSE_ENGINEERING.md (раздел 3)` (живой опрос + HCI-дамп + сопоставление).

### 1. Артефакты в репозитории

| Файл/папка | Что это |
|---|---|
| `REVERSE_ENGINEERING.md (раздел 2)` | Реверс кадров из `libapp.so` (формат, CRC, команды). Частично устарел — см. «расхождения». |
| `REVERSE_ENGINEERING.md (раздел 4)` | Анализ APK 1.1.4, OSINT производителя. |
| `REVERSE_ENGINEERING.md (раздел 3)` | **Самый полный и актуальный**: реальный протокол (HCI-дамп), декодирование payload, сопоставление с открытыми источниками. |
| `protocol-BLE.md` | **Первоисточник (производитель)**: протокол из ПО «Upper Computer» (`Agreement/*.xml` + `BatteryMonitor.exe`) — кадр, CID2, телеметрия, блок параметров. |
| `16S_V20_ADDR_EN.xml` | Копия карты протокола производителя (16S, EN). |
| `btlogs/` | HCI-snoop дампы с телефона (BTSnoop v1 / H4). В `.gitignore`. |
| `emu1101-…-v1-0-en.pdf` | Официальный datasheet. |
| `axml.py` | Вспомогательный парсер Android XML. |
| `/tmp/kilo/bms_out/asm/...` | Декомпиляция Dart-AOT (blutter) — **вне репозитория, может пропасть!** |

> ⚠️ Декомпиляция `bms_out` лежит в `/tmp` и не переживёт перезагрузку.
> При необходимости восстановить: `blutter` + APK (см. `REVERSE_ENGINEERING.md (раздел 4)`).

### 2. Достоверно установленный протокол (из HCI-дампа, см. FINDINGS §10–11)

#### Устройство
- BMS: имя **`BP00`**, MAC `28:xx:xx:xx:xx:xx`, GATT-сервис
  `0000ff00-0000-1000-8000-00805f9b34fb`.
- GATT (по handle): **write `ff02` (h=0x0014)**, **notify `ff01` (h=0x0011)**.
  (`ff03`/`ff04` приложением не используются.)
- Пак — **16S** (16 ячеек ×~3.26 В ⇒ 48/51.2 В).

#### Формат кадра
```
Запрос (app→BMS): 7E | 10 | 00 | 46 | <cmd1> | <len:u16be> | payload | <crc:u16be> | 0D
Ответ  (BMS→app): 7E | 14 | 00 | <cmd1> | <len:u16be> | payload | <crc:u16be> | 0D
```
- **tail = `0x0D`** (не `0x1A`!).
- **CRC-16/CCITT** (полином `0x1021`, init 0, big-endian) считается по кадру
  **без ведущего `0x7E`** (от `0x10`/`0x14`).
- В ответе `addr` = `0x14`; в запросе `addr` = `0`.
- Ответы приходят **фрагментами notify** (MTU) — склеивать по полю длины.

#### Команды (запросы)
```
BasicInfo       7e1000465100003a7f0d
Battery         7e10004661000100f7c10d
ReadBMSParams   7e10004647000100e7160d
Write 0xA1      7e100046a100a9<169B payload><crc>0d   (две операции записи)
```
ACK на запись: `7e1400a100000080e70d`.

#### Декодированные payload
- `BasicInfo (0x51)` → ASCII `CAN:PNG_DYE_Luxp_TBB1101-XO17` + байты.
- `Battery (0x61)` (106 Б): `00 00 10` + **16×u16be мВ** + `06` + **6×u16be temp**
  (0.1 K, офсет −2731 ⇒ 2985→25.4 °C) + ток/SOC/флаги.
- `ReadBMSParams (0x47)` / Write `0xA1` — блок параметров **169 Б**.
- Из APK (`parseBody_Battery`): модель `Bms_Recv_Model`, масштабы `0.001/0.1/0.01`;
  ячейки `мВ×0.001 = В`.

### 3. Расхождения: старый `REVERSE_ENGINEERING.md (раздел 2)` vs реальность

| Параметр | В старом документе | Реально |
|---|---|---|
| write / notify | `ff01` / `ff02` | **`ff02` (0x14) / `ff01` (0x11)** |
| tail кадра | `0x1A` | **`0x0D`** |
| CRC-диапазон | «заголовок+payload» (?) | **без ведущего `0x7E`** |
| `addr` | 0 | 0 в запросе, **`0x14` в ответе** |
| команды | 0x51/0x61/0x62/0x47/0x63 | + обнаружена **`0xA1`** (запись) |

→ При правках кода/доков использовать данные из `REVERSE_ENGINEERING.md (раздел 3)`.

### 4. Открытые задачи (для следующих сессий)

1. **Полная карта `Bms_Recv_Model` (0x61)**: по-полевое сопоставление
   offset→смысл (ток, SOC, ёмкость, флаги защит) трассировкой
   `parseBody_Battery` (0x3f3a18) в `BmsMsgUtil.dart`.
   → **Почти решено**: порядок и масштабы полей телеметрии есть в
   `protocol-BLE.md` §4 (CID2=0x42), битовые защиты — §6.
2. **Блок `Bms_PackParamter_Model` (0x47/0xA1, 169 Б)**: разобрать
   `parseBody_PackParams` (0x3e91b8), получить список настроек/порогов.
   → **Решено по составу**: список параметров/порогов (int/bit/adjust) —
   в `protocol-BLE.md` §7; осталось уточнить байтовые смещения (см. §9).
3. **`addr` в параллельной сборке**: как адресуются модули (DIP/авто-адрес);
   в дампе один пак, addr запроса = 0.
4. **Обновить `REVERSE_ENGINEERING.md (раздел 2)`** под реальные значения (tail/CRC/роли/0xA1)
   или явно пометить его как частично устаревший.
5. ~~Установить ПО **Upper Computer**~~ — **сделано** (см. `protocol-BLE.md`):
   ПО и карты протокола получены и разобраны; при желании — снять живой трафик
   RS-485 (baud **19200**) для сверки блока параметров.

### 5. Как продолжать (инфраструктура и команды)

#### Файлы дампов (уже сняты)
`./btlogs/btsnoop_hci.log` (+ `.last`, `.cfa.curf`) — BTSnoop v1/H4.

```bash
## список всех ATT-кадров
tshark -r btlogs/btsnoop_hci.log -Y btatt -T fields \
  -e frame.number -e btatt.opcode -e btatt.handle -e btatt.value
```
Склейка/парсер: `/tmp/kilo/decode2.py`, `/tmp/kilo/reassemble2.py`
(если `/tmp` очищен — воссоздать; логика: длина в байтах `[5:7]`, payload с `[7]`,
CRC считать по `frame[1:]`).

#### Живой опрос (если нужно снова)
- Сервер `192.168.x.x`, root — пароль в связке ключей
  (`secret-tool lookup service sudo username <user>`).
- ⚠️ **Правило: BT-адаптер сервера НЕ трогать** (никаких рестартов hci/bluez).
- На сервере есть `bluetoothctl`, `gatttool`, python `bleak` 3.0.2.
- Пример опроса (write `ff02`, notify `ff01`): `/tmp/kilo/ble_*.py`
  (на сервере в `/tmp`). Правильный кадр: tail `0D`, CRC без `7E`.

#### Снятие HCI-дампа с телефона (рабочая методика, 2026-09-30)
1. На телефоне (IIIF150 B3, Android 14) включить **Developer options →
   Bluetooth HCI snoop log**; затем перезапустить BT-стек
   (`adb shell svc bluetooth disable/enable` с паузой) — иначе
   `SnoopLogSettingAtEnable` остаётся `EMPTY`.
2. ADB по Wi-Fi: `adb pair <ip>:<pairport> <code>` → `adb connect <ip>:<port>`.
3. Лог пишется в **`/data/misc/bluetooth/logs/btsnoop_hci.log`**; shell его НЕ
   читает (SELinux). Снимать через **`adb bugreport`** — внутри zip лежит копия
   `FS/data/misc/bluetooth/logs/btsnoop_hci.log*`.
4. Разбор: `tshark -r btsnoop_hci.log ...`.

### 6. Производитель (OSINT, подтверждено)

- **Shanghai Energy Electronic Technology Co., Ltd.** / 上海恩阶电子科技有限公司
  (Enjie / EN / **N ENERGY**): `cnshenergy.com`, `energyborn.com`, `enjiebms.com`.
- Продукт **EMU1101 V16** (8S–16S, 24–51.2 В, 100–300 A, LFP/NCM/LTO, CAN/RS485,
  BT/WiFi — опция). Семейства EMU1101/1102/1103, 12V 1202–1205, HV EHVS500.
- **Bluetooth**: модуль **BT2** — BLE↔UART-мост к LCD/UART-порту платы; тот же
  «верхний» протокол, что по RS485 (ПО Upper Computer, baud 9600/19200).
- Инверторный протокол из `BasicInfo` — **`PN-GDLT`** (Luxpower/Deye/Sol-Ark/
  Growatt, семейство Pylontech).
- Полезное: `cnshenergy.com/downloads` (даташиты), `…/software-download`
  (ENBMS, Upper Computer), PDF `bt2-module-product-specification-en.pdf`.

### 7. Ограничения/правила (не нарушать)

- Язык ответов — русский (см. глобальный `AGENTS.md`).
- Приватные данные — только в `.kilo/`; секреты не логировать.
- Не трогать BT-адаптер сервера (только пассивный скан/подключение).
- `secret-tool` в `background_process` возвращает пустую строку → SSH-пароль
  там не проходит; использовать блокирующий `bash`-вызов.
- Поисковики (DDG/Google/Yandex/Ecosia/Marginalia) блокируют бота; рабочие —
  **Brave** (`search.brave.com`) и **GitHub repositories** (код-поиск — только
  с логином).

### 8. Быстрые подсказки

- GitHub BMS-протоколы: `ai-republic/bms-to-inverter`, `marcelrv/seplosBMSv3`,
  `ul-gh/pylon_bms_diagnostics`.
- Pylontech CAN ID: `0x351,0x355,0x356,0x359,0x35C,0x35E`.
- Seplos/PACE (для сравнения): Modbus-RTU 19200 8N1, блоки PIA/PIB/PIC/SPA/SFA/SCA.

## 9. TCP-мост USR-DR164, BLE-хост gsrv и вывод по RS485 (2026-10-02)

### 9.1. TCP-адаптер USR-DR164 (PUSR / USR IOT)

Использовался для попытки выйти на BMS по RS485 через TCP. Веб-морда:
`http://192.0.2.75` (`<login>/<password>` — в `.kilo/`, `Server: HTTPD`; на внутренних страницах
`Microsoft-IIS/5.0`). Меню: System / Work Mode / STA·AP Setting / Serial Setting /
Net Setting / Account / Upgrade SW / Reboot.

Считанные реквизиты и настройки (2026-10-02):

| Параметр | Значение |
|---|---|
| MID | `USR-DR164` |
| SW | `V1.0.15.000000.0000` |
| SN | `0220…3240` (замаскирован) |
| Wi-Fi режим | STA (`GHome-LN-B0`), AP `10.10.100.254` / SSID `USR-DR164_xxxx` |
| STA IP / MAC | `192.0.2.75` / `xx:xx:xx:xx:xx:xx` |
| Net | Protocol **TCP**, Mode **SERVER**, Port **8899**, TCP Timeout 300 |
| Serial | 9600/19200, **8N1**, Pack Interval 20 мс, Pack Size 1400, Com Heart OFF |
| ModBUS Enabled | **OFF** |

Распиновка клемм (мануал §1.6, `USR-DR164/162 User Manual`):

| Клемма | RS232 | RS485 |
|---|---|---|
| 1 | DC 5–36 В + | |
| 2 | DC 5–36 В − | |
| 3 | RX | **A** |
| 4 | TX | **B** |
| 5 | GND | GND |

Стык с BMS (8P8C RS485, даташит §10.2): **A = пины 2/7**, **B = пины 1/8**,
**GND = 3/6**. Мануал: `pusr.com/uploads/20241212/c0e4f462ecead06a7e47e13fee88a488.pdf`.

### 9.2. «ModBUS Enabled» — что это

Встроенный Modbus-шлюз адаптера (только для socket A):

- **OFF** — прозрачная передача байт TCP↔RS485 (нужно для протокола Enjie);
- **Protocol Conversion** — Modbus TCP ↔ Modbus RTU (адаптер разбирает Modbus);
- **Multi Host Polling** — адаптер сам опрашивает Modbus-слейвы (Poll Timeout /
  Poll Interval / Abnormal Response относятся к этому режиму).

Для нашего протокола — только **OFF**.

Смена настроек в вебе проходит **двумя шагами**: POST в `do_cmd_en.html` (Save) →
POST `HF_PROCESS_CMD=RESTART` в `success_en.html` (Reboot); без ребута не применяется.
Ребут подтверждается кратковременным разрывом (порт на ~2–3 с уходит в `DOWN`).

### 9.3. Линия adapter↔BMS

Рабочая связка: прозрачный IP-RS485-шлюз `192.0.2.77:502` → BMS по диалекту
**ASCII PACE** (host-RS485 19200 / RM485 9600). Полный разбор, команды и форматы —
[`protocol-485.md`](protocol-485.md). Для перебора транспортов —
`tools/tcp_probe.py`; для опроса — `tools/rs485_pace.py`.

### 9.4. BLE-хост gsrv

BLE-опрос делался не с рабочей машины, а через отдельный хост рядом с BMS:

- `user@192.0.2.253` (hostname `gsrv`), Ubuntu 22.04, BLE `hci0`, `bleak`;
- пароль — в связке ключей: `secret-tool lookup server 192.0.2.253`;
- BMS: `BP00`, `28:xx:xx:xx:xx:xx`, сервис `0000ff00`, notify `0000ff01`, write `0000ff02`.

### 9.5. Вывод по RS485

Верхний **host-RS485** (п. 10.2, 19200) работает по диалекту **ASCII-hex PACE**
(`~ VER ADR 46 CID2 LEN INFO CHK CR`, `CHK` = сумма-дополнение ASCII): read-команды
идут **без INFO** (`LEN=0000`) и доступны телеметрия (`0x42`), состояние/защиты
(`0x44`), инфо (`0x4F`/`0x51`), **параметры** (`0x47`, 169 Б), время (`0x4D`),
история (`0x4B`), SN (`0xA4`). На **RM485** (п. 10.1, 9600) доступны только
`0x42/0x44/0x4F/0x51`. Команда `0x64` (BLE) относится к **инверторному** каналу
CAN/RM485 и на этой плате даёт `RTN=0xE2` (см. `protocol-BLE.md` §13.3).
Полное описание — [`protocol-485.md`](protocol-485.md).

### 9.6. «CAN Verify Password»

Локальный пароль приложения (Setting Password) в `shared_preferences`
(`app_user`/`password`, `SetSpPassword`, страница `MY_SETPASSWORD`); в кадр
переключения не входит и устройством не проверяется. Не влияет на реверс-опрос.
