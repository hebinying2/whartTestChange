<template>
  <a-modal
    :visible="visible"
    :title="text.title"
    width="min(1300px, calc(100vw - 24px))"
    :mask-closable="false"
    :footer="false"
    @cancel="handleClose"
  >
    <div class="app-screen-viewer">
      <!-- 左侧：画面画布 + 工具栏 -->
      <div class="screen-side">
        <div ref="canvasWrapRef" class="screen-canvas-wrap">
          <canvas
            ref="canvasRef"
            class="screen-canvas"
            :class="{ interactive: streaming }"
            :style="canvasStyle"
            @pointerdown="onPointerDown"
            @pointerup="onPointerUp"
          />
          <div v-if="!hasFrame" class="screen-overlay">
            <a-spin :loading="connecting" />
            <span>{{ statusText || text.waiting }}</span>
          </div>
          <div v-else class="screen-badge" :class="streaming ? 'is-live' : 'is-off'">
            {{ streaming ? text.live : text.off }}
          </div>
        </div>
        <div class="screen-toolbar">
          <a-input
            v-model="inputText"
            :placeholder="text.inputPlaceholder"
            size="small"
            allow-clear
            @keyup.enter="sendText"
          />
          <a-button size="small" @click="sendText">{{ text.send }}</a-button>
          <a-button size="small" @click="sendKey(4)">{{ text.back }}</a-button>
          <a-button size="small" @click="sendKey(3)">{{ text.home }}</a-button>
        </div>
        <div class="screen-toolbar">
          <a-button size="small" type="primary" :loading="dumping" @click="dumpElements">
            {{ text.capture }}
          </a-button>
          <a-button size="small" :type="recording ? 'primary' : 'outline'" status="warning" @click="toggleRecording">
            {{ recording ? text.stopRecord : text.startRecord }}
          </a-button>
          <span class="toolbar-hint">{{ text.tapHint }}</span>
        </div>
      </div>

      <!-- 右侧：元素面板（控件树 / 录制步骤） -->
      <div class="elements-side">
        <a-tabs :active-key="panelTab" size="small" @change="panelTab = $event as string">
          <a-tab-pane key="elements" :title="`${text.elementsTitle}${nodes.length ? ` (${nodes.length})` : ''}`">
            <div class="elements-list">
              <div
                v-for="(n, i) in nodes"
                :key="i"
                class="element-item"
                :class="{ selected: selectedNode === n }"
                @click="selectedNode = n"
              >
                <div class="element-main">
                  <a-tag size="small" color="arcoblue">{{ n.locator_type }}</a-tag>
                  <span class="element-value">{{ n.locator_value || text.noLocator }}</span>
                </div>
                <div class="element-meta">
                  {{ n.class }}{{ n.text ? ` · "${n.text}"` : '' }}{{ n.content_desc ? ` · desc:${n.content_desc}` : '' }}
                </div>
                <div class="element-actions">
                  <a-button size="mini" type="text" @click.stop="copyLocator(n)">{{ text.copy }}</a-button>
                </div>
              </div>
              <div v-if="!nodes.length" class="elements-empty">{{ text.elementsEmpty }}</div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="record" :title="`${text.recordTitle}${recordedSteps.length ? ` (${recordedSteps.length})` : ''}`">
            <div class="record-list">
              <div v-for="(s, i) in recordedSteps" :key="i" class="record-item">
                <a-tag size="small" color="orange">{{ i + 1 }}</a-tag>
                <a-tag size="small" color="arcoblue">{{ s.operation_type }}</a-tag>
                <span class="record-value">{{ s.locator_type }}: {{ s.locator_value }}</span>
                <a-button size="mini" type="text" status="danger" @click="recordedSteps.splice(i, 1)">×</a-button>
              </div>
              <div v-if="!recordedSteps.length" class="elements-empty">{{ text.recordEmpty }}</div>
            </div>
            <div v-if="recordedSteps.length" class="record-save">
              <a-select
                v-model="caseModuleId"
                :placeholder="text.modulePlaceholder"
                size="small"
                allow-search
              >
                <a-option v-for="m in modules" :key="m.id" :value="m.id">{{ m.name }}</a-option>
              </a-select>
              <a-input v-model="caseName" :placeholder="text.caseNamePlaceholder" size="small" />
              <a-button type="primary" size="small" :loading="savingCase" @click="saveAsCase">
                {{ text.saveCase }}
              </a-button>
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useAppI18n } from '@/composables/useAppI18n'
import { testCaseApi, moduleApi } from '../api'
import { uiWebSocket, UiSocketEnum } from '../services/websocket'
import { extractResponseData } from '../types'

const props = defineProps<{
  visible: boolean
  /** 目标设备 AVD 名（执行器按 avd/在线模拟器自动匹配） */
  avdName?: string
  /** 用例归属项目/模块（保存用例时使用） */
  projectId?: number | null
  selectedModuleId?: number | null
}>()

const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const { isEnglish } = useAppI18n()
const text = computed(() => (
  isEnglish.value
    ? {
        title: 'APP Live Screen',
        waiting: 'Requesting screen stream…',
        live: 'LIVE', off: 'Stream off',
        inputPlaceholder: 'Input text to device',
        send: 'Send', back: 'Back', home: 'Home',
        capture: 'Capture Elements', startRecord: 'Start Record',
        stopRecord: 'Stop Record',
        tapHint: 'Tap canvas = tap device (records a step when recording)',
        elementsTitle: 'Elements', elementsEmpty: 'No elements captured. Click "Capture Elements".',
        recordTitle: 'Recorded Steps', recordEmpty: 'No steps recorded yet.',
        copy: 'Copy', noLocator: '(no locator)',
        caseNamePlaceholder: 'New case name',
        modulePlaceholder: 'Select module (required)',
        saveCase: 'Save as Case',
        wsError: 'WebSocket connection failed',
        sendFail: 'Failed to send command',
        captureFail: 'Element capture failed: ',
        saveOk: 'APP case created: ',
        saveFail: 'Failed to save case: ',
        moduleRequired: 'Please select a module first',
        recorded: 'Step recorded: ',
        copyOk: 'Locator copied',
      }
    : {
        title: 'APP 实时画面',
        waiting: '正在请求画面推流…',
        live: '推流中', off: '已停止',
        inputPlaceholder: '输入要注入设备的文本',
        send: '发送', back: '返回', home: 'HOME',
        capture: '采集元素', startRecord: '开始录制',
        stopRecord: '停止录制',
        tapHint: '点击画布 = 点击设备（录制中同时生成步骤）',
        elementsTitle: '元素', elementsEmpty: '尚未采集元素，请点击「采集元素」。',
        recordTitle: '录制步骤', recordEmpty: '尚未录制步骤：点击画布即生成点击步骤。',
        copy: '复制', noLocator: '（无可定位属性）',
        caseNamePlaceholder: '新用例名称',
        modulePlaceholder: '选择模块（必选）',
        saveCase: '保存为用例',
        wsError: 'WebSocket 连接失败',
        sendFail: '指令发送失败',
        captureFail: '元素采集失败：',
        saveOk: 'APP 用例已创建：',
        saveFail: '保存用例失败：',
        moduleRequired: '请先选择用例归属模块',
        recorded: '已录制步骤：',
        copyOk: '定位已复制',
      }
))

// ---------------- 画布与帧 ----------------

const canvasRef = ref<HTMLCanvasElement | null>(null)
const canvasWrapRef = ref<HTMLElement | null>(null)
const canvasSize = reactive({ width: 0, height: 0 })
const viewport = reactive({ width: 1080, height: 2400 })
const hasFrame = ref(false)
const connecting = ref(false)
const streaming = ref(false)
const statusText = ref('')
const dumping = ref(false)
const inputText = ref('')

let downPoint: { x: number; y: number } | null = null

const canvasStyle = computed(() => ({
  aspectRatio: `${viewport.width} / ${viewport.height}`,
  width: canvasSize.width ? `${canvasSize.width}px` : '100%',
  height: canvasSize.height ? `${canvasSize.height}px` : 'auto',
}))

function drawFrame(b64: string) {
  const canvas = canvasRef.value
  if (!canvas) return
  const img = new Image()
  img.onload = () => {
    viewport.width = img.naturalWidth || 1080
    viewport.height = img.naturalHeight || 2400
    canvas.width = viewport.width
    canvas.height = viewport.height
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0, viewport.width, viewport.height)
    hasFrame.value = true
    streaming.value = true
    statusText.value = ''
    fitCanvas()
  }
  img.src = `data:image/png;base64,${b64}`
}

function fitCanvas() {
  const wrap = canvasWrapRef.value
  if (!wrap) return
  const rect = wrap.getBoundingClientRect()
  if (rect.width < 2 || rect.height < 2) return
  const ratio = viewport.width / viewport.height
  let cw = rect.width
  let ch = cw / ratio
  if (ch > rect.height) {
    ch = rect.height
    cw = ch * ratio
  }
  canvasSize.width = Math.floor(cw)
  canvasSize.height = Math.floor(ch)
}

// ---------------- 消息订阅 ----------------

const onScreenFrame = (data: any) => {
  if (!props.visible) return
  const args = data?.data?.func_args || {}
  const frame = args.frame
  if (frame?.data) drawFrame(frame.data)
}

const onScreenStatus = (data: any) => {
  if (!props.visible) return
  const args = data?.data?.func_args || {}
  if (args.status === 'error') {
    // 注入失败（scope=input）仅提示，不影响推流状态
    if (args.scope === 'input') {
      Message.warning(args.message || text.value.sendFail)
      return
    }
    streaming.value = false
    statusText.value = `${args.message || text.value.sendFail}`
    Message.warning(statusText.value)
  } else if (args.streaming === false) {
    streaming.value = false
  }
}

const nodes = ref<any[]>([])
const selectedNode = ref<any>(null)
const lastDumpScreenshot = ref<string>('')

const onElementsResult = (data: any) => {
  if (!props.visible) return
  const args = data?.data?.func_args || {}
  dumping.value = false
  if (args.status === 'error') {
    Message.error(`${text.value.captureFail}${args.message || ''}`)
    return
  }
  nodes.value = args.nodes || []
  lastDumpScreenshot.value = args.screenshot || ''
  panelTab.value = 'elements'
  Message.success(`${text.value.elementsTitle}: ${nodes.value.length}`)
}

let offFrame: (() => void) | null = null
let offStatus: (() => void) | null = null
let offElements: (() => void) | null = null
let resizeObserver: ResizeObserver | null = null

const startStream = async () => {
  try {
    await uiWebSocket.connect()
  } catch {
    Message.error(text.value.wsError)
    return
  }
  connecting.value = true
  statusText.value = text.value.waiting
  const ok = uiWebSocket.send(UiSocketEnum.APP_SCREEN_START, {
    avd_name: props.avdName || undefined,
    fps: 2,
  })
  connecting.value = false
  if (!ok) Message.error(text.value.sendFail)
}

const stopStream = () => {
  if (uiWebSocket.connected.value) {
    uiWebSocket.send(UiSocketEnum.APP_SCREEN_STOP, {})
  }
}

const handleClose = () => {
  stopStream()
  emit('update:visible', false)
}

watch(() => props.visible, (v) => {
  if (v) {
    nodes.value = []
    recordedSteps.value = []
    hasFrame.value = false
    streaming.value = false
    loadModules()
    nextTick(() => { startStream(); fitCanvas() })
  } else {
    stopStream()
  }
})

onMounted(() => {
  offFrame = uiWebSocket.on(UiSocketEnum.APP_SCREEN_FRAME, onScreenFrame as any)
  offStatus = uiWebSocket.on(UiSocketEnum.APP_SCREEN_STATUS, onScreenStatus as any)
  offElements = uiWebSocket.on(UiSocketEnum.APP_ELEMENTS_RESULT, onElementsResult as any)
  resizeObserver = new ResizeObserver(() => fitCanvas())
  if (canvasWrapRef.value) resizeObserver.observe(canvasWrapRef.value)
})

onBeforeUnmount(() => {
  stopStream()
  offFrame?.(); offStatus?.(); offElements?.()
  resizeObserver?.disconnect()
})

// ---------------- 交互注入 + 点选录制（阶段 4b） ----------------

const sendInput = (payload: Record<string, any>) => {
  if (!uiWebSocket.connected.value) {
    Message.error(text.value.sendFail)
    return
  }
  uiWebSocket.send(UiSocketEnum.APP_SCREEN_INPUT, payload)
}

const canvasRatio = (e: PointerEvent) => {
  const canvas = canvasRef.value
  if (!canvas) return null
  const rect = canvas.getBoundingClientRect()
  return {
    x_ratio: (e.clientX - rect.left) / rect.width,
    y_ratio: (e.clientY - rect.top) / rect.height,
  }
}

const onPointerDown = (e: PointerEvent) => {
  if (!hasFrame.value) return
  downPoint = canvasRatio(e)
}

const onPointerUp = (e: PointerEvent) => {
  if (!hasFrame.value || !downPoint) return
  const up = canvasRatio(e)
  if (!up) return
  const dx = up.x_ratio - downPoint.x_ratio
  const dy = up.y_ratio - downPoint.y_ratio
  const dist = Math.abs(dx) + Math.abs(dy)
  if (dist > 0.05) {
    // 位移明显 → 滑动手势
    sendInput({
      type: 'swipe',
      x1_ratio: downPoint.x_ratio, y1_ratio: downPoint.y_ratio,
      x2_ratio: up.x_ratio, y2_ratio: up.y_ratio,
    })
    recordStep({ operation_type: 'swipe', locator_type: 'uiautomator',
      locator_value: '', value: `${Math.round(dx * viewport.width)},${Math.round(dy * viewport.height)}` })
  } else {
    // 点击：注入 + 命中控件树生成定位
    const hit = findNodeAtRatio(downPoint.x_ratio, downPoint.y_ratio)
    sendInput({ type: 'tap', x_ratio: downPoint.x_ratio, y_ratio: downPoint.y_ratio })
    if (hit) {
      recordStep({
        operation_type: 'click',
        locator_type: hit.locator_type,
        locator_value: hit.locator_value,
      })
    }
  }
  downPoint = null
}

const sendText = () => {
  const t = inputText.value.trim()
  if (!t) return
  sendInput({ type: 'text', text: t })
  // 输入录制：命中可编辑节点生成 input 步骤
  const editable = nodes.value.find((n) => n.editable)
  if (editable) {
    recordStep({
      operation_type: 'input',
      locator_type: editable.locator_type,
      locator_value: editable.locator_value,
      value: t,
    })
  }
  inputText.value = ''
}

const sendKey = (keycode: number) => {
  sendInput({ type: 'key', keycode })
  if (keycode === 4) {
    recordStep({ operation_type: 'press_back', locator_type: 'resource_id', locator_value: '' })
  }
}

// ---------------- 元素采集（阶段 4a） ----------------

const dumpElements = async () => {
  try {
    await uiWebSocket.connect()
  } catch {
    Message.error(text.value.wsError)
    return
  }
  dumping.value = true
  const ok = uiWebSocket.send(UiSocketEnum.APP_ELEMENTS_DUMP, {
    avd_name: props.avdName || undefined,
  })
  if (!ok) {
    dumping.value = false
    Message.error(text.value.sendFail)
  }
}

const copyLocator = (n: any) => {
  navigator.clipboard?.writeText(n.locator_value || '').then(() => {
    Message.success(text.value.copyOk)
  })
}

const findNodeAtRatio = (xr: number, yr: number) => {
  const x = xr * viewport.width
  const y = yr * viewport.height
  let best: any = null
  let bestArea = Number.MAX_SAFE_INTEGER
  for (const n of nodes.value) {
    const r = n.rect
    if (!r) continue
    if (r.x1 <= x && x <= r.x2 && r.y1 <= y && y <= r.y2) {
      const area = r.w * r.h
      if (area < bestArea) { best = n; bestArea = area }
    }
  }
  return best
}

// ---------------- 点选录制（阶段 4b） ----------------

const panelTab = ref('elements')
const recording = ref(false)
const recordedSteps = ref<any[]>([])
const caseName = ref('')
const savingCase = ref(false)
const modules = ref<any[]>([])
const caseModuleId = ref<number | null>(null)

// module 是后端必填外键（传 null 会 400），打开弹窗时加载项目模块供选择
const loadModules = async () => {
  if (!props.projectId || modules.value.length) return
  try {
    const res: any = await moduleApi.list({ project: props.projectId })
    modules.value = extractResponseData<any[]>(res) || []
    if (!caseModuleId.value && modules.value.length) {
      caseModuleId.value = props.selectedModuleId ?? modules.value[0]?.id ?? null
    }
  } catch {
    /* 模块加载失败不阻塞画面功能，保存时再提示 */
  }
}

const toggleRecording = () => {
  recording.value = !recording.value
  if (recording.value) {
    recordedSteps.value = []
    panelTab.value = 'record'
    loadModules()
  }
}

const recordStep = (step: Record<string, any>) => {
  if (!recording.value) return
  recordedSteps.value.push(step)
  Message.info(`${text.value.recorded}${step.operation_type} → ${step.locator_type}: ${step.locator_value || ''}`)
}

const saveAsCase = async () => {
  if (!recordedSteps.value.length) return
  if (!caseModuleId.value) {
    Message.warning(text.value.moduleRequired)
    return
  }
  const name = caseName.value.trim() || `APP录制_${new Date().toISOString().slice(0, 16).replace('T', '_')}`
  savingCase.value = true
  try {
    await testCaseApi.create({
      name,
      project: props.projectId,
      module: caseModuleId.value,
      case_type: 'app',
      app_steps: recordedSteps.value.map((s, i) => ({ ...s, step_id: i + 1 })),
    } as any)
    Message.success(`${text.value.saveOk}${name}`)
    recordedSteps.value = []
    recording.value = false
  } catch (err: any) {
    Message.error(`${text.value.saveFail}${err?.message || err}`)
  } finally {
    savingCase.value = false
  }
}
</script>

<style scoped>
.app-screen-viewer {
  display: flex;
  gap: 12px;
  height: min(72vh, 760px);
}

.screen-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.screen-canvas-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #111;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  min-height: 0;
}

.screen-canvas {
  border-radius: 4px;
}

.screen-canvas.interactive {
  cursor: crosshair;
  touch-action: none;
}

.screen-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #c9cdd4;
  font-size: 13px;
}

.screen-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  color: #fff;
}

.screen-badge.is-live { background: rgba(0, 180, 42, 0.85); }
.screen-badge.is-off { background: rgba(134, 144, 156, 0.85); }

.screen-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
}

.toolbar-hint {
  font-size: 12px;
  color: var(--color-text-3);
}

.elements-side {
  width: 380px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border-2);
  padding-left: 12px;
  min-height: 0;
  overflow: hidden;
}

/* arco tabs 默认不约束内容高度，需穿透让其填满并在内部滚动 */
.elements-side :deep(.arco-tabs) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.elements-side :deep(.arco-tabs-content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.elements-side :deep(.arco-tabs-content-item) {
  height: 100%;
}

.elements-side :deep(.arco-tabs-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.elements-list,
.record-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.element-item {
  padding: 6px 8px;
  border: 1px solid var(--color-border-2);
  border-radius: 6px;
  cursor: pointer;
}

.element-item.selected {
  border-color: var(--primary-6);
  background: var(--primary-light-1);
}

.element-main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.element-value {
  font-size: 12px;
  word-break: break-all;
}

.element-meta {
  font-size: 11px;
  color: var(--color-text-3);
  margin-top: 2px;
  word-break: break-all;
}

.element-actions {
  display: flex;
  justify-content: flex-end;
}

.elements-empty {
  color: var(--color-text-3);
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}

.record-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border: 1px solid var(--color-border-2);
  border-radius: 6px;
}

.record-value {
  flex: 1;
  font-size: 12px;
  word-break: break-all;
}

.record-save {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}
</style>
