import { computed } from '/vendor/vue.esm-browser.prod.js';

export function useTags(options) {
  const {
    API,
    buildQuery,
    saveArrayToStorage,
    favoritesKey,
    recentKey,
    normalizeTagQuery,
    parseAliases,
    tags,
    tagFilters,
    tagCategoriesList,
    selectedTag,
    tagStatusText,
    isLoadingTags,
    tagExamplesLoading,
    tagExamples,
    hasLoadedTags,
    tagTotal,
    tagOffset,
    tagPageSize,
    favoriteTagNames,
    recentTagNames
  } = options;

  let tagSearchTimer = null;
  let tagExampleRequestId = 0;

  function tagIdentity(tag) {
    if (!tag || typeof tag !== 'object') {
      return '';
    }
    if (tag.id) {
      return String(tag.id);
    }
    return `${String(tag.source || '')}|${String(tag.name || '')}`;
  }

  function isTagStored(listOrSet, tag) {
    const id = tagIdentity(tag);
    const name = String(tag?.name || '');
    if (!id && !name) {
      return false;
    }
    if (listOrSet instanceof Set) {
      return (id && listOrSet.has(id)) || (name && listOrSet.has(name));
    }
    if (Array.isArray(listOrSet)) {
      return (id && listOrSet.includes(id)) || (name && listOrSet.includes(name));
    }
    return false;
  }

  const tagCategories = computed(() => tagCategoriesList.value);
  const filteredTags = computed(() => {
    const q = normalizeTagQuery(tagFilters.q);

    return tags.value.filter((tag) => {
      if (tagFilters.view === 'favorites' && !isTagStored(favoriteTagNames.value, tag)) {
        return false;
      }
      if (tagFilters.view === 'recent' && !isTagStored(recentTagNames.value, tag)) {
        return false;
      }
      if (!q) {
        return true;
      }
      return normalizeTagQuery(`${tag.name} ${tag.aliases}`).includes(q);
    });
  });
  const visibleTags = computed(() => filteredTags.value);
  const tagHasMore = computed(() => tagFilters.view === 'all' && tags.value.length < tagTotal.value);
  const tagCountText = computed(() => `Showing ${visibleTags.value.length} of ${tagTotal.value} tag(s)`);
  const selectedTagAliases = computed(() => parseAliases(selectedTag.value?.aliases));
  const selectedTagExamples = computed(() => {
    if (!selectedTag.value) {
      return [];
    }
    const examples = tagExamples.value[selectedTag.value.name] || {};
    return Object.entries(examples)
      .map(([site, value]) => ({
        site,
        score: typeof value?.score === 'number' ? value.score : null,
        image_url: value?.image_url || '',
        page_url: value?.page_url || value?.post_url || ''
      }))
      .filter((item) => item.image_url || item.page_url);
  });

  async function fetchTags({ append = false } = {}) {
    isLoadingTags.value = true;
    tagStatusText.value = append ? 'Loading more tags...' : 'Loading tags...';

    try {
      const nextOffset = append ? tagOffset.value : 0;
      const response = await fetch(
        buildQuery(API.tags, {
          q: tagFilters.q,
          category: tagFilters.category,
          limit: tagPageSize,
          offset: nextOffset
        })
      );
      if (!response.ok) {
        throw new Error(`Failed to load tags (${response.status})`);
      }

      const payload = await response.json();
      const incoming = Array.isArray(payload.tags) ? payload.tags : [];
      const normalizedIncoming = incoming.map((tag) => ({
        id: String(tag.id || `${String(tag.source || '')}|${String(tag.name || '')}`),
        name: String(tag.name || ''),
        source: String(tag.source || ''),
        sourceCategory: String(tag.source_category || ''),
        category: String(tag.category || ''),
        count: Number(tag.count || 0),
        aliases: String(tag.aliases || '')
      }));
      tags.value = append ? tags.value.concat(normalizedIncoming) : normalizedIncoming;
      tagOffset.value = tags.value.length;
      tagTotal.value = Number(payload.total || tags.value.length);
      tagCategoriesList.value = Array.isArray(payload.categories)
        ? payload.categories.map(String)
        : tagCategoriesList.value;

      hasLoadedTags.value = true;
      tagStatusText.value = `Loaded ${tags.value.length} of ${tagTotal.value} tag(s).`;

      if (selectedTag.value) {
        const selectedId = tagIdentity(selectedTag.value);
        const refreshed = tags.value.find((tag) => tagIdentity(tag) === selectedId);
        selectedTag.value = refreshed || null;
      }
    } catch (error) {
      console.error(error);
      tagStatusText.value = error?.message || 'Failed to load tags.';
    } finally {
      isLoadingTags.value = false;
    }
  }

  function isTagFavorite(tagOrName) {
    if (tagOrName && typeof tagOrName === 'object') {
      return isTagStored(favoriteTagNames.value, tagOrName);
    }
    const name = String(tagOrName || '');
    return favoriteTagNames.value.has(name);
  }

  function persistFavorites() {
    saveArrayToStorage(favoritesKey, Array.from(favoriteTagNames.value));
  }

  function persistRecent() {
    saveArrayToStorage(recentKey, recentTagNames.value);
  }

  function toggleTagFavorite(tag) {
    if (!tag?.name) {
      return;
    }

    const tagId = tagIdentity(tag);
    const next = new Set(favoriteTagNames.value);
    if (tagId && next.has(tagId)) {
      next.delete(tagId);
    } else if (next.has(tag.name)) {
      next.delete(tag.name);
    } else {
      next.add(tagId || tag.name);
    }

    favoriteTagNames.value = next;
    persistFavorites();
  }

  function loadMoreTags() {
    if (!tagHasMore.value || isLoadingTags.value) {
      return;
    }
    fetchTags({ append: true });
  }

  async function fetchTagExamples(tagName) {
    if (!tagName) {
      return;
    }

    const requestId = (tagExampleRequestId += 1);
    tagExamplesLoading.value = true;
    try {
      const url = buildQuery(API.tagExamples, { tag: tagName });
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to load examples (${response.status})`);
      }
      const payload = await response.json();
      tagExamples.value = {
        ...tagExamples.value,
        [tagName]: payload.examples && typeof payload.examples === 'object' ? payload.examples : {}
      };
    } catch (error) {
      console.error(error);
    } finally {
      if (requestId === tagExampleRequestId) {
        tagExamplesLoading.value = false;
      }
    }
  }

  function setSelectedTag(tag) {
    selectedTag.value = tag;
    const tagId = tagIdentity(tag) || tag.name;
    recentTagNames.value = [
      tagId,
      ...recentTagNames.value.filter((value) => value !== tagId && value !== tag.name)
    ].slice(0, 50);
    persistRecent();
  }

  async function selectTag(tag) {
    setSelectedTag(tag);
    await fetchTagExamples(tag.name);
  }

  async function stepSelectedTag(delta) {
    if (!visibleTags.value.length) {
      return;
    }

    const selectedId = tagIdentity(selectedTag.value);
    const currentIndex = visibleTags.value.findIndex((tag) => tagIdentity(tag) === selectedId);
    const fallbackIndex = delta > 0 ? -1 : visibleTags.value.length;
    const nextIndex = Math.min(
      visibleTags.value.length - 1,
      Math.max(0, (currentIndex >= 0 ? currentIndex : fallbackIndex) + delta)
    );
    const nextTag = visibleTags.value[nextIndex];
    setSelectedTag(nextTag);
    await fetchTagExamples(nextTag.name);
  }

  function exampleImageUrl(url) {
    return buildQuery(API.tagExampleImage, { url });
  }

  function tagSearchUrl(tagName, site) {
    if (site === 'danbooru') {
      return `https://danbooru.donmai.us/posts?tags=${encodeURIComponent(tagName)}`;
    }
    return `https://e621.net/posts?tags=${encodeURIComponent(tagName)}`;
  }

  function scheduleTagSearch() {
    if (!hasLoadedTags.value || tagFilters.view !== 'all') {
      return;
    }
    if (tagSearchTimer) {
      clearTimeout(tagSearchTimer);
    }
    tagSearchTimer = setTimeout(() => {
      fetchTags({ append: false });
    }, 180);
  }

  function clearTagSearchTimer() {
    if (tagSearchTimer) {
      clearTimeout(tagSearchTimer);
      tagSearchTimer = null;
    }
  }

  return {
    tagCategories,
    filteredTags,
    visibleTags,
    tagHasMore,
    tagCountText,
    selectedTagAliases,
    selectedTagExamples,
    fetchTags,
    isTagFavorite,
    toggleTagFavorite,
    loadMoreTags,
    selectTag,
    stepSelectedTag,
    exampleImageUrl,
    tagSearchUrl,
    scheduleTagSearch,
    clearTagSearchTimer
  };
}
