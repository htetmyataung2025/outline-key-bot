import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from '@/views/OverviewView.vue'
import SlipsView from '@/views/SlipsView.vue'
import KeysView from '@/views/KeysView.vue'
import RedeemsView from '@/views/RedeemsView.vue'
import PurchasesView from '@/views/PurchasesView.vue'
import CustomersView from '@/views/CustomersView.vue'
import CustomerDetailView from '@/views/CustomerDetailView.vue'
import SettingsView from '@/views/SettingsView.vue'

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'Overview', component: OverviewView },
  { path: '/slips', name: 'Slips', component: SlipsView },
  { path: '/purchases', name: 'Purchases', component: PurchasesView },
  { path: '/keys', name: 'Keys', component: KeysView },
  { path: '/redeems', name: 'Redeems', component: RedeemsView },
  { path: '/customers', name: 'Customers', component: CustomersView },
  { path: '/customers/:chatId', name: 'CustomerDetail', component: CustomerDetailView, props: true },
  { path: '/settings', name: 'Settings', component: SettingsView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
