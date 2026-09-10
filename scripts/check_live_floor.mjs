// Inspect the served floor plan without starting an analysis.
import assert from 'node:assert/strict';
const {default:puppeteer}=await import(process.env.PUPPETEER_MODULE||'puppeteer');
const browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox']});
try {
 const page=await browser.newPage(); await page.setViewport({width:1440,height:1000});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8070',{waitUntil:'networkidle0'});
 await page.evaluate(()=>[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('Floor plan')).click());
 await page.waitForSelector('.react-flow__node-zone');
 await new Promise(r=>setTimeout(r,500));
 assert.equal((await page.$$('.react-flow__node-zone')).length,2);
 const agents=(await page.$$('.react-flow__node-agent')).length;
 assert(agents>=5&&agents<=7);
 await page.screenshot({path:'/tmp/memstara-floor-professional-live.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('PASS: resource and agent layers served; 1–3 hypotheses; no browser errors or analysis started');
} finally {await browser.close();}
