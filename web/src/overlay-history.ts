/** One browser-history guard while an editor or sheet is open. No draft in URL/state. */
export function overlayHistory(isOpen: () => boolean, back: () => void) {
  const key = "typelessOverlay";
  let pending = false;
  function sync() {
    if (pending) return;
    if (isOpen() && !history.state?.[key]) {
      history.pushState({...history.state, [key]:true}, "");
    } else if (!isOpen() && history.state?.[key]) {
      pending = true;
      history.back();
    }
  }
  window.addEventListener("popstate", () => {
    if (pending) pending = false;
    else if (isOpen()) back();
    sync();
  });
  return sync;
}
