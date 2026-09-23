"""Render the offline design prototype. Screenshots are not native product tests."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
with sync_playwright() as w:
 b=w.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
 p=b.new_page(viewport={'width':1440,'height':1150},device_scale_factor=1)
 p.set_content((R/'prototype/index.html').read_text(),wait_until='load')
 for s in ('idle','text','markup','whiteboard','retry'):
  p.evaluate('(s)=>demo.scene(s)',s);p.wait_for_timeout(250)
  p.screenshot(path=str(R/f'design/{s}.png'),full_page=True)
  p.locator('#phone').screenshot(path=str(R/f'design/phone-{s}.png'))
  if s=='markup':
   p.click('#doneBtn');p.locator('#phone').screenshot(path=str(R/'design/phone-composer.png'))
  if s=='retry':
   p.click('#historyBtn');p.locator('#phone').screenshot(path=str(R/'design/phone-recovery.png'))
 p.evaluate("demo.scene('whiteboard')");p.click('#themeToggle');p.wait_for_timeout(150)
 p.locator('#phone').screenshot(path=str(R/'design/phone-dark.png'))
 b.close()
print('Rendered 14 design previews')
