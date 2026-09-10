import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'light'});
 await page.addInitScript(()=>localStorage.setItem('memstara-selection-v1',JSON.stringify({runTag:null})));
 await page.goto('http://localhost:8070');await page.getByRole('button',{name:'Switch to light mode'}).waitFor();
 assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
 const bg=page.locator('.pipeline-background');await bg.waitFor({state:'attached',timeout:60000});
 assert.equal(await bg.evaluate(e=>getComputedStyle(e).visibility),'hidden');
 assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(16, 23, 34)');
 const darkStage=await page.locator('.react-flow__node-pipelineStage h3').first().evaluate(e=>getComputedStyle(e).color);
 assert.equal(darkStage,'rgb(129, 197, 151)');
 await page.screenshot({path:'/tmp/palette-dark.png'});
 await page.getByRole('button',{name:'Switch to light mode'}).click();assert.equal(await bg.evaluate(e=>getComputedStyle(e).visibility),'visible');
 assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(245, 243, 238)');
 assert.equal(await page.locator('.react-flow__node-pipelineStage h3').first().evaluate(e=>getComputedStyle(e).color),'rgb(47, 107, 71)');
 await page.screenshot({path:'/tmp/palette-light.png'});
 await page.reload();await page.getByRole('button',{name:'Switch to dark mode'}).waitFor();assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
 console.log('PASS: ivory and navy backgrounds; stage colors update with theme; dark dots hidden; default and saved preference retained.');
}finally{await browser.close();}
