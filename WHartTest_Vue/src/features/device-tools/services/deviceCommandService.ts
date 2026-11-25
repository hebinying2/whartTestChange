import { request } from '@/utils/request';
import type {
  DeviceCatalog,
  DeviceCodeSource,
  DeviceCommandResult,
  DeviceExecutePayload,
} from '../types/deviceCommand';

const BASE = '/device-tools';

/** 获取设备类型、查询指令与参数定义。 */
export const getDeviceCatalog = () =>
  request<DeviceCatalog>({ url: `${BASE}/catalog/`, method: 'GET' });

/** 获取可配置的设备编码候选列表。 */
export const getDeviceCodes = () =>
  request<DeviceCodeSource>({ url: `${BASE}/device-codes/`, method: 'GET' });

/** 经后端代理执行一次设备查询指令。 */
export const executeDeviceCommand = (payload: DeviceExecutePayload) =>
  request<DeviceCommandResult>({ url: `${BASE}/execute/`, method: 'POST', data: payload });
