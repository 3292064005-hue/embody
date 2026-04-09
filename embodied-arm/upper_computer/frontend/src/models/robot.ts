export interface HardwareState {
  joints: number[];
  gripperOpen: boolean;
  homed: boolean;
  limits: boolean[];
  poseName?: string;
  busy: boolean;
  errorCode?: string;
  rawStatus?: Record<string, unknown>;
  sourceStm32Online?: boolean;
  sourceStm32Authoritative?: boolean;
  sourceStm32TransportMode?: string;
  sourceStm32Controllable?: boolean;
  sourceStm32Simulated?: boolean;
  sourceStm32SimulatedFallback?: boolean;
  sourceStm32ExecutionPreviewOnly?: boolean;
  sourceStm32ExecutionSemantics?: string;
  sourceEsp32Online?: boolean;
  sourceEsp32StreamSemantic?: string;
  sourceEsp32StreamReserved?: boolean;
  sourceCameraFrameIngressLive?: boolean;
  sourcePerceptionLive?: boolean;
}
