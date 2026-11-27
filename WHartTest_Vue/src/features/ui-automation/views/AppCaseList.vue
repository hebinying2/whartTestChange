<template>
  <div class="device-profile-list">
    <a-card :bordered="false">
      <div class="toolbar">
        <a-space>
          <a-button type="primary" @click="openCreate">{{ tl('新建 APP 用例') }}</a-button>
          <a-button @click="refresh">{{ tl('刷新') }}</a-button>
        </a-space>
        <a-input-search
          v-model="search"
          :placeholder="tl('搜索用例名称')"
          style="width: 240px"
          allow-clear
          @search="refresh"
        />
      </div>

      <a-table
        :data="cases"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @page-change="onPageChange"
      >
        <template #columns>
          <a-table-column :title="tl('用例名称')" data-index="name" :width="200" />
          <a-table-column :title="tl('包名')" data-index="app_package" :width="180">
            <template #cell="{ record }">{{ record.app_package || '-' }}</template>
          </a-table-column>
          <a-table-column :title="tl('步骤数')" :width="90">
            <template #cell="{ record }">{{ (record.app_steps || []).length }}</template>
          </a-table-column>
          <a-table-column :title="tl('绑定设备')" :width="140">
            <template #cell="{ record }">{{ deviceName(record.device_profile) }}</template>
          </a-table-column>
          <a-table-column :title="tl('最近状态')" :width="100">
            <template #cell="{ record }">
              <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column :title="tl('创建时间')" data-index="created_at" :width="160">
            <template #cell="{ record }">{{ formatTime(record.created_at) }}</template>
          </a-table-column>
          <a-table-column :title="tl('操作')" :width="220" fixed="right">
            <template #cell="{ record }">
              <a-space>
                <a-button size="small" type="primary" status="success" @click="runCase(record)">
                  {{ tl('执行') }}
                </a-button>
                <a-button size="small" @click="openEdit(record)">{{ tl('编辑') }}</a-button>
                <a-popconfirm :content="tl('确认删除该用例？')" @ok="removeCase(record)">
                  <a-button size="small" status="danger">{{ tl('删除') }}</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>

    <!-- 新建 / 编辑弹窗 -->
    <a-modal
      v-model:visible="modalVisible"
      :title="editingId ? tl('编辑 APP 用例') : tl('新建 APP 用例')"
      :width="860"
      :mask-closable="false"
      @ok="submit"
      :ok-loading="submitting"
    >
      <a-form :model="form" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item :label="tl('用例名称')" required>
              <a-input v-model="form.name" :placeholder="tl('例如：登录冒烟用例')" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="tl('所属模块')" required>
              <a-select v-model="form.module" :placeholder="tl('选择模块')" allow-search>
                <a-option
                  v-for="m in modules"
                  :key="m.id"
                  :value="m.id"
                  :label="m.name || m.title"
                >
                  {{ m.name || m.title }}
                </a-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item :label="tl('APP 包名')">
              <a-input v-model="form.app_package" placeholder="com.example.app" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="tl('启动 Activity')">
              <a-input v-model="form.app_activity" placeholder=".MainActivity" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item :label="tl('绑定设备')">
          <a-select v-model="form.device_profile" :placeholder="tl('选择 APP 设备（可留空）')" allow-clear>
            <a-option
              v-for="d in devices"
              :key="d.id"
              :value="d.id"
              :label="`${d.name}（${d.avd_name}）`"
            />
          </a-select>
        </a-form-item>
        <a-form-item :label="tl('用例描述')">
          <a-textarea v-model="form.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
        </a-form-item>

        <!-- 步骤编辑器 -->
        <a-form-item :label="tl('执行步骤')">
          <div class="steps-editor">
            <div
              v-for="(step, index) in form.app_steps"
              :key="step.__uid ?? index"
              class="step-row"
              :class="{ 'step-row-dragging': dragIndex === index, 'step-row-drag-over': dragOverIndex === index }"
              draggable="true"
              @dragstart="onDragStart(index, $event)"
              @dragover.prevent="dragOverIndex = index"
              @drop.prevent="onDrop(index)"
              @dragend="dragIndex = null; dragOverIndex = null"
            >
              <span class="drag-handle" :title="tl('拖拽调整顺序')">⠿</span>
              <a-tag color="arcoblue" size="small">{{ index + 1 }}</a-tag>
              <a-select v-model="step.operation_type" size="small" style="width: 140px">
                <a-option value="click">{{ tl('点击') }}</a-option>
                <a-option value="input">{{ tl('输入') }}</a-option>
                <a-option value="clear">{{ tl('清空') }}</a-option>
                <a-option value="assert_exists">{{ tl('断言存在') }}</a-option>
                <a-option value="assert_visible">{{ tl('断言可见') }}</a-option>
                <a-option value="launch_app">{{ tl('拉起 APP') }}</a-option>
                <a-option value="press_back">{{ tl('返回键') }}</a-option>
                <a-option value="swipe">{{ tl('滑动') }}</a-option>
                <a-option value="wait">{{ tl('等待(秒)') }}</a-option>
                <a-option value="screenshot">{{ tl('截图') }}</a-option>
              </a-select>
              <template v-if="needLocator(step.operation_type)">
                <a-select v-model="step.locator_type" size="small" style="width: 140px">
                  <a-option value="resource_id">resource-id</a-option>
                  <a-option value="accessibility_id">accessibility-id</a-option>
                  <a-option value="xpath">xpath</a-option>
                  <a-option value="class_name">class-name</a-option>
                  <a-option value="uiautomator">uiautomator</a-option>
                </a-select>
                <a-input
                  v-model="step.locator_value"
                  size="small"
                  :placeholder="tl('定位表达式')"
                  style="width: 200px"
                />
              </template>
              <a-input
                v-if="needValue(step.operation_type)"
                v-model="step.value"
                size="small"
                :placeholder="valuePlaceholder(step.operation_type)"
                style="width: 180px"
              />
              <a-input-number
                v-if="needLocator(step.operation_type)"
                v-model="step.wait_time"
                size="small"
                :min="1"
                :max="60"
                :placeholder="tl('等待秒数')"
                style="width: 100px"
              />
              <a-space :size="2">
                <a-button
                  size="mini"
                  type="text"
                  :disabled="index === 0"
                  @click="moveStep(index, -1)"
                >↑</a-button>
                <a-button
                  size="mini"
                  type="text"
                  :disabled="index === form.app_steps.length - 1"
                  @click="moveStep(index, 1)"
                >↓</a-button>
                <a-button size="small" status="danger" @click="form.app_steps.splice(index, 1)">
                  {{ tl('删除') }}
                </a-button>
              </a-space>
            </div>
            <a-button size="small" type="dashed" long @click="addStep">
              + {{ tl('添加步骤') }}
            </a-button>
          </div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useAppI18n } from '@/composables/useAppI18n'
import { useProjectStore } from '@/store/projectStore'
import { testCaseApi, deviceProfileApi, moduleApi } from '../api'
import { UiSocketEnum } from '../services/websocket'
import { uiWebSocket } from '../services/websocket'
import type { UiDeviceProfile } from '../types'
import { extractResponseData } from '../types'

// 左侧模块管理选中的模块（联动：列表过滤 + 创建默认值）
const props = defineProps<{
  selectedModuleId?: number
}>()

const { tl } = useAppI18n()
const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)

const loading = ref(false)
const cases = ref<any[]>([])
const devices = ref<UiDeviceProfile[]>([])
const modules = ref<any[]>([])
const search = ref('')
const page = ref(1)
const total = ref(0)
const pagination = computed(() => ({
  total: total.value,
  current: page.value,
  pageSize: 10,
  showTotal: true,
}))

const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const submitting = ref(false)

interface AppStep {
  operation_type: string
  locator_type?: string
  locator_value?: string
  value?: string
  wait_time?: number
}

const form = reactive({
  name: '',
  module: undefined as number | undefined,
  description: '',
  app_package: '',
  app_activity: '',
  device_profile: undefined as number | undefined,
  app_steps: [] as AppStep[],
})

const CASE_TYPE = 'app'

const refresh = async () => {
  if (!projectId.value) {
    cases.value = []
    return
  }
  loading.value = true
  try {
    const res: any = await testCaseApi.list({
      project: projectId.value,
      case_type: CASE_TYPE,
      module: props.selectedModuleId || undefined,
      search: search.value || undefined,
      page: page.value,
    })
    const data: any = extractResponseData<any>(res)
    cases.value = data?.items ?? data?.results ?? (Array.isArray(data) ? data : [])
    total.value = data?.count ?? cases.value.length
  } catch (error) {
    Message.error(tl('加载 APP 用例失败'))
  } finally {
    loading.value = false
  }
}

const refreshDevices = async () => {
  if (!projectId.value) return
  try {
    const res: any = await deviceProfileApi.list({ project: projectId.value })
    const data: any = extractResponseData<any>(res)
    devices.value = data?.items ?? data?.results ?? (Array.isArray(data) ? data : [])
  } catch {
    /* 静默 */
  }
}

const refreshModules = async () => {
  if (!projectId.value) return
  try {
    const res: any = await moduleApi.tree(projectId.value)
    // 统一解包：响应拦截器包装 {status, data} -> 内层 data
    const data = extractResponseData<any[]>(res) || []
    // tree 接口返回嵌套结构，扁平化后供下拉选择
    const flatten = (mods: any[], level = 0, visited = new Set<number>()): any[] =>
      (mods || []).flatMap((m) => {
        if (!m || visited.has(m.id)) return []
        visited.add(m.id)
        return [
          { ...m, __level: level },
          ...flatten(m.children || [], level + 1, visited),
        ]
      })
    modules.value = flatten(Array.isArray(data) ? data : [])
  } catch {
    /* 静默 */
  }
}

const onPageChange = (p: number) => {
  page.value = p
  refresh()
}

const needLocator = (op: string) =>
  ['click', 'input', 'clear', 'assert_exists', 'assert_visible'].includes(op)
const needValue = (op: string) =>
  ['input', 'launch_app', 'wait', 'swipe'].includes(op)

const valuePlaceholder = (op: string) => {
  if (op === 'input') return tl('输入内容')
  if (op === 'launch_app') return tl('包名')
  if (op === 'wait') return tl('秒数')
  if (op === 'swipe') return 'x1,y1,x2,y2'
  return ''
}

const addStep = () => {
  form.app_steps.push({
    __uid: ++stepUidSeq,
    operation_type: 'click',
    locator_type: 'resource_id',
    locator_value: '',
    value: '',
    wait_time: 10,
  })
}

// ==================== 步骤排序（拖拽 + 上下移动） ====================
let stepUidSeq = 0
const dragIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

const withUid = (steps: any[]) => steps.map((s: any) => ({ __uid: ++stepUidSeq, ...s }))

const onDragStart = (index: number, event: DragEvent) => {
  dragIndex.value = index
  // Firefox 需要设置数据才能触发 drop
  event.dataTransfer?.setData('text/plain', String(index))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

const onDrop = (target: number) => {
  const from = dragIndex.value
  dragIndex.value = null
  dragOverIndex.value = null
  if (from === null || from === target) return
  const steps = form.app_steps
  const [moved] = steps.splice(from, 1)
  steps.splice(target, 0, moved)
}

const moveStep = (index: number, offset: number) => {
  const target = index + offset
  if (target < 0 || target >= form.app_steps.length) return
  const steps = form.app_steps
  const [moved] = steps.splice(index, 1)
  steps.splice(target, 0, moved)
}

const openCreate = async () => {
  if (!projectId.value) {
    Message.warning(tl('请先选择项目'))
    return
  }
  // 模块/设备未加载时先拉取，避免下拉为空
  if (!modules.value.length) await refreshModules()
  if (!devices.value.length) await refreshDevices()
  editingId.value = null
  Object.assign(form, {
    name: '',
    module: props.selectedModuleId ?? modules.value[0]?.id,
    description: '',
    app_package: '',
    app_activity: '',
    device_profile: undefined,
    app_steps: [],
  })
  modalVisible.value = true
}

const openEdit = async (record: any) => {
  if (!modules.value.length) await refreshModules()
  if (!devices.value.length) await refreshDevices()
  // 列表接口是精简字段（不含 app_package/app_steps 等），必须拉详情回显，
  // 否则空值提交会覆盖数据库原数据
  let full: any = record
  try {
    const res: any = await testCaseApi.get(record.id)
    const data: any = extractResponseData<any>(res)
    if (data && typeof data === 'object') full = { ...record, ...data }
  } catch {
    /* 详情拉取失败时用列表行兜底 */
  }
  editingId.value = full.id
  Object.assign(form, {
    name: full.name,
    module: full.module,
    description: full.description || '',
    app_package: full.app_package || '',
    app_activity: full.app_activity || '',
    device_profile: full.device_profile || undefined,
    app_steps: withUid((full.app_steps || []).map((s: any) => ({ ...s }))),
  })
  modalVisible.value = true
}

const submit = async () => {
  if (!projectId.value) {
    Message.warning(tl('请先选择项目'))
    return false
  }
  if (!form.name.trim()) {
    Message.warning(tl('请输入用例名称'))
    return false
  }
  if (!form.module) {
    Message.warning(tl('请选择所属模块'))
    return false
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      module: form.module,
      project: projectId.value,
      description: form.description,
      case_type: CASE_TYPE,
      app_package: form.app_package,
      app_activity: form.app_activity,
      device_profile: form.device_profile ?? null,
      app_steps: form.app_steps.map((s, i) => {
        const { __uid, ...rest } = s as any
        return { ...rest, step_id: i + 1 }
      }),
    }
    if (editingId.value) {
      await testCaseApi.update(editingId.value, payload)
      Message.success(tl('用例已更新'))
    } else {
      await testCaseApi.create(payload as any)
      Message.success(tl('用例已创建'))
    }
    modalVisible.value = false
    await refresh()
    return true
  } catch (error: any) {
    Message.error(error?.response?.data ? JSON.stringify(error.response.data) : tl('保存失败'))
    return false
  } finally {
    submitting.value = false
  }
}

const removeCase = async (record: any) => {
  try {
    await testCaseApi.delete(record.id)
    Message.success(tl('用例已删除'))
    await refresh()
  } catch {
    Message.error(tl('删除失败'))
  }
}

const runCase = async (record: any) => {
  try {
    await uiWebSocket.connect()
  } catch {
    Message.error(tl('WebSocket 连接失败，请刷新页面重试'))
    return
  }
  const device = devices.value.find((d) => d.id === record.device_profile)
  const sent = uiWebSocket.send(UiSocketEnum.APP_TEST_CASE, {
    case_id: record.id,
    udid: device?.udid || undefined,
    avd_name: device?.avd_name || undefined,
  })
  if (!sent) {
    Message.error(tl('WebSocket 未连接，无法下发执行指令'))
    return
  }
  Message.info(tl('执行指令已发送，可在执行记录页签查看结果'))
}

const deviceName = (id: number | null) => {
  const d = devices.value.find((x) => x.id === id)
  return d ? d.name : tl('未绑定')
}

const statusColor = (status: number) =>
  ({ 0: 'gray', 1: 'arcoblue', 2: 'green', 3: 'red' } as Record<number, string>)[status] ?? 'gray'

const statusText = (status: number) =>
  ({
    0: tl('未执行'),
    1: tl('执行中'),
    2: tl('成功'),
    3: tl('失败'),
  } as Record<number, string>)[status] ?? String(status)

const formatTime = (value?: string) => (value ? value.replace('T', ' ').slice(0, 19) : '-')

const handleCaseResult = (payload: any) => {
  const args = payload?.data?.func_args || payload?.func_args || payload || {}
  if (!args.case_id) return
  if (args.status === 'success') {
    Message.success(`${tl('APP 用例执行成功')}: ${args.passed_steps}/${args.total_steps}`)
  } else {
    Message.error(`${tl('APP 用例执行失败')}: ${args.message || ''}`)
  }
  refresh()
}

// 设备/执行器链路错误提示（如「当前没有可用执行器」）
const handleAppDeviceResult = (payload: any) => {
  const args = payload?.data?.func_args || payload?.func_args || payload || {}
  if (args.status === 'error' && args.message) {
    Message.error(args.message)
  }
}

// 项目切换 / 左侧模块选择变化时重新加载（onMounted 时项目可能未就绪）
watch(projectId, () => {
  refresh()
  refreshDevices()
  refreshModules()
})

watch(() => props.selectedModuleId, () => {
  page.value = 1
  refresh()
})

onMounted(() => {
  refresh()
  refreshDevices()
  refreshModules()
  uiWebSocket.on(UiSocketEnum.CASE_RESULT, handleCaseResult)
  uiWebSocket.on(UiSocketEnum.APP_DEVICE_RESULT, handleAppDeviceResult)
})

onBeforeUnmount(() => {
  uiWebSocket.off(UiSocketEnum.CASE_RESULT, handleCaseResult)
  uiWebSocket.off(UiSocketEnum.APP_DEVICE_RESULT, handleAppDeviceResult)
})

defineExpose({ refresh })
</script>

<style scoped>
.device-profile-list {
  padding: 0;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.steps-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.drag-handle {
  cursor: grab;
  color: var(--color-text-3);
  user-select: none;
  font-weight: bold;
  letter-spacing: -2px;
}
.drag-handle:active {
  cursor: grabbing;
}

.step-row-dragging {
  opacity: 0.4;
}

.step-row-drag-over {
  border-top: 2px solid var(--primary-6);
}
</style>
