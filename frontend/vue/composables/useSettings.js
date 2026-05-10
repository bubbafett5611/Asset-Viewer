import { computed } from '/vendor/vue.esm-browser.prod.js';

function titleCaseSettingKey(key) {
  return String(key || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function useSettings(options) {
  const {
    API,
    appSettings,
    appSettingsSchema,
    settingsStatus,
    isLoadingSettings,
    isSavingSettings,
    settingsListDrafts,
    roots,
    filters,
    blurThumbnails
  } = options;

  function applySettings(settings) {
    if (!settings || typeof settings !== 'object') {
      return;
    }
    appSettings.value = settings;
    const viewer = settings.viewer || {};
    if (['compact', 'comfortable', 'large'].includes(viewer.density)) {
      filters.density = viewer.density;
    }
    blurThumbnails.value = Boolean(viewer.preview);
  }

  function resolveSettingsSchemaRef(schema) {
    if (!schema || typeof schema !== 'object') {
      return {};
    }
    if (schema.$ref && appSettingsSchema.value?.$defs) {
      const refName = String(schema.$ref).replace('#/$defs/', '');
      return appSettingsSchema.value.$defs[refName] || schema;
    }
    return schema;
  }

  function settingsInputType(schema) {
    if (Array.isArray(schema.enum)) {
      return 'select';
    }
    if (schema.type === 'boolean') {
      return 'boolean';
    }
    if (schema.type === 'array' && schema.items?.type === 'string') {
      return 'string_list';
    }
    return 'text';
  }

  const settingsSections = computed(() => {
    const schema = appSettingsSchema.value;
    if (!schema || typeof schema !== 'object') {
      return [];
    }
    const rootProperties = schema.properties || {};
    return Object.entries(rootProperties).map(([sectionKey, sectionSchema]) => {
      const resolvedSection = resolveSettingsSchemaRef(sectionSchema);
      const fields = Object.entries(resolvedSection.properties || {}).map(([fieldKey, fieldSchema]) => {
        const resolvedField = resolveSettingsSchemaRef(fieldSchema);
        return {
          key: fieldKey,
          label: resolvedField.title || titleCaseSettingKey(fieldKey),
          type: settingsInputType(resolvedField),
          description: resolvedField.description || '',
          options: Array.isArray(resolvedField.enum)
            ? resolvedField.enum.map((value) => ({ value, label: titleCaseSettingKey(value) }))
            : []
        };
      });
      return {
        key: sectionKey,
        label: sectionSchema.title || resolvedSection.title || titleCaseSettingKey(sectionKey),
        fields
      };
    });
  });

  async function fetchSettings() {
    isLoadingSettings.value = true;
    settingsStatus.value = 'Loading settings...';
    try {
      const response = await fetch(API.settings);
      if (!response.ok) {
        throw new Error(`Failed to load settings (${response.status})`);
      }
      const payload = await response.json();
      appSettingsSchema.value = payload.schema && typeof payload.schema === 'object' ? payload.schema : null;
      applySettings(payload.settings);
      settingsStatus.value = 'Settings loaded.';
    } catch (error) {
      console.error(error);
      settingsStatus.value = error?.message || 'Settings failed to load.';
    } finally {
      isLoadingSettings.value = false;
    }
  }

  function settingsFieldValue(sectionKey, fieldKey) {
    return appSettings.value?.[sectionKey]?.[fieldKey];
  }

  function settingsListValue(sectionKey, fieldKey) {
    const value = settingsFieldValue(sectionKey, fieldKey);
    return Array.isArray(value) ? value : [];
  }

  function settingsListDraftKey(sectionKey, fieldKey) {
    return `${sectionKey}.${fieldKey}`;
  }

  function settingsListDraftValue(sectionKey, fieldKey) {
    return settingsListDrafts[settingsListDraftKey(sectionKey, fieldKey)] || '';
  }

  function updateSettingsListDraft(sectionKey, fieldKey, value) {
    settingsListDrafts[settingsListDraftKey(sectionKey, fieldKey)] = value;
  }

  async function saveSettings(nextSettings) {
    isSavingSettings.value = true;
    settingsStatus.value = 'Saving settings...';
    try {
      const response = await fetch(API.settings, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextSettings)
      });
      if (!response.ok) {
        throw new Error(`Failed to save settings (${response.status})`);
      }
      const payload = await response.json();
      appSettingsSchema.value = payload.schema && typeof payload.schema === 'object' ? payload.schema : null;
      applySettings(payload.settings);
      if (Array.isArray(payload.roots)) {
        roots.value = payload.roots;
        if (filters.root && !roots.value.some((root) => root.key === filters.root)) {
          filters.root = roots.value[0]?.key || '';
        }
      }
      settingsStatus.value = 'Settings saved.';
    } catch (error) {
      console.error(error);
      settingsStatus.value = error?.message || 'Settings failed to save.';
    } finally {
      isSavingSettings.value = false;
    }
  }

  function cloneSettingsPayload() {
    return JSON.parse(JSON.stringify(appSettings.value || {}));
  }

  function updateSetting(sectionKey, fieldKey, value) {
    const nextSettings = cloneSettingsPayload();
    nextSettings[sectionKey] =
      nextSettings[sectionKey] && typeof nextSettings[sectionKey] === 'object' ? nextSettings[sectionKey] : {};
    nextSettings[sectionKey][fieldKey] = value;
    saveSettings(nextSettings);
  }

  function updateStringListItem(sectionKey, fieldKey, index, value) {
    const nextValue = [...settingsListValue(sectionKey, fieldKey)];
    const cleanedValue = String(value || '').trim();
    if (cleanedValue) {
      nextValue[index] = cleanedValue;
    } else {
      nextValue.splice(index, 1);
    }
    updateSetting(sectionKey, fieldKey, nextValue);
  }

  function addStringListSetting(sectionKey, fieldKey) {
    const draftKey = settingsListDraftKey(sectionKey, fieldKey);
    const nextItem = String(settingsListDrafts[draftKey] || '').trim();
    if (!nextItem) {
      return;
    }
    updateSetting(sectionKey, fieldKey, [...settingsListValue(sectionKey, fieldKey), nextItem]);
    settingsListDrafts[draftKey] = '';
  }

  function removeStringListItem(sectionKey, fieldKey, index) {
    const nextValue = [...settingsListValue(sectionKey, fieldKey)];
    nextValue.splice(index, 1);
    updateSetting(sectionKey, fieldKey, nextValue);
  }

  return {
    settingsSections,
    fetchSettings,
    settingsFieldValue,
    settingsListValue,
    settingsListDraftValue,
    updateSettingsListDraft,
    updateSetting,
    updateStringListItem,
    addStringListSetting,
    removeStringListItem
  };
}
