# APP UI 自动化方案（第一版）

> 状态：方案沉淀 / 待实施  
> 范围：Android 模拟器 + 原生 APP UI 自动化  
> 目标：在不推翻现有 Web UI 自动化架构的前提下，新增一条 APP 执行链路

---

## 1. 背景与结论

当前 UI 自动化模块基于 Playwright，主要面向浏览器页面，核心链路是：

```text
前端用例 / 步骤
    ↓
Django 调度
    ↓
WHartTest_Actuator
    ↓
Playwright
    ↓
浏览器页面
```

它不能直接用于 APP UI 自动化，原因包括：

- 页面模型基于 URL
- 元素定位方式是 Web 定位器
- 执行器依赖 Playwright 浏览器上下文
- 录制器依赖浏览器 DOM 与 JS 注入
- Trace、截图、登录态能力均基于浏览器

本方案不重写现有 UI 自动化，而是在现有体系上新增 **APP 执行能力**，并优先支持 **Android 模拟器 + 原生 APP**。

第一版推荐方案：

```text
Android Emulator
    ↓
ADB / Appium UiAutomator2
    ↓
WHartTest_Actuator
    ↓
现有 UI 自动化调度体系
```

---

## 2. 第一版目标

第一版只做最小闭环，目标是能完成一次完整的 APP UI 用例执行：

1. 支持管理 Android 模拟器配置
2. 支持启动、停止模拟器
3. 支持安装、启动 APP
4. 支持基于 Appium UiAutomator2 执行 APP 元素操作
5. 支持截图记录
6. 支持执行结果写入现有执行记录体系
7. 支持前端查看执行状态与截图
8. 支持简单的 APP 元素点选采集

第一版不做：

- iOS Simulator
- 云真机
- 复杂手势录制
- 高帧率视频直播
- AI 自动修复 APP 元素
- 大规模并发设备池
- 混合 APP 的深度 WebView 调试

---

## 3. 总体架构

```text
WHartTest_Vue
  └─ APP UI 自动化页面
      ├─ 模拟器管理
      ├─ APP 页面 / 元素 / 步骤 / 用例
      ├─ 执行记录
      └─ 执行画面

WHartTest_Django
  ├─ ui_automation
  │   ├─ 模块 / 页面 / 元素 / 步骤 / 用例
  │   ├─ 执行记录
  │   ├─ APP 环境配置
  │   └─ 设备配置
  └─ WebSocket
      ├─ /ws/ui/web/
      └─ /ws/ui/actuator/

WHartTest_Actuator
  ├─ PlaywrightExecutor          # 现有 Web 执行
  ├─ AppiumExecutor              # 新增 APP 执行
  ├─ EmulatorManager             # 新增模拟器管理
  ├─ AdbManager                  # 新增 ADB 管理
  ├─ DeviceManager               # 新增设备池管理
  └─ AppScreenStreamer           # APP 截图流

Android Emulator
  └─ Android SDK / AVD / ADB

Appium Server
  └─ UiAutomator2 Driver
```

核心原则：

- 调度体系复用现有 WebSocket 通道
- 用例、步骤、执行记录复用现有模型
- APP 执行器与 Web 执行器并列，不混入 Playwright 逻辑
- 模拟器由 Actuator 侧管理，Django 只保存配置与状态

---

## 4. 技术选型

### 4.1 模拟器

第一版使用：

```text
Android Emulator + AVD
```

依赖：

- Android SDK
- Android Platform Tools / ADB
- Android Emulator
- AVD 系统镜像

推荐使用系统镜像：

```text
Android 13 / API 33
或 Android 14 / API 34
```

### 4.2 自动化引擎

第一版使用：

```text
Appium 2.x
UiAutomator2 Driver
appium-python-client
```

安装：

```bash
npm install -g appium
appium driver install uiautomator2
```

Python 依赖：

```bash
pip install Appium-Python-Client
```

### 4.3 不使用 Appium 自动启动模拟器的原因

Appium 支持 `avd` 能力自动启动模拟器，但第一版建议由 Actuator 自己管理模拟器，原因：

1. 便于后续接入真机、云设备
2. 便于维护模拟器生命周期状态
3. 便于执行前做预启动、预热
4. 便于设备池化与并发控制

---

## 5. 数据模型设计

### 5.1 UiPage 扩展

现有 `UiPage` 已有：

```python
name
url
description
```

新增字段建议：

```python
target_type = models.CharField(
    _("目标类型"),
    max_length=16,
    choices=[("web", "Web"), ("app", "APP")],
    default="web",
)

app_package = models.CharField(
    _("APP 包名"),
    max_length=128,
    null=True,
    blank=True,
)

app_activity = models.CharField(
    _("APP Activity"),
    max_length=256,
    null=True,
    blank=True,
)

app_screen_name = models.CharField(
    _("APP 页面名称"),
    max_length=128,
    null=True,
    blank=True,
)
```

说明：

- `target_type=web`：继续使用现有 Playwright 执行
- `target_type=app`：走新增 Appium 执行链路
- `app_package` / `app_activity` 用于启动 APP
- `app_screen_name` 用于前端展示，例如“登录页”“首页”“设置页”

### 5.2 UiElement 扩展

现有元素定位类型以 Web 为主：

```python
css
xpath
text
role
label
placeholder
test_id
id
name
```

新增字段：

```python
target_type = models.CharField(
    _("目标类型"),
    max_length=16,
    choices=[("web", "Web"), ("app", "APP")],
    default="web",
)
```

同时扩展 `LOCATOR_TYPE_CHOICES`：

```python
accessibility_id
android_id
android_xpath
uiautomator
class_name
```

第一版推荐定位优先级：

```text
1. accessibility_id
2. android_id
3. uiautomator
4. android_xpath
```

原因：

- `accessibility_id` 稳定性最好
- `android_id` 次之
- `uiautomator` 表达能力强
- `android_xpath` 尽量只作为兜底

### 5.3 UiDeviceProfile 新增

新增设备配置模型，用于模拟器管理。

字段建议：

```python
class UiDeviceProfile(models.Model):
    """APP 自动化设备配置"""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="ui_device_profiles",
        verbose_name=_("所属项目"),
    )

    name = models.CharField(_("设备名称"), max_length=64)
    platform = models.CharField(
        _("平台"),
        max_length=16,
        choices=[("android", "Android"), ("ios", "iOS")],
        default="android",
    )

    device_type = models.CharField(
        _("设备类型"),
        max_length=16,
        choices=[("emulator", "模拟器"), ("real", "真机")],
        default="emulator",
    )

    avd_name = models.CharField(_("AVD 名称"), max_length=128)
    android_version = models.CharField(_("Android 版本"), max_length=32)
    device_name = models.CharField(_("Device Name"), max_length=128)

    udid = models.CharField(
        _("设备 UDID"),
        max_length=128,
        null=True,
        blank=True,
    )

    cpu_core = models.PositiveIntegerField(_("CPU 核数"), default=4)
    ram_size_mb = models.PositiveIntegerField(_("内存"), default=4096)
    screen_resolution = models.CharField(_("分辨率"), max_length=32)

    headless = models.BooleanField(_("无窗口模式"), default=True)
    snapshot_enabled = models.BooleanField(_("启用快照"), default=True)

    status = models.CharField(
        _("状态"),
        max_length=32,
        choices=[
            ("stopped", _("已停止")),
            ("starting", _("启动中")),
            ("running", _("运行中")),
            ("stopping", _("停止中")),
            ("error", _("异常")),
        ],
        default="stopped",
    )

    description = models.TextField(_("描述"), blank=True, null=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_ui_device_profiles",
        verbose_name=_("创建人"),
    )
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        verbose_name = _("APP 设备配置")
        verbose_name_plural = _("APP 设备配置")
        ordering = ["-id"]
        db_table = "ui_device_profile"
```

第一版中，`device_type` 固定为 `emulator`，`platform` 固定为 `android`，但字段预留扩展能力。

---

## 6. Actuator 侧设计

### 6.1 新增模块

建议在 `WHartTest_Actuator/` 下新增：

```text
appium_executor.py
emulator_manager.py
adb_manager.py
device_manager.py
app_screen_streamer.py
app_capabilities.py
```

职责划分：

| 模块 | 职责 |
|---|---|
| `adb_manager.py` | 封装 adb 命令，检查设备状态，安装/卸载 APP |
| `emulator_manager.py` | 启动、停止、重启 AVD |
| `device_manager.py` | 管理设备槽位与并发 |
| `appium_executor.py` | 通过 Appium UiAutomator2 执行 APP 步骤 |
| `app_screen_streamer.py` | 截图轮询并通过 WebSocket 推送画面 |
| `app_capabilities.py` | 构建 Appium capabilities |

### 6.2 执行器能力上报

现有执行器上报包含：

```text
browser_type
supported_browsers
max_slots
headless
```

需要扩展为：

```json
{
  "type": "ui",
  "capabilities": {
    "web": {
      "supported_browsers": ["chromium", "firefox"]
    },
    "app": {
      "supported_platforms": ["android"],
      "supported_device_types": ["emulator"],
      "max_device_slots": 1,
      "installed_tools": ["adb", "appium", "uiautomator2"]
    }
  }
}
```

Django 调度时根据用例类型选择执行器：

```text
target_type=web → PlaywrightExecutor
target_type=app → AppiumExecutor
```

---

## 7. 模拟器管理流程

### 7.1 启动流程

```text
用户点击启动
    ↓
Django 下发启动指令到 Actuator
    ↓
EmulatorManager 检查 AVD 是否存在
    ↓
分配设备槽位
    ↓
启动 emulator
    ↓
等待 adb device
    ↓
等待 sys.boot_completed
    ↓
更新设备状态为 running
    ↓
回传启动结果
```

### 7.2 停止流程

```text
用户点击停止
    ↓
Django 下发停止指令到 Actuator
    ↓
检查是否有执行中的用例
    ↓
无执行则停止模拟器
    ↓
更新设备状态为 stopped
    ↓
释放设备槽位
```

### 7.3 启动命令示例

```bash
emulator -avd Pixel_6_API_34 \
  -port 5554 \
  -no-window \
  -no-audio \
  -no-boot-anim \
  -gpu swiftshader_indirect
```

等待设备上线：

```bash
adb wait-for-device
adb shell getprop sys.boot_completed
```

只有 `sys.boot_completed=1` 才认为启动成功。

---

## 8. APP 执行流程

### 8.1 执行链路

```text
前端触发 APP 用例执行
    ↓
Django 校验用例 / 页面 / 元素 / 设备
    ↓
判断 target_type == app
    ↓
选择支持 Android 模拟器的 Actuator
    ↓
下发任务到 Actuator
    ↓
Actuator 启动模拟器
    ↓
等待设备就绪
    ↓
构建 Appium capabilities
    ↓
创建 Appium Session
    ↓
安装 / 启动 APP
    ↓
按页面步骤执行
    ↓
每步截图
    ↓
失败记录错误与截图
    ↓
回传执行结果
    ↓
Django 保存 UiExecutionRecord
    ↓
前端展示执行结果
```

### 8.2 Appium capabilities 示例

```python
capabilities = {
    "platformName": "Android",
    "automationName": "UiAutomator2",
    "deviceName": "Pixel_6_API_34",
    "avd": "Pixel_6_API_34",
    "avdLaunchTimeout": 120000,
    "avdReadyTimeout": 120000,
    "appPackage": "com.example.app",
    "appActivity": ".MainActivity",
    "noReset": False,
    "fullReset": False,
    "newCommandTimeout": 300,
    "autoGrantPermissions": True,
}
```

如果 Actuator 已经提前启动模拟器，则 `avd` 能力不是必须项，可改为指定 `udid`：

```python
capabilities = {
    "platformName": "Android",
    "automationName": "UiAutomator2",
    "deviceName": "Pixel_6_API_34",
    "udid": "emulator-5554",
    "appPackage": "com.example.app",
    "appActivity": ".MainActivity",
    "autoGrantPermissions": True,
}
```

---

## 9. APP 元素采集方案

第一版提供简单可用的元素点选能力。

流程：

```text
选择模拟器
    ↓
启动 APP
    ↓
进入目标页面
    ↓
采集控件树
    ↓
前端展示控件树
    ↓
用户点选控件
    ↓
生成定位表达式
    ↓
保存 UiElement
```

### 9.1 控件树采集

优先使用：

```python
driver.page_source
```

备选：

```bash
adb shell uiautomator dump
```

推荐使用 Appium 控件树，因为结构更统一，解析更稳定。

### 9.2 定位生成规则

按以下优先级生成：

1. `accessibility-id`
2. `resource-id`
3. `UiAutomator`
4. `xpath`

示例：

```json
{
  "locator_type": "accessibility_id",
  "locator_value": "login_button"
}
```

如果只有文本可用：

```json
{
  "locator_type": "uiautomator",
  "locator_value": "new UiSelector().text(\"登录\")"
}
```

### 9.3 第一版录制范围

第一版只支持以下基础操作：

```text
点击
长按
输入
清空
等待
断言元素存在
断言元素可见
断言文本相等
```

暂不支持：

```text
滑动
拖拽
多指手势
复杂控件操作
```

---

## 10. 执行画面方案

第一版采用截图轮询方式。

```text
Actuator
    ↓
Appium Driver / ADB
    ↓
截图 PNG / JPEG
    ↓
WebSocket
    ↓
前端执行画面
```

建议频率：

```text
执行中：1~3 fps
元素采集：3~5 fps
```

第一版不追求实时视频直播，目标是能看到设备状态与执行过程。

### 10.1 后续优化方向

后续可接入：

```text
scrcpy
minicap
adb screenrecord
```

实现更高帧率画面直播与录像。

---

## 11. 后端接口设计

### 11.1 设备管理接口

新增或扩展：

```text
GET    /api/ui/devices/
POST   /api/ui/devices/
PUT    /api/ui/devices/{id}/
DELETE /api/ui/devices/{id}/

POST   /api/ui/devices/{id}/start/
POST   /api/ui/devices/{id}/stop/
POST   /api/ui/devices/{id}/restart/

GET    /api/ui/devices/{id}/status/
```

### 11.2 APP 管理接口

```text
GET    /api/ui/devices/{id}/apps/
POST   /api/ui/devices/{id}/apps/install/
POST   /api/ui/devices/{id}/apps/uninstall/
POST   /api/ui/devices/{id}/apps/start/
POST   /api/ui/devices/{id}/apps/stop/
```

### 11.3 元素采集接口

```text
GET    /api/ui/devices/{id}/elements/
POST   /api/ui/devices/{id}/elements/select/
```

说明：

- `elements/` 返回当前 APP 控件树
- `elements/select/` 根据控件信息生成定位表达式

### 11.4 执行画面接口

第一版可复用现有 WebSocket 通道，不新增 REST 接口。

---

## 12. 前端页面设计

### 12.1 页面结构

在 UI 自动化模块下新增：

```text
APP 自动化
  ├─ 模拟器管理
  ├─ APP 页面管理
  ├─ APP 元素管理
  ├─ APP 步骤管理
  ├─ APP 用例
  ├─ 执行记录
  └─ 环境配置
```

### 12.2 模拟器管理页

页面包含：

- 设备名称
- Android 版本
- 分辨率
- CPU / 内存
- 状态
- Appium 状态
- 操作按钮：
  - 启动
  - 停止
  - 重启
  - 打开画面
  - 安装 APK
  - 查看日志

### 12.3 APP 元素采集页

页面布局建议：

```text
左侧：模拟器画面
右侧：控件树
下方：生成定位表达式与保存按钮
```

支持：

- 点选控件
- 查看定位类型
- 查看定位表达式
- 保存元素
- 添加到页面步骤

---

## 13. 实施步骤

### 阶段 1：模拟器管理闭环

目标：能从平台创建并启动 Android 模拟器。

任务：

1. 新增 `UiDeviceProfile`
2. 编写迁移
3. 新增设备管理 ViewSet
4. Actuator 新增 `adb_manager.py`
5. Actuator 新增 `emulator_manager.py`
6. 实现 WebSocket 指令：
   - start_device
   - stop_device
   - device_status
7. 前端新增模拟器管理页面

验收标准：

```text
能创建 AVD 配置
能启动模拟器
能停止模拟器
能看到设备状态
```

---

### 阶段 2：APP 执行能力

目标：Actuator 能执行一个简单 APP 用例。

任务：

1. 新增 `appium_executor.py`
2. 实现 Appium session 创建
3. 实现 APP 安装 / 启动 / 关闭
4. 实现 APP 元素定位
5. 实现基础操作：
   - click
   - input
   - clear
   - wait
   - assert
6. 对接现有步骤模型
7. 保存执行截图

验收标准：

```text
能执行一个包含点击与输入的 APP 用例
每一步有截图
执行结果写入 UiExecutionRecord
```

---

### 阶段 3：执行画面与结果展示

目标：执行时能看到模拟器画面。

任务：

1. 新增 `app_screen_streamer.py`
2. 定时截图
3. 通过 WebSocket 推送
4. 前端复用执行画面组件
5. 保存失败截图
6. 保存执行录像

验收标准：

```text
执行中能看到模拟器画面
失败步骤能查看截图
执行记录能回放
```

---

### 阶段 4：APP 元素采集

目标：可视化生成 APP 元素。

任务：

1. 实现控件树采集
2. 前端渲染控件树
3. 支持点选控件
4. 生成定位表达式
5. 保存 `UiElement`
6. 支持将元素加入步骤

验收标准：

```text
能采集 APP 当前页面控件树
能点选控件生成定位
能保存元素
能用于后续步骤执行
```

---

### 阶段 5：调度能力完善

目标：平台能正确区分 Web 与 APP 用例。

任务：

1. Actuator 上报 APP capability
2. 调度逻辑按 `target_type` 分发
3. 环境配置增加 APP 字段
4. 执行前校验：
   - Actuator 是否支持 Android
   - Appium 是否可用
   - ADB 是否可用
   - 模拟器是否可启动

验收标准：

```text
Web 用例不会误调 APP 执行器
APP 用例能正确调度到支持模拟器的执行器
执行失败时返回明确原因
```

---

## 14. 第一版验收标准

第一版完成后，应满足以下条件：

1. 可创建 Android 模拟器配置
2. 可启动、停止模拟器
3. 可安装、启动、停止 APP
4. 可执行包含点击与输入的 APP UI 用例
5. 每个步骤生成截图
6. 失败用例记录失败原因与截图
7. 执行结果写入现有 `UiExecutionRecord`
8. 前端可查看执行状态、执行耗时、截图
9. 支持基于控件树生成简单 APP 元素

---

## 15. 关键风险与应对

| 风险 | 说明 | 应对 |
|---|---|---|
| 模拟器启动慢 | AVD 启动可能超过 1 分钟 | 支持预启动 / 常驻模拟器 |
| 元素定位不稳定 | APP 控件经常缺少 ID | 优先 accessibility_id，少用 XPath |
| Appium 环境复杂 | Java / SDK / Appium 版本敏感 | 执行器启动时做环境自检 |
| WebView 场景复杂 | Hybrid APP 需要切换 context | 第一版暂不深度支持 |
| 截图流帧率低 | `screencap` / Appium 截图速率有限 | 第一版接受低帧率，后期接 scrcpy |
| 资源占用高 | 模拟器 + Appium 占用资源较多 | 第一版限制单 Actuator 最多 1~2 台模拟器 |

---

## 16. 后续演进方向

第一版稳定后再逐步扩展：

1. iOS Simulator
2. Android 真机
3. 云真机
4. 高帧率画面直播
5. 滑动、拖拽、多点触控
6. Hybrid / WebView 自动化
7. APP Trace 与日志分析
8. AI 元素自愈
9. AI 生成 APP 用例

---

## 17. 推荐配置

### 17.1 Actuator 部署机

第一版建议配置：

```text
CPU：8 核及以上
内存：16GB 及以上
磁盘：100GB 及以上
系统：Windows 10/11 或 Linux
```

如果只跑一台模拟器：

```text
CPU：4~6 核
内存：8~12GB
```

### 17.2 Android SDK

```bash
ANDROID_HOME=/path/to/android-sdk
ANDROID_SDK_ROOT=/path/to/android-sdk
```

必须包含：

```text
platform-tools
emulator
cmdline-tools
system-images
```

### 17.3 Appium

```bash
npm install -g appium
appium driver install uiautomator2
```

启动：

```bash
appium --port 4723 --allow-insecure=adb_shell
```

---

## 18. 交付物清单

第一版需要交付：

1. `UiDeviceProfile` 模型与迁移
2. 设备管理接口
3. Actuator 模拟器管理模块
4. Actuator APP 执行模块
5. APP 截图流模块
6. APP 元素采集模块
7. 前端模拟器管理页面
8. 前端 APP 元素采集页面
9. APP 执行记录展示
10. 环境自检与调度校验
11. 使用文档与部署说明
