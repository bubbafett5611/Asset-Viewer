import { reactive } from '/vendor/vue.esm-browser.prod.js';

const state = reactive({ toasts: [] });
let nextId = 1;

export function dismissToast(id) {
  const index = state.toasts.findIndex((toast) => toast.id === id);
  if (index === -1) {
    return;
  }
  clearTimeout(state.toasts[index].timer);
  state.toasts.splice(index, 1);
}

/**
 * Show a short-lived notification. `action` is an optional { label, run } pair rendered as a button
 * (e.g. Undo); running it dismisses the toast.
 */
export function showToast({ message, action = null, tone = 'info', timeout = 6000 } = {}) {
  const id = nextId++;
  const toast = { id, message: String(message || ''), action, tone, timer: null, busy: false };
  state.toasts.push(toast);
  while (state.toasts.length > 4) {
    dismissToast(state.toasts[0].id);
  }
  if (timeout > 0) {
    toast.timer = setTimeout(() => dismissToast(id), timeout);
  }
  return id;
}

export const ToastHost = {
  name: 'ToastHost',
  setup() {
    const runAction = async (toast) => {
      if (!toast.action || toast.busy) {
        return;
      }
      toast.busy = true;
      clearTimeout(toast.timer);
      try {
        await toast.action.run();
      } finally {
        dismissToast(toast.id);
      }
    };
    return { state, dismissToast, runAction };
  },
  template: `
    <div class="toast-region" role="status" aria-live="polite">
      <TransitionGroup name="toast">
        <div v-for="toast in state.toasts" :key="toast.id" class="toast" :class="'toast--' + toast.tone">
          <span class="toast-message">{{ toast.message }}</span>
          <button v-if="toast.action" class="toast-action" type="button" :disabled="toast.busy" @click="runAction(toast)">
            {{ toast.busy ? 'Working…' : toast.action.label }}
          </button>
          <button class="toast-close" type="button" aria-label="Dismiss notification" @click="dismissToast(toast.id)">×</button>
        </div>
      </TransitionGroup>
    </div>
  `
};
