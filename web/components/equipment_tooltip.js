let nextId = 0;

// Portal outside the equipment card so neither its edges nor scrolling clip it.
export function createEquipmentTooltip(root, getItem, {markup, className, rank = () => ''}) {
  const events = new AbortController();
  const tip = document.createElement('div');
  tip.id = `equipment-tooltip-${++nextId}`;
  tip.className = className;
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  document.body.append(tip);
  let anchor = null;
  function hide() {
    anchor?.removeAttribute('aria-describedby');
    anchor = null;
    tip.hidden = true;
  }
  function show(button) {
    if (!button || anchor === button) return;
    hide();
    const item = getItem(button.dataset.slot);
    if (!item) return;
    anchor = button;
    tip.innerHTML = markup(item);
    tip.dataset.rank = rank(item);
    tip.hidden = false;
    anchor.setAttribute('aria-describedby', tip.id);
    const box = button.getBoundingClientRect();
    const {width, height} = tip.getBoundingClientRect();
    const margin = 8, gap = 10;
    const preferredLeft = box.right + gap + width <= innerWidth - margin ? box.right + gap : box.left - gap - width;
    tip.style.left = `${Math.max(margin, Math.min(preferredLeft, innerWidth - width - margin))}px`;
    tip.style.top = `${Math.max(margin, Math.min(box.top, innerHeight - height - margin))}px`;
  }
  const buttonFor = target => target instanceof Element ? target.closest('[data-slot]') : null;
  root.addEventListener('pointerover', event => show(buttonFor(event.target)), {signal: events.signal});
  root.addEventListener('pointerout', event => {
    if (anchor && !anchor.contains(event.relatedTarget)) hide();
  }, {signal: events.signal});
  root.addEventListener('focusin', event => show(buttonFor(event.target)), {signal: events.signal});
  root.addEventListener('focusout', hide, {signal: events.signal});
  window.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); }, {signal: events.signal});
  window.addEventListener('scroll', hide, {capture: true, signal: events.signal});
  window.addEventListener('resize', hide, {signal: events.signal});
  window.addEventListener('blur', hide, {signal: events.signal});
  return {hide, dispose() { hide(); events.abort(); tip.remove(); }};
}
