import { createApp } from 'vue';
import { createPinia } from 'pinia';
import {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus';

import 'element-plus/es/components/base/style/css';
import 'element-plus/es/components/button/style/css';
import 'element-plus/es/components/form/style/css';
import 'element-plus/es/components/form-item/style/css';
import 'element-plus/es/components/input/style/css';
import 'element-plus/es/components/input-number/style/css';
import 'element-plus/es/components/message/style/css';
import 'element-plus/es/components/message-box/style/css';
import 'element-plus/es/components/notification/style/css';
import 'element-plus/es/components/option/style/css';
import 'element-plus/es/components/select/style/css';
import 'element-plus/es/components/switch/style/css';
import 'element-plus/es/components/table/style/css';
import 'element-plus/es/components/table-column/style/css';
import 'element-plus/es/components/tag/style/css';

import App from './App.vue';
import router from './router';
import './styles/index.css';

const app = createApp(App);
const pinia = createPinia();

const GLOBAL_ELEMENT_COMPONENTS = {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
} as const;

app.use(pinia);
app.use(router);
Object.entries(GLOBAL_ELEMENT_COMPONENTS).forEach(([name, component]) => {
  app.component(name, component);
});

app.mount('#app');
