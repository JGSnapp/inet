// Minimal UI localisation: Russian for Russian-language browsers, English otherwise.
// Override with ?lang=en|ru or the localStorage key "inet-lang".
function detect(): 'ru' | 'en' {
  try {
    const forced =
      new URLSearchParams(window.location.search).get('lang') || localStorage.getItem('inet-lang');
    if (forced === 'ru' || forced === 'en') return forced;
  } catch {
    /* storage may be unavailable */
  }
  return (navigator.language || '').toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

export const lang = detect();

export const tr = (ru: string, en: string): string => (lang === 'ru' ? ru : en);

document.documentElement.lang = lang;
document.title = tr('INET — пространство исследования', 'INET — research workspace');
