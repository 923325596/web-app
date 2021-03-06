import Account from '@/views/Account.vue';
import ExchangesOverview from '@/views/ExchangesOverview.vue';
import Home from '@/views/Home.vue';
import NotFound from '@/views/NotFound.vue';
import SignIn from '@/views/SignIn.vue';
import SignUp from '@/views/SignUp.vue';
import Vue from 'vue';
import Router from 'vue-router';

Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/',
      name: 'Home',
      component: Home,
    },
    {
      path: '/sign-in',
      name: 'SignIn',
      component: SignIn,
    },
    {
      path: '/sign-up',
      name: 'SignUp',
      component: SignUp,
    },
    {
      path: '/sign-out',
      redirect: '/',
    },
    {
      path: '/account',
      name: 'Account',
      component: Account,
    },
    {
      path: '/exchanges/overview',
      name: 'ExchangesOverview',
      component: ExchangesOverview,
    },
    {
      path: '**',
      name: 'NotFound',
      component: NotFound,
    },
  ],
});
