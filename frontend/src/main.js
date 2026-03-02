import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/css/fonts.css'
import './assets/css/colors.css'
import 'vue-multiselect/dist/vue-multiselect.css'
import '@vuepic/vue-datepicker/dist/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

router.afterEach((to) => {
  document.title = to.meta.metaTitle? `Chronika | ${to.meta.metaTitle}` : 'Chronika';
});

app.mount('#app')
