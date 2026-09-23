export function installInputMotion(input: HTMLTextAreaElement, indicator: HTMLElement) {
  let enabled = true, timer = 0;
  try { enabled = localStorage.getItem('dt-input-motion') !== 'off'; } catch {}
  const apply = () => document.documentElement.classList.toggle('motion-off', !enabled);
  apply();
  const stop = () => {
    clearTimeout(timer); input.classList.remove('input-active'); indicator.hidden = true;
  };
  input.addEventListener('input', () => {
    stop();
    if (!enabled || document.hidden) return;
    input.classList.add('input-active'); indicator.hidden = false;
    timer = window.setTimeout(stop, 1400);
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  return {
    get enabled() { return enabled; },
    setEnabled(value: boolean) {
      enabled = value; apply(); if (!value) stop();
      try { localStorage.setItem('dt-input-motion', value ? 'on' : 'off'); } catch {}
    },
  };
}
