const { chromium } = require('@playwright/test');
(async()=>{
  const browser = await chromium.launch({executablePath:'/usr/bin/chromium', args:['--no-sandbox']});
  const page = await browser.newPage();
  for (const url of ['http://127.0.0.1:4173/','http://localhost:4173/']) {
    try {
      await page.goto(url, {waitUntil:'load', timeout:10000});
      console.log('OK', url, await page.title());
    } catch (e) {
      console.log('ERR', url, String(e));
    }
  }
  await browser.close();
})();
