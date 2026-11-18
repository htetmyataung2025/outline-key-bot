import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'Overview', component: () => import('@/views/OverviewView.vue') },
  { path: '/slips', name: 'Slips', component: () => import('@/views/SlipsView.vue') },
  { path: '/purchases', name: 'Purchases', component: () => import('@/views/PurchasesView.vue') },
  { path: '/keys', name: 'Keys', component: () => import('@/views/KeysView.vue') },
  { path: '/redeems', name: 'Redeems', component: () => import('@/views/RedeemsView.vue') },
  { path: '/customers', name: 'Customers', component: () => import('@/views/CustomersView.vue') },
  { path: '/customers/:chatId', name: 'CustomerDetail', component: () => import('@/views/CustomerDetailView.vue'), props: true },
  { path: '/settings', name: 'Settings', component: () => import('@/views/SettingsView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
