const paths: Record<string,string> = {
 settingsBtn:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
 historyBtn:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',
 connectBtn:'<rect x="3" y="4" width="7" height="16" rx="2"/><path d="M14 7h7v10h-7M15 11h4M15 14h4"/>',
 clearDraft:'<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',

 pen:'<path d="m4 17 1 3 3-1L20 7l-3-3L4 17Z M14 7l3 3"/>',
 marker:'<path d="m5 15 8-11 6 4-8 11-6-4Z M5 15l-2 5 6-1"/>',
 highlight:'<path d="m7 14 6-10 6 4-6 10-6-4Z M7 14l-3 5 6 1 3-2 M3 22h17"/>',
 arrow:'<path d="M4 20 20 4 M9 4h11v11"/>',
 rect:'<rect x="4" y="5" width="16" height="14" rx="2"/>',
 ellipse:'<ellipse cx="12" cy="12" rx="9" ry="7"/>',
 line:'<path d="M4 20 20 4"/>',
 number:'<circle cx="12" cy="12" r="9"/><path d="m10 9 2-2v10 M9 17h6"/>',
 crop:'<path d="M7 3v14h14 M3 7h14v14"/>',
 text:'<path d="M4 6V4h16v2 M12 4v16 M8 20h8"/>',
 eraser:'<path d="m4 14 9-10 7 6-9 10H8l-4-4v-2Z M9 9l7 6 M11 20h10"/>',
 mask:'<rect x="3" y="6" width="18" height="12" rx="2"/><path d="m5 16 9-9 M10 17l9-9 M3 10l4-4"/>',
 select:'<path d="m5 3 2 17 4-6 7-2L5 3Z M12 15l4 6"/>',
 pan:'<path d="M8 12V5a2 2 0 0 1 4 0v7-8a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v8c0 5-4 7-7 7-4 0-5-2-7-5l-3-5a2 2 0 0 1 3-2l2 2"/>',
 captureBtn:'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8 M12 16v5 M7 7h10v5H7z"/>',
 photoBtn:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 5-5 4 4 4-7 5 8"/>',
 boardBtn:'<path d="M14 3H5v18h14V8l-5-5Z M14 3v5h5 M8 16l2-4 3 4 3-4"/>',
};
export function decorateTools(root:HTMLElement) {
 for (const button of Array.from(root.querySelectorAll<HTMLButtonElement>('[data-tool],#captureBtn,#photoBtn,#boardBtn,#settingsBtn,#historyBtn,#connectBtn,#clearDraft'))) {
  const key=button.dataset.tool || button.id, label=button.textContent || '';
  if(!button.hasAttribute('aria-label')) button.setAttribute('aria-label',label);button.title=label;
  button.classList.add('icon-tool');
  button.innerHTML=`<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[key] || ''}</svg><span>${label}</span>`;
 }
 const colors=['红色','蓝色','蓝紫色','黑色'];
 root.querySelectorAll('[data-color]').forEach((b,i)=>b.setAttribute('aria-label',colors[i] || '画笔颜色'));
}
