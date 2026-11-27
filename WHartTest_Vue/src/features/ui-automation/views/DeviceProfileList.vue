<template>
  <div class="device-profile-list">
    <div class="header">
      <div class="title">
        <h3>{{ tl('APP 设备配置') }}</h3>
        <span class="count">{{ tl('共') }} {{ devices.length }} {{ tl('台') }}</span>
      </div>
      <div class="actions">
        <a-button @click="refresh" :loading="loading">
          <template #icon><icon-refresh /></template>
          {{ tl('刷新') }}
        </a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          {{ tl('新建设备') }}
        </a-button>
      </div>
    </div>

    <a-table
      :data="devices"
      :loading="loading"
      :pagination="false"
      stripe
    >
      <template #columns>
        <a-table-column :title="tl('状态')" :width="90" align="center">
          <template #cell="{ record }">
            <a-tag :color="statusColor(record.status)" size="small">
              {{ tl(statusLabel(record.status)) }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column :title="tl('设备名称')" data-index="name" :width="160" />
        <a-table-column :title="tl('AVD')" data-index="avd_name" :width="180" />
        <a-table-column :title="tl('Android 版本')" data-index="android_version" :width="120" />
        <a-table-column :title="tl('分辨率')" data-index="screen_resolution" :width="120" />
        <a-table-column :title="tl('无窗口')" :width="90" align="center">
          <template #cell="{ record }">
            <a-tag :color="record.headless ? 'orangered' : 'green'" size="small">
              {{ record.headless ? tl('是') : tl('否') }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column :title="tl('操作')" :width="240" align="center">
          <template #cell="{ record }">
            <a-button
              type="text"
              size="mini"
              :disabled="record.status === 'running' || record.status === 'starting'"
              @click="startDevice(record)"
            >
              {{ tl('启动') }}
            </a-button>
            <a-button
              type="text"
              size="mini"
              :disabled="record.status !== 'running'"
              @click="stopDevice(record)"
            >
              {{ tl('停止') }}
            </a-button>
            <a-button
              type="text"
              size="mini"
              status="success"
              @click="openScreen(record)"
            >
              {{ tl('画面') }}
            </a-button>
            <a-button type="text" size="mini" @click="openEdit(record)">
              {{ tl('编辑') }}
            </a-button>
            <a-popconfirm :content="tl('确认删除该设备配置？')" @ok="removeDevice(record)">
              <a-button type="text" size="mini" status="danger">{{ tl('删除') }}</a-button>
            </a-popconfirm>
          </template>
        </a-table-column>
      </template>
    </a-table>

    <a-modal
      v-model:visible="modalVisible"
      :title="editingId ? tl('编辑设备') : tl('新建设备')"
      :ok-loading="submitting"
      @before-ok="submit"
      @cancel="cancel"
      width="520"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item field="name" :label="tl('设备名称')" required>
          <a-input v-model="form.name" :placeholder="tl('如 Pixel_6_Emulator')" />
        </a-form-item>
        <a-form-item field="avd_name" :label="tl('AVD 名称')" required>
          <a-input v-model="form.avd_name" :placeholder="tl('如 Pixel_6_API_34')" />
        </a-form-item>
        <a-form-item field="android_version" :label="tl('Android 版本')" required>
          <a-input v-model="form.android_version" :placeholder="tl('如 14 / API 34')" />
        </a-form-item>
        <a-form-item field="device_name" :label="tl('Device Name')" required>
          <a-input v-model="form.device_name" :placeholder="tl('如 Pixel 6')" />
        </a-form-item>
        <a-form-item field="screen_resolution" :label="tl('分辨率')">
          <a-input v-model="form.screen_resolution" placeholder="1080x2400" />
        </a-form-item>
        <a-form-item field="headless" :label="tl('无窗口模式')">
          <a-switch v-model="form.headless" />
        </a-form-item>
        <a-form-item field="snapshot_enabled" :label="tl('启用快照')">
          <a-switch v-model="form.snapshot_enabled" />
        </a-form-item>
        <a-form-item field="description" :label="tl('描述')">
          <a-textarea v-model="form.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
        </a-form-item>
      </a-form>
    </a-modal>

    <AppScreenViewer
      v-model:visible="screenVisible"
      :avd-name="screenDevice?.avd_name"
      :project-id="projectId"
      :selected-module-id="null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus, IconRefresh } from '@arco-design/web-vue/es/icon'
import { useAppI18n } from '@/composables/useAppI18n'
import { useProjectStore } from '@/store/projectStore'
import { deviceProfileApi } from '../api'
import type { UiDeviceProfile, UiDeviceProfileForm } from '../types'
import { uiWebSocket, UiSocketEnum } from '../services/websocket'
import AppScreenViewer from '../components/AppScreenViewer.vue'

const screenVisible = ref(false)
const screenDevice = ref<UiDeviceProfile | null>(null)
const openScreen = (device: UiDeviceProfile) => {
  screenDevice.value = device
  screenVisible.value = true
}

const { tl } = useAppI18n()
const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)

const devices = ref<UiDeviceProfile[]>([])
const loading = ref(false)
const submitting = ref(false)
const modalVisible = ref(false)
const editingId = ref<number | null>(null)

const defaultForm = (): UiDeviceProfileForm => ({
  name: '',
  avd_name: '',
  android_version: '',
  device_name: '',
  cpu_core: 4,
  ram_size_mb: 4096,
  screen_resolution: '',
  headless: true,
  snapshot_enabled: true,
  description: '',
})

const form = reactive<UiDeviceProfileForm>(defaultForm())

const statusColor = (status: UiDeviceProfile['status']) => {
  switch (status) {
    case 'running':
      return 'green'
    case 'starting':
      return 'orange'
    case 'error':
      return 'red'
    default:
      return 'gray'
  }
}

const statusLabel = (status: UiDeviceProfile['status']) => {
  switch (status) {
    case 'running':
      return '运行中'
    case 'starting':
      return '启动中'
    case 'stopping':
      return '停止中'
    case 'error':
      return '异常'
    default:
      return '已停止'
  }
}

const extractList = (payload: any): UiDeviceProfile[] => {
  if (Array.isArray(payload)) return payload
  if (payload?.results) return payload.results
  if (payload?.data) return extractList(payload.data)
  return []
}

const refresh = async () => {
  loading.value = true
  try {
    const res: any = await deviceProfileApi.list(
      projectId.value ? { project: projectId.value } : undefined,
    )
    devices.value = extractList(res?.data ?? res)
  } catch (error) {
    console.error('加载 APP 设备失败', error)
    Message.error(tl('加载 APP 设备失败'))
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  Object.assign(form, defaultForm())
  modalVisible.value = true
}

const openEdit = (device: UiDeviceProfile) => {
  editingId.value = device.id
  Object.assign(form, {
    name: device.name,
    avd_name: device.avd_name,
    android_version: device.android_version,
    device_name: device.device_name,
    cpu_core: device.cpu_core,
    ram_size_mb: device.ram_size_mb,
    screen_resolution: device.screen_resolution,
    headless: device.headless,
    snapshot_enabled: device.snapshot_enabled,
    description: device.description || '',
  })
  modalVisible.value = true
}

const cancel = () => {
  modalVisible.value = false
}

const submit = async () => {
  if (!projectId.value) {
    Message.warning(tl('请先选择项目'))
    return false
  }
  if (!form.name.trim()) {
    Message.warning(tl('请输入设备名称'))
    return false
  }
  if (!form.avd_name.trim()) {
    Message.warning(tl('请输入 AVD 名称'))
    return false
  }
  submitting.value = true
  try {
    if (editingId.value) {
      await deviceProfileApi.update(editingId.value, form)
      Message.success(tl('设备已更新'))
    } else {
      await deviceProfileApi.create({ ...form, project: projectId.value })
      Message.success(tl('设备已创建'))
    }
    modalVisible.value = false
    await refresh()
    return true
  } catch (error: any) {
    Message.error(error?.message || tl('保存设备失败'))
    return false
  } finally {
    submitting.value = false
  }
}

const removeDevice = async (device: UiDeviceProfile) => {
  try {
    await deviceProfileApi.delete(device.id)
    Message.success(tl('设备已删除'))
    await refresh()
  } catch (error: any) {
    Message.error(error?.message || tl('删除设备失败'))
  }
}

const sendDeviceCommand = async (action: 'start' | 'stop', device: UiDeviceProfile) => {
  try {
    await uiWebSocket.connect()
  } catch {
    Message.error(tl('WebSocket 连接失败，请刷新页面重试'))
    return
  }
  const sent = uiWebSocket.send(
    action === 'start' ? UiSocketEnum.APP_DEVICE_START : UiSocketEnum.APP_DEVICE_STOP,
    {
      action,
      avd_name: device.avd_name,
      device_name: device.device_name,
      headless: device.headless,
      snapshot_enabled: device.snapshot_enabled,
    },
  )
  if (!sent) {
    Message.error(tl('WebSocket 未连接，无法下发指令'))
    return
  }
  // 本地乐观更新：启动/停止指令已发出，等待执行器结果回调确认
  const target = devices.value.find((d) => d.id === device.id)
  if (target) target.status = action === 'start' ? 'starting' : 'stopping'
  Message.info(action === 'start' ? tl('启动指令已发送，请等待启动完成') : tl('停止指令已发送'))
}

const startDevice = (device: UiDeviceProfile) => sendDeviceCommand('start', device)
const stopDevice = (device: UiDeviceProfile) => sendDeviceCommand('stop', device)

const handleDeviceResult = (payload: any) => {
  // SocketDataModel: 真正的业务参数位于 data.func_args
  const args = payload?.data?.func_args || payload?.func_args || payload || {}
  const action = args.action
  const status = args.status
  const message = args.message
  const avdName = args.avd_name || args.device_name

  // 按设备同步本地状态
  const target = devices.value.find((d) => d.avd_name === avdName)
  if (target && !status) {
    // 无状态字段时按 action 推断
    target.status = action === 'start' ? 'running' : 'stopped'
  } else if (target && status) {
    if (status === 'error') {
      target.status = 'error'
    } else if (action === 'start') {
      target.status = status === 'running' || status === 'success' ? 'running' : target.status
    } else if (action === 'stop') {
      target.status = status === 'stopped' || status === 'success' ? 'stopped' : target.status
    } else if (action === 'status') {
      target.status = status === 'running' ? 'running' : 'stopped'
    }
  }

  if (status === 'error') {
    Message.error(message || tl('设备操作失败'))
  } else {
    Message.success(message || (action === 'start' ? tl('设备已启动') : action === 'stop' ? tl('设备已停止') : tl('设备操作成功')))
  }
  refresh()
}

defineExpose({ refresh })

onMounted(() => {
  refresh()
  uiWebSocket.on(UiSocketEnum.APP_DEVICE_RESULT, handleDeviceResult)
})

onBeforeUnmount(() => {
  uiWebSocket.off(UiSocketEnum.APP_DEVICE_RESULT, handleDeviceResult)
})
</script>

<style scoped>
.device-profile-list {
  padding: 8px 4px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.title h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.count {
  font-size: 12px;
  color: var(--color-text-3);
}

.actions {
  display: flex;
  gap: 8px;
}
</style>
