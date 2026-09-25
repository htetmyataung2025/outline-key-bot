import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from '@/views/OverviewView.vue'
import SlipsView from '@/views/SlipsView.vue'
import KeysView from '@/views/KeysView.vue'
import RedeemsView from '@/views/RedeemsView.vue'
import CustomersView from '@/views/CustomersView.vue'

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'Overview', component: OverviewView },
  { path: '/slips', name: 'Slips', component: SlipsView },
  { path: '/keys', name: 'Keys', component: KeysView },
  { path: '/redeems', name: 'Redeems', component: RedeemsView },
  { path: '/customers', name: 'Customers', component: CustomersView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
