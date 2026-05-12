export const API = {
  roots: '/api/roots',
  settings: '/api/settings',
  appInfo: '/api/app/info',
  updateLatest: '/api/update/latest',
  list: '/api/assets/list',
  duplicates: '/api/assets/duplicates',
  duplicatesStream: '/api/assets/duplicates/stream',
  duplicatesTaskStatus: '/api/assets/duplicates/tasks',
  metadataHealth: '/api/assets/metadata/health',
  repairMetadata: '/api/assets/metadata/repair',
  stats: '/api/assets/stats',
  details: '/api/assets/details',
  thumb: '/api/assets/thumb',
  file: '/api/assets/file',
  tags: '/api/tags',
  upload: '/bubba/assets/upload',
  delete: '/bubba/assets/delete',
  openFolder: '/api/assets/open-folder',
  tagExamples: '/bubba/tag_examples',
  tagExampleImage: '/bubba/tag_example_image'
};

export function buildQuery(base, params = {}) {
  const url = new URL(base, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

export function thumbUrl(asset) {
  return buildQuery(API.thumb, { path: asset.path, size: 320 });
}

export function fileUrl(path) {
  return buildQuery(API.file, { path });
}
