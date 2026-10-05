# protocol-485.md — опрос BMS Enjie (EMU110x) по RS485

Результат реверса **RS485-канала** BMS Enjie EMU1101 через прозрачный
IP-RS485-шлюз `192.0.2.77:502`. Проверено вживью (только чтение) 2026-10-04.
Данные сняты на обоих портах BMS: **RM485** (п. 10.1, 9600 8N1) и
**host-RS485** (п. 10.2, 19200 8N1).

> **Главный вывод.** RS485-канал — это **ASCII-hex вариант семейства
> «CID» YD/T 1363 (PACE)**, а **не** бинарный кадр приложения/BLE и **не** Modbus.
> Диалект BLE (BT2-мост) бинарный и по RS485 не используется.
> **host-RS485** отдаёт телеметрию (`0x42`), состояние/защиты (`0x44`), инфо
> (`0x4F`/`0x51`), **параметры** (`0x47`), время (`0x4D`), историю (`0x4B`),
> SN (`0xA4`); **RM485** — только `0x42/0x44/0x4F/0x51`.

## 1. Транспорт и доступ

<table>
<thead>
<tr><th>Параметр</th><th>Значение</th></tr>
</thead>
<tbody>
<tr><td>Шлюз</td><td><code>192.0.2.77</code>, TCP-порт <b>502</b> (прозрачный: байты TCP ↔ RS485)</td></tr>
<tr><td>Порты BMS</td><td><b>RM485</b> (п. 10.1, 9600 8N1) и <b>host-RS485</b> (п. 10.2, 19200 8N1)</td></tr>
<tr><td>Web шлюза</td><td><code>:80</code>, Basic-auth <code>realm="USER LOGIN"</code></td></tr>
</tbody>
</table>

### 1.1. Порты BMS и их функции (руководство пользователя)

<table>
<thead>
<tr><th>Порт</th><th>П. мануала</th><th>Скорость</th><th>Назначение</th><th>Интерфейс 8P8C</th></tr>
</thead>
<tbody>
<tr><td><b>CAN</b></td><td>10.1</td><td>500 кбит/с</td><td>инвертор (Pylon/Goodwe/Deye/Luxpower/TBB…), выгрузка данных/статуса в PCS</td><td>4=CAN-H, 5=CAN-L; 1,8=B; 2,7=A; 3,6=GND</td></tr>
<tr><td><b>RM485</b></td><td>10.1</td><td><b>9600</b></td><td>инвертор (Pylon/Growatt/SRNE), выгрузка данных/статуса в PCS</td><td>1,8=RS485-B; 2,7=RS485-A; 3,6=GND</td></tr>
<tr><td><b>RS485 (host)</b></td><td>10.2</td><td><b>19200</b></td><td>верхнее ПО: мониторинг, телеуправление, <b>настройка параметров</b>, чтение истории</td><td>1,8=RS485-B; 2,7=RS485-A; 3,6=GND; 4,5=internal</td></tr>
<tr><td><b>RS485 (parallel)</b></td><td>10.3</td><td>—</td><td>параллельная связь между батареями (адрес по DIP)</td><td>—</td></tr>
</tbody>
</table>

Отсюда следствия: команды `0x42/0x44/0x4F/0x51` доступны на RM485; для чтения
и записи параметров (`0x47`/`0xA1` и т.п.) и истории нужен **host-RS485 (10.2,
19200)**. Проверено, что `0x47` на RM485 → `RTN=04`.

### 1.2. Отличия в работе портов (проверено на живом устройстве)

<table>
<thead>
<tr><th>Признак</th><th><b>RM485</b> (10.1, 9600)</th><th><b>host-RS485</b> (10.2, 19200)</th></tr>
</thead>
<tbody>
<tr><td>Формат кадра</td><td>ASCII PACE</td><td>ASCII PACE (то же ядро)</td></tr>
<tr><td><code>INFO</code> в запросе read-команд</td><td><code>0x42/0x44</code> — <b>нужен <code>INFO=[00]</code></b> (<code>LEN=…01…</code>)</td><td><code>0x42/0x44</code> — <b>INFO НЕ нужен</b> (<code>LEN=0000</code>); при INFO → <code>RTN=03</code> LenCheckError</td></tr>
<tr><td><code>0x42</code> TeleMeter</td><td><code>RTN=00</code>, 75 Б</td><td><code>RTN=00</code>, 75 Б</td></tr>
<tr><td><code>0x44</code> TeleState</td><td><code>RTN=00</code>, 49 Б</td><td><code>RTN=00</code>, 49 Б</td></tr>
<tr><td><code>0x4F</code> ProtocolVer</td><td><code>RTN=00</code></td><td><code>RTN=00</code></td></tr>
<tr><td><code>0x51</code> Manufacture</td><td><code>RTN=00</code>, 32 Б</td><td><code>RTN=00</code>, 32 Б</td></tr>
<tr><td><code>0x47</code> GetAllParas (параметры)</td><td>❌ <code>RTN=04</code> (No Support)</td><td>✅ <code>RTN=00</code>, <b>169 Б</b></td></tr>
<tr><td><code>0x4D</code> GetTime</td><td>❌ <code>RTN=04</code></td><td>✅ <code>RTN=00</code>, 7 Б (дата/время: <code>07EA 0A 05 00 17 31</code> = 2026-10-05 00:23:49)</td></tr>
<tr><td><code>0x4B</code> GetHistoryData</td><td>❌ <code>RTN=04</code></td><td>✅ <code>RTN=00</code>, 97 Б (1 запись истории)</td></tr>
<tr><td><code>0xA4</code> GetBatSN</td><td>❌ <code>RTN=04</code></td><td>✅ <code>RTN=00</code>, 30 Б ASCII (<code>EMU110110S-XXXX-20220120-00001</code>)</td></tr>
<tr><td><code>0x90</code> GetPacksNum</td><td>❌ <code>RTN=04</code></td><td>❌ <code>RTN=04</code></td></tr>
<tr><td>Назначение</td><td>инвертор (данные/статус в PCS)</td><td>верхнее ПО: мониторинг, управление, <b>настройка</b>, история</td></tr>
</tbody>
</table>

**Вывод:** «урезанность» набора на RM485 — не особенность прошивки, а назначение
порта. Параметры и историю отдаёт только **host-RS485**, причём **без `INFO`**.

### 1.3. DIP-адресация параллельной сборки (`dips.pdf`)

Поддержка до **16 батарей** в параллель. DIP 8 бит на плате (рядом с разъёмами
`CAN/RS485`, `RS4851`, `RS4852`):

- **Хост (master):** `#1–#4 = 0` → адрес **0**; `#5–#8` = двоичный код `N−1`
  (число блоков минус 1), `#5` — младший бит.
- **Слейв:** `#1–#4` = двоичный адрес пакета (**1…15**), `#5–#8 = 0`.
- Колонки таблицы `dips.pdf` — число блоков `1P…16P`; строка 1 — хост,
  строки 2..N — слейвы с адресами `1..N−1`.

Код хоста (`N−1`, `#5`=LSB):

<table>
<thead>
<tr><th>Блоков N</th><th>#5</th><th>#6</th><th>#7</th><th>#8</th></tr>
</thead>
<tbody>
<tr><td>2</td><td>ON</td><td>OFF</td><td>OFF</td><td>OFF</td></tr>
<tr><td>3</td><td>OFF</td><td>ON</td><td>OFF</td><td>OFF</td></tr>
<tr><td>4</td><td>ON</td><td>ON</td><td>OFF</td><td>OFF</td></tr>
<tr><td>5</td><td>OFF</td><td>OFF</td><td>ON</td><td>OFF</td></tr>
<tr><td>6</td><td>ON</td><td>OFF</td><td>ON</td><td>OFF</td></tr>
<tr><td>7</td><td>OFF</td><td>ON</td><td>ON</td><td>OFF</td></tr>
<tr><td>8</td><td>ON</td><td>ON</td><td>ON</td><td>OFF</td></tr>
<tr><td>9</td><td>OFF</td><td>OFF</td><td>OFF</td><td>ON</td></tr>
<tr><td>10</td><td>ON</td><td>OFF</td><td>OFF</td><td>ON</td></tr>
<tr><td>11</td><td>OFF</td><td>ON</td><td>OFF</td><td>ON</td></tr>
<tr><td>12</td><td>ON</td><td>ON</td><td>OFF</td><td>ON</td></tr>
<tr><td>13</td><td>OFF</td><td>OFF</td><td>ON</td><td>ON</td></tr>
<tr><td>14</td><td>ON</td><td>OFF</td><td>ON</td><td>ON</td></tr>
<tr><td>15</td><td>OFF</td><td>ON</td><td>ON</td><td>ON</td></tr>
<tr><td>16</td><td>ON</td><td>ON</td><td>ON</td><td>ON</td></tr>
</tbody>
</table>

Адрес слейва: `#1–#4` = двоичный код адреса (адрес 1 → `#1`; 2 → `#2`;
3 → `#1#2`; … 15 → `#1#2#3#4`), `#5–#8` = 0.

**Итого: 16 блоков = 1 хост (ADDR 0) + 15 слейвов (ADDR 1..15).** Совпадает с
«Таблицей 2 (host)» на стр.2 (`并机数` 2..15). Опрос хоста — `ADR=0`.

## 2. Формат кадра (ASCII PACE)

```
Запрос:  ~  VER(2) ADR(2) 46 CID2(2) LEN(4) INFO(hex) CHK(4) CR
Ответ :  ~  VER(2) ADR(2) 46 RTN(2) LEN(4) INFO(hex) CHK(4) CR
```
- `~` = `0x7E`, `CR` = `0x0D`; все поля — **ASCII-hex** (2 символа на байт).
- `CID1 = 0x46` всегда.
- `LEN` (запрос) = `LCHKSUM<<12 | LENID`, где `LENID = len(INFO)` в байтах, а
  `LCHKSUM` — 4-битное дополнение суммы трёх нибблов `LENID`. У **ответа** поле
  `LENID` = число **hex-символов** INFO (2 × байт), т.е. `len(INFO) = LENID/2`.
- `CHK` = 16-битное **дополнение суммы ASCII-кодов** символов от `VER` до конца
  `INFO` (включая hex-символы, не считая `~`, `CHK` и `CR`):
  `CHK = ((~ sum(ord(c)) ) & 0xFFFF) + 1`.
- `RTN` — код результата (см. §3).

Алгоритм `CHK` и `LCHKSUM` сверены с реальным PACE-кадром
`~010146F20000FD9C` (сумма → `FD9C`). Реализация — `tools/rs485_pace.py`.

## 3. Коды возврата `RTN` (из ПО Upper Computer `GetReturnMessage`)

<table>
<thead>
<tr><th>RTN</th><th>Значение (EN)</th><th>Значение (RU)</th></tr>
</thead>
<tbody>
<tr><td><code>00</code></td><td>Normal</td><td>Успешно</td></tr>
<tr><td><code>01</code></td><td>Protocol Version Error</td><td>Ошибка версии протокола</td></tr>
<tr><td><code>02</code></td><td>Data Check Error</td><td>Ошибка контроля данных (CRC/сумма)</td></tr>
<tr><td><code>03</code></td><td>Len Check Error</td><td>Ошибка проверки длины (<code>LEN</code>)</td></tr>
<tr><td><code>04</code></td><td>Command No Support</td><td>Команда не поддерживается</td></tr>
<tr><td><code>05</code></td><td>Data Format Error</td><td>Ошибка формата данных</td></tr>
<tr><td><code>06</code></td><td>Data Invalid</td><td>Недопустимые данные</td></tr>
<tr><td><code>07</code></td><td>Address Error</td><td>Ошибка адреса</td></tr>
<tr><td><code>08</code></td><td>Flash Error</td><td>Ошибка Flash</td></tr>
<tr><td><code>80..EF</code></td><td>User Defined RTN error</td><td>Пользовательская ошибка</td></tr>
<tr><td>прочее</td><td>Undefined RTN Error</td><td>Неопределённая ошибка</td></tr>
</tbody>
</table>

## 4. Поддерживаемые команды

<table>
<thead>
<tr><th>CID2</th><th>Имя (EN)</th><th>Имя (RU)</th><th>INFO</th><th>RM485 (9600)</th><th>host-RS485 (19200)</th></tr>
</thead>
<tbody>
<tr><td><code>0x42</code></td><td>TeleMeter</td><td>Телеметрия</td><td>RM485: <code>[00]</code>; host: —</td><td>✅ 75 Б</td><td>✅ 75 Б</td></tr>
<tr><td><code>0x44</code></td><td>TeleState</td><td>Состояние/защиты</td><td>RM485: <code>[00]</code>; host: —</td><td>✅ 49 Б</td><td>✅ 49 Б</td></tr>
<tr><td><code>0x4F</code></td><td>ProtocolVer</td><td>Версия протокола</td><td>—</td><td>✅ 0 Б</td><td>✅ 0 Б</td></tr>
<tr><td><code>0x51</code></td><td>Manufacture</td><td>Инфо производителя</td><td>—</td><td>✅ 32 Б</td><td>✅ 32 Б</td></tr>
<tr><td><code>0x47</code></td><td>GetAllParas (параметры)</td><td>Чтение всех параметров</td><td>—</td><td>❌ <code>RTN=04</code></td><td>✅ 169 Б</td></tr>
<tr><td><code>0x4B</code></td><td>GetHistoryData</td><td>Чтение истории</td><td>—</td><td>❌ <code>RTN=04</code></td><td>✅ 97 Б (1 запись)</td></tr>
<tr><td><code>0x4D</code></td><td>GetTime</td><td>Чтение времени</td><td>—</td><td>❌ <code>RTN=04</code></td><td>✅ 7 Б</td></tr>
<tr><td><code>0xA4</code></td><td>GetBatSN</td><td>Серийный номер батареи</td><td>—</td><td>❌ <code>RTN=04</code></td><td>✅ 30 Б</td></tr>
<tr><td><code>0x90</code></td><td>GetPacksNum</td><td>Число пакетов</td><td>—</td><td>❌ <code>RTN=04</code></td><td>❌ <code>RTN=04</code></td></tr>
<tr><td><code>0x49</code></td><td>SetPara</td><td>Запись одного параметра</td><td>—</td><td>—</td><td>❌ <code>RTN=04</code></td></tr>
<tr><td><code>0xA1</code></td><td>SetAllParas</td><td>Запись всех параметров</td><td>—</td><td>—</td><td>✅ запись (169 Б)</td></tr>
<tr><td><code>0x4E</code></td><td>SetTime</td><td>Установка времени</td><td>—</td><td>—</td><td>✅ (7 Б)</td></tr>
<tr><td><code>0x45</code></td><td>TeleCtrl (реле/режим)</td><td>Управление реле/режимом</td><td><code>[packIndex:1][bitNo:1][action:1]</code></td><td>—</td><td>запись (не проверялось)</td></tr>
<tr><td><code>0xA0</code></td><td>Calibration</td><td>Калибровка</td><td><code>[paraIndex:1][value:2 BE]</code></td><td>—</td><td>запись (не проверялось)</td></tr>
<tr><td><code>0xA2</code></td><td>GetSN / HistoryCtrl</td><td>Чтение SN / управление записью истории</td><td>чтение: <code>[]</code>; старт: <code>[0x10][start:Y2 dm hms][end:…][interval:2]</code>; стоп: <code>[0x1F]</code></td><td>—</td><td>чтение/запись (не проверялось)</td></tr>
<tr><td><code>0xA3</code></td><td>SetSN</td><td>Запись SN</td><td><code>[ASCII 30]</code> (пробелы)</td><td>—</td><td>запись (не проверялось)</td></tr>
<tr><td><code>0xA5</code></td><td>SetBatSN</td><td>Запись серийного номера батареи</td><td><code>[ASCII 30]</code> (пробелы)</td><td>—</td><td>запись (не проверялось)</td></tr>
<tr><td><code>0xA6</code></td><td>SetCanProtocol</td><td>Выбор CAN-протокола инвертора</td><td><code>[type:1]</code>, type <code>1..7</code> (см. §4.1)</td><td>—</td><td>✅ запись (проверено)</td></tr>
<tr><td><code>0xA7</code></td><td>Set485Protocol</td><td>Выбор 485-протокола</td><td><code>[type:1]</code> (по карте — авто)</td><td>—</td><td>запись (не проверялось)</td></tr>
</tbody>
</table>

> На host-RS485 read-команды уходят **с `LEN=0000` (без INFO)**; на RM485 для
> `0x42/0x44` нужен один байт `INFO=[00]` (`LEN=0xF001`). Перебор `0x47` на RM485
> с разными `VER/ADR/INFO` — всегда `RTN=04`.

### 4.1. Команды управления / калибровки / SN / протокола — расшифровка

Все команды — host-RS485, диалект ASCII PACE; `LEN = LCHKSUM<<12 | 2·len(INFO)`.
Проверено: запись параметров (`0xA1`, §8.1) и установка времени (`0x4E`, §8.4) —
работают; управление ключами (`0x45`) устройством **отвергается** — см. §4.2.

**`0x45` TeleCtrl — управление реле/режимом.** `INFO = [packIndex:1][bitNo:1][action:1]`,
где `bitNo = ByteIndex·8 + BitIndex` (карта `teleControl`):

<table>
<thead>
<tr><th>bitNo</th><th>Функция (EN)</th><th>Функция (RU)</th><th>Тип</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>Discharge switch</td><td>Разрядный ключ</td><td>OnOff</td></tr>
<tr><td>1</td><td>Charge switch</td><td>Зарядный ключ</td><td>OnOff</td></tr>
<tr><td>2</td><td>Current-limit switch</td><td>Ключ ограничения тока</td><td>OnOff</td></tr>
<tr><td>3</td><td>Temperature control switch</td><td>Управление термо (нагрев)</td><td>OnOff</td></tr>
<tr><td>4</td><td>Shutdown</td><td>Выключение BMS</td><td>Shutdown</td></tr>
<tr><td>5</td><td>Reset</td><td>Сброс/перезапуск</td><td>Reset</td></tr>
</tbody>
</table>

`action`: для типа **OnOff** — `0x10` («Open», включить), если сейчас выключено,
иначе `0x1F` («Close», выключить); для **Shutdown**/**Reset** — `0x00`.

**`0xA0` Calibration — калибровка.** `INFO = [paraIndex:1][value:2 BE]` — запись
калибровочного значения параметра.

**`0xA2` — двухрежимная:** чтение SN (`INFO = []`) и управление записью истории:
старт `[0x10][start:Y2 dm hms][end:Y2 dm hms][interval:2]`, стоп `[0x1F]`
(`Y2` — год u16be, далее месяц/день/час/мин/сек по байту).

**`0xA3` / `0xA5` — запись SN** (устройства / батареи): 30 ASCII-символов,
дополняются пробелами. Чтение SN — `0xA2` (устройство) / `0xA4` (батарея).

**`0xA6` SetCanProtocol — выбор CAN-протокола инвертора.** `INFO = [type:1]`.
После записи имя отражается в `0x51` (байты 12–31, `CAN:<ИМЯ>`):

<table>
<thead>
<tr><th>type</th><th>Имя</th><th>Бренды инверторов</th></tr>
</thead>
<tbody>
<tr><td>1</td><td>PN-GDLT</td><td>Pylontech / Deye / Luxpower / TBB / Goodwe</td></tr>
<tr><td>2</td><td>GRWT</td><td>Growatt (SPF/SPH)</td></tr>
<tr><td>3</td><td>VCTR</td><td>Victron</td></tr>
<tr><td>4</td><td>SMA-SF</td><td>SMA / SOFAR</td></tr>
<tr><td>5</td><td>GINL</td><td>Solis (Ginlong)</td></tr>
<tr><td>6</td><td>STUD</td><td>Studer</td></tr>
<tr><td>7</td><td>MUST</td><td>MUST</td></tr>
</tbody>
</table>

> На BLE-диалекте тот же выбор — командой `0x63` (`SwitchCAN`) с теми же `type 1..7`
> (устройство ожидает `1..7`, хотя enum приложения даёт чётные `{2,4,…}`).

**Проверено на host-RS485 (2026-10-04):**

```
TX ~200046A6E00204<CHK>CR  -> RTN=00; 0x51 => "CAN:SMA_SOFAR"      (type 4, SOFAR)
TX ~200046A6E00201<CHK>CR  -> RTN=00; 0x51 => "CAN:PNG_DYE_Luxp_TBB" (type 1, возврат)
```
Имя в `0x51` (байты 12–31) — 20 байт ASCII с дозаполнением пробелами.

**`0xA7` Set485Protocol — выбор 485-протокола.** `INFO = [type:1]`. По карте
производителя (`XML`) списка 485-протоколов нет, 485-протокол **самоадаптируемый**
(вручную не выбирается). Варианты по enum приложения `PROTOCOL_485`:

<table>
<thead>
<tr><th>App value</th><th>Имя</th><th>Бренд/инвертор</th><th>type (предположительно)</th></tr>
</thead>
<tbody>
<tr><td>0</td><td><code>PN</code></td><td>Pylontech</td><td>1</td></tr>
<tr><td>1</td><td><code>GRWT</code></td><td>Growatt</td><td>2</td></tr>
<tr><td>2</td><td><code>VLTC</code></td><td>Victron</td><td>3</td></tr>
<tr><td>3</td><td><code>SF</code></td><td>SMA / SOFAR</td><td>4</td></tr>
<tr><td>4</td><td><code>Luxp</code></td><td>Luxpower</td><td>5</td></tr>
</tbody>
</table>

> **!!! Предположение !!!** Соответствие `type` = app value + 1 взято по аналогии с
> `0xA6` (CAN), где enum `0..6` → device `1..7`. На живом устройстве не проверялось.

### 4.2. Управление ключами (MOSFET) — попытки и результат (2026-10-05)

Формат `0x45` подтверждён по IL вендорского ПО `BatteryMonitor.exe`
(см. `REVERSE_ENGINEERING.md` §5.2) и **совпадает** с тем, что шлёт редактор:
`INFO = [packIndex][bitNo][action]`, где `bitNo = ByteIndex·8 + BitIndex`;
для типа `OnOff`: `0x10` «Open» (включить) / `0x1F` «Close» (выключить),
для `Shutdown`/`Reset` — `0x00`.

Несмотря на верный формат, **управление ключами на этой прошивке недоступно**:

<table>
<thead><tr><th>Команда (цель)</th><th>Канал</th><th>Ответ</th><th><code>Ext_Bit[6]</code></th></tr></thead>
<tbody>
<tr><td><code>0x45</code> <code>00 00 1F</code> (разряд off)</td><td>host-RS485, VER=<code>20</code></td><td><code>RTN=04</code></td><td>без изменений</td></tr>
<tr><td><code>0x45</code>, <code>0x9A</code>, <code>0x9B</code></td><td>host-RS485, VER=<code>25</code></td><td><code>RTN=04</code></td><td>без изменений</td></tr>
<tr><td><code>0x45</code>, <code>0x9A</code>, <code>0x9B</code></td><td>BLE (<code>BP00</code>)</td><td>нет кадра (тишина)</td><td>без изменений</td></tr>
</tbody>
</table>

`RTN=04` = «Invalid CID2» — команда не поддержана прошивкой, а не «нет прав»:
пароля/разблокировки в протоколе нет (§4.3). Контроль состояния — из `0x44`
`Ext_Bit[6]` (bit0 разряд, bit1 заряд); после попыток остался `0x03` (оба Вкл).
Смена `VER` на `25` неверную версию **не** вызывает `RTN=01` — устройство всё
равно отвечает `RTN=04`.

**Вывод:** коммутацией MOSFET данной платы удалённо (host-RS485/BLE) управлять
нельзя; похоже, ключи управляются только из прошивки/физически.

### 4.3. Идентификация протокола: семейство Seplos / PACE (pacesic v2.0)

Наш кадр `~ 20 00 46 CID2 …` и модельный ряд `EMU110x` (SN `EMU1101…`) соответствуют
**Seplos MODBUS-ASCII V2.0** (устройства `EMU10XX/EMU11XX`, `1101-*`). Официальная
таблица CID2 (Seplos V2.0, Table 4) совпадает с нашим набором команд:

<table>
<thead><tr><th>CID2</th><th>Значение</th></tr></thead>
<tbody>
<tr><td>42H</td><td>телеметрия</td></tr>
<tr><td>44H</td><td>телесигнализация / состояние</td></tr>
<tr><td>45H</td><td>Telecontrol command (управление)</td></tr>
<tr><td>47H</td><td>чтение уставок (параметры)</td></tr>
<tr><td>49H</td><td>Setting of teleregulation information (запись уставок)</td></tr>
<tr><td>4FH</td><td>версия протокола</td></tr>
<tr><td>51H</td><td>инфо о производителе</td></tr>
<tr><td>4BH</td><td>исторические данные</td></tr>
<tr><td>4DH / 4EH</td><td>чтение / установка времени</td></tr>
<tr><td>A0H / A1H / A2H</td><td>калибровка / производственные настройки / отложенная запись</td></tr>
</tbody>
</table>

Родственные реализации и источники:
- `ichernev/seplos-bms-tool` — Python, тот же кадр `~20{addr}46…`; `get-time`=`0x4D`,
  `set-time`=`0x4E`, чтение/запись настроек `0x47`/`0xA1`; в репозитории — те же
  вендорские XML (`07S…16S_V20_ADDR[_EN].xml`).
- `syssi/esphome-seplos-bms` — ESPHome, тот же протокол; официальные PDF-спеки в `docs/`.
- PACE/paceic — `nkinnan/esphome-pace-bms` (v20: `0x4D/0x4E` время, `0x95` shutdown;
  v25: `0x99` свитчи, `0x9A`/`0x9B` MOSFET-ключи, `0x9C` shutdown) и `kitor/pace2pylon`.
  Команды v25 на нашем устройстве также отвергнуты (`RTN=04`).

> Замечание: наш протокол — не Modbus и не Pylontech, а OEM-диалект Seplos/PACE;
> PDF Seplos в этих репозиториях описывают кадр/команды, но payload `45H`/`49H`
> не детализируют.

## 5. TeleMeter — CID2 `0x42` (INFO 75 байт)

Запрос: `~20004642F00100FD37`. Ответ: `~200046001096<100 hex-символов>…DC99`.
Раскладка INFO (big-endian) — по карте производителя `16S_V20_ADDR.xml`
(в EN-версии `16S_V20_ADDR_EN.xml` **потеряны последние 4 поля**, они здесь
восстановлены из китайской карты):

<table>
<thead>
<tr><th>Смещ.</th><th>Размер</th><th>Поле (EN)</th><th>Поле (RU)</th><th>Масштаб</th><th>Значение</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td><code>dataflag</code></td><td>флаг данных</td><td>—</td><td>0</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>Данные валидны (0 = корректно). Служебный байт блока, не настройка.</em></small></td></tr>
<tr><td>1</td><td>1</td><td><code>slaveNo</code></td><td>номер пакета (слейва)</td><td>—</td><td>0</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>Индекс пакета в параллельной сборке; для одиночной батареи 0.</em></small></td></tr>
<tr><td>2</td><td>1</td><td>cell count</td><td>число ячеек</td><td>—</td><td>16</td><td>❌</td></tr>
<tr><td>3</td><td>16×2</td><td><code>Cell01..16</code></td><td>напряжение ячеек 1..16</td><td>×0.001 В</td><td>3.249…3.255 В</td><td>❌</td></tr>
<tr><td>35</td><td>1</td><td>temp count</td><td>число датчиков температуры</td><td>—</td><td>6</td><td>❌</td></tr>
<tr><td>36</td><td>6×2</td><td><code>Battery temp1..4</code>, <code>Ambient temp</code>, <code>Power temp</code></td><td>темп. ячеек 1..4, среды, силовой части</td><td>×0.1 К, −273.1</td><td>23.1…28.5 °C</td><td>❌</td></tr>
<tr><td>48</td><td>2</td><td><code>Current</code></td><td>ток (s16, − = разряд)</td><td>×0.01 А</td><td>−11.03 А</td><td>❌</td></tr>
<tr><td>50</td><td>2</td><td><code>Total voltage</code></td><td>напряжение сборки</td><td>×0.01 В</td><td>52.06 В</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>Сумма напряжений ячеек; сравнивается с <code>Bus voltage</code> (клеммы) для оценки потерь в цепи.</em></small></td></tr>
<tr><td>52</td><td>2</td><td><code>Remaining capacity</code></td><td>остаточная ёмкость</td><td>×0.01 А·ч</td><td>89.22 А·ч</td><td>❌</td></tr>
<tr><td>54</td><td>1</td><td>field count</td><td>число полей блока</td><td>—</td><td><code>0x0A</code> = 10</td><td>❌</td></tr>
<tr><td>55</td><td>2</td><td><code>Total capacity</code></td><td>полная ёмкость</td><td>×0.01 А·ч</td><td>314.00 А·ч</td><td>❌</td></tr>
<tr><td>57</td><td>2</td><td><code>SOC</code></td><td>уровень заряда</td><td>×0.1 %</td><td>28.4 %</td><td>❌</td></tr>
<tr><td>59</td><td>2</td><td><code>Rated capacity</code></td><td>номинальная ёмкость</td><td>×0.01 А·ч</td><td>314.00 А·ч</td><td>❌</td></tr>
<tr><td>61</td><td>2</td><td><code>Battery cycles</code></td><td>число циклов</td><td>×1</td><td>5</td><td>❌</td></tr>
<tr><td>63</td><td>2</td><td><code>SOH</code></td><td>здоровье/износ</td><td>×0.1 %</td><td>100.0 %</td><td>❌</td></tr>
<tr><td>65</td><td>2</td><td><code>Bus voltage</code></td><td>напряжение на клеммах</td><td>×0.01 В</td><td>52.08 В</td><td>❌</td></tr>
<tr><td>67</td><td>2</td><td>temp-drift current</td><td>ток температурного дрейфа</td><td>×0.001 А</td><td>0.025…0.036 А</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!! Поправка (offset) измерения тока, зависящая от температуры; вычитается из измеренного тока для компенсации температурного ухода датчика/шунта.</em></small></td></tr>
<tr><td>69</td><td>2</td><td>zero-point current</td><td>ток нулевой точки</td><td>×0.001 А</td><td>0.000 А</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!! Ток при нулевой нагрузке (аддитивная поправка нуля канала измерения тока), используемый для калибровки.</em></small></td></tr>
<tr><td>71</td><td>2</td><td>charge energy</td><td>энергия заряда</td><td>×0.1 кВт·ч</td><td>77.6 кВт·ч</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>Накопительный счётчик энергии, закачанной в батарею за время работы.</em></small></td></tr>
<tr><td>73</td><td>2</td><td>discharge energy</td><td>энергия разряда</td><td>×0.1 кВт·ч</td><td>70.6 кВт·ч</td><td>❌</td></tr>
<tr><td colspan="7"><small><em>Накопительный счётчик энергии, отданной батареей за время работы.</em></small></td></tr>
</tbody>
</table>

Итого `2 + (1+32) + (1+12) + 6 + (1+20) = 75` — совпадает с ответом.
Все поля телеметрии — **только чтение** (запись через RS485 невозможна).
Никакого «недокументированного хвоста» нет: последние 8 байт — это u16-поля
temp-drift current / zero-point current / charge energy / discharge energy
(ток температурного дрейфа, ток нулевой точки, энергия заряда, энергия разряда),
присутствующие только в китайской карте протокола.

## 6. TeleState — CID2 `0x44` (INFO 49 байт)

Запрос: `~20004644F00100FD35`. Ответ: `~200046008062<98 hex-символов>…EB33`.

Формат выведен из карты `teleSignal_Group` (`16S_V20_ADDR_EN.xml`) и **сверен с
IL-декодером** Upper Computer (`TreatRcvFrame` + `ExtractBitStateData`):

<table>
<thead>
<tr><th>Смещ.</th><th>Поле (EN)</th><th>Поле (RU)</th><th>Содержимое</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0–1</td><td>header</td><td>заголовок</td><td><code>dataflag=0</code>, <code>slaveNo=0</code></td><td>❌</td></tr>
<tr><td>2</td><td>cell count</td><td>число ячеек</td><td><code>0x10</code> = 16</td><td>❌</td></tr>
<tr><td>3–18</td><td>cell GB bytes</td><td>байты состояния ячеек</td><td>по 1 байту на ячейку (Protect); в норме <code>00</code></td><td>❌</td></tr>
<tr><td colspan="5"><small><em>Побайтовые статусы защиты/аварии каждой ячейки; <code>00</code> — норма.</em></small></td></tr>
<tr><td>19</td><td>temp count</td><td>число датчиков</td><td><code>0x06</code></td><td>❌</td></tr>
<tr><td>20–25</td><td>temp GB bytes</td><td>байты состояния температур</td><td>в норме <code>00</code></td><td>❌</td></tr>
<tr><td>26–27</td><td>2 GB bytes</td><td>состояния тока/напряжения</td><td><code>Current</code>, <code>Total voltage</code> (состояние)</td><td>❌</td></tr>
<tr><td>28</td><td>Ext_Bit count</td><td>счётчик блока Ext_Bit</td><td><code>0x14</code> (=20); реально читается <code>count−1</code> = <b>19 байт</b></td><td>❌</td></tr>
<tr><td>29–47</td><td><code>Ext_Bit</code></td><td>расширенный блок защит/статусов</td><td>защит/аварий нет; <code>[6]=0x03</code> (ключи разряда+заряда), <code>[9]=0x01</code></td><td>❌</td></tr>
<tr><td colspan="5"><small><em>Битовая карта предупреждений/защит, см. §6.1; на BLE недоступна, по RS485 читается.</em></small></td></tr>
<tr><td>48</td><td><code>Mode_Byte</code></td><td>режим работы</td><td><code>0x01</code> = <b>Discharge</b> (разряд)</td><td>❌</td></tr>
</tbody>
</table>

Итого `2+(1+16)+(1+6)+2+(1+19)+1 = 49` — совпадает с ответом.
Механика `Ext_Bit`: блок помечен `NumFieldEnable=True` (читается байт-счётчик),
затем берётся `count + ByteNumAdjust` (в XML `ByteNumAdjust=-1`), т.е. `20−1=19`
байт передаются в `ExtractBitStateData`. Поэтому `Ext_Bit` на 5 байт длиннее
формального диапазона XML (Byte0..13 = 14 Б); байты `14..18` XML не описывает.

Косвенно подтверждается: `Ext_Bit[6]` = `0x03` → ключи разряда и заряда
включены (Normal), а последний байт `0x01` = режим **Discharge**, что совпадает
со знаком тока (разряд).

### 6.1. Карта `Ext_Bit` (14 байт; из XML `teleSignal_Group`)

Байт 0: неисправность датчиков напр.(0)/темп.(1)/тока(2)/кнопки(3)/разброса(4),
зарядного(5)/разрядного(6) ключа/ключа огр. тока(7) — Warn.
Байт 1: авария(0)/защита(1) перенапр. ячейки; авария(2)/защита(3) недонапр. ячейки;
авария(4)/защита(5) перенапр. сборки; авария(6)/защита(7) недонапр. сборки.
Байт 2: перегрев/переохлаждение заряда (авария/защита), перегрев/переохлаждение разряда.
Байт 3: среда (перегрев/переохлаждение, авария/защита), силовая часть (защита/авария),
подогрев ячеек, вторичная защита.
Байт 4: переток заряда/разряда (авария/защита), импульсная защита, КЗ выхода,
блокировки импульс/КЗ.
Байт 5: защита повыш. U заряда, прерывистый заряд, авария/защита остатка,
запрет заряда при низком U, обратное подключение, аэрозоль, плавный пуск.
Байт 6 (Normal): ключ разряда(0)/заряда(1)/огр. тока(2)/термо(3).
Байты 7–8 (Normal): балансировка Equalization1..16.
Байт 12: авто(4)/ручное(5) ожидание заряда — Warn.
Байт 13: EEPROM(0)/RTC(1)/калибровка U(2)/тока(3)/нуля(4)/синхронизация календаря(5).

Полная таблица (75 сигналов, Byte/Bit/Type) — `protocol-BLE.md` §7 и
`tools/params_table.py` (BITGROUPS — для параметров).

## 7. Manufacture — CID2 `0x51` (INFO 32 байта)

Запрос: `~200046510000FDAE`. Ответ: `~20004600C040…F01A`.

<table>
<thead>
<tr><th>Смещ.</th><th>Поле (EN)</th><th>Поле (RU)</th><th>Значение</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0–9</td><td>module name</td><td>имя модуля</td><td><code>1101-XO17 </code></td><td>❌</td></tr>
<tr><td>10–11</td><td>service</td><td>служебное</td><td><code>10 06</code></td><td>❌</td></tr>
<tr><td>12–31</td><td>inverter protocol name</td><td>имя активного протокола инвертора</td><td><code>CAN:PNG_DYE_Luxp_TBB</code> (PN-GDLT)</td><td>❌</td></tr>
<tr><td colspan="5"><small><em>Read-only. Смена CAN-протокола инвертора — командой <code>0xA6</code> (см. <code>protocol-BLE.md</code> §8.4/§9).</em></small></td></tr>
</tbody>
</table>

## 8. Параметры и настройки BMS — CID2 `0x47` (host-RS485)

**Читаются полностью на host-RS485 (п. 10.2, 19200).** Ключевое отличие от
RM485: запрос уходит **без INFO** (`LEN=0000`). На host-порту наличие INFO
(`LEN=...01...`) даёт `RTN=03` (Len Check Error). На RM485 всё наоборот: нужен
`INFO=[packIndex]`, но сама команда не поддержана (`RTN=04`).

```
Запрос: ~200046470000<CHK>CR
Ответ : ~20004600<LEN><INFO…>   RTN=00, INFO = 169 байт
```
Структура INFO:
`packIndex(1) + IntParaCnt(1)=60 + 60×u16 + ByteParaCnt(1)=27 + 27×u8 +
BitGroupCnt(1)=8 + 8×u8 + module_name(10)`.
Температурные параметры (ед. `℃`): `значение = raw×0.1 − 273.1`.

### 8.1. Значения параметров (живое чтение)

Индексы `0x00..0x3B` — `u16`, `0x3C..0x56` — `u8`.

<table>
<thead>
<tr><th>Индекс</th><th>Параметр (EN)</th><th>Параметр (RU)</th><th>Сырое</th><th>Значение</th><th>Ед.</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0x00</td><td>Cell over voltage alarm</td><td>Авария перенапряжения ячейки</td><td>3500</td><td>3.500</td><td>V</td><td>✅</td></tr>
<tr><td>0x01</td><td>Cell over voltage alarm recovery</td><td>Восстановление аварии перенапряжения ячейки</td><td>3400</td><td>3.400</td><td>V</td><td>✅</td></tr>
<tr><td>0x02</td><td>Cell under voltage alarm</td><td>Авария недонапряжения ячейки</td><td>2900</td><td>2.900</td><td>V</td><td>✅</td></tr>
<tr><td>0x03</td><td>Cell under voltage alarm recovery</td><td>Восстановление аварии недонапряжения ячейки</td><td>3100</td><td>3.100</td><td>V</td><td>✅</td></tr>
<tr><td>0x04</td><td>Cell over voltage protection</td><td>Защита от перенапряжения ячейки</td><td>3650</td><td>3.650</td><td>V</td><td>✅</td></tr>
<tr><td>0x05</td><td>Cell over voltage protection recovery</td><td>Восстановление защиты от перенапряжения ячейки</td><td>3500</td><td>3.500</td><td>V</td><td>✅</td></tr>
<tr><td>0x06</td><td>Cell under voltage protection</td><td>Защита от недонапряжения ячейки</td><td>2700</td><td>2.700</td><td>V</td><td>✅</td></tr>
<tr><td>0x07</td><td>Cell under voltage protection recovery</td><td>Восстановление защиты от недонапряжения ячейки</td><td>3100</td><td>3.100</td><td>V</td><td>✅</td></tr>
<tr><td>0x08</td><td>Balance turn-on voltage</td><td>Напряжение включения балансировки</td><td>3400</td><td>3.400</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Порог напряжения ячейки, выше которого разрешено включение балансировки (пассивной). Ниже порога балансировка не запускается.</em></small></td></tr>
<tr><td>0x09</td><td>Battery low voltage forbidden charging</td><td>Запрет заряда при низком напряжении</td><td>1500</td><td>1.500</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Порог напряжения, ниже которого заряд полностью запрещается (защита от заряда глубоко разряженной/повреждённой батареи).</em></small></td></tr>
<tr><td>0x0A</td><td>Pack over voltage alarm</td><td>Авария перенапряжения сборки</td><td>5600</td><td>56.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x0B</td><td>Pack over voltage alarm recovery</td><td>Восстановление аварии перенапряжения сборки</td><td>5400</td><td>54.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x0C</td><td>Pack under voltage alarm</td><td>Авария недонапряжения сборки</td><td>4640</td><td>46.400</td><td>V</td><td>✅</td></tr>
<tr><td>0x0D</td><td>Pack under voltage alarm recovery</td><td>Восстановление аварии недонапряжения сборки</td><td>4800</td><td>48.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x0E</td><td>Pack over voltage protection</td><td>Защита от перенапряжения сборки</td><td>5760</td><td>57.600</td><td>V</td><td>✅</td></tr>
<tr><td>0x0F</td><td>Pack over voltage protection recovery</td><td>Восстановление защиты от перенапряжения сборки</td><td>5400</td><td>54.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x10</td><td>Pack under voltage protection</td><td>Защита от недонапряжения сборки</td><td>4320</td><td>43.200</td><td>V</td><td>✅</td></tr>
<tr><td>0x11</td><td>Pack under voltage protection recovery</td><td>Восстановление защиты от недонапряжения сборки</td><td>4800</td><td>48.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x12</td><td>Charging overvoltage protection</td><td>Защита от перенапряжения при заряде</td><td>6300</td><td>63.000</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Отдельный порог перенапряжения сборки, действующий только в режиме заряда (может использоваться для плавного ограничения заряда).</em></small></td></tr>
<tr><td>0x13</td><td>Charging overvoltage recovery</td><td>Восстановление после перенапряжения при заряде</td><td>6100</td><td>61.000</td><td>V</td><td>✅</td></tr>
<tr><td>0x14</td><td>Charging over temperature alarm</td><td>Авария перегрева при заряде</td><td>3231</td><td>50.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x15</td><td>Charging over temperature alarm recovery</td><td>Восстановление аварии перегрева при заряде</td><td>3201</td><td>47.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x16</td><td>Charging under temperature alarm</td><td>Авария переохлаждения при заряде</td><td>2751</td><td>2.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x17</td><td>Charging under temperature alarm recovery</td><td>Восстановление аварии переохлаждения при заряде</td><td>2781</td><td>5.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x18</td><td>Charging over temperature protection</td><td>Защита от перегрева при заряде</td><td>3281</td><td>55.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x19</td><td>Charging over temperature protection recovery</td><td>Восстановление защиты от перегрева при заряде</td><td>3231</td><td>50.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1A</td><td>Charging under temperature protection</td><td>Защита от переохлаждения при заряде</td><td>2731</td><td>0.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1B</td><td>Charging under temperature protection recovery</td><td>Восстановление защиты от переохлаждения при заряде</td><td>2831</td><td>10.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1C</td><td>Discharge over temperature alarm</td><td>Авария перегрева при разряде</td><td>3251</td><td>52.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1D</td><td>Discharge over temperature alarm recovery</td><td>Восстановление аварии перегрева при разряде</td><td>3201</td><td>47.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1E</td><td>Discharge under temperature alarm</td><td>Авария переохлаждения при разряде</td><td>2631</td><td>−10.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x1F</td><td>Discharge under temperature alarm recovery</td><td>Восстановление аварии переохлаждения при разряде</td><td>2761</td><td>3.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x20</td><td>Discharge over temperature protection</td><td>Защита от перегрева при разряде</td><td>3281</td><td>55.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x21</td><td>Discharge over temperature protection recovery</td><td>Восстановление защиты от перегрева при разряде</td><td>3231</td><td>50.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x22</td><td>Discharge under temperature protection</td><td>Защита от переохлаждения при разряде</td><td>2581</td><td>−15.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x23</td><td>Discharge under temperature protection recovery</td><td>Восстановление защиты от переохлаждения при разряде</td><td>2731</td><td>0.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x24</td><td>Cell low temperature heating</td><td>Подогрев ячеек при низкой температуре</td><td>2731</td><td>0.0</td><td>℃</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Температура, ниже которой включается нагреватель ячеек (для заряда при отрицательных температурах).</em></small></td></tr>
<tr><td>0x25</td><td>Cell heating recovery</td><td>Восстановление подогрева ячеек</td><td>2831</td><td>10.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x26</td><td>Environmental over temperature alarm</td><td>Авария перегрева среды</td><td>3331</td><td>60.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x27</td><td>Environmental over temperature alarm recovery</td><td>Восстановление аварии перегрева среды</td><td>3281</td><td>55.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x28</td><td>Environmental under temperature alarm</td><td>Авария переохлаждения среды</td><td>2581</td><td>−15.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x29</td><td>Environmental under temperature alarm recovery</td><td>Восстановление аварии переохлаждения среды</td><td>2611</td><td>−12.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2A</td><td>Environmental over temperature protection</td><td>Защита от перегрева среды</td><td>3411</td><td>68.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2B</td><td>Environmental over temperature protection recovery</td><td>Восстановление защиты от перегрева среды</td><td>3381</td><td>65.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2C</td><td>Environmental under temperature protection</td><td>Защита от переохлаждения среды</td><td>2531</td><td>−20.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2D</td><td>Environmental under temperature protection recovery</td><td>Восстановление защиты от переохлаждения среды</td><td>2631</td><td>−10.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2E</td><td>Power over temperature alarm</td><td>Авария перегрева силовой части</td><td>3631</td><td>90.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x2F</td><td>Power over temperature alarm recovery</td><td>Восстановление аварии перегрева силовой части</td><td>3581</td><td>85.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x30</td><td>Power over temperature protection</td><td>Защита от перегрева силовой части</td><td>3731</td><td>100.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x31</td><td>Power over temperature protection recovery</td><td>Восстановление защиты от перегрева силовой части</td><td>3581</td><td>85.0</td><td>℃</td><td>✅</td></tr>
<tr><td>0x32</td><td>Charging overcurrent alarm</td><td>Авария перетока при заряде</td><td>20000</td><td>200.000</td><td>A</td><td>✅</td></tr>
<tr><td>0x33</td><td>Charging overcurrent recovery</td><td>Восстановление после перетока при заряде</td><td>19500</td><td>195.000</td><td>A</td><td>✅</td></tr>
<tr><td>0x34</td><td>Discharge overcurrent alarm</td><td>Авария перетока при разряде</td><td>45036</td><td>450.360</td><td>A</td><td>✅</td></tr>
<tr><td>0x35</td><td>Discharge overcurrent recovery</td><td>Восстановление после перетока при разряде</td><td>45236</td><td>452.360</td><td>A</td><td>✅</td></tr>
<tr><td>0x36</td><td>Charge overcurrent protection</td><td>Защита от перетока при заряде</td><td>21000</td><td>210.000</td><td>A</td><td>✅</td></tr>
<tr><td>0x37</td><td>Discharge overcurrent protection</td><td>Защита от перетока при разряде</td><td>44536</td><td>445.360</td><td>A</td><td>✅</td></tr>
<tr><td>0x38</td><td>Transient overcurrent protection</td><td>Защита от импульсного перетока</td><td>35536</td><td>355.360</td><td>A</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Порог защиты от короткого импульса тока (бросок при подключении/КЗ), действует быстрее обычной токовой защиты.</em></small></td></tr>
<tr><td>0x39</td><td>Output soft start delay</td><td>Задержка плавного пуска выхода</td><td>2000</td><td>2000.000</td><td>mS</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Время плавного нарастания тока при включении выхода (soft-start) для ограничения броска.</em></small></td></tr>
<tr><td>0x3A</td><td>Battery rated capacity</td><td>Номинальная ёмкость батареи</td><td>31400</td><td>314.000</td><td>Ah</td><td>✅</td></tr>
<tr><td>0x3B</td><td>Remaining capacity</td><td>Остаточная ёмкость</td><td>15000</td><td>150.000</td><td>Ah</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Текущее значение остаточной ёмкости, хранимое в параметрах (используется для инициализации расчёта SOC).</em></small></td></tr>
<tr><td>0x3C</td><td>Voltage differential start</td><td>Порог пуска по разнице напряжений</td><td>50</td><td>0.500</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Разница напряжений (напр. сборка минус клеммы или между половинами), при превышении которой запускается функция ограничения/выравнивания.</em></small></td></tr>
<tr><td>0x3D</td><td>Voltage differential stop</td><td>Порог останова по разнице напряжений</td><td>30</td><td>0.300</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Порог, при снижении ниже которого функция из <code>0x3C</code> выключается (гистерезис).</em></small></td></tr>
<tr><td>0x3E</td><td>Balance start voltage difference</td><td>Разница напряжений включения балансировки</td><td>30</td><td>0.030</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Разброс между самой высокой и низкой ячейкой, при превышении которого включается балансировка.</em></small></td></tr>
<tr><td>0x3F</td><td>Balance stop voltage difference</td><td>Разница напряжений выключения балансировки</td><td>20</td><td>0.020</td><td>V</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Разброс ячеек, при снижении ниже которого балансировка выключается.</em></small></td></tr>
<tr><td>0x40</td><td>Static equilibrium time</td><td>Время статической балансировки</td><td>10</td><td>10</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Длительность/период работы статической (при отсутствии тока) балансировки.</em></small></td></tr>
<tr><td>0x41</td><td>Cell number</td><td>Число ячеек</td><td>16</td><td>16</td><td>шт</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Число последовательных ячеек в сборке.</em></small></td></tr>
<tr><td>0x42</td><td>Charge overcurrent delay</td><td>Задержка защиты от перетока при заряде</td><td>10</td><td>10</td><td>с</td><td>✅</td></tr>
<tr><td>0x43</td><td>Discharge overcurrent delay</td><td>Задержка защиты от перетока при разряде</td><td>10</td><td>10</td><td>с</td><td>✅</td></tr>
<tr><td>0x44</td><td>Transient overcurrent delay</td><td>Задержка защиты от импульсного перетока</td><td>30</td><td>30</td><td>мс</td><td>✅</td></tr>
<tr><td>0x45</td><td>Overcurrent delay recovery</td><td>Задержка восстановления после перетока</td><td>60</td><td>60</td><td>с</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Время, по истечении которого после снятия перетока разрешается автоматическое восстановление.</em></small></td></tr>
<tr><td>0x46</td><td>Overcurrent recovery times</td><td>Число восстановлений после перетока</td><td>5</td><td>5</td><td>раз</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Сколько раз допускается автоматически восстанавливаться после перетока, прежде чем потребуется ручной сброс.</em></small></td></tr>
<tr><td>0x47</td><td>Charge current limit delay</td><td>Задержка ограничения тока заряда</td><td>5</td><td>5</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Задержка перед включением ограничения тока заряда.</em></small></td></tr>
<tr><td>0x48</td><td>Charge activation delay</td><td>Задержка активации заряда</td><td>1</td><td>1</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Пауза перед повторной активацией заряда (для прерывистого/капельного заряда).</em></small></td></tr>
<tr><td>0x49</td><td>Charging activation interval</td><td>Интервал активации заряда</td><td>10</td><td>10</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Период повторных «включений» заряда в режиме прерывистого заряда.</em></small></td></tr>
<tr><td>0x4A</td><td>Charge activation times</td><td>Число активаций заряда</td><td>10</td><td>10</td><td>раз</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Сколько раз выполняется активация заряда в цикле прерывистого заряда.</em></small></td></tr>
<tr><td>0x4B</td><td>Work record interval</td><td>Интервал записи при работе</td><td>30</td><td>30</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Периодичность сохранения записи истории во время работы.</em></small></td></tr>
<tr><td>0x4C</td><td>Standby recording interval</td><td>Интервал записи в режиме ожидания</td><td>240</td><td>240</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>Периодичность сохранения записи истории в режиме ожидания.</em></small></td></tr>
<tr><td>0x4D</td><td>Standby shutdown delay</td><td>Задержка выключения в режиме ожидания</td><td>48</td><td>48</td><td>мин</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Время без активности/обмена, по истечении которого BMS переходит в сон/выключается.</em></small></td></tr>
<tr><td>0x4E</td><td>Remaining capacity alarm</td><td>Авария по остаточной ёмкости</td><td>10</td><td>10</td><td>%</td><td>✅</td></tr>
<tr><td>0x4F</td><td>Remaining capacity protection</td><td>Защита по остаточной ёмкости</td><td>5</td><td>5</td><td>%</td><td>✅</td></tr>
<tr><td>0x50</td><td>Interval charge capacity</td><td>Ёмкость интервального заряда</td><td>96</td><td>96</td><td>%</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Уровень заряда (SOC), до которого выполняется интервальный/поддерживающий заряд.</em></small></td></tr>
<tr><td>0x51</td><td>Cycle cumulative capacity</td><td>Накопленная ёмкость цикла</td><td>80</td><td>80</td><td>%</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Доля номинальной ёмкости, накопление которой засчитывается как один полный цикл.</em></small></td></tr>
<tr><td>0x52</td><td>Connection fault impedance</td><td>Сопротивление неисправности соединения</td><td>100</td><td>10.0</td><td>мОм</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Порог сопротивления, при превышении которого фиксируется плохой контакт/обрыв соединения.</em></small></td></tr>
<tr><td>0x53</td><td>Compensation point 1 position</td><td>Позиция точки компенсации 1</td><td>9</td><td>9</td><td>№</td><td>✅</td></tr>
<tr><td colspan="7"><small><em>!!! Предположение !!!_ Номер ячейки/точки, для которой задаётся сопротивление компенсации (учёт сопротивления соединений при измерении).</em></small></td></tr>
<tr><td>0x54</td><td>Compensation point 1 impedance</td><td>Сопротивление точки компенсации 1</td><td>0</td><td>0.0</td><td>мОм</td><td>✅</td></tr>
<tr><td>0x55</td><td>Compensation point 2 position</td><td>Позиция точки компенсации 2</td><td>13</td><td>13</td><td>№</td><td>✅</td></tr>
<tr><td>0x56</td><td>Compensation point 2 impedance</td><td>Сопротивление точки компенсации 2</td><td>0</td><td>0.0</td><td>мОм</td><td>✅</td></tr>
</tbody>
</table>

**Метод записи — см. §8.3** (проверено: `0x05` 3500 → 3550 В, `RTN=00`).

### 8.2. Бит-группы (маски включения функций/защит)

Значения-маски и побитовая расшифровка (живое чтение). `1` = функция включена.
`RW` = ✅ можно записать через RS485 (командой `0xA1`); ниже — метод записи.

**Байт 0 — `group0 = 0xFF` (маски отключения/игнорирования датчиков и ключей)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td colspan="5"><small><em>Бит = 1 означает, что соответствующий вход/датчик не участвует в защитной логике (игнорируется) — сервисный флаг конфигурации.</em></small></td></tr>
<tr><td>0</td><td>1</td><td>Voltage sensor invalidation</td><td>Игнорирование датчика напряжения</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Temperature sensor invalidation</td><td>Игнорирование датчика температуры</td><td>✅</td></tr>
<tr><td>2</td><td>1</td><td>Current sensor invalidation</td><td>Игнорирование датчика тока</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Button switch invalidation</td><td>Игнорирование кнопки</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Cell differential voltage invalidation</td><td>Игнорирование контроля разброса ячеек</td><td>✅</td></tr>
<tr><td>5</td><td>1</td><td>Charge switch invalidation</td><td>Игнорирование зарядного ключа</td><td>✅</td></tr>
<tr><td>6</td><td>1</td><td>Discharge switch invalidation</td><td>Игнорирование разрядного ключа</td><td>✅</td></tr>
<tr><td>7</td><td>1</td><td>Current limit switch invalidation</td><td>Игнорирование ключа ограничения тока</td><td>✅</td></tr>
</tbody>
</table>

**Байт 1 — `group1 = 0xFF` (маски аварий/защит по напряжению)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Cell over voltage alarm</td><td>Авария перенапряжения ячейки</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Cell over voltage protection</td><td>Защита от перенапряжения ячейки</td><td>✅</td></tr>
<tr><td>2</td><td>1</td><td>Cell under voltage alarm</td><td>Авария недонапряжения ячейки</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Cell under voltage protection</td><td>Защита от недонапряжения ячейки</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Pack over voltage alarm</td><td>Авария перенапряжения сборки</td><td>✅</td></tr>
<tr><td>5</td><td>1</td><td>Pack over voltage protection</td><td>Защита от перенапряжения сборки</td><td>✅</td></tr>
<tr><td>6</td><td>1</td><td>Pack under voltage alarm</td><td>Авария недонапряжения сборки</td><td>✅</td></tr>
<tr><td>7</td><td>1</td><td>Pack under voltage protection</td><td>Защита от недонапряжения сборки</td><td>✅</td></tr>
</tbody>
</table>

**Байт 2 — `group2 = 0xFF` (маски аварий/защит по температуре заряда/разряда)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Charging over temperature alarm</td><td>Авария перегрева при заряде</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Charging over temperature protection</td><td>Защита от перегрева при заряде</td><td>✅</td></tr>
<tr><td>2</td><td>1</td><td>Charging under temperature alarm</td><td>Авария переохлаждения при заряде</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Charging under temperature protection</td><td>Защита от переохлаждения при заряде</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Discharge over temperature alarm</td><td>Авария перегрева при разряде</td><td>✅</td></tr>
<tr><td>5</td><td>1</td><td>Discharge over temperature protection</td><td>Защита от перегрева при разряде</td><td>✅</td></tr>
<tr><td>6</td><td>1</td><td>Discharge under temperature alarm</td><td>Авария переохлаждения при разряде</td><td>✅</td></tr>
<tr><td>7</td><td>1</td><td>Discharge under temperature protection</td><td>Защита от переохлаждения при разряде</td><td>✅</td></tr>
</tbody>
</table>

**Байт 3 — `group3 = 0xBF` (среда / силовая часть / нагрев)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Environmental over temperature alarm</td><td>Авария перегрева среды</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Environmental over temperature protection</td><td>Защита от перегрева среды</td><td>✅</td></tr>
<tr><td>2</td><td>1</td><td>Environmental under temperature alarm</td><td>Авария переохлаждения среды</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Environmental under temperature protection</td><td>Защита от переохлаждения среды</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Power over temperature protection</td><td>Защита от перегрева силовой части</td><td>✅</td></tr>
<tr><td>5</td><td>1</td><td>Power over temperature alarm</td><td>Авария перегрева силовой части</td><td>✅</td></tr>
<tr><td>6</td><td>0</td><td>Cell low temperature heating</td><td>Подогрев ячеек при низкой температуре</td><td>✅</td></tr>
<tr><td>7</td><td>1</td><td>Secondary tripping protection</td><td>Вторичная (резервная) защита</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Бит7 = независимая от ПО аппаратная защита (второй порог/триппинг), срабатывающая при отказе основной.</em></small></td></tr>
</tbody>
</table>

**Байт 4 — `group4 = 0xBF` (токовые защиты)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Charging overcurrent alarm</td><td>Авария перетока при заряде</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Charge overcurrent protection</td><td>Защита от перетока при заряде</td><td>✅</td></tr>
<tr><td>2</td><td>1</td><td>Discharge overcurrent alarm</td><td>Авария перетока при разряде</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Discharge overcurrent protection</td><td>Защита от перетока при разряде</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Transient current protection</td><td>Защита от импульсного (броскового) тока</td><td>✅</td></tr>
<tr><td>5</td><td>1</td><td>Output short circuit protection</td><td>Защита от КЗ на выходе</td><td>✅</td></tr>
<tr><td>6</td><td>0</td><td>Transient overcurrent lockout</td><td>Блокировка при импульсном перетоке</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Бит6 = после срабатывания импульсной защиты выход блокируется до ручного сброса/перезапуска (не восстанавливается автоматически).</em></small></td></tr>
<tr><td>7</td><td>1</td><td>Output short circuit locking</td><td>Блокировка при КЗ на выходе</td><td>✅</td></tr>
</tbody>
</table>

**Байт 5 — `group5 = 0x9F` (повышенное напряжение / остаток / функции выхода)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Charging high voltage protection</td><td>Защита от повышенного напряжения заряда</td><td>✅</td></tr>
<tr><td>1</td><td>1</td><td>Intermittent charging function</td><td>Функция прерывистого заряда</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Бит1 = периодическое включение/выключение заряда малыми порциями (для дозаряда/выравнивания в верхнем диапазоне). См. параметры <code>0x48..0x4A</code>.</em></small></td></tr>
<tr><td>2</td><td>1</td><td>Remaining capacity alarm</td><td>Авария по остаточной ёмкости</td><td>✅</td></tr>
<tr><td>3</td><td>1</td><td>Remaining capacity protection</td><td>Защита по остаточной ёмкости</td><td>✅</td></tr>
<tr><td>4</td><td>1</td><td>Battery low voltage forbidden charging</td><td>Запрет заряда при низком напряжении</td><td>✅</td></tr>
<tr><td>5</td><td>0</td><td>Output reverse connection protection</td><td>Защита от обратного подключения выхода</td><td>✅</td></tr>
<tr><td>6</td><td>0</td><td>Aerosol failure</td><td>Срабатывание аэрозольного пожаротушения</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Бит6 = дискретный сигнал на систему аэрозольного пожаротушения (сухой контакт) при аварии батареи.</em></small></td></tr>
<tr><td>7</td><td>1</td><td>Output soft start function</td><td>Функция плавного пуска выхода</td><td>✅</td></tr>
</tbody>
</table>

**Байт 6 — `group6 = 0xAF` (балансировка / активация заряда)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Charge equalization function</td><td>Функция балансировки при заряде</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Пассивная балансировка ячеек во время заряда: включается по разбросу ячеек (порог <code>0x3E</code>), пока идёт ток заряда.</em></small></td></tr>
<tr><td>1</td><td>1</td><td>Static equilibrium function</td><td>Функция статической балансировки</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Балансировка без тока (в покое), см. параметр <code>0x40</code> (Static equilibrium time).</em></small></td></tr>
<tr><td>2</td><td>1</td><td>Timeout prohibits equalization</td><td>Запрет балансировки по таймауту</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>!!! Предположение !!! Автоматически запрещает балансировку после истечения отведённого времени, чтобы не разряжать ячейки бесконечно.</em></small></td></tr>
<tr><td>3</td><td>1</td><td>Over temperature prohibits equalization</td><td>Запрет балансировки при перегреве</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Запрещает балансировку при повышении температуры ячеек выше допустимой (предотвращает дополнительный нагрев).</em></small></td></tr>
<tr><td>4</td><td>0</td><td>Automatically activate charging</td><td>Автоактивация заряда</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>!!! Предположение !!! Разрешает BMS самой инициировать/возобновлять заряд (например, при просадке SOC) без внешней команды.</em></small></td></tr>
<tr><td>5</td><td>1</td><td>Manually activate charging</td><td>Ручная активация заряда</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>!!! Предположение !!! Разрешает активацию заряда по внешней команде (оператор/верхнее ПО), а не автоматически.</em></small></td></tr>
<tr><td>6</td><td>0</td><td>Take the initiative current limiting charging</td><td>Активное ограничение тока заряда</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>BMS сама снижает запрашиваемый ток заряда (активное воздействие на инвертор через протокол).</em></small></td></tr>
<tr><td>7</td><td>1</td><td>Passive current limiting charging</td><td>Пассивное ограничение тока заряда</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Ограничение тока без связи с инвертором (например, размыканием зарядного ключа).</em></small></td></tr>
</tbody>
</table>

**Байт 7 — `group7 = 0x1F` (сервисные функции)**

<table>
<thead>
<tr><th>Бит</th><th>Знач.</th><th>Функция (EN)</th><th>Функция (RU)</th><th>RW</th></tr>
</thead>
<tbody>
<tr><td>0</td><td>1</td><td>Switch shut down function</td><td>Выключение по кнопке</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает выключение BMS кнопкой (обычно длительное нажатие).</em></small></td></tr>
<tr><td>1</td><td>1</td><td>Standby shutdown function</td><td>Автоотключение в режиме ожидания</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает автоматическое выключение при длительном простое без активности (см. параметр <code>0x4D</code> Standby shutdown delay).</em></small></td></tr>
<tr><td>2</td><td>1</td><td>History record function</td><td>Ведение истории</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает ведение и сохранение истории событий/измерений (интервалы <code>0x4B</code>/<code>0x4C</code>).</em></small></td></tr>
<tr><td>3</td><td>1</td><td>LCD display function</td><td>Дисплей LCD</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает вывод данных на LCD-дисплей (если он установлен).</em></small></td></tr>
<tr><td>4</td><td>1</td><td>Bluetooth communication function</td><td>Bluetooth-связь</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает Bluetooth/BLE-связь с приложением.</em></small></td></tr>
<tr><td>5</td><td>0</td><td>Automatic address coding</td><td>Автоадресация</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Автоматическое присвоение адреса пакета при параллельном включении (без ручного DIP).</em></small></td></tr>
<tr><td>6</td><td>0</td><td>Parallel external polling</td><td>Внешний опрос при параллельном включении</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешает внешнему устройству опрашивать пакеты параллельной сборки.</em></small></td></tr>
<tr><td>7</td><td>0</td><td>Single BMS 1.0C charging</td><td>Одиночный BMS: заряд 1.0C</td><td>✅</td></tr>
<tr><td colspan="5"><small><em>Разрешение заряда током 1.0C для одиночной батареи.</em></small></td></tr>
</tbody>
</table>

**Метод записи — см. §8.3** (проверено: `group1.bit0` 1 → 0 → 1, `RTN=00`).

### 8.3. Запись параметров и флагов — процедура (ПРОВЕРЕНО)

Запись выполняется **только** командой `CID2=0xA1` (весь блок 169 Б), метод
**read-modify-write**: прочитать `0x47`, изменить нужные байты, отправить `0xA1`.
Команда одиночной записи `0x49` на host-RS485 **не поддерживается** (`RTN=04`).

Кадр: `~ 20 00 46 A1 <LEN> <payload 169B> <CHK> CR`, где
`LEN = LCHKSUM<<12 | (2·len(INFO))` — host-порт считает длину в **hex-символах**;
для 169 Б `LEN = 0x8152`. Успех — `RTN=00`; результат проверять контрольным
чтением `0x47`.

**Смещения полей в payload (169 Б):**

<table>
<thead>
<tr><th>Что</th><th>Смещение</th><th>Тип</th></tr>
</thead>
<tbody>
<tr><td>packIndex</td><td>0</td><td>u8</td></tr>
<tr><td>int-параметры <code>0x00..0x3B</code></td><td><code>2 + 2·i</code></td><td>u16be</td></tr>
<tr><td>byte-параметры <code>0x3C..0x56</code></td><td><code>123 + (idx − 0x3C)</code></td><td>u8</td></tr>
<tr><td>бит-группа <code>G</code> (<code>0x00..0x07</code>)</td><td><code>151 + G</code></td><td>u8 (бит <code>b</code> = <code>1&lt;&lt;b</code>)</td></tr>
<tr><td>module name</td><td>159..168</td><td>ASCII 10</td></tr>
</tbody>
</table>

**Проверено наживую (2026-10-04):**

<table>
<thead>
<tr><th>Что</th><th>До</th><th>Запись</th><th>После (чтение)</th><th>RTN</th></tr>
</thead>
<tbody>
<tr><td>Параметр <code>0x05</code> Cell OVP recovery</td><td>3500 (3.500 В)</td><td>3550</td><td>3550 (3.550 В)</td><td><code>00</code></td></tr>
<tr><td>Флаг <code>group1.bit0</code> Cell over voltage alarm</td><td>1 (<code>0xFF</code>)</td><td>0 (<code>0xFE</code>)</td><td>0</td><td><code>00</code></td></tr>
<tr><td>Флаг <code>group1.bit0</code> (восстановление)</td><td>0</td><td>1</td><td>1 (<code>0xFF</code>)</td><td><code>00</code></td></tr>
</tbody>
</table>

Запись всех прочих параметров/флагов без явного запроса не выполнять.

`module_name = 1101-XO17 `.

> На **RM485** (п. 10.1) `0x47` не поддержан (`RTN=04`) — параметры там недоступны.
> Формат блока идентичен BLE-варианту (`protocol-BLE.md` §8, `DEVICE_SNAPSHOT.md` §4).

### 8.4. Установка времени BMS — `CID2=0x4E` (ПРОВЕРЕНО)

- **Чтение времени** `CID2=0x4D`, INFO пусто → 7 Б:
  `[year:2 BE][month:1][day:1][hour:1][min:1][sec:1]`.
- **Установка** `CID2=0x4E`, INFO = тот же 7-байтовый формат.
- host-RS485: `LEN = LCHKSUM<<12 | (2·len(INFO))`; для 7 Б `LEN = 0x200E`.
- Ответ `RTN=00` — успех; проверять контрольным чтением `0x4D`.
- Часы BMS хранят **локальное время** (без часового пояса/TZ) — здесь задаётся MSK (UTC+3).
- Проверено 2026-10-04: записано `2026-10-04 21:07:19` MSK
  (`INFO=07 EA 0A 04 15 07 13`), контрольное чтение → `2026-10-04 21:07:20`.
  Было до записи: `2026-10-05 02:06:03` (сбито).

```
Запрос: ~2000464E200E07EA0A04150713<CHK>CR
Ответ : ~200046000000<CHK>CR        RTN=00
```

## 9. Инструмент

```sh
python3 tools/rs485_pace.py --host HOST             # все читающие блоки (host-режим)
python3 tools/rs485_pace.py --host HOST --port-type rm485   # RM485 (0x42/0x44 с INFO=[00])
python3 tools/rs485_pace.py --host HOST --cid 0x47          # параметры (host, 169 Б)
python3 tools/rs485_pace.py --host HOST --cid 0x42          # только телеметрия
python3 tools/rs485_pace.py --host HOST --port 502          # другой TCP-порт шлюза
python3 tools/rs485_pace.py --host HOST --adr 1 --cid 0x42  # слейв 1
```

> `--host` теперь обязателен: жёсткий дефолт на конкретный шлюз убран
> (сетевое взаимодействие с ним допускается только по отдельному разрешению).
- `--port-type host` (по умолчанию) — read-команды без INFO (host-RS485, 19200).
- `--port-type rm485` — для `0x42/0x44` добавляет `INFO=[00]` (RM485, 9600).
- Только чтение: скрипт отказывается слать нечитающие CID2; `0x47` декодируется
  по `tools/params_table.py`.

## 10. Сырые кадры (примеры, живое устройство)

```
TeleMeter  TX ~20004642F00100FD37
           RX ~2000460010960000100CB80CB60CB80CB80CB70CB70CB70CB80CB30CB70CB80CB80CB5
              0CB70CB60CB6060B9E0B950B920BA00BC80BA9FB96145824520A7AA801287AA80005
              03E8145A00280000030802C0DC99
TeleState  TX ~20004644F00100FD35
           RX ~20004600806200001000000000000000000000000000000000060000000000000000
              140000000000000300000100000000000000000001EB33
Manufacture TX ~200046510000FDAE
           RX ~20004600C040313130312D584F313720100643414E3A504E475F4459455F4C7578
              705F544242F01A
ProtocolVer TX ~2000464F0000FD9A
           RX ~200046000000FDB4
```

## 11. Бэклог

- **Управление ключами (`0x45`/`0x9A`/`0x9B`) — ЗАКРЫТО**: проверены host-RS485
  (VER `20`/`25`) и BLE; устройство отвечает `RTN=04`/тишиной, состояние не меняется
  (см. §4.2). Протокол идентифицирован как Seplos/PACE v2.0 (§4.3). Считать
  удалённое управление MOSFET не поддержанным прошивкой.
- Подтвердить блок `Ext_Bit`+`Mode` TeleState на живом изменении режима
  (заряд/разряд/балансировка): структура и длина (19 Б) точны, но смысл байтов
  `Ext_Bit[14..18]` (за пределами XML Byte0..13) производителем не описан.
- Разобрать формат истории (`0x4B`, 97 Б на запись); формат даты/времени уже
  подтверждён (`0x4D`/`0x4E`, §8.4).
- Проверить адресацию слейвов (`ADR=01..0F`) при параллельной сборке.
- Запись параметров подтверждена (`0xA1`, read-modify-write, §8.1); проверить
  допустимые диапазоны значений и поведение при выходе за допуски.
- Сверить значения параметров, прочитанные по RS485, с BLE-эталоном
  (`DEVICE_SNAPSHOT.md` §4).
