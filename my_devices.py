# -*- coding: utf-8 -*-
"""my_devices.py —— 雷柏 VT9 Pro 电量面板

用法：
    python my_devices.py            打开界面（默认自动刷新）
    python my_devices.py --once     命令行读一次就退出
    python my_devices.py --autostart on|off|status
    python my_devices.py --install-links

界面只有一张卡片：雷柏 VT9 Pro 的电量。
底层协议见 rapoo_proto.py（被动状态广播，每 3 秒一包）。
"""

from __future__ import annotations

import argparse
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Optional

import rapoo_proto as rp
import tray_common as tc
import win_link


# ==========================================================================
# 读取层
# ==========================================================================
@dataclass
class Reading:
    title: str
    subtitle: str
    level: Optional[int] = None
    status: str = ""
    detail: str = ""
    error: str = ""
    extra: str = ""

    @property
    def ok(self) -> bool:
        return self.level is not None


def read_mouse() -> Reading:
    """读雷柏 VT9 Pro 电量。"""
    r = Reading("雷柏 VT9 Pro", "正在查找接收器…")
    iface = rp.find_interface()
    if iface is None:
        r.subtitle = "未找到设备"
        r.error = "没找到雷柏设备（请把 2.4G 接收器插上、鼠标开机）"
        return r

    r.subtitle = f"{iface.vid_pid} · {iface.product or 'Rapoo Gaming Device'}"
    try:
        res = rp.read_battery(timeout=6.0)
    except Exception as e:
        r.error = f"读取出错：{e}"
        return r

    if res.battery is None:
        r.error = res.detail or "没有收到电量报文"
        return r

    r.level = res.battery
    r.detail = "被动状态广播 · 每 3 秒一包"
    r.extra = f"原始报文 {res.raw.hex(' ').upper()}"
    return r


def read_all() -> list[Reading]:
    return [read_mouse()]


# ==========================================================================
# 命令行模式
# ==========================================================================
def cli_once() -> None:
    for r in read_all():
        if r.ok:
            print(f"{r.title}: {r.level}%")
            print(f"    {r.detail}")
            if r.extra:
                print(f"    {r.extra}")
        else:
            print(f"{r.title}: 读取失败 —— {r.error}")


# ==========================================================================
# 界面
# ==========================================================================
BG = "#1b1c1f"
PANEL = "#232529"
PANEL2 = "#2b2e33"
FG = "#e8e8ea"
MUTED = "#9aa0a6"
FONT = ("Microsoft YaHei UI", 10)

LEVEL_STYLE = [
    (60, "#5ddc8a", "电量充足"),
    (30, "#f5c451", "电量中等"),
    (0,  "#ff6b6b", "电量偏低"),
]


def level_color(level: Optional[int]) -> str:
    if level is None:
        return MUTED
    for threshold, color, _ in LEVEL_STYLE:
        if level >= threshold:
            return color
    return LEVEL_STYLE[-1][1]


def level_text(level: Optional[int]) -> str:
    if level is None:
        return ""
    for threshold, _, label in LEVEL_STYLE:
        if level >= threshold:
            return label
    return LEVEL_STYLE[-1][2]


class DeviceCard:
    """一块设备卡片。"""

    def __init__(self, parent, title: str):
        from tkinter import ttk

        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=18)
        self.lab_title = ttk.Label(self.frame, text=title, style="CardTitle.TLabel")
        self.lab_title.pack(anchor="w")
        self.lab_sub = ttk.Label(self.frame, text="正在读取…", style="CardSub.TLabel")
        self.lab_sub.pack(anchor="w", pady=(2, 0))

        self.lab_level = ttk.Label(self.frame, text="--", style="CardBig.TLabel")
        self.lab_level.pack(anchor="w", pady=(12, 0))
        self.lab_status = ttk.Label(self.frame, text="", style="CardSub.TLabel")
        self.lab_status.pack(anchor="w")

        self.bar = ttk.Progressbar(self.frame, mode="determinate", maximum=100,
                                   style="Card.Horizontal.TProgressbar")
        self.bar.pack(fill="x", pady=(12, 10))

        self.lab_detail = ttk.Label(self.frame, text="", style="CardSub.TLabel",
                                    wraplength=560, justify="left")
        self.lab_detail.pack(anchor="w")
        self.lab_extra = ttk.Label(self.frame, text="", style="CardSub.TLabel",
                                   wraplength=560, justify="left")
        self.lab_extra.pack(anchor="w", pady=(4, 0))

    def update(self, r: Reading) -> None:
        self.lab_sub.configure(text=r.subtitle)
        if r.ok:
            self.lab_level.configure(text=f"{r.level}%",
                                     foreground=level_color(r.level))
            self.lab_status.configure(text=level_text(r.level),
                                      foreground=level_color(r.level))
            self.bar["value"] = r.level or 0
            self.lab_detail.configure(text=r.detail)
            self.lab_extra.configure(text=r.extra)
        else:
            self.lab_level.configure(text="--", foreground=MUTED)
            self.lab_status.configure(text="", foreground=MUTED)
            self.bar["value"] = 0
            self.lab_detail.configure(text=r.error)
            self.lab_extra.configure(text="")


def build_ui():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(tc.UI_TITLE)
    root.configure(bg=BG)
    root.geometry("700x480")
    root.minsize(620, 440)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, font=FONT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=PANEL)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG, font=FONT)
    style.configure("H1.TLabel", background=BG, foreground=FG,
                    font=("Microsoft YaHei UI", 15, "bold"))
    style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                    font=("Microsoft YaHei UI", 9))
    style.configure("CardTitle.TLabel", background=PANEL, foreground=FG,
                    font=("Microsoft YaHei UI", 12, "bold"))
    style.configure("CardSub.TLabel", background=PANEL, foreground=MUTED,
                    font=("Microsoft YaHei UI", 9))
    style.configure("CardBig.TLabel", background=PANEL, foreground="#5ddc8a",
                    font=("Microsoft YaHei UI", 44, "bold"))
    style.configure("Card.Horizontal.TProgressbar", background="#4f8cff",
                    troughcolor=PANEL2, borderwidth=0, thickness=10)
    style.configure("TButton", background=PANEL2, foreground=FG, borderwidth=0,
                    focusthickness=0, padding=(14, 7), font=FONT)
    style.map("TButton", background=[("active", "#3a3f47"), ("disabled", "#2a2c30")],
              foreground=[("disabled", "#6b7076")])
    style.configure("Accent.TButton", background="#4f8cff", foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#6ea1ff")])
    style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT)
    style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2,
                    foreground=FG)

    state = {"busy": False, "auto": True, "interval": 60, "after_id": None,
             "starting": False, "started_at": 0.0, "notice": "", "notice_until": 0.0}
    # Tkinter 不是线程安全的：后台线程只往队列里放结果，主线程统一取出来处理
    results: "queue.Queue[tuple]" = queue.Queue()

    cfg = tc.load_config()
    state["interval"] = int(cfg["interval"])

    # ---- 顶部 ----
    head = ttk.Frame(root, padding=(18, 16, 18, 8))
    head.pack(fill="x")
    ttk.Label(head, text=tc.UI_TITLE, style="H1.TLabel").pack(side="left")

    v_auto = tk.BooleanVar(value=True)
    v_interval = tk.StringVar(
        value=dict((s, l) for s, l in tc.INTERVAL_CHOICES).get(state["interval"], "1 分钟"))

    def on_auto():
        state["auto"] = v_auto.get()
        _reschedule()

    btn = ttk.Button(head, text="立即刷新", style="Accent.TButton")
    btn.pack(side="right")
    ttk.Checkbutton(head, text="自动刷新", variable=v_auto,
                    command=on_auto).pack(side="right", padx=(0, 12))

    # ---- 卡片 ----
    body = ttk.Frame(root, padding=(18, 4, 18, 4))
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)

    card = DeviceCard(body, "雷柏 VT9 Pro")
    card.frame.grid(row=0, column=0, sticky="nsew")

    foot = ttk.Label(root, text="正在读取…", style="Muted.TLabel", padding=(18, 4))
    foot.pack(fill="x", side="bottom")

    # ---- 设置区 ----
    setbar = ttk.Frame(root, style="Panel.TFrame", padding=(14, 10))
    setbar.pack(fill="x", padx=18, pady=(2, 8))

    def refresh_tray_state():
        if state.get("starting"):
            return
        if state.get("notice") and time.time() < state.get("notice_until", 0):
            lab_tray.configure(text=state["notice"])
            btn_tray.configure(state="normal",
                               text="退出托盘程序" if tc.is_tray_running()
                               else "启动托盘程序")
            return
        state["notice"] = ""
        running = tc.is_tray_running()
        btn_tray.configure(state="normal",
                           text="退出托盘程序" if running else "启动托盘程序")
        lab_tray.configure(text="托盘运行中：右键托盘图标即可打开本窗口"
                                if running else "托盘未运行：不会后台自动刷新")

    def notify(text: str, seconds: float = 8.0) -> None:
        state["notice"] = text
        state["notice_until"] = time.time() + seconds
        refresh_tray_state()

    def on_interval(_event=None):
        sec = dict((label, sec) for sec, label in tc.INTERVAL_CHOICES)[v_interval.get()]
        cfg["interval"] = sec
        tc.save_config(cfg)
        state["interval"] = sec
        tc.post_to_tray(tc.MSG_RELOAD)
        _reschedule()
        refresh()

    def on_boot():
        want = bool(v_boot.get())
        ok = tc.set_autostart(want)
        cfg["autostart"] = want
        tc.save_config(cfg)
        tc.post_to_tray(tc.MSG_RELOAD)
        if want and not ok:
            notify("开机自启设置失败：无法创建启动文件夹快捷方式")
        elif want:
            notify("已加入开机自启（任务管理器 →「启动」标签里能看到 电量托盘）", 12)
        else:
            notify("已取消开机自启")

    def tray_done(ok: bool):
        state["starting"] = False
        refresh_tray_state()
        if not ok:
            notify("启动失败：可双击桌面「电量托盘」再试", 12)

    def on_links():
        btn_link.configure(state="disabled", text="正在创建…")

        def work():
            try:
                r = tc.install_desktop_links()
            except Exception as e:
                traceback.print_exc()
                r = {"folder": "", "links": {}, "errors": [str(e)]}
            results.put(("links", r))

        threading.Thread(target=work, daemon=True).start()

    def links_done(r: dict):
        import tkinter.messagebox as mb
        btn_link.configure(state="normal", text="重建桌面链接")
        bits = []
        kind = r.get("folder") or ""
        if kind:
            bits.append(f"文件夹→{win_link.KIND_LABEL.get(kind, kind)}")
        for name, k in (r.get("links") or {}).items():
            bits.append(f"{name}→{win_link.KIND_LABEL.get(k, k)}")
        if bits:
            notify("桌面链接已更新：" + "；".join(bits), 12)
        else:
            notify("桌面链接创建失败", 12)
        if r.get("errors"):
            mb.showwarning("桌面链接", "\n".join(r["errors"]))

    def on_tray_toggle():
        if tc.is_tray_running():
            tc.post_to_tray(tc.MSG_QUIT)
            for delay in (600, 1500, 3000):
                root.after(delay, refresh_tray_state)
            return

        state["starting"] = True
        state["started_at"] = time.time()
        btn_tray.configure(state="disabled", text="正在启动…")
        lab_tray.configure(text="正在启动托盘程序…")

        def work():
            try:
                ok = tc.start_tray_app()
            except Exception:
                traceback.print_exc()
                ok = False
            results.put(("tray", ok))

        threading.Thread(target=work, daemon=True).start()

    row_a = ttk.Frame(setbar, style="Panel.TFrame")
    row_a.pack(fill="x")
    row_b = ttk.Frame(setbar, style="Panel.TFrame")
    row_b.pack(fill="x", pady=(9, 0))

    ttk.Label(row_a, text="设置", style="CardTitle.TLabel").pack(side="left")
    ttk.Label(row_a, text="刷新间隔", style="CardSub.TLabel").pack(side="left", padx=(16, 6))
    combo = ttk.Combobox(row_a, textvariable=v_interval, width=8, state="readonly",
                         values=[label for _, label in tc.INTERVAL_CHOICES])
    combo.pack(side="left")
    combo.bind("<<ComboboxSelected>>", on_interval)

    v_boot = tk.BooleanVar(value=tc.is_autostart_enabled())
    ttk.Checkbutton(row_a, text="开机自启（任务管理器可见）", variable=v_boot,
                    command=on_boot).pack(side="left", padx=(18, 0))

    btn_tray = ttk.Button(row_b, text="退出托盘程序", command=on_tray_toggle)
    btn_tray.pack(side="right")
    btn_link = ttk.Button(row_b, text="重建桌面链接", command=on_links)
    btn_link.pack(side="right", padx=(0, 8))
    lab_tray = ttk.Label(row_b, text="", style="CardSub.TLabel")
    lab_tray.pack(side="right", padx=(0, 12))
    refresh_tray_state()

    # ---- 刷新逻辑 ----
    def apply(readings: list[Reading]):
        card.update(readings[0])
        ok = 1 if readings[0].ok else 0
        foot.configure(text=f"更新于 {time.strftime('%H:%M:%S')}   "
                            f"成功读取 {ok}/1 个设备"
                            + ("" if state["auto"] else "   （自动刷新已关闭）"))
        state["busy"] = False
        btn.configure(state="normal")

    def worker():
        try:
            readings = read_all()
        except Exception:
            traceback.print_exc()
            readings = [Reading("雷柏 VT9 Pro", "", error="读取异常")]
        results.put(("readings", readings))

    def refresh():
        if state["busy"]:
            return
        state["busy"] = True
        btn.configure(state="disabled")
        foot.configure(text="正在读取…（设备每 3 秒上报一次，最多等 6 秒）")
        threading.Thread(target=worker, daemon=True).start()

    def _reschedule():
        if state["after_id"]:
            root.after_cancel(state["after_id"])
            state["after_id"] = None
        if state["auto"]:
            state["after_id"] = root.after(state["interval"] * 1000, _tick)

    def _tick():
        refresh()
        _reschedule()

    btn.configure(command=refresh)

    root.after(300, refresh)
    _reschedule()

    def pump():
        try:
            while True:
                kind, payload = results.get_nowait()
                if kind == "readings":
                    apply(payload)
                elif kind == "tray":
                    tray_done(payload)
                elif kind == "links":
                    links_done(payload)
        except queue.Empty:
            pass
        except Exception:
            traceback.print_exc()
            state["busy"] = False
            state["starting"] = False
            btn.configure(state="normal")

        if state["starting"] and time.time() - state["started_at"] > 20:
            state["starting"] = False
            refresh_tray_state()

        refresh_tray_state()
        root.after(1000, pump)

    root.after(1000, pump)

    def raise_me():
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass
    root.after(250, raise_me)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="雷柏 VT9 Pro 电量")
    parser.add_argument("--once", action="store_true", help="命令行读一次就退出")
    parser.add_argument("--install-links", action="store_true",
                        help="在桌面重建软连接（项目文件夹 + 启动脚本）")
    parser.add_argument("--autostart", choices=["on", "off", "status"],
                        help="开机自启：on 打开 / off 关闭 / status 查看")
    args = parser.parse_args()

    if args.install_links:
        r = tc.install_desktop_links()
        print("桌面链接：")
        print(f"  项目文件夹 {tc.DESKTOP_LINK_NAME} -> "
              f"{win_link.KIND_LABEL.get(r['folder'], r['folder'] or '创建失败')}")
        for name, kind in r["links"].items():
            print(f"  {name} -> {win_link.KIND_LABEL.get(kind, kind)}")
        for msg in r["errors"]:
            print("  注意：", msg)
        return

    if args.autostart:
        if args.autostart == "status":
            st = tc.autostart_status()
            print("开机自启：", "已启用" if st["enabled"] else "未启用")
            print("  方式：", st["method"])
            print("  快捷方式：", st["shortcut"],
                  "(存在)" if st["shortcut_exists"] else "(不存在)")
            print("  任务管理器状态：", st["taskmanager_state"])
            print("  目标：", st["target"])
            print("  旧注册表项：", "还在" if st["legacy_registry"] else "已清理")
        else:
            ok = tc.set_autostart(args.autostart == "on")
            print("已" + ("加入" if args.autostart == "on" else "取消") + "开机自启",
                  "" if ok else "（失败）")
        return

    if args.once:
        cli_once()
        return
    try:
        root = build_ui()
    except Exception:
        print("无法启动图形界面，改用命令行模式：")
        traceback.print_exc()
        cli_once()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
