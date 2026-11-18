import { API } from '/vue/api.js';
import { showToast } from '/vue/components/ToastHost.js';

/** "Send to…" confirm dialog: pick a Bubba Nodes destination; nothing is sent until the named button is pressed. */
export const SendDialog = {
  name: 'SendDialog',
  data() {
    return { paths: [], targets: [], targetId: '', message: '', loading: false, sending: false, error: '' };
  },
  computed: {
    target() {
      return this.targets.find((item) => item.id === this.targetId) || null;
    },
    countLabel() {
      return `${this.paths.length} ${this.paths.length === 1 ? 'file' : 'files'}`;
    },
    sendLabel() {
      return this.target ? `Send ${this.countLabel} to ${this.target.label}` : 'Choose a destination';
    }
  },
  methods: {
    async open(paths) {
      this.paths = (paths || []).filter(Boolean);
      if (!this.paths.length) return;
      this.error = '';
      this.message = '';
      this.$refs.dialog.showModal();
      this.loading = true;
      try {
        const response = await fetch(API.sendTargets);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || 'Could not load destinations.');
        this.targets = payload.targets || [];
        this.error = payload.error || '';
        if (!this.targets.some((item) => item.id === this.targetId)) this.targetId = '';
        if (this.targets.length === 1) this.targetId = this.targets[0].id;
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
    close() {
      this.$refs.dialog.close();
    },
    async send() {
      if (!this.target || this.sending) return;
      this.sending = true;
      this.error = '';
      try {
        const response = await fetch(API.send, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target: this.target.id,
            paths: this.paths,
            message: this.target.kind === 'discord' ? this.message : '',
            confirmed: true
          })
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || payload.description || `Send failed (${response.status})`);
        showToast({ message: `Sent ${payload.sent} to ${payload.destination}.`, tone: 'success' });
        this.close();
      } catch (error) {
        this.error = error.message;
      } finally {
        this.sending = false;
      }
    }
  },
  template: `
    <Teleport to="body">
      <dialog ref="dialog" class="send-dialog" aria-labelledby="send-dialog-title">
        <form method="dialog" class="send-form" @submit.prevent="send">
          <h2 id="send-dialog-title">Send {{ countLabel }} to…</h2>
          <p v-if="loading" role="status">Loading destinations…</p>
          <fieldset v-else-if="targets.length" class="send-targets">
            <legend>Destination (from Bubba Nodes settings)</legend>
            <label v-for="item in targets" :key="item.id" class="send-target">
              <input v-model="targetId" type="radio" name="send-target" :value="item.id" />
              <span>{{ item.label }}</span>
            </label>
          </fieldset>
          <label v-if="target && target.kind === 'discord'" class="send-message">Message (optional)
            <textarea v-model="message" rows="2" maxlength="2000" placeholder="Posted with the images"></textarea>
          </label>
          <p v-if="error" class="send-error" role="alert">{{ error }}</p>
          <div class="send-actions">
            <button class="button" type="button" @click="close">Cancel</button>
            <button class="button button--primary" type="submit" :disabled="!target || sending">{{ sending ? 'Sending…' : sendLabel }}</button>
          </div>
        </form>
      </dialog>
    </Teleport>`
};
