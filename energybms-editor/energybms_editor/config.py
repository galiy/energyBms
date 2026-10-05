"""Портативная конфигурация: JSON рядом с запускаемым модулем."""
import json
import os
import sys

CONFIG_NAME = "energybms_editor.json"

DEFAULTS = {
    "transport": "tcp",          # tcp | serial | ble
    "tcp_host": "192.0.2.77",
    "tcp_port": 502,
    "port_type": "host",         # host | rm485 (для RS485)
    "serial_port": "",
    "baud": 19200,
    "ble_name": "BP00",
    "ble_address": "",
    "adr": 0,
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def config_path():
    return os.path.join(app_dir(), CONFIG_NAME)


def dump_last_read(blocks):
    """Сохраняет сырой результат последнего чтения рядом с конфигом (диагностика)."""
    data = {}
    for cid, res in blocks.items():
        data["0x%02X" % cid] = {"ok": res.ok, "rtn": res.rtn, "info_hex": res.info.hex()}
    path = os.path.join(app_dir(), "energybms_last_read.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except OSError:
        return None


def has_saved():
    """Есть ли сохранённый конфиг (значит, соединение уже настраивали)."""
    return os.path.exists(config_path())


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    """Сохраняет конфиг. Возвращает (path, error|None); при сбое не бросает."""
    data = dict(DEFAULTS)
    data.update(cfg)
    path = config_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return path, None
    except OSError as exc:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return path, str(exc)
