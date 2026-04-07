import type { AxiosAdapter, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { mockRuntime } from '@/shared/mock/runtime';
import { generateRequestId } from '@/utils/id';
import type { ApiResponse } from '@/models/api';

function normalizeUrl(url?: string): string {
  return (url || '').replace(/^https?:\/\/[^/]+/, '');
}

function parseBody(data: unknown): Record<string, unknown> {
  if (!data) return {};
  if (typeof data === 'string') {
    try {
      return JSON.parse(data) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  if (typeof data === 'object') return data as Record<string, unknown>;
  return {};
}

function buildResponse<T>(config: AxiosRequestConfig, data: T, status = 200, message = 'ok'): AxiosResponse<ApiResponse<T>> {
  const response: ApiResponse<T> = {
    code: status === 200 ? 0 : status,
    message,
    requestId: String(config.headers?.['X-Request-Id'] || generateRequestId()),
    timestamp: new Date().toISOString(),
    data
  };
  return {
    data: response,
    status,
    statusText: status === 200 ? 'OK' : 'ERROR',
    headers: config.headers || {},
    config: config as InternalAxiosRequestConfig
  };
}

async function resolveMock(config: AxiosRequestConfig): Promise<AxiosResponse> {
  const method = String(config.method || 'get').toLowerCase();
  const url = normalizeUrl(config.url);
  const body = parseBody(config.data);

  await new Promise((resolve) => setTimeout(resolve, 80));

  if (method === 'get' && url === '/api/system/summary') return buildResponse(config, mockRuntime.getSystemSummary());
  if (method === 'get' && url === '/api/system/readiness') return buildResponse(config, mockRuntime.getReadiness());
  if (method === 'post' && url === '/api/system/home') return buildResponse(config, mockRuntime.homeRobot());
  if (method === 'post' && url === '/api/system/reset-fault') return buildResponse(config, mockRuntime.resetFault());
  if (method === 'post' && url === '/api/system/emergency-stop') return buildResponse(config, mockRuntime.emergencyStop());

  if (method === 'get' && url === '/api/task/current') return buildResponse(config, mockRuntime.getCurrentTask());
  if (method === 'get' && url === '/api/task/templates') return buildResponse(config, mockRuntime.getTaskTemplates());
  if (method === 'get' && url === '/api/task/history') return buildResponse(config, mockRuntime.getTaskHistory());
  if (method === 'post' && url === '/api/task/start') return buildResponse(config, mockRuntime.startTask(body));
  if (method === 'post' && url === '/api/task/stop') return buildResponse(config, mockRuntime.stopTask());

  if (method === 'get' && url === '/api/vision/targets') return buildResponse(config, mockRuntime.getTargets());
  if (method === 'get' && url === '/api/calibration/profile') return buildResponse(config, mockRuntime.getCalibrationProfile());
  if (method === 'get' && (url === '/api/calibration/profiles' || url === '/api/calibration/versions')) return buildResponse(config, mockRuntime.getCalibrationVersions());
  if ((method === 'put' || method === 'post') && url === '/api/calibration/profile') return buildResponse(config, mockRuntime.saveCalibrationProfile(body));
  if ((method === 'put' || method === 'post') && /\/api\/calibration\/(profiles\/[^/]+\/activate|activate)$/.test(url)) {
    const profileId = String(body.profileId || url.split('/').at(-2) || '');
    return buildResponse(config, mockRuntime.activateCalibrationProfile(profileId));
  }
  if (method === 'post' && url === '/api/calibration/reload') return buildResponse(config, mockRuntime.getCalibrationProfile());

  if (method === 'get' && url === '/api/hardware/state') return buildResponse(config, mockRuntime.getHardwareState());
  if (method === 'post' && url === '/api/hardware/gripper') return buildResponse(config, mockRuntime.commandGripper(Boolean(body.open)));
  if (method === 'post' && url === '/api/hardware/jog-joint') return buildResponse(config, mockRuntime.jogJoint(Number(body.jointIndex), Number(body.direction) as -1 | 1, Number(body.stepDeg)));
  if (method === 'post' && url === '/api/hardware/servo-cartesian') {
    try {
      return buildResponse(config, mockRuntime.servoCartesian(String(body.axis || 'x'), Number(body.delta || 0)));
    } catch (error) {
      return buildResponse(config, null, 409, error instanceof Error ? error.message : 'SERVO_CARTESIAN 执行失败');
    }
  }
  if (method === 'post' && url === '/api/hardware/set-mode') return buildResponse(config, mockRuntime.setControllerMode(String(body.mode || 'idle')));

  if (method === 'get' && (url === '/api/logs' || url === '/api/logs/events')) return buildResponse(config, mockRuntime.getLogs());
  if (method === 'get' && url === '/api/logs/audit') return buildResponse(config, mockRuntime.getAuditLogs());
  if (method === 'get' && url === '/api/diagnostics/summary') return buildResponse(config, mockRuntime.getDiagnosticsSummary());

  return buildResponse(config, null, 404);
}

export const mockApiAdapter: AxiosAdapter = (config) => resolveMock(config);
