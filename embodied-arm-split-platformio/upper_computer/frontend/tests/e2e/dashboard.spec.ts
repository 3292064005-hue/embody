import { expect, test } from '@playwright/test';

test('dashboard mock runtime bootstrap renders semantic status fields', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('ROS2 桌面具身智能机械臂主控 HMI')).toBeVisible();
  await expect(page.getByText(/CTRL /)).toBeVisible();
  await expect(page.getByText(/TASK /)).toBeVisible();
  await expect(page.getByText('READY')).toBeVisible();
});
