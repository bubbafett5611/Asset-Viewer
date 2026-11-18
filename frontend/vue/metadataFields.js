import { formatBytes, formatDate } from './formatters.js';

export const hasValue = (value) => {
  if (value === null || value === undefined) {
    return false;
  }
  if (typeof value === 'string') {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return true;
};

/** File, generation and embedded-metadata rows for an asset (shared by the inspector and Compare). */
export function buildMetadataSummary(selectedAsset, assetDetails) {
  if (!selectedAsset) {
    return {
      filePairs: [],
      generationPairs: [],
      extraBubbaPairs: [],
      metadataPairs: [],
      metadataBadgeClass: 'metadata-status metadata-status-none',
      metadataBadgeText: 'No metadata detected',
      copyPromptValue: '',
      copySeedValue: '',
      isSweep: false
    };
  }

  const details = assetDetails && typeof assetDetails === 'object' ? assetDetails : selectedAsset;
  const metadata = details.metadata && typeof details.metadata === 'object' ? details.metadata : {};
  const embedded = metadata.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {};
  const bubbaMetadata =
    embedded.bubba_metadata && typeof embedded.bubba_metadata === 'object' ? embedded.bubba_metadata : null;
  const extractedGeneration =
    embedded.generation && typeof embedded.generation === 'object' ? embedded.generation : null;
  const generationSource = bubbaMetadata || extractedGeneration;

  const filePairs = [
    ['name', details.name],
    ['path', details.path],
    ['relative', details.relative_path],
    ['extension', details.extension || '(none)'],
    ['size', formatBytes(details.size_bytes)],
    ['modified', formatDate(details.modified_ts)]
  ];

  const generationPairs = [];
  if (generationSource) {
    const addGenerationField = (label, key) => {
      if (Object.prototype.hasOwnProperty.call(generationSource, key) && hasValue(generationSource[key])) {
        const value = generationSource[key];
        generationPairs.push([
          label,
          Array.isArray(value) ? value.join(', ') : typeof value === 'string' ? value : JSON.stringify(value, null, 2)
        ]);
      }
    };

    const addGenerationFieldFromKeys = (label, keys) => {
      for (const key of keys) {
        if (Object.prototype.hasOwnProperty.call(generationSource, key) && hasValue(generationSource[key])) {
          addGenerationField(label, key);
          return;
        }
      }
    };

    addGenerationFieldFromKeys('model', [
      'model_name',
      'model',
      'ckpt_name',
      'checkpoint',
      'checkpoint_name',
      'sd_model_name',
      'base_model'
    ]);
    addGenerationFieldFromKeys('seed', ['seed', 'seeds']);
    addGenerationFieldFromKeys('steps', ['steps', 'num_steps']);
    addGenerationFieldFromKeys('clip_skip', ['clip_skip']);
    addGenerationFieldFromKeys('cfg', ['cfg', 'cfg_scale']);
    addGenerationFieldFromKeys('sampler', ['sampler_name', 'sampler']);
    addGenerationFieldFromKeys('scheduler', ['scheduler']);
    addGenerationFieldFromKeys('denoise', ['denoise', 'denoise_strength']);
    addGenerationFieldFromKeys('time_seconds', ['sampler_time_seconds', 'time_seconds']);
    const loraNames = Array.isArray(generationSource.loras) ? generationSource.loras : [];
    const loraStrengths = Array.isArray(generationSource.lora_strengths) ? generationSource.lora_strengths : [];
    if (loraNames.length && loraStrengths.length) {
      const loraChips = loraNames.map((name, index) => {
        const [modelStrength, clipStrength] = loraStrengths[index] || [1, 1];
        return {
          label: `${name} (${modelStrength === clipStrength ? modelStrength : `${modelStrength}/${clipStrength}`})`,
          value: String(name)
        };
      });
      generationPairs.push(['loras', loraChips.map((chip) => chip.label).join(', '), loraChips]);
    } else {
      addGenerationFieldFromKeys('loras', ['loras']);
    }
    addGenerationFieldFromKeys('vae', ['vae_name']);
    addGenerationFieldFromKeys('clip', ['clip_name']);
    if (generationSource.width > 0 && generationSource.height > 0) {
      generationPairs.push(['size', `${generationSource.width}x${generationSource.height}`]);
    }
    addGenerationFieldFromKeys('sampler_info', ['sampler_info']);
    addGenerationFieldFromKeys('positive_prompt', ['positive_prompt', 'prompt']);
    addGenerationFieldFromKeys('negative_prompt', ['negative_prompt', 'negative']);
    addGenerationFieldFromKeys('prompt_sections', ['prompt_sections']);
    const xySweep = /^XY sweep (.+)$/.exec(String(generationSource.notes || '').trim());
    if (Array.isArray(generationSource.sweep_x_labels) && generationSource.sweep_x_labels.length) {
      generationPairs.push(['xy_sweep_x', generationSource.sweep_x_labels.join(', ')]);
      if (Array.isArray(generationSource.sweep_y_labels) && generationSource.sweep_y_labels.length) {
        generationPairs.push(['xy_sweep_y', generationSource.sweep_y_labels.join(', ')]);
      }
      const index = Number(generationSource.sweep_index);
      if (Number.isInteger(index) && index >= 0) {
        const columns = generationSource.sweep_x_labels.length;
        const yLabel = (generationSource.sweep_y_labels || [])[Math.floor(index / columns)];
        generationPairs.push([
          'xy_cell',
          [generationSource.sweep_x_labels[index % columns], yLabel].filter(Boolean).join(' · ')
        ]);
      } else {
        generationPairs.push(['xy_cell', 'labelled sheet']);
      }
    } else if (xySweep) {
      const [xAxis, yAxis] = xySweep[1].split(' | ');
      generationPairs.push(['xy_sweep_x', xAxis]);
      if (yAxis) {
        generationPairs.push(['xy_sweep_y', yAxis]);
      }
    } else {
      addGenerationFieldFromKeys('notes', ['notes']);
    }
    addGenerationFieldFromKeys('save_prefix', ['save_prefix']);
    addGenerationFieldFromKeys('filepath', ['filepath', 'file', 'path']);
  }

  // Values that make useful "find all media like this" searches become clickable chips.
  const filterableLabels = new Set(['model', 'seed', 'sampler', 'scheduler', 'vae', 'clip']);
  for (const pair of generationPairs) {
    if (pair[2] || !filterableLabels.has(pair[0])) {
      continue;
    }
    const value = String(pair[1] || '').trim();
    if (value && value.length <= 200 && !value.includes('\n')) {
      pair[2] = [{ label: value, value }];
    }
  }

  const extraBubbaPairs = [];
  if (bubbaMetadata) {
    const known = new Set([
      'model_name',
      'clip_skip',
      'seed',
      'steps',
      'cfg',
      'sampler_name',
      'scheduler',
      'denoise',
      'sampler_time_seconds',
      'sampler_info',
      'positive_prompt',
      'negative_prompt',
      'loras',
      'lora_strengths',
      'vae_name',
      'clip_name',
      'width',
      'height',
      'notes',
      'save_prefix',
      'prompt_sections',
      'filepath',
      'sweep_id',
      'sweep_x_labels',
      'sweep_y_labels',
      'sweep_index',
      'content_rating',
      'nsfw_score',
      'nsfw_regions'
    ]);

    for (const [key, value] of Object.entries(bubbaMetadata)) {
      if (known.has(key) || !hasValue(value)) {
        continue;
      }
      extraBubbaPairs.push([`bubba.${key}`, typeof value === 'string' ? value : JSON.stringify(value, null, 2)]);
    }
  }

  const metadataPairs = [];
  if (metadata.format) {
    metadataPairs.push(['format', metadata.format]);
  }
  if (Array.isArray(metadata.keys)) {
    metadataPairs.push(['keys', metadata.keys.join(', ') || '(none)']);
  }
  if (embedded && typeof embedded === 'object') {
    for (const [key, value] of Object.entries(embedded)) {
      if (key === 'bubba_metadata') {
        continue;
      }
      metadataPairs.push([key, typeof value === 'string' ? value : JSON.stringify(value, null, 2)]);
    }
  }

  const hasGenerationData = generationPairs.length > 0;
  const hasAnyMetadata = hasGenerationData || metadataPairs.length > 0;

  const metadataBadgeClass = hasGenerationData
    ? 'metadata-status metadata-status-ok'
    : hasAnyMetadata
      ? 'metadata-status metadata-status-warn'
      : 'metadata-status metadata-status-none';
  const metadataBadgeText = hasGenerationData
    ? 'Generation data detected'
    : hasAnyMetadata
      ? 'Metadata found (no generation)'
      : 'No metadata detected';

  const copyPromptValue =
    generationSource && hasValue(generationSource.positive_prompt) ? String(generationSource.positive_prompt) : '';
  const copySeedValue = generationSource && hasValue(generationSource.seed) ? String(generationSource.seed) : '';

  const isSweep = Boolean(
    generationSource && (generationSource.sweep_id || /^XY sweep /.test(String(generationSource.notes || '').trim()))
  );

  return {
    isSweep,
    filePairs,
    generationPairs,
    extraBubbaPairs,
    metadataPairs,
    metadataBadgeClass,
    metadataBadgeText,
    copyPromptValue,
    copySeedValue
  };
}
