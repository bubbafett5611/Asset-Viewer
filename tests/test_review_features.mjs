import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { SavedViews } from '../frontend/vue/components/SavedViews.js';

const source = await readFile(new URL('../frontend/vue/components/ReviewSlideshow.js', import.meta.url), 'utf8');
const apiUrl = new URL('../frontend/vue/api.js', import.meta.url).href;
const { ReviewSlideshow } = await import(`data:text/javascript;base64,${Buffer.from(source.replace('/vue/api.js', apiUrl)).toString('base64')}`);

function instance(component, props = {}) {
  const vm = { ...component.data(), ...props };
  for (const [key, method] of Object.entries(component.methods)) vm[key] = method.bind(vm);
  return vm;
}

test('saved views persist, replace by name, isolate roots and restore filters', () => {
  const storage = new Map();
  globalThis.localStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) };
  const vm = instance(SavedViews, { filters: { root: 'one', folder: 'renders', q: 'fox', ext: '.png', metadataBadge: '', sortBy: 'modified', sortDir: 'desc' } });
  vm.name = 'Favorites'; vm.save();
  vm.filters.q = 'bird'; vm.name = 'Favorites'; vm.save();
  assert.equal(vm.views.length, 1);
  assert.equal(SavedViews.data().views[0].filters.q, 'bird');
  vm.filters.root = 'two';
  assert.equal(SavedViews.computed.rootViews.call(vm).length, 0);
  vm.filters.root = 'one'; vm.filters.q = '';
  vm.apply(vm.views[0]);
  assert.equal(vm.filters.q, 'bird');
  vm.remove(vm.views[0]);
  assert.equal(SavedViews.data().views.length, 0);
});

test('invalid storage and write failures are recoverable', () => {
  globalThis.localStorage = { getItem: () => '{broken', setItem: () => { throw Error('full'); } };
  const vm = instance(SavedViews, { filters: { root: 'one' } });
  assert.deepEqual(vm.views, []);
  vm.name = 'Test'; vm.save();
  assert.equal(vm.views.length, 0);
  assert.match(vm.message, /Could not save/);
});

test('review snapshots the batch, starts at selection, wraps and restores focus', () => {
  let opened = false, focused = false;
  globalThis.document = { activeElement: { focus() { focused = true; } } };
  const assets = [{ path: 'a' }, { path: 'b' }];
  const vm = instance(ReviewSlideshow, { assets, selectedPath: 'b', $refs: { dialog: { showModal() { opened = true; } }, close: { focus() {} } } });
  vm.open();
  assert.equal(opened, true);
  assert.equal(vm.index, 1);
  assets.push({ path: 'c' });
  assert.equal(vm.items.length, 2);
  vm.step(1); assert.equal(vm.index, 0);
  vm.step(-1); assert.equal(vm.index, 1);
  vm.toggle(); assert.equal(vm.playing, true);
  assert.ok(vm.timer);
  vm.onClose();
  assert.equal(vm.playing, false);
  assert.equal(focused, true);
  assert.deepEqual(vm.items, []);
});

test('review keyboard events do not reach library shortcuts', () => {
  const vm = instance(ReviewSlideshow, { items: [{ path: 'a' }, { path: 'b' }] });
  let stopped = false, prevented = false;
  vm.keydown({ key: 'ArrowRight', target: { tagName: 'BUTTON' }, stopPropagation() { stopped = true; }, preventDefault() { prevented = true; } });
  assert.equal(vm.index, 1);
  assert.equal(stopped, true);
  assert.equal(prevented, true);
});
