export interface VisionTarget {
  id: string;
  category: string;
  pixelX: number;
  pixelY: number;
  worldX: number;
  worldY: number;
  angle?: number;
  confidence: number;
  graspable: boolean;
}

export interface VisionFrame {
  available: boolean;
  width?: number;
  height?: number;
  frameId?: string;
  source?: string;
  sourceType?: string;
  mockProfile?: string;
  frameSequence?: number;
  targetCount: number;
  previewDataUrl?: string;
  providerKind?: string;
  providerLabel?: string;
  frameIngressMode?: string;
  frameIngressLive?: boolean;
  cameraLive?: boolean;
  syntheticPreview?: boolean;
  frameTransportHealthy?: boolean;
  authoritativeVisualSource?: string;
  capturedAt?: string;
  message?: string;
  summary?: Record<string, unknown> | string;
}

export interface CalibrationProfile {
  profileName: string;
  roi: { x: number; y: number; width: number; height: number };
  tableScaleMmPerPixel: number;
  offsets: { x: number; y: number; z: number };
  updatedAt: string;
}

export interface CalibrationProfileVersion extends CalibrationProfile {
  id: string;
  operator: string;
  meanErrorMm?: number;
  maxErrorMm?: number;
  sampleCount?: number;
  active?: boolean;
}
