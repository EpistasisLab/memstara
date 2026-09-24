// Verify the served UI without launching a pipeline or modifying the existing run.
import assert from 'node:assert/strict';
const {default:puppeteer}=await import(process.env.PUPPETEER_MODULE||'puppeteer');
const browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox']});
try{
 const page=await browser.newPage();await page.setViewport({width:1440,height:1000});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8070',{waitUntil:'networkidle0'});
 await page.hover('button[aria-label="Help: Trials"]');
 await page.waitForFunction(()=>[...document.querySelectorAll('[role="tooltip"]')].some(n=>n.textContent.includes('does not create 4 agents')));
 await page.screenshot({path:'/tmp/memstara-live-help.png',fullPage:true});
 await page.keyboard.press('Escape');
 const menu=await page.evaluate(async()=>await(await fetch('/control/playbooks')).json());
 assert.equal(menu.max_hypotheses,3);assert(menu.catalog.some(x=>x.id==='ml_governance'));
 await page.waitForSelector('.react-flow__node-chainAdd button');
 await page.click('.react-flow__node-chainAdd button');await page.waitForSelector('dialog[open]');
 assert(await page.$('dialog input[type="file"]'));
 await page.screenshot({path:'/tmp/memstara-live-skill-panel.png',fullPage:true});
 await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);
 console.log('PASS: localhost:8070 serves V1 catalog and description/upload panel; no pipeline was started');
}finally{await browser.close();}
