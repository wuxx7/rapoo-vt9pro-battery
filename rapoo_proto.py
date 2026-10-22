# -*- coding: utf-8 -*-
"""rapoo_proto.py —— 雷柏（Rapoo）VT9 Pro 电量协议

协议来源：在本机 24AE:185A 上实测抓包得到（见 README 的逆向记录）。

## 接口

- VID:PID = `24AE:185A`（雷柏 VT9 Pro / VT9PRO_Wireless）
- 接口：usage page `0xFF00`，usage `0x0002`，输入 7 字节 / 输出 7 字节
- **没有 Feature Report**（feature_len = 0）
- 同一设备另有 `0xFF00:0x000E`（32 字节）接口，实测不上报任何报文，
  真正的状态广播走 `0xFF00:0x0002`

## 报文（7 字节，被动上报，每 3 秒一包）

```
BB B0 42 20 03 01 <电量>
```

| 偏移 | 值 | 含义 |
|---|---|---|
| 0 | `0xBB` | 帧头 |
| 1 | `0xB0` | 帧类型 |
| 2 | `0x42` | 固定 |
| 3 | `0x20` | 状态包标识 |
| 4 | `0x03` | 固定 |
| 5 | `0x01` | 固定 |
| 6 | 0..100 | **电量百分比** |

## 关键结论

1. **电量是被动上报的**，不需要也不能主动查询。
   每 3 秒一包，因此打开面板后最多等 3 秒就能拿到第一个值。
2. **写通道被固件封死**：`HidD_SetOutputReport` 对任何 Report ID / 长度
   都返回 `ERROR_INVALID_FUNCTION(1)`，`WriteFile` 返回 `ERROR_INVALID_PARAMETER(87)`。
   所以这个型号只能"听"，不能"问"。
3. 电量值随实际放电变化（实测 100 → 99），确认第 6 字节就是电量。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw

VID = 0x24AE
PID = 0x185A

# 状态包的固定前缀（前 6 字节），用于识别电量包
FRAME_PREFIX = bytes([0xBB, 0xB0, 0x42, 0x20, 0x03, 0x01])
FRAME_LEN = 7
BATTERY_INDEX = 6

# 设备一次上报的间隔（秒），用于估算等待时间
REPORT_INTERVAL = 3.0


@dataclass
class RapooReading:
    """一次读取结果。"""
    online: bool = False
    battery: Optional[int] = None
    raw: bytes = b""
    detail: str = ""
    product: str = ""
    vid_pid: str = ""
    age: float = 0.0          # 报文距今多少秒


def find_interface() -> Optional[hw.HidInterface]:
    """找到雷柏的 7 字节状态接口。

    优先精确匹配 VID:PID + usage page 0xFF00 + 7 字节输入，
    匹配不到时退一步只按 VID + 7 字节输入找（兼容同厂其他型号）。
    """
    candidates = [d for d in hw.enumerate_hid() if d.vid == VID]
    # 1) 最精确：指定 PID + 0xFF00 + 7 字节
    for d in candidates:
        if d.pid == PID and d.usage_page == 0xFF00 and d.input_len == FRAME_LEN:
            return d
    # 2) 同 VID 的 0xFF00 且 7 字节
    for d in candidates:
        if d.usage_page == 0xFF00 and d.input_len == FRAME_LEN:
            return d
    # 3) 同 VID 的 0xFF00 任意长度（有些型号包长不同，仍可尝试）
    for d in candidates:
        if d.usage_page == 0xFF00:
            return d
    return None


def parse_status(data: bytes) -> Optional[int]:
    """从一条报文里取出电量；不是电量包就返回 None。"""
    if len(data) < FRAME_LEN:
        return None
    if not data.startswith(FRAME_PREFIX):
        return None
    level = data[BATTERY_INDEX]
    if 0 <= level <= 100:
        return level
    return None


def read_battery(timeout: float = 6.0,
                 stop_flag=None,
                 on_raw=None) -> RapooReading:
    """读一次电量。

    设备每 3 秒才上报一包，所以默认等 6 秒（足够拿到 1~2 包）。
    期间收到的所有报文都会经过 `on_raw` 回调（调试用）。
    """
    out = RapooReading()
    iface = find_interface()
    if iface is None:
        out.detail = "没找到雷柏设备（请确认 2.4G 接收器已插上、鼠标已开机）"
        return out

    out.vid_pid = iface.vid_pid
    out.product = iface.product or "Rapoo"

    try:
        dev = hw.HidDevice(iface.path, write=False)
    except Exception as e:
        out.detail = f"无法打开设备：{e}"
        return out

    try:
        deadline = time.monotonic() + max(timeout, 0.5)
        while time.monotonic() < deadline:
            if stop_flag is not None and stop_flag():
                break
            data = dev.read_input(timeout_ms=400)
            if not data:
                continue
            if on_raw is not None:
                try:
                    on_raw(data)
                except Exception:
                    pass
            level = parse_status(data)
            if level is not None:
                out.online = True
                out.battery = level
                out.raw = data
                out.age = 0.0
                out.detail = "被动状态广播（BB B0 42 20 03 01 xx）"
                return out
        out.detail = ("设备在线，但 %.0f 秒内没收到状态包"
                      "（动一下鼠标，或鼠标刚唤醒）" % timeout)
    except Exception as e:
        out.detail = f"读取出错：{e}"
    finally:
        dev.close()
    return out


def read_battery_only(timeout: float = 6.0) -> tuple[Optional[int], str]:
    """给托盘用的简化接口：返回 (电量, 错误说明)。"""
    r = read_battery(timeout=timeout)
    if r.battery is not None:
        return r.battery, ""
    return None, r.detail or "没有收到电量报文"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("查找雷柏设备…")
    it = find_interface()
    if it:
        print("  %s  usage=0x%04X:0x%04X  in=%d out=%d  product=%r" %
              (it.vid_pid, it.usage_page, it.usage, it.input_len,
               it.output_len, it.product))
    else:
        print("  没找到")
    print("读取电量（最多等 6 秒）…")
    res = read_battery(timeout=6.0, on_raw=lambda d: print("  RAW", d.hex(" ")))
    if res.battery is not None:
        print("电量: %d%%  (%s)" % (res.battery, res.detail))
    else:
        print("失败:", res.detail)
