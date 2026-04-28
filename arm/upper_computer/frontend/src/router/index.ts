import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import AppLayout from '@/layouts/AppLayout.vue';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/dashboard' },
      { path: '/dashboard', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
      { path: '/tasks', name: 'tasks', component: () => import('@/pages/TaskCenterPage.vue') },
      { path: '/vision', name: 'vision', component: () => import('@/pages/VisionCalibrationPage.vue') },
      { path: '/maintenance', name: 'maintenance', component: () => import('@/pages/MaintenancePage.vue') },
      { path: '/logs', name: 'logs', component: () => import('@/pages/LogsPage.vue') },
      { path: '/settings', name: 'settings', component: () => import('@/pages/SettingsPage.vue') }
    ]
  }
];

export default createRouter({
  history: createWebHistory(),
  routes
});
