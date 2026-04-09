import axios from 'axios';
import type { AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';
import { ApiClientError, type ApiResponse, type ApiErrorPayload } from '@/models/api';
import { generateRequestId } from '@/utils/id';
import { readLocalStorage } from '@/utils/storage';
import type { OperatorRole } from '@/models/safety';
import { mockApiAdapter } from './mockAdapter';
import { isFixtureMockEnabled } from '@/shared/mock/mode';

const DEFAULT_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT_MS || 8000);
const USE_NETWORK_MOCK = isFixtureMockEnabled();
const APP_ROLE_KEY = 'embodied-arm-hmi:operator-role';
const LEGACY_APP_ROLE_KEY = 'embodied-arm-hmi:operator-mode';

function readOperatorRoleHeaderValue(): OperatorRole {
  const role = readLocalStorage<OperatorRole>(APP_ROLE_KEY, readLocalStorage<OperatorRole>(LEGACY_APP_ROLE_KEY, 'operator'));
  return role === 'viewer' || role === 'operator' || role === 'maintainer' ? role : 'operator';
}

function withRequestContext(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  const headers = config.headers;
  headers.set?.('X-Request-Id', generateRequestId());
  headers.set?.('X-Client-Source', 'embodied-arm-hmi');
  headers.set?.('X-Requested-At', new Date().toISOString());
  const operatorRole = readOperatorRoleHeaderValue();
  headers.set?.('X-Operator-Role', operatorRole);
  return config;
}

function normalizeAxiosError(error: AxiosError<ApiErrorPayload>): never {
  const response = error.response;
  const payload = response?.data;
  throw new ApiClientError(
    payload?.message || error.message || '请求失败',
    {
      status: response?.status,
      code: payload?.code,
      requestId: payload?.requestId,
      detail: payload?.detail,
      error: payload?.error,
      failureClass: payload?.failureClass,
      operatorActionable: payload?.operatorActionable
    }
  );
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  timeout: DEFAULT_TIMEOUT,
  adapter: USE_NETWORK_MOCK ? mockApiAdapter : undefined
});

apiClient.interceptors.request.use(withRequestContext);
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => normalizeAxiosError(error)
);

export async function unwrapResponse<T>(request: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const response = await request;
  return response.data.data;
}

export async function postVoid(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<void> {
  await apiClient.post(url, data, config);
}

export async function putVoid(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<void> {
  await apiClient.put(url, data, config);
}
