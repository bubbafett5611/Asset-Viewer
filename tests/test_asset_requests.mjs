import assert from 'node:assert/strict';
import { test } from 'node:test';
import { useAssets } from '../frontend/vue/composables/useAssets.js';

const ref = value => ({ value });
function fixture() {
  const options = {
    API: { list: '/assets' }, buildQuery: (url, params) => url + '?' + new URLSearchParams(params),
    nextTick: async () => {}, pageSize: 2, filters: { root: 'one', q: '', folder: '', ext: '', metadataBadge: '', sortBy: 'name', sortDir: 'asc' },
    offset: ref(0), assets: ref([]), selectedAsset: ref(null), selectedPath: ref(''), selectedPaths: ref(new Set()),
    lastSelectedIndex: ref(-1), details: ref(null), statusText: ref(''), isLoading: ref(false), isLoadingMore: ref(false),
    assetError: ref(''), paginationError: ref(false), hasMore: ref(false), measureAssetList() {},
    replaceSelectedPaths(paths) { options.selectedPaths.value = new Set(paths); }
  };
  return { state: options, ...useAssets(options) };
}
const response = paths => ({ ok: true, json: async () => ({ assets: paths.map(path => ({ path })) }) });

test('late responses cannot replace a newer search or its loading state', async t => {
  const pending = [];
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => pending.push(resolve)));
  const { state, fetchAssets } = fixture();
  const first = fetchAssets();
  state.filters.q = 'new';
  const second = fetchAssets();
  pending[0](response(['old']));
  await first;
  assert.equal(state.isLoading.value, true);
  assert.deepEqual(state.assets.value, []);
  pending[1](response(['new']));
  await second;
  assert.deepEqual(state.assets.value, [{ path: 'new' }]);
  assert.equal(state.isLoading.value, false);
});

test('a query changed during debounce invalidates an in-flight result', async t => {
  let resolve;
  t.mock.method(globalThis, 'fetch', () => new Promise(done => resolve = done));
  const { state, fetchAssets } = fixture();
  const request = fetchAssets();
  state.filters.root = 'two';
  resolve(response(['from-one']));
  await request;
  assert.deepEqual(state.assets.value, []);
});

test('failed pagination preserves media and retries the same offset', async t => {
  const offsets = [];
  let fail = false;
  t.mock.method(globalThis, 'fetch', async url => {
    offsets.push(Number(new URL(url, 'http://test').searchParams.get('offset')));
    return fail ? { ok: false, status: 503 } : response(offsets.length === 1 ? ['a', 'b'] : ['c', 'd']);
  });
  const { state, fetchAssets, loadMore } = fixture();
  await fetchAssets();
  fail = true;
  await loadMore();
  assert.equal(state.offset.value, 0);
  assert.equal(state.paginationError.value, true);
  assert.deepEqual(state.assets.value.map(a => a.path), ['a', 'b']);
  fail = false;
  await loadMore();
  assert.deepEqual(offsets, [0, 2, 2]);
  assert.deepEqual(state.assets.value.map(a => a.path), ['a', 'b', 'c', 'd']);
  assert.equal(state.offset.value, 2);
  assert.equal(state.assetError.value, '');
  state.filters.q = 'different';
  await loadMore();
  assert.deepEqual(offsets, [0, 2, 2], 'must not append another query to the current batch');
});

test('refresh failure keeps displayed media and the committed page offset', async t => {
  let fail = false;
  t.mock.method(globalThis, 'fetch', async () => fail ? { ok: false, status: 500 } : response(['a', 'b']));
  const { state, fetchAssets, loadMore, refreshAssets } = fixture();
  await fetchAssets();
  await loadMore();
  fail = true;
  await refreshAssets();
  assert.equal(state.offset.value, 2);
  assert.equal(state.assets.value.length, 4);
  assert.match(state.assetError.value, /500/);
  assert.equal(state.paginationError.value, false);
});
