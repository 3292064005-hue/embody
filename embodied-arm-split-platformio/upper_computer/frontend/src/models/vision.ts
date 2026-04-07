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
