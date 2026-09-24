"""Optional integrations with configured CAPTCHA providers, always budgeted."""
import asyncio
import providers

async def solve_widget(page,automation):
    widget=page.locator('.cf-turnstile[data-sitekey],.g-recaptcha[data-sitekey]').first
    if not await widget.count():return False
    sitekey=await widget.get_attribute('data-sitekey')
    classes=await widget.get_attribute('class') or ''
    turnstile='cf-turnstile' in classes
    service=next((s for s in ('capsolver','twocaptcha') if automation.vault.configured(s)),None)
    if not service:return False
    import os
    if not automation.budget(service,int(os.getenv('CAPTCHA_MONTHLY_LIMIT','20'))):raise ValueError('CAPTCHA budget exhausted')
    key=automation.vault.get(service)
    base='https://api.capsolver.com' if service=='capsolver' else 'https://api.2captcha.com'
    task_type=('AntiTurnstileTaskProxyLess' if turnstile else 'ReCaptchaV2TaskProxyLess') if service=='capsolver' else ('TurnstileTaskProxyless' if turnstile else 'RecaptchaV2TaskProxyless')
    created=(await providers.request(base+'/createTask',method='POST',json={'clientKey':key,'task':{'type':task_type,'websiteURL':page.url,'websiteKey':sitekey}})).json()
    if created.get('errorId'):raise ValueError('CAPTCHA provider rejected task')
    task_id=created.get('taskId');solution=created.get('solution')
    for _ in range(24):
        if solution:break
        await asyncio.sleep(3)
        result=(await providers.request(base+'/getTaskResult',method='POST',json={'clientKey':key,'taskId':task_id})).json()
        if result.get('errorId'):raise ValueError('CAPTCHA provider failed task')
        if result.get('status')=='ready':solution=result.get('solution')
    token=(solution or {}).get('token') or (solution or {}).get('gRecaptchaResponse')
    if not token:raise ValueError('CAPTCHA timeout')
    callback=await widget.get_attribute('data-callback')
    await page.evaluate('''({token,callback,turnstile})=>{
      const selector=turnstile?'[name="cf-turnstile-response"]':'[name="g-recaptcha-response"]';
      for(const e of document.querySelectorAll(selector)){e.value=token;e.dispatchEvent(new Event('change',{bubbles:true}));}
      if(callback&&typeof window[callback]==='function')window[callback](token);
    }''',{'token':token,'callback':callback,'turnstile':turnstile})
    return True
