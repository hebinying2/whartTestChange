<template>
  <div class="device-command-page">
    <header class="page-head">
      <div>
        <h2 class="page-title">{{ pageText.pageTitle }}</h2>
        <p class="page-desc">{{ pageText.pageDescription }}</p>
      </div>
    </header>

    <div class="workspace">
      <!-- 左：请求配置 -->
      <section class="panel">
        <div class="panel-head">
          <span class="bar" />
          <h3>{{ pageText.requestConfig }}</h3>
          <span class="hint">{{ pageText.keyHint }}</span>
        </div>

        <div class="panel-body">
          <a-spin :loading="catalogLoading" style="width: 100%">
            <div class="form-row">
              <label class="form-label req">{{ pageText.host }}</label>
              <div class="control">
                <a-select
                  v-model="host"
                  filterable
                >
                  <a-option
                    v-for="item in hostOptions"
                    :key="item"
                    :value="item"
                    :label="item"
                  />
                </a-select>
                <div class="field-hint">{{ pageText.hostHint }}</div>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label req">{{ pageText.apiKey }}</label>
              <div class="control">
                <a-input-password
                  v-model="apiKey"
                  :placeholder="pageText.apiKeyPlaceholder"
                  autocomplete="off"
                  allow-clear
                />
                <div class="field-hint">{{ pageText.apiKeyHint }}</div>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label req">{{ pageText.productType }}</label>
              <div class="control">
                <a-select v-model="productType" @change="handleProductTypeChange">
                  <a-option
                    v-for="item in productTypes"
                    :key="item.value"
                    :value="item.value"
                    :label="`${item.label}（${item.value}）`"
                  />
                </a-select>
                <div class="field-hint">{{ currentProduct?.description || '' }}</div>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label req">{{ pageText.vid }}</label>
              <div class="control">
                <a-auto-complete
                  v-model="vid"
                  :data="deviceCodeOptions"
                  :loading="deviceCodesLoading"
                  :placeholder="pageText.vidPlaceholder"
                  allow-clear
                  :filter-option="filterDeviceCode"
                  @focus="fetchDeviceCodes"
                />
                <div class="field-hint">{{ pageText.vidHint }}</div>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label req">{{ pageText.action }}</label>
              <div class="control">
                <a-select
                  v-model="actionKey"
                  allow-search
                  :filter-option="filterActionOption"
                  @change="handleActionChange"
                >
                  <a-option
                    v-for="item in currentActions"
                    :key="item.serviceId"
                    :value="item.serviceId"
                    :label="`${item.label}（${item.serviceId}）`"
                  />
                </a-select>
                <div class="field-hint">{{ currentAction?.description || '' }}</div>
              </div>
            </div>

            <div class="param-box">
              <div class="param-title">
                {{ pageText.params }}
                <span class="count">{{ paramCountText }}</span>
              </div>
              <div v-if="!currentParams.length" class="empty-params">{{ pageText.noParams }}</div>
              <div v-else class="param-grid">
                <div v-for="param in currentParams" :key="param.key" class="param-field">
                  <div class="p-label">
                    {{ param.label }}
                    <em>{{ param.key }}</em>
                    <span v-if="param.required" class="required-mark">*</span>
                  </div>
                  <a-input
                    v-model="paramValues[param.key]"
                    :type="param.type === 'number' ? 'number' : 'text'"
                    :placeholder="param.placeholder"
                    allow-clear
                  />
                  <div v-if="param.range" class="p-meta">
                    <span class="meta-label">{{ pageText.paramRange }}</span>
                    <span class="meta-value">{{ param.range }}</span>
                  </div>
                  <div v-if="param.definition" class="p-meta">
                    <span class="meta-label">{{ pageText.paramDefinition }}</span>
                    <span class="meta-value">{{ param.definition }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="divider" />

            <div class="preview-title">
              {{ pageText.preview }}
              <span class="mini">{{ pageText.previewHint }}</span>
            </div>
            <div class="url-box">
              <span class="method">POST</span>
              <span class="url-text">{{ previewUrl }}</span>
            </div>
            <div class="chips">
              <span class="chip">api-key: <b>{{ apiKey ? '••••••••' : pageText.notFilled }}</b></span>
              <span class="chip">content-type: <b>application/json</b></span>
            </div>
            <a-textarea
              v-model="bodyText"
              class="body-input"
              :auto-size="{ minRows: 6, maxRows: 14 }"
              spellcheck="false"
              @input="bodyEdited = true"
            />
            <div v-if="bodyEdited" class="body-flag">
              {{ pageText.bodyEdited }}
              <a-button type="text" size="mini" @click="forceRebuildBody">{{ pageText.rebuild }}</a-button>
            </div>

            <div class="actions">
              <a-button type="primary" long :loading="loading" @click="handleSend">
                {{ pageText.send }}
              </a-button>
              <a-button @click="resetAll">{{ pageText.reset }}</a-button>
              <a-button @click="copyCurl">{{ pageText.copyCurl }}</a-button>
            </div>
          </a-spin>
        </div>
      </section>

      <!-- 右：响应结果 -->
      <section class="panel">
        <div class="panel-head">
          <span class="bar" />
          <h3>{{ pageText.response }}</h3>
          <span class="hint">{{ responseHint }}</span>
        </div>

        <div v-if="loading" class="resp-loading">
          <a-spin dot />
          <span>{{ pageText.requesting }}</span>
        </div>

        <div v-else-if="!result" class="resp-empty">
          <div v-if="lastError" class="resp-error">{{ lastError }}</div>
          <template v-else>
            <p>{{ pageText.respEmpty }}</p>
            <span>{{ pageText.respEmptyHint }}</span>
          </template>
        </div>

        <div v-else>
          <div class="resp-meta">
            <span class="method-tag">POST</span>
            <span class="status-pill" :class="statusClass">{{ statusText }}</span>
            <span class="meta-text">{{ pageText.duration }} {{ result.durationMs }} ms</span>
            <span class="meta-text">{{ pageText.size }} {{ formatSize(result.sizeBytes) }}</span>
            <div class="meta-right">
              <a-button size="mini" @click="copyResponse">{{ pageText.copyResponse }}</a-button>
            </div>
          </div>

          <a-tabs v-model:active-key="activeTab" class="resp-tabs" lazy-load>
            <a-tab-pane key="body" :title="pageText.respBody">
              <div v-if="result.isJson" class="json-editor-shell">
                <VueMonacoEditor
                  :value="formattedBody"
                  language="json"
                  :theme="themeStore.isBlack ? 'vs-dark' : 'vs'"
                  :options="responseEditorOptions"
                />
              </div>
              <pre v-else class="code-block">{{ formattedBody }}</pre>
            </a-tab-pane>
            <a-tab-pane key="headers" :title="pageText.respHeaders">
              <div class="json-editor-shell">
                <VueMonacoEditor
                  :value="formattedHeaders"
                  language="json"
                  :theme="themeStore.isBlack ? 'vs-dark' : 'vs'"
                  :options="responseEditorOptions"
                />
              </div>
            </a-tab-pane>
          </a-tabs>
        </div>
      </section>
    </div>

    <!-- 会话内请求记录 -->
    <section class="panel history-panel">
      <div class="panel-head">
        <span class="bar" />
        <h3>{{ pageText.history }}</h3>
        <span class="hint">{{ pageText.historyHint }}</span>
      </div>
      <table class="history-table">
        <thead>
          <tr>
            <th style="width: 90px">{{ pageText.colTime }}</th>
            <th style="width: 120px">{{ pageText.colProduct }}</th>
            <th style="width: 180px">{{ pageText.colVid }}</th>
            <th>{{ pageText.colAction }}</th>
            <th style="width: 90px">{{ pageText.colStatus }}</th>
            <th style="width: 90px">{{ pageText.colDuration }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!history.length">
            <td colspan="6" class="empty-cell">{{ pageText.historyEmpty }}</td>
          </tr>
          <tr
            v-for="(item, index) in history"
            :key="`${item.time}-${index}`"
            class="history-row"
            @click="restoreHistory(item)"
          >
            <td class="mono">{{ item.time }}</td>
            <td><span class="tag">{{ item.productType }}</span></td>
            <td class="mono">{{ item.vid }}</td>
            <td>{{ actionLabel(item) }}</td>
            <td>
              <span class="tag" :class="item.status < 400 ? 'tag-green' : 'tag-red'">{{ item.status }}</span>
            </td>
            <td class="mono">{{ item.duration }} ms</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import {
  AutoComplete as AAutoComplete,
  Button as AButton,
  Input as AInput,
  InputPassword as AInputPassword,
  Message,
  Option as AOption,
  Select as ASelect,
  Spin as ASpin,
  TabPane as ATabPane,
  Tabs as ATabs,
  Textarea as ATextarea,
} from '@arco-design/web-vue';
import { useAppI18n } from '@/composables/useAppI18n';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import { useThemeStore } from '@/store/themeStore';
import { executeDeviceCommand, getDeviceCatalog, getDeviceCodes } from '../services/deviceCommandService';
import type {
  DeviceAction,
  DeviceCatalog,
  DeviceCommandHistoryItem,
  DeviceCommandResult,
  DeviceProductType,
} from '../types/deviceCommand';

const { isEnglish } = useAppI18n();
const themeStore = useThemeStore();

const pageText = computed(() => (
  isEnglish.value
    ? {
        pageTitle: 'Device Command Query',
        pageDescription: 'Assemble a query command by device type and relay it to the device gateway through the backend for debugging.',
        requestConfig: 'Request Config',
        keyHint: 'api-key is forwarded for this request only',
        host: 'Host',
        hostHint: 'Provided by backend whitelist; select one from the list.',
        apiKey: 'API Key',
        apiKeyPlaceholder: 'Enter api-key (memory only)',
        apiKeyHint: 'Confidential: never logged or stored; cleared after refresh.',
        productType: 'Device Type',
        vid: 'Device ID',
        vidPlaceholder: 'e.g. SN-20240001',
        vidHint: 'Used as {vid} in the request path.',
        action: 'Command',
        params: 'Parameters',
        noParams: 'This command takes no parameters',
        paramRange: 'Range:',
        paramDefinition: 'Definition:',
        preview: 'Request Preview',
        previewHint: '(auto-assembled, body is editable)',
        notFilled: 'Not set',
        bodyEdited: 'Body was edited manually.',
        rebuild: 'Rebuild',
        send: 'Send Request',
        reset: 'Reset',
        copyCurl: 'Copy cURL',
        requesting: 'Requesting device gateway…',
        response: 'Response',
        respEmpty: 'Send a request to see the gateway response here',
        respEmptyHint: 'Response body and headers are shown as JSON and can be copied.',
        duration: 'Duration',
        size: 'Size',
        copyResponse: 'Copy Response',
        respBody: 'Body',
        respHeaders: 'Headers',
        history: 'Session Request History',
        historyHint: 'In-memory only, cleared on refresh; click a row to restore.',
        historyEmpty: 'No requests yet',
        colTime: 'Time',
        colProduct: 'Type',
        colVid: 'Device ID',
        colAction: 'Command',
        colStatus: 'Status',
        colDuration: 'Duration',
        waiting: 'Waiting',
        latest: 'Latest request',
        loadFailed: 'Failed to load device catalog',
        fillKey: 'Please enter api-key',
        fillVid: 'Please enter device ID',
        fillParams: 'Please fill in required parameters',
        invalidJson: 'Body is not valid JSON',
        invalidBody: 'Body must be a JSON object',
        requestFailed: 'Request failed',
        copied: 'Copied',
        nothingToCopy: 'Nothing to copy',
        resetDone: 'Reset',
        restored: 'Configuration restored',
      }
    : {
        pageTitle: '设备指令查询',
        pageDescription: '按设备类型组装查询指令，经后端代理转发至设备接入网关，便于联调与排障。',
        requestConfig: '请求配置',
        keyHint: 'api-key 仅随本次请求转发，不保存',
        host: '服务地址',
        hostHint: '服务地址由后端白名单提供，仅允许从列表中选择。',
        apiKey: 'API Key',
        apiKeyPlaceholder: '请输入 api-key（仅内存使用）',
        apiKeyHint: '涉及机密：不写日志、不落库、刷新页面即清空。',
        productType: '设备类型',
        vid: '设备编号',
        vidPlaceholder: '如 SN-20240001',
        vidHint: '对应接口路径中的 {vid}。',
        action: '查询指令',
        params: '指令参数',
        noParams: '该指令无入参',
        paramRange: '范围：',
        paramDefinition: '定义：',
        preview: '请求预览',
        previewHint: '（自动组装，可手动修改 Body）',
        notFilled: '未填写',
        bodyEdited: 'Body 已被手动修改。',
        rebuild: '重新组装',
        send: '发送请求',
        reset: '重置',
        copyCurl: '复制 cURL',
        requesting: '正在请求设备网关…',
        response: '响应结果',
        respEmpty: '发送一次请求后，这里展示设备网关返回结果',
        respEmptyHint: '响应体与响应头将以 JSON 形式展示，支持一键复制。',
        duration: '耗时',
        size: '大小',
        copyResponse: '复制响应',
        respBody: '响应体',
        respHeaders: '响应头',
        history: '本次会话请求记录',
        historyHint: '仅保存在当前页面内存中，刷新即清空；点击行可恢复配置',
        historyEmpty: '暂无请求记录',
        colTime: '时间',
        colProduct: '设备类型',
        colVid: '设备编号',
        colAction: '查询指令',
        colStatus: '状态',
        colDuration: '耗时',
        waiting: '等待请求',
        latest: '最近一次请求',
        loadFailed: '加载设备指令目录失败',
        fillKey: '请先输入 api-key',
        fillVid: '请填写设备编号 vid',
        fillParams: '请补全必填的指令参数',
        invalidJson: 'Body 不是合法 JSON，请检查',
        invalidBody: 'Body 必须是 JSON 对象',
        requestFailed: '请求失败',
        copied: '已复制',
        nothingToCopy: '暂无可复制内容',
        resetDone: '已重置',
        restored: '已恢复该次请求配置',
      }
));

const catalogLoading = ref(false);
const catalog = ref<DeviceCatalog | null>(null);

// api-key 仅保存在组件内存中，不写入 localStorage。
const apiKey = ref('');
const host = ref('');
const productType = ref('');
const vid = ref('');
const actionKey = ref<number | ''>('');
const paramValues = reactive<Record<string, string>>({});

const bodyText = ref('');
const bodyEdited = ref(false);

const loading = ref(false);
const responseEditorOptions = {
  readOnly: true,
  domReadOnly: true,
  minimap: { enabled: false },
  fontSize: 13,
  lineNumbers: 'on' as const,
  renderLineHighlight: 'all' as const,
  scrollBeyondLastLine: false,
  wordWrap: 'off' as const,
  automaticLayout: true,
};
const deviceCodesLoading = ref(false);
const deviceCodeItems = ref<string[]>([]);
const deviceCodeSourceError = ref('');
const result = ref<DeviceCommandResult | null>(null);
const lastError = ref('');
const activeTab = ref<'body' | 'headers'>('body');
const history = ref<DeviceCommandHistoryItem[]>([]);

const productTypes = computed<DeviceProductType[]>(() => catalog.value?.productTypes || []);
const hostOptions = computed<string[]>(() => {
  const options = catalog.value?.hostOptions || [];
  return options.length ? options : catalog.value?.host ? [catalog.value.host] : [];
});
const currentProduct = computed(() => productTypes.value.find((item) => item.value === productType.value));
const currentActions = computed<DeviceAction[]>(() => currentProduct.value?.actions || []);
const currentAction = computed(() => currentActions.value.find((item) => item.serviceId === actionKey.value));
const currentParams = computed(() => currentAction.value?.params || []);
const deviceCodeOptions = computed(() => deviceCodeItems.value);

const paramCountText = computed(() => (
  currentParams.value.length
    ? (isEnglish.value ? `${currentParams.value.length} parameter(s)` : `共 ${currentParams.value.length} 个参数`)
    : ''
));

const previewUrl = computed(() => {
  const selectedHost = (host.value || catalog.value?.host || '').replace(/\/+$/, '');
  const template = catalog.value?.pathTemplate || '/api/devices/{productType}/{vid}/action/execute';
  const path = template
    .replace('{productType}', 'ESD')
    .replace('{vid}', vid.value.trim() || '{vid}');
  return `${selectedHost}${path}`;
});

function filterDeviceCode(inputValue: string, option: string): boolean {
  const keyword = inputValue.trim().toLowerCase();
  if (!keyword) return true;
  return option.toLowerCase().includes(keyword);
}

function filterActionOption(inputValue: string, option: any): boolean {
  const keyword = inputValue.trim().toLowerCase();
  if (!keyword) return true;
  const label = String(option?.label ?? '').toLowerCase();
  const value = String(option?.value ?? '').toLowerCase();
  return label.includes(keyword) || value.includes(keyword);
}

async function fetchDeviceCodes() {
  if (deviceCodesLoading.value) return;
  deviceCodesLoading.value = true;
  const res = await getDeviceCodes();
  deviceCodesLoading.value = false;
  if (!res.success || !res.data) return;
  deviceCodeItems.value = res.data.items || [];
  deviceCodeSourceError.value = res.data.error || '';
  if (deviceCodeSourceError.value) {
    Message.warning(deviceCodeSourceError.value);
  }
}

const responseHint = computed(() => {
  if (loading.value) return pageText.value.requesting;
  return result.value ? pageText.value.latest : pageText.value.waiting;
});

const statusText = computed(() => {
  if (!result.value) return '';
  const suffix = result.value.truncated
    ? (isEnglish.value ? ' (truncated)' : '（已截断）')
    : '';
  return `${result.value.upstreamStatus}${suffix}`;
});

const statusClass = computed(() => (
  result.value && result.value.upstreamStatus < 400 ? 'status-ok' : 'status-err'
));

const formattedBody = computed(() => {
  if (!result.value) return '';
  if (!result.value.isJson) return result.value.bodyText;
  try {
    return JSON.stringify(result.value.body, null, 2);
  } catch {
    return result.value.bodyText;
  }
});

const formattedHeaders = computed(() => (
  result.value ? JSON.stringify(result.value.headers, null, 2) : ''
));

function buildBody(): string {
  const action = currentAction.value;
  const body: Record<string, unknown> = { serviceId: actionKey.value };
  if (action && action.params.length) {
    const params: Record<string, unknown> = {};
    action.params.forEach((param) => {
      const raw = (paramValues[param.key] ?? '').trim();
      if (raw === '') return;
      params[param.key] = param.type === 'number' ? Number(raw) : raw;
    });
    body.params = params;
  }
  return JSON.stringify(body, null, 2);
}

function resetParamValues() {
  Object.keys(paramValues).forEach((key) => delete paramValues[key]);
  currentParams.value.forEach((param) => {
    paramValues[param.key] = param.default ?? '';
  });
}

function forceRebuildBody() {
  bodyEdited.value = false;
  bodyText.value = buildBody();
}

function handleProductTypeChange() {
  actionKey.value = currentActions.value[0]?.serviceId ?? '';
  resetParamValues();
  forceRebuildBody();
}

function handleActionChange() {
  resetParamValues();
  forceRebuildBody();
}

// 参数变化时自动重新组装 Body（手动编辑过则跳过）。
watch(paramValues, () => {
  if (!bodyEdited.value) {
    bodyText.value = buildBody();
  }
}, { deep: true });

async function loadCatalog() {
  catalogLoading.value = true;
  const res = await getDeviceCatalog();
  catalogLoading.value = false;
  if (!res.success || !res.data) {
    Message.error(res.error || pageText.value.loadFailed);
    return;
  }
  catalog.value = res.data;
  host.value = res.data.host;
  const first = res.data.productTypes[0];
  if (first) {
    productType.value = first.value;
    actionKey.value = first.actions[0]?.serviceId ?? '';
    resetParamValues();
    forceRebuildBody();
  }
}

function validate(): Record<string, unknown> | null {
  if (!apiKey.value.trim()) {
    Message.warning(pageText.value.fillKey);
    return null;
  }
  if (!vid.value.trim()) {
    Message.warning(pageText.value.fillVid);
    return null;
  }
  const missing = currentParams.value.filter(
    (param) => param.required && !(paramValues[param.key] ?? '').trim(),
  );
  if (missing.length) {
    Message.warning(pageText.value.fillParams);
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText.value);
  } catch {
    Message.error(pageText.value.invalidJson);
    return null;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    Message.error(pageText.value.invalidBody);
    return null;
  }
  return parsed as Record<string, unknown>;
}

async function handleSend() {
  const body = validate();
  if (!body) return;

  loading.value = true;
  lastError.value = '';
  const res = await executeDeviceCommand({
    productType: productType.value,
    vid: vid.value.trim(),
    apiKey: apiKey.value.trim(),
    host: host.value,
    body,
  });
  loading.value = false;

  if (!res.success || !res.data) {
    result.value = null;
    lastError.value = res.error || res.message || pageText.value.requestFailed;
    Message.error(lastError.value);
    return;
  }

  result.value = res.data;
  activeTab.value = 'body';

  history.value.unshift({
    time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    productType: productType.value,
    vid: vid.value.trim(),
    action: String(actionKey.value),
    status: res.data.upstreamStatus,
    duration: res.data.durationMs,
  });
  history.value = history.value.slice(0, 20);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function actionLabel(item: DeviceCommandHistoryItem): string {
  const product = productTypes.value.find((p) => p.value === item.productType);
  const action = product?.actions.find((a) => String(a.serviceId) === item.action);
  return action ? action.label : item.action;
}

function copyText(text: string) {
  if (!text) {
    Message.info(pageText.value.nothingToCopy);
    return;
  }
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => Message.success(pageText.value.copied));
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
  Message.success(pageText.value.copied);
}

function copyResponse() {
  copyText(formattedBody.value || formattedHeaders.value);
}

function copyCurl() {
  const url = previewUrl.value || '{url}';
  const curl = `curl -X POST '${url}' \\\n  -H 'api-key: $DEVICE_API_KEY' \\\n  -H 'content-type: application/json' \\\n  -d '${bodyText.value.replace(/\n/g, '')}'`;
  copyText(curl);
}

function resetAll() {
  apiKey.value = '';
  vid.value = '';
  bodyEdited.value = false;
  bodyText.value = buildBody();
  result.value = null;
  lastError.value = '';
  activeTab.value = 'body';
  Message.success(pageText.value.resetDone);
}

function restoreHistory(item: DeviceCommandHistoryItem) {
  productType.value = item.productType;
  nextTick(() => {
    actionKey.value = Number(item.action) || '';
    vid.value = item.vid;
    bodyEdited.value = false;
    resetParamValues();
    bodyText.value = buildBody();
    Message.info(pageText.value.restored);
  });
}

onMounted(() => {
  loadCatalog();
  fetchDeviceCodes();
});
</script>

<style scoped>
.device-command-page {
  height: 100%;
  box-sizing: border-box;
  padding: 16px 20px 32px;
  overflow-y: auto;
  color: var(--color-text-1);
}

.page-head {
  margin-bottom: 14px;
}

.page-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
}

.page-desc {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-3);
}

.workspace {
  display: grid;
  grid-template-columns: minmax(380px, 470px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.panel {
  background: var(--color-bg-2);
  border: 1px solid var(--color-border-1);
  border-radius: 8px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--color-border-1);
}

.panel-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.panel-head .bar {
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: rgb(var(--primary-6));
}

.panel-head .hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--color-text-3);
}

.panel-body {
  padding: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  margin-bottom: 14px;
}

.form-label {
  font-size: 13px;
  color: var(--color-text-2);
  text-align: right;
  line-height: 32px;
}

.form-label.req::after {
  content: '*';
  color: rgb(var(--danger-6));
  margin-left: 3px;
}

.field-hint {
  font-size: 11px;
  color: var(--color-text-3);
  margin-top: 5px;
  line-height: 1.5;
}

.param-box {
  background: var(--color-fill-1);
  border: 1px solid var(--color-border-1);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 14px;
}

.param-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-2);
  margin-bottom: 10px;
}

.param-title .count {
  color: var(--color-text-3);
  font-weight: 400;
}

.param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.p-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-2);
  margin-bottom: 5px;
}

.p-label em {
  font-style: normal;
  font-size: 11px;
  color: var(--color-text-3);
}

.p-label .required-mark {
  color: rgb(var(--danger-6));
}

.p-meta {
  display: flex;
  gap: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-3);
  margin-top: 4px;
  word-break: break-word;
}

.p-meta .meta-label {
  flex-shrink: 0;
  color: var(--color-text-3);
}

.p-meta .meta-value {
  flex: 1;
  color: var(--color-text-2);
}

.empty-params {
  font-size: 12px;
  color: var(--color-text-3);
  padding: 4px 0;
}

.divider {
  height: 1px;
  background: var(--color-border-1);
  margin: 16px -16px;
}

.preview-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-2);
  margin-bottom: 10px;
}

.preview-title .mini {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-3);
}

.url-box {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 12px;
  line-height: 1.55;
  background: var(--color-fill-1);
  border: 1px solid var(--color-border-2);
  border-radius: 4px;
  padding: 8px 10px;
  word-break: break-all;
  margin-bottom: 10px;
}

.url-box .method {
  color: rgb(var(--primary-6));
  font-weight: 700;
  margin-right: 6px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.chip {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 11px;
  color: var(--color-text-2);
  background: var(--color-fill-1);
  border: 1px solid var(--color-border-1);
  border-radius: 3px;
  padding: 3px 7px;
}

.chip b {
  color: var(--color-text-1);
  font-weight: 500;
}

.body-input :deep(textarea) {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}

.body-flag {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgb(var(--warning-6));
  margin-top: 5px;
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.actions :deep(.arco-btn-primary) {
  flex: 1;
}

.resp-empty {
  padding: 90px 20px;
  text-align: center;
  color: var(--color-text-3);
  font-size: 13px;
}

.resp-empty p {
  margin: 0 0 6px;
}

.resp-empty span {
  font-size: 12px;
  color: var(--color-text-4);
}

.resp-error {
  margin: 0 20px;
  padding: 10px 14px;
  border-radius: 6px;
  background: var(--color-danger-light-1);
  color: rgb(var(--danger-6));
  font-size: 12px;
}

.resp-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 90px 0;
  font-size: 13px;
  color: var(--color-text-3);
}

.resp-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-1);
}

.method-tag {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 11px;
  font-weight: 700;
  color: rgb(var(--primary-6));
  background: var(--color-primary-light-1);
  border-radius: 3px;
  padding: 2px 6px;
}

.status-pill {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.status-ok {
  color: rgb(var(--success-6));
  background: var(--color-success-light-1);
}

.status-err {
  color: rgb(var(--danger-6));
  background: var(--color-danger-light-1);
}

.meta-text {
  font-size: 12px;
  color: var(--color-text-3);
}

.meta-right {
  margin-left: auto;
}

.resp-tabs {
  padding: 0 16px 16px;
}

.json-editor-shell {
  height: 430px;
  border: 1px solid var(--color-border-1);
  border-radius: 6px;
  overflow: hidden;
  background: var(--color-fill-1);
}

:deep(.json-editor-shell .monaco-editor),
:deep(.json-editor-shell .overflow-guard) {
  height: 100%;
  width: 100%;
}

:deep(.json-editor-shell .monaco-editor-background) {
  background: var(--color-fill-1) !important;
}

:deep(.json-editor-shell .margin) {
  background: var(--color-fill-1) !important;
}

.code-block {
  margin: 0;
  padding: 12px 14px;
  min-height: 300px;
  max-height: 430px;
  overflow: auto;
  background: var(--color-fill-1);
  border: 1px solid var(--color-border-1);
  border-radius: 6px;
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre;
}

.history-panel {
  margin-top: 16px;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
}

.history-table th {
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-3);
  background: var(--color-fill-1);
  padding: 9px 14px;
  border-bottom: 1px solid var(--color-border-1);
}

.history-table td {
  font-size: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border-1);
}

.history-table tbody tr:last-child td {
  border-bottom: none;
}

.history-row {
  cursor: pointer;
}

.history-row:hover {
  background: var(--color-fill-1);
}

.empty-cell {
  text-align: center;
  color: var(--color-text-3);
  padding: 26px 0 !important;
}

.mono {
  font-family: var(--mono, 'JetBrains Mono', Consolas, monospace);
  font-size: 11.5px;
}

.tag {
  display: inline-block;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 3px;
  background: var(--color-fill-2);
  color: var(--color-text-2);
}

.tag-green {
  background: var(--color-success-light-1);
  color: rgb(var(--success-6));
}

.tag-red {
  background: var(--color-danger-light-1);
  color: rgb(var(--danger-6));
}

@media (max-width: 1280px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .code-block {
    max-height: 340px;
  }
}
</style>
