export type MockRuntimeMode = 'gateway' | 'fixture';

function normalizeMode(value: string | undefined): MockRuntimeMode {
  return String(value || 'gateway').trim().toLowerCase() === 'fixture' ? 'fixture' : 'gateway';
}

export const MOCK_RUNTIME_ENABLED = import.meta.env.VITE_ENABLE_MOCK === 'true';
export const MOCK_RUNTIME_MODE: MockRuntimeMode = normalizeMode(import.meta.env.VITE_API_MOCK_MODE);

export function isFixtureMockEnabled(): boolean {
  return MOCK_RUNTIME_ENABLED && MOCK_RUNTIME_MODE === 'fixture';
}

export function isGatewayMockEnabled(): boolean {
  return MOCK_RUNTIME_ENABLED && MOCK_RUNTIME_MODE === 'gateway';
}
