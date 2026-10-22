# 雷柏 VT9 Pro 电量

Windows 上读取**雷柏 VT9 Pro** 2.4G 无线鼠标电量的小工具。
**纯 ctypes 调系统 DLL，零第三方依赖**——不用 hidapi、不用 pystray、不用 Pillow、不用 pywin32，装了 Python 就能跑。

## 协议（本机实测逆向，非猜测）

| 项 | 值 |
|---|---|
| 设备 | `24AE:185A`「Rapoo Gaming Device」（VT9PRO_Wireless） |
| 接口 | usage page `0xFF00`，usage `0x0002`，输入/输出各 **7 字节**，**无 Feature Report** |
| 上报方式 | **被动广播**，每 **3 秒**一包，不需要也不能主动查询 |
| 报文 | `BB B0 42 20 03 01 <电量>` |
| 电量位置 | **第 7 字节（索引 6）**，0–100 |

### 为什么是"被动听"而不是"主动问"

雷柏 VT9 Pro 的写通道被固件封死了。实测结论：

- `HidD_SetOutputReport` 对任何 Report ID（0–15）、任何长度（6/7/8/20/31/32/33）
  一律返回 `ERROR_INVALID_FUNCTION(1)`
- `WriteFile` 一律返回 `ERROR_INVALID_PARAMETER(87)`
- `HidD_SetFeature` 同样全部失败（设备 `feature_len = 0`，本就没有 Feature Report）
- 同设备另有一个 `0xFF00:0x000E` 的 32 字节接口，实测**从不上报任何报文**

所以这个型号只能"听"。好消息是设备很勤快——**每 3 秒主动广播一次电量**，
打开面板最多等 3 秒就能拿到值，比主动轮询还省事。

### 验证过程

1. 枚举全部 HID 接口 → 定位 `24AE:185A` 的两个厂商私有接口
2. 被动监听 6 秒 → 抓到 `BB B0 42 20 03 01 64`，末字节 `0x64` = **100**
3. 监听 60 秒 → 稳定每 3 秒一包，共 20 包
4. 隔一段时间再听 → 变成 `... 63` = **99**，与鼠标实际放电一致 ✅
5. 交叉验证：雷柏官方驱动配置里 `vid=9390(0x24AE)`、`pid=6234(0x185A)`，设备名 `VT9PRO_Wireless`

## 使用方法

```bash
python my_devices.py              # 打开界面
python my_devices.py --once       # 命令行读一次就退出
python rapoo_proto.py             # 只看协议层（调试用，会打印原始报文）
python tray_app.py --debug        # 托盘前台运行并输出日志
```

面板里显示电量、进度条、数据来源和原始报文，默认自动刷新，底部可改刷新间隔。

## 开机自启

已配置为「启动」文件夹里的快捷方式（`电量托盘.lnk`），
**任务管理器 →「启动」标签**里能直接看到「电量托盘」，可以随时启用/禁用。

```bash
python my_devices.py --autostart on      # 开启
python my_devices.py --autostart off     # 关闭
python my_devices.py --autostart status  # 查看
```

快捷方式目标是 `pythonw.exe` + `tray_app.py`，**不弹黑窗**。

## 托盘交互

- **右键图标** → 打开/前置简洁面板（已开则不重复开）
- **左键图标** → 立刻刷新一次
- **悬停** → 显示「雷柏 VT9 Pro：99%（更新时间）」
- 图标内容就是电量数字，颜色随电量变化：≥60 绿 / 30–59 黄 / <30 红

## 文件说明

| 文件 | 说明 |
|---|---|
| `rapoo_proto.py` | **雷柏协议**：接口查找、报文解析、电量读取 |
| `hid_win.py` | HID 底层：枚举接口、Feature Report 读写、异步 Input Report |
| `my_devices.py` | **主界面**（简洁面板） |
| `tray_app.py` | 托盘程序（`Shell_NotifyIconW` + `SetTimer`，空闲几乎不占 CPU） |
| `tray_common.py` | 配置、开机自启、进程间消息 |
| `win_icon.py` | 点阵数字 → ICO → HICON（图标就是电量数字） |
| `win_link.py` | 软连接：符号链接 / 目录 junction / 硬链接，按权限自动降级 |
| `win_shell.py` | 已知文件夹路径 + 用 ctypes COM 创建 `.lnk` |

## 两个值得一提的实现细节

1. **同一 HID 句柄上并发「阻塞读 + 写」会直接杀掉进程**（连异常栈都没有）。
   正确做法是独立的 `FILE_FLAG_OVERLAPPED` 读句柄 + 事件超时 + `CancelIoEx`。
2. **销毁托盘窗口后必须 `PostQuitMessage(0)`**。只调 `DestroyWindow` 会留下
   「窗口和图标都没了、但进程还活着」的僵尸进程，它占着单实例锁，导致之后再启动都没反应。

## 隐私

- **不联网**：没有任何 http / socket / urllib / 遥测调用，所有读取都在本地 HID 层完成
- **不写日志**：默认不产生任何日志文件；只有 `--debug` 时才往控制台打印
- **不上传**：设备信息只在内存里用，不落盘

## 说明

协议是通过本机抓包分析得到的，仅供学习与个人使用。
换别的雷柏型号时，报文格式可能不同——先用 `rapoo_proto.py` 打印原始报文确认。
