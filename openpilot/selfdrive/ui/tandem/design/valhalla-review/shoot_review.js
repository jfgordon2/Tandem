// Capture review boards and check that the gallery opens every draft. Uses the same Playwright dependency as shoot_mocks.js.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport:{width:1600,height:1600}});
  const errors=[];
  page.on('pageerror', error => errors.push(String(error)));
  const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'manifest.json'),'utf8'));
  for (const state of manifest.states) {
    await page.goto('file://'+path.join(__dirname,'..',state.file+'.html'));
    await page.evaluate(()=>Promise.all([400,500,600,700,800].map(w=>document.fonts.load(w+' 18px Figtree'))));
    await page.evaluate(()=>document.fonts.ready);
    const result=await page.evaluate(()=>{
      const root=document.querySelector('body > div');
      const r=root.getBoundingClientRect();
      return {width:r.width,height:r.height,fonts:[400,500,600,700,800].every(w=>document.fonts.check(w+' 18px Figtree')),brokenImages:[...document.images].filter(i=>!i.complete||!i.naturalWidth).length};
    });
    if(result.width!==1125||result.height!==563||!result.fonts||result.brokenImages) errors.push({id:state.id,...result});
    if (!fs.existsSync(path.join(__dirname,'..','screenshots',state.file+'.png'))) errors.push('Missing screenshot: '+state.file);
  }
  for (const file of fs.readdirSync(__dirname).filter(f=>/^board-.*\.html$/.test(f))) {
    await page.goto('file://'+path.join(__dirname,file));
    await page.evaluate(()=>document.fonts.ready);
    await page.locator('main').screenshot({path:path.join(__dirname,file.replace('.html','.png'))});
    console.log(file.replace('.html','.png'));
  }
  await page.goto('file://'+path.join(__dirname,'index.html'));
  const gallery = await page.evaluate(()=>({cards:document.querySelectorAll('article').length,buttons:document.querySelectorAll('[data-filter]').length}));
  await page.getByRole('button',{name:'Driving screen',exact:true}).click();
  if(await page.locator('section[data-group]:not(.hidden)').count()!==1) errors.push('Gallery category filter failed');
  await page.locator('section[data-group="onroad"] .zoom').first().click();
  if(!await page.locator('dialog').evaluate(d=>d.open)) errors.push('Gallery full-size preview failed');
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('button',{name:'All '+manifest.states.length,exact:true}).click();
  const deadLinks=await page.evaluate(()=>[...document.querySelectorAll('a')].map(a=>a.getAttribute('href')).filter(h=>h&&!h.startsWith('#')));
  for(const href of deadLinks) if(!fs.existsSync(path.resolve(__dirname,href))) errors.push('Missing link: '+href);
  const report={states:manifest.states.length,gallery,errors};
  fs.writeFileSync(path.join(__dirname,'qa.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
  await browser.close();
  if(errors.length) process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
