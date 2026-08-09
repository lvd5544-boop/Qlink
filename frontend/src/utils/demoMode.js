const DEMO_MODE_KEY = 'qlink_demo_mode';

export function syncDemoModeFromLocation() {
  if (typeof window === 'undefined') return false;
  const mode = new URLSearchParams(window.location.search).get('demo');
  if (mode === 'en') window.localStorage.setItem(DEMO_MODE_KEY, 'en');
  if (mode === 'off') window.localStorage.removeItem(DEMO_MODE_KEY);
  const enabled = window.localStorage.getItem(DEMO_MODE_KEY) === 'en';
  if (enabled && typeof document !== 'undefined') document.title = 'QLink · AI Job Workflow';
  return enabled;
}

export function isEnglishDemoMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('demo') === 'en'
    || window.localStorage.getItem(DEMO_MODE_KEY) === 'en';
}

export function disableEnglishDemoMode() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(DEMO_MODE_KEY);
}

export function demoText(chinese, english) {
  return isEnglishDemoMode() ? english : chinese;
}
