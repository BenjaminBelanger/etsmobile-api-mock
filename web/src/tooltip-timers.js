import { Tooltip } from '@fluentui/web-components/tooltip/class.js';

const pending = new Map();

function schedule(tooltip, kind, delay, run) {
  clearTimeout(pending.get(tooltip)?.timer);
  const timer = setTimeout(() => {
    pending.delete(tooltip);
    run();
  }, delay);
  pending.set(tooltip, { kind, timer });
}

Tooltip.prototype.showTooltip = function (delay = this.defaultDelay) {
  if (!this.anchorPositioningReady) {
    this.setFallbackStyles().then(() => this.showTooltip(delay));
    return;
  }
  schedule(this, 'show', delay, () => {
    if (!this.isConnected || this.matches(':popover-open')) return;
    this.setAttribute('aria-hidden', 'false');
    this.showPopover();
  });
};

Tooltip.prototype.hideTooltip = function (delay = this.defaultDelay) {
  schedule(this, 'hide', delay, () => {
    if (this.matches(':hover') || this.anchorElement?.matches(':hover')) {
      this.hideTooltip(delay);
      return;
    }
    this.setAttribute('aria-hidden', 'true');
    if (this.matches(':popover-open')) this.hidePopover();
  });
};

document.addEventListener(
  'pointerdown',
  () => {
    for (const [tooltip, { kind, timer }] of pending) {
      if (kind !== 'show') continue;
      clearTimeout(timer);
      pending.delete(tooltip);
    }
  },
  true,
);
