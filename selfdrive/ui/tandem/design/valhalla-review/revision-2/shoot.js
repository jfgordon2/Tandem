const fs=require('fs');
const path=require('path');
const {chromium}=require('playwright');
(async()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'manifest.json'),'utf8'));
 const browser=await chromium.launch();
 const page=await browser.newPage({viewport:{width:1600,height:1600}});
 const errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 for(const s of manifest.states){
  await page.goto('file://'+path.join(__dirname,'../..',s.file+'.html'));
  await page.evaluate(()=>Promise.all([400,500,600,700,800].map(w=>document.fonts.load(w+' 18px Figtree'))));
  const result=await page.evaluate(()=>{const r=document.querySelector('body > div').getBoundingClientRect();return {width:r.width,height:r.height,fonts:[400,500,600,700,800].every(w=>document.fonts.check(w+' 18px Figtree')),images:[...document.images].every(i=>i.complete&&i.naturalWidth)};});
  if(result.width!==1125||result.height!==563||!result.fonts||!result.images)errors.push({id:s.id,...result});
  const cramped=await page.evaluate(()=>[...document.querySelectorAll('button.primary')].map(b=>b.getBoundingClientRect()).filter(r=>r.height<59||r.bottom>564||r.right>1126).map(r=>({height:r.height,bottom:r.bottom,right:r.right})));
  if(cramped.length)errors.push({id:s.id,crampedPrimaryActions:cramped});
  if(!fs.existsSync(path.join(__dirname,'../../screenshots',s.file+'.png')))errors.push('Missing screenshot: '+s.file);
 }
 for(const file of fs.readdirSync(__dirname).filter(f=>/^board-.*\.html$/.test(f))){
  await page.goto('file://'+path.join(__dirname,file));
  await page.evaluate(()=>document.fonts.ready);
  await page.locator('main').screenshot({path:path.join(__dirname,file.replace('.html','.png'))});
  console.log(file.replace('.html','.png'));
 }
 await page.goto('file://'+path.join(__dirname,'index.html'));
 const cards=await page.locator('article').count();
 if(cards!==manifest.states.length)errors.push('Missing gallery cards');
 await page.getByRole('button',{name:'Region-download ideas',exact:true}).click();
 if(await page.locator('section[data-group]:not(.hidden)').count()!==1)errors.push('Filter failed');
 await page.locator('section[data-group="regions"] .zoom').first().click();
 if(!await page.locator('dialog').evaluate(d=>d.open))errors.push('Full-size preview failed');
 await page.getByRole('button',{name:'Close',exact:true}).click();
 for(const href of await page.evaluate(()=>[...document.querySelectorAll('a')].map(a=>a.getAttribute('href')).filter(h=>h&&!h.startsWith('#')))){
  if(!fs.existsSync(path.resolve(__dirname,href)))errors.push('Missing link: '+href);
 }
 const report={revision:2,states:manifest.states.length,galleryCards:cards,errors};
 fs.writeFileSync(path.join(__dirname,'qa.json'),JSON.stringify(report,null,2)+'\n');
 await browser.close();
 console.log(JSON.stringify(report));
 if(errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
