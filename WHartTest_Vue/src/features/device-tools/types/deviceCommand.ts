/**
 * 设备指令查询相关类型定义。
 * 结构与后端 /api/device-tools/catalog/ 返回保持一致（camelCase）。
 */

export interface DeviceActionParam {
  key: string;
  label: string;
  type: 'text' | 'number';
  required: boolean;
  placeholder: string;
  default: string;
  /** 输入参数数据范围。 */
  range: string;
  /** 输入参数定义。 */
  definition: string;
}

export interface DeviceAction {
  serviceId: number;
  label: string;
  description: string;
  params: DeviceActionParam[];
}

export interface DeviceProductType {
  value: string;
  label: string;
  description: string;
  actions: DeviceAction[];
}

export interface DeviceCodeSource {
  /** 是否已配置设备编码数据源。 */
  configured: boolean;
  /** 可选设备编码列表。 */
  items: string[];
  /** 数据源查询失败或配置异常时的提示信息。 */
  error: string;
}

export interface DeviceCatalog {
  /** 默认设备接入网关地址。 */
  host: string;
  /** 后端白名单内的可选设备接入网关地址。 */
  hostOptions: string[];
  /** 接口路径模板，含 {productType} 与 {vid}。 */
  pathTemplate: string;
  productTypes: DeviceProductType[];
}

export interface DeviceExecutePayload {
  productType: string;
  vid: string;
  /** 仅随本次请求转发，不持久化。 */
  apiKey: string;
  /** 后端白名单内的服务地址。 */
  host: string;
  body: Record<string, unknown>;
}

export interface DeviceCommandResult {
  method: string;
  url: string;
  upstreamStatus: number;
  durationMs: number;
  sizeBytes: number;
  truncated: boolean;
  headers: Record<string, string>;
  body: unknown;
  bodyText: string;
  isJson: boolean;
}

export interface DeviceCommandHistoryItem {
  time: string;
  productType: string;
  vid: string;
  action: string;
  status: number;
  duration: number;
}
