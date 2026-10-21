import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests',testMatch:'responsive.spec.ts',timeout:180_000,workers:2,retries:0,
 reporter:[['list'],['html',{open:'never',outputFolder:'responsive-report'}]],
 projects:['chromium','firefox','webkit','chromium-125','chromium-150','chromium-200'].map(name=>({name})),
 webServer:[
  {command:'node scripts/serve-test-ui.mjs',url:'http://127.0.0.1:4175',reuseExistingServer:false,timeout:15_000},
  {command:'node scripts/serve-test-fixtures.mjs',url:'http://127.0.0.1:4177',reuseExistingServer:false,timeout:15_000},
 ],
});
