import type { CalibrationProfile, CalibrationProfileVersion, VisionTarget } from '@/models/vision';
import { unwrapResponse, apiClient, putVoid } from './client';

export async function fetchTargets(): Promise<VisionTarget[]> {
  return unwrapResponse(apiClient.get('/api/vision/targets'));
}

export async function fetchCalibrationProfile(): Promise<CalibrationProfile> {
  return unwrapResponse(apiClient.get('/api/calibration/profile'));
}

export async function fetchCalibrationVersions(): Promise<CalibrationProfileVersion[]> {
  return unwrapResponse(apiClient.get('/api/calibration/profiles'));
}

export async function saveCalibrationProfile(profile: CalibrationProfile): Promise<void> {
  await putVoid('/api/calibration/profile', profile);
}

export async function activateCalibrationProfile(profileId: string): Promise<void> {
  await putVoid(`/api/calibration/profiles/${profileId}/activate`);
}
