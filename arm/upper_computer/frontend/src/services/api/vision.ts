import type { CalibrationProfile, CalibrationProfileVersion, VisionFrame, VisionTarget } from '@/models/vision';
import {
  activateCalibrationProfileVersion,
  clearVisionTargetSet,
  getCalibrationProfile,
  getCalibrationVersions,
  getVisionFrame,
  getVisionTargets,
  putCalibrationProfile,
} from '@/api/generated';

export async function fetchTargets(): Promise<VisionTarget[]> {
  return getVisionTargets();
}

export async function fetchVisionFrame(): Promise<VisionFrame> {
  return getVisionFrame();
}

export async function fetchCalibrationProfile(): Promise<CalibrationProfile> {
  return getCalibrationProfile();
}

export async function fetchCalibrationVersions(): Promise<CalibrationProfileVersion[]> {
  return getCalibrationVersions();
}

export async function saveCalibrationProfile(profile: CalibrationProfile): Promise<void> {
  await putCalibrationProfile(profile);
}

export async function activateCalibrationProfile(profileId: string): Promise<void> {
  await activateCalibrationProfileVersion(profileId);
}

export async function clearVisionTargets(): Promise<void> {
  await clearVisionTargetSet();
}
