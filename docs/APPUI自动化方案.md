# APP UI 自动化方案（第一版）

> 状态：方案沉淀 / 阶段 1、2 已实施  
> 范围：Android 模拟器 + 原生 APP UI 自动化  
> 目标：在不推翻现有 Web UI 自动化架构的前提下，新增一条 APP 执行链路
>
> **实施进度（2026-11-27）**：
> - ✅ 阶段 1 模拟器管理闭环（含按 AVD 名识别、动态端口、结果落库，自测 selftest_app_device.py 12 通过）
> - ✅ 阶段 2 APP 执行能力（AppiumExecutor 已接线执行链路，APP 用例执行闭环，自测 selftest_app_case.py 15 通过）
> - ✅ 阶段 2 增强（2026-11-27 链路联调修复）：执行器账号 API 权限（manage.py grant_actuator_perms）、任务来源登记与结果校验（task_token）、执行人兜底落库、步骤截图上传后端（screenshots/upload/）并可前端展示、未绑定设备自动选用在线设备（模拟器优先）、异常后 Appium session 自动恢复、Web/录制器入口拦截 APP 用例（防误入 Playwright 链路）、APP 步骤前端拖拽排序与上下移动、执行器失活连接自动清理 + 手动断开接口
> - ✅ 阶段 3 执行画面（2026-11-27，方案 A：adb 截图轮询流，见第 19 章协议）：AppScreenStreamer 接线 TaskConsumer（u_app_screen_start/frame/input/status/stop 五消息全实现）、Django 按 user 定向转发帧（不走组广播）、前端 DeviceProfileList「画面」入口 + AppScreenViewer 组件（画布点击/滑动注入、文本/返回/HOME 注入、推流状态角标）；失败步骤截图已可上传与查看 ✅；⬜ 执行录像未做（第一版可接受）
> - ✅ 阶段 4 APP 元素采集与点选录制（2026-11-27）：app_elements.py 控件树解析（uiautomator dump XML，可交互节点过滤）、定位生成按 accessibility_id → resource_id → uiautomator → xpath 优先级、画面点选即命中控件生成步骤（录制模式）、录制步骤列表一键保存为 APP 用例（testCaseApi.create）；执行互斥：用例执行期间推流自动降频 2fps→0.5fps
> - ◐ 阶段 5 部分完成：执行器已上报 app_capability（installed_tools/is_ready）、前后端入口按 case_type 分流；⬜ 环境配置 APP 字段、执行前完整环境校验待做
>
> 联调自测：selftest_app_case_route.py（转发/登记/校验 9 通过）、selftest_actuator_disconnect.py（失活清理/断开 11 通过）、selftest_screen_elements.py（画面/解析/推流 12 断言通过）、selftest_app_screen_route.py（帧定向转发/元素路由 9 通过）
>
> 首轮联调修复（2026-11-27 12:03）：①横屏模拟器 tap 坐标错位——wm size 返回未旋转尺寸（900x1600），screen_size 改用截图 PNG IHDR 解析（实测 1600x900，tap 桌面图标启动 APP 验证通过）；②adb input text 不支持中文（静默丢字符）——非 ASCII 明确拒绝并经 APP_SCREEN_STATUS(scope=input) 回传前端提示，ASCII 特殊字符（@ 等）转义修复；③录制保存用例 400——module 为必填外键不可传 null，画面组件加模块下拉必选。自测 selftest_screen_fix.py 通过
>
> 二轮联调修复（2026-11-27 14:06）：④元素采集报 "could not get idle state"——页面持续动画（EMS 仪表盘图表）致 uiautomator dump 无法进入 idle；两级采集链：adb dump（清理残留 pkill + 递增重试）→ 失败降级 Appium（forceAppLaunch=false attach 前台应用 + waitForIdleTimeout=0 绕过 idle 检测，attach 后需等 3s a11y 树就绪）；⑤解析器兼容两种 XML 格式（uiautomator dump 用 &lt;node&gt; 标签、Appium page_source 用类名标签）；⑥**坐标系根因修正**：模拟器显示方向随前台 APP 动态切换（portrait app 前台时系统转回竖屏），分辨率不能缓存，改为每帧从 PNG IHDR 头解析更新（推流与 tap/控件树坐标系始终与画面一致）；⑦录制步骤列表超长溢出弹窗——右侧面板改 flex 自适应内部滚动。Appium server 由平台负责启动（appium --port 4723）。自测 selftest_screen_elements.py 回归通过、test_coord_mapping.py 实验定位坐标系根因
>
> 与原方案的实现差异：
> - APP 用例为平铺步骤（`UiTestCase.case_type='app'` + `app_steps` JSON），暂未走页面/元素体系
> - 模拟器识别按 AVD 名（`adb emu avd name`），端口动态分配（5556 起步），因为本机第三方模拟器会抢占 5554
> - APP 用例执行消息为 `u_app_test_case`，结果复用 `u_case_result`，由 `save_execution_result` 落库

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

状态：⬜ 待实施。画面嵌入页面的方案对比、消息协议与验收标准见 **第 19 章**（推荐 adb 截图轮询流先行，scrcpy 视频流升级）。

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

---

## 19. 待办：模拟器画面嵌入页面方案评估

> 状态：待实施（对应阶段 3）  
> 需求：在平台页面上实时查看模拟器画面并进行基本操作，而不是只在本地启动模拟器窗口  
> 评估时间：2026-11-26

### 19.1 方案对比

| 方案 | 原理 | 帧率/延迟 | 工作量 | 评估结论 |
|---|---|---|---|---|
| **A. adb 截图轮询流** | 执行器循环 `adb exec-out screencap` → WS 推帧 → 前端 canvas/img；操作反向下发 `adb input tap` | 2~5 fps / ~300ms | 1~2 天 | **第一阶段采用**。已有 70% 基础（`AppScreenStreamer`），协议与 Web 侧 `EXEC_FRAME` 同构，画布组件可复用 |
| **B. scrcpy 视频流** | adb 拉起 scrcpy-server，H.264 硬编码 → WebSocket 转发 → 浏览器 WebCodecs 解码；鼠标键盘原生注入 | 30~60 fps / <100ms | 3~5 天 | **第二阶段升级**。参考 ws-scrcpy（NetrisTV）；Google 模拟器 API 34 镜像支持 H.264 硬编码；需引入 Node 服务或自研帧转发 |
| **C. Google 官方容器方案** | `android-emulator-container-scripts`：Docker + gRPC + WebRTC(janus) | 60 fps / <50ms | 1 周+ | 不采用。本机部署场景架构过重 |

### 19.2 推荐路线：A 先行，B 升级

两阶段共享同一套消息协议，B 阶段只替换推流源与前端解码层，升级无感。

**方案 A 架构：**

```text
前端 APP 设备页签「实时画面」
    ↓ u_app_screen_start {avd_name}
执行器 AppScreenStreamer（2 fps 轮询 adb screencap → base64）
    ↓ u_app_screen_frame {frame:{w,h,data}} → Django 组转发 → 前端画布
前端点击/输入
    ↓ u_app_screen_input {type:'tap'|'text'|'swipe', 坐标}
执行器 adb input tap / text / swipe
    ↓ u_app_screen_stop
结束推流
```

### 19.3 消息协议设计（新增 5 个）

| 消息 | 方向 | 参数 | 说明 |
|---|---|---|---|
| `u_app_screen_start` | 前端→执行器 | `avd_name` / `udid`、`fps` | 开始推流；设备未运行时报错或自动拉起 |
| `u_app_screen_frame` | 执行器→前端 | `frame: {w, h, data}`（base64 JPEG） | 按 user 定向推送发起人 |
| `u_app_screen_input` | 前端→执行器 | `type`, 坐标或文本 | tap/text/swipe/key，坐标按设备分辨率比例换算 |
| `u_app_screen_status` | 执行器→前端 | `streaming`, `fps`, 分辨率 | 推流状态回报 |
| `u_app_screen_stop` | 前端→执行器 | - | 结束推流，释放轮询任务 |

实现要点：

1. 复用 `AppScreenStreamer`（已实现 adb 截图轮询 → base64 回调），接线到 `TaskConsumer` 并统一帧结构为 `{w, h, data}`
2. 帧转发沿用 `handle_app_device_result` 的组广播模式，但 `u_app_screen_frame` 按 `user` 定向（只有发起人收帧，避免广播带宽浪费）
3. 推流与用例执行互斥：Appium session 执行期间暂停/降频轮询，避免 screencap 与 UiAutomator2 抢资源
4. 单执行器同一时刻只允许 1 路推流；`stop` 必须幂等清理 asyncio 任务
5. Django 层透传（不落库），断线时执行器检测到连接关闭自动停止推流

### 19.4 第二阶段（方案 B）升级要点

1. 执行器进程内以 `adb forward` + scrcpy-server.jar 拉起视频流，或部署独立 ws-scrcpy Node 服务
2. H.264 裸流经 WS 转发，前端用 WebCodecs（Chrome/Edge 均支持）解码渲染
3. 操作注入改走 scrcpy 控制通道（支持多点触控、剪贴板、物理按键），`u_app_screen_input` 协议不变
4. 兼容性风险：模拟器镜像需支持 H.264 编码（API 34 google_apis 已验证可用）；浏览器需支持 WebCodecs

### 19.5 验收标准

```text
APP 设备页签可打开「实时画面」窗口
画面能看到模拟器屏幕（方案 A 2~5 fps）
点击画布能在模拟器内触发对应坐标点击
可输入文本、按返回键、上下滑动
关闭窗口后推流任务被正确清理
用例执行期间推流自动降频或暂停，互不干扰
```
