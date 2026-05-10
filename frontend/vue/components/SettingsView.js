export const SettingsView = {
    name: "SettingsView",
    props: {
        layoutStyle: {
            type: Object,
            required: true,
        },
        settingsSections: {
            type: Array,
            required: true,
        },
        settingsStatus: {
            type: String,
            required: true,
        },
        isSavingSettings: {
            type: Boolean,
            default: false,
        },
        settingsFieldValue: {
            type: Function,
            required: true,
        },
        settingsListValue: {
            type: Function,
            required: true,
        },
        settingsListDraftValue: {
            type: Function,
            required: true,
        },
        updateSettingsListDraft: {
            type: Function,
            required: true,
        },
        updateSetting: {
            type: Function,
            required: true,
        },
        updateStringListItem: {
            type: Function,
            required: true,
        },
        addStringListSetting: {
            type: Function,
            required: true,
        },
        removeStringListItem: {
            type: Function,
            required: true,
        },
    },
    template: `
        <div class="layout layout--single layout--utility tab-panel" :style="layoutStyle">
            <section class="panel settings-panel">
                <div class="settings-header">
                    <div>
                        <h2>Settings</h2>
                    </div>
                </div>

                <div class="settings-content">
                    <section v-for="section in settingsSections" :key="section.key" class="settings-list">
                        <h3>{{ section.label }}</h3>
                        <div
                            v-for="field in section.fields"
                            :key="section.key + '.' + field.key"
                            class="settings-row"
                            :class="{ 'settings-row--list': field.type === 'string_list' }"
                        >
                            <label :for="'setting-' + section.key + '-' + field.key">{{ field.label }}</label>
                            <select
                                v-if="field.type === 'select'"
                                :id="'setting-' + section.key + '-' + field.key"
                                class="select settings-control"
                                :value="settingsFieldValue(section.key, field.key)"
                                :disabled="isSavingSettings"
                                @change="updateSetting(section.key, field.key, $event.target.value)"
                            >
                                <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
                            </select>
                            <button
                                v-else-if="field.type === 'boolean'"
                                :id="'setting-' + section.key + '-' + field.key"
                                class="toggle-switch settings-switch"
                                :class="{ 'is-active': settingsFieldValue(section.key, field.key) }"
                                type="button"
                                :aria-pressed="Boolean(settingsFieldValue(section.key, field.key))"
                                :disabled="isSavingSettings"
                                @click="updateSetting(section.key, field.key, !settingsFieldValue(section.key, field.key))"
                            >
                                <span class="toggle-switch-track" aria-hidden="true">
                                    <span class="toggle-switch-thumb"></span>
                                </span>
                                <span>{{ settingsFieldValue(section.key, field.key) ? 'On' : 'Off' }}</span>
                            </button>
                            <div
                                v-else-if="field.type === 'string_list'"
                                class="settings-list-control"
                            >
                                <div class="settings-list-items">
                                    <div
                                        v-for="(item, index) in settingsListValue(section.key, field.key)"
                                        :key="section.key + '.' + field.key + '.' + index"
                                        class="settings-list-item"
                                    >
                                        <input
                                            :id="'setting-' + section.key + '-' + field.key + '-' + index"
                                            class="input settings-list-input"
                                            :value="item"
                                            :disabled="isSavingSettings"
                                            @change="updateStringListItem(section.key, field.key, index, $event.target.value)"
                                        />
                                        <button
                                            class="button button--icon settings-icon-button"
                                            type="button"
                                            :aria-label="'Remove ' + field.label"
                                            :disabled="isSavingSettings"
                                            @click="removeStringListItem(section.key, field.key, index)"
                                        >-</button>
                                    </div>
                                    <div class="settings-list-item settings-list-add">
                                        <input
                                            :id="'setting-' + section.key + '-' + field.key"
                                            class="input settings-list-input"
                                            :placeholder="'Add ' + field.label"
                                            :value="settingsListDraftValue(section.key, field.key)"
                                            :disabled="isSavingSettings"
                                            @input="updateSettingsListDraft(section.key, field.key, $event.target.value)"
                                            @keydown.enter.prevent="addStringListSetting(section.key, field.key)"
                                        />
                                        <button
                                            class="button button--icon settings-icon-button"
                                            type="button"
                                            :aria-label="'Add ' + field.label"
                                            :disabled="isSavingSettings || !settingsListDraftValue(section.key, field.key).trim()"
                                            @click="addStringListSetting(section.key, field.key)"
                                        >+</button>
                                    </div>
                                </div>
                            </div>
                            <input
                                v-else
                                :id="'setting-' + section.key + '-' + field.key"
                                class="input settings-control"
                                :value="settingsFieldValue(section.key, field.key)"
                                :disabled="isSavingSettings"
                                @change="updateSetting(section.key, field.key, $event.target.value)"
                            />
                        </div>
                    </section>
                    <div class="settings-empty">{{ settingsStatus }}</div>
                </div>
            </section>
        </div>
    `,
};