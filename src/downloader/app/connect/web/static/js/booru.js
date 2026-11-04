// Ізольований модуль вітрини Booru (Yande.re): перегляд, роздільні тумблери Прев'ю/Оригінал, вибір колонок, підказки тегів, скрол, скачування
window.createBooruModule = function ({ ref, currentTab }) {
    const booruPosts = ref([]);
    const booruQuery = ref('order:score');
    const booruPage = ref(1);
    const booruPerPage = ref(24);
    const booruCols = ref(4); // Кількість колонок у рядку (2, 3, 4, 5, 6)
    const isBooruLoading = ref(false);
    const hasMoreBooru = ref(true);
    const infiniteScrollEnabled = ref(true);
    const booruScrollSentinel = ref(null);
    const selectedBooruPost = ref(null);
    const booruDownloadingIds = ref({});
    const booruSavedIds = ref({});

    // Тумблер відображення у загальній стрічці: 'preview' або 'original'
    const booruViewMode = ref('preview');

    // Пропорції та розмір контейнера прев'ю (16:9, 4:3, 1:1, 3:4, 9:16 або Auto)
    const booruPreviewAspect = ref('auto');
    const booruContainerSize = ref('normal');

    // Окремий тумблер для модального вікна: НЕ змінює показ усієї сітки при перемиканні в модалці!
    const booruModalViewMode = ref('original');

    // Автодоповнення (підказки) при вводі тегів
    const tagSuggestions = ref([]);
    const showTagSuggestions = ref(false);
    const activeSuggestionIdx = ref(-1);
    const isTagSuggestLoading = ref(false);
    let tagSuggestTimer = null;

    const booruDownloadOpts = ref({
        format: 'original',
        max_side: null,
        batchPreset: '10',
        customBatchLimit: 15,
        isBatchRunning: false
    });

    const getBooruDisplayUrl = (post, isModal = false) => {
        if (!post) return '';
        const currentMode = isModal ? booruModalViewMode.value : booruViewMode.value;
        if (currentMode === 'original') {
            return post.file_url || post.sample_url || post.preview_url;
        }
        if (isModal) {
            return post.sample_url || post.preview_url || post.file_url;
        }
        return post.preview_url || post.sample_url || post.file_url;
    };

    const handleBooruImgError = (event, post, isModal = false) => {
        const imgEl = event.target;
        if (!imgEl || imgEl.dataset.proxied === '1') return;
        const rawUrl = getBooruDisplayUrl(post, isModal);
        if (rawUrl) {
            imgEl.dataset.proxied = '1';
            imgEl.src = `/api/v1/booru/proxy?url=${encodeURIComponent(rawUrl)}`;
        }
    };

    const getCurrentTypingTagPrefix = () => {
        const val = booruQuery.value || '';
        if (val.endsWith(' ')) return '';
        const parts = val.split(/\s+/);
        return (parts[parts.length - 1] || '').trim().replace(/^#/, '');
    };

    const fetchTagSuggestions = async (prefix) => {
        isTagSuggestLoading.value = true;
        try {
            const res = await fetch(`/api/v1/booru/tags?q=${encodeURIComponent(prefix)}&limit=12`);
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data)) {
                    tagSuggestions.value = data;
                    activeSuggestionIdx.value = -1;
                }
            }
        } catch (e) {
            console.error('Tag suggestion error:', e);
        } finally {
            isTagSuggestLoading.value = false;
        }
    };

    const onBooruQueryFocus = () => {
        showTagSuggestions.value = true;
        fetchTagSuggestions(getCurrentTypingTagPrefix());
    };

    const onBooruQueryInput = () => {
        showTagSuggestions.value = true;
        const prefix = getCurrentTypingTagPrefix();
        if (tagSuggestTimer) clearTimeout(tagSuggestTimer);
        tagSuggestTimer = setTimeout(() => {
            fetchTagSuggestions(prefix);
        }, 180);
    };

    const closeTagSuggestions = () => {
        setTimeout(() => {
            showTagSuggestions.value = false;
            activeSuggestionIdx.value = -1;
        }, 150);
    };

    const searchBooru = async (reset = false) => {
        if (reset) {
            booruPage.value = 1;
            booruPosts.value = [];
            hasMoreBooru.value = true;
            showTagSuggestions.value = false;
        }
        if (isBooruLoading.value || !hasMoreBooru.value) return;
        isBooruLoading.value = true;

        try {
            const encoded = encodeURIComponent(booruQuery.value.trim());
            const perPage = Number(booruPerPage.value) || 24;
            const res = await fetch(`/api/v1/booru/posts?tags=${encoded}&limit=${perPage}&page=${booruPage.value}`);
            if (res.ok) {
                const data = await res.json();
                if (!Array.isArray(data) || data.length < perPage) {
                    hasMoreBooru.value = false;
                }
                if (Array.isArray(data)) {
                    if (reset) {
                        booruPosts.value = data;
                    } else {
                        const existingIds = new Set(booruPosts.value.map(p => p.id));
                        const fresh = data.filter(p => !existingIds.has(p.id));
                        booruPosts.value.push(...fresh);
                    }
                    booruPage.value++;
                }
            }
        } catch (e) {
            console.error('Booru search error:', e);
        } finally {
            isBooruLoading.value = false;
        }
    };

    const selectTagSuggestion = (tagName) => {
        const raw = booruQuery.value || '';
        if (!raw.trim() || raw.endsWith(' ')) {
            const existing = raw.trim().split(/\s+/).filter(Boolean);
            if (!existing.includes(tagName)) {
                existing.push(tagName);
            }
            booruQuery.value = existing.join(' ') + ' ';
        } else {
            const parts = raw.split(/\s+/).filter(Boolean);
            parts.pop();
            if (!parts.includes(tagName)) {
                parts.push(tagName);
            }
            booruQuery.value = parts.join(' ') + ' ';
        }
        showTagSuggestions.value = false;
        activeSuggestionIdx.value = -1;
        searchBooru(true);
    };

    const onBooruQueryKeydown = (e) => {
        if (!showTagSuggestions.value || tagSuggestions.value.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeSuggestionIdx.value = (activeSuggestionIdx.value + 1) % tagSuggestions.value.length;
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeSuggestionIdx.value =
                activeSuggestionIdx.value <= 0
                    ? tagSuggestions.value.length - 1
                    : activeSuggestionIdx.value - 1;
        } else if ((e.key === 'Enter' || e.key === 'Tab') && activeSuggestionIdx.value >= 0) {
            e.preventDefault();
            const chosen = tagSuggestions.value[activeSuggestionIdx.value];
            if (chosen && chosen.name) {
                selectTagSuggestion(chosen.name);
            }
        } else if (e.key === 'Escape') {
            showTagSuggestions.value = false;
            activeSuggestionIdx.value = -1;
        }
    };

    const loadNextBooruPage = () => {
        searchBooru(false);
    };

    const setBooruTag = (tag) => {
        booruQuery.value = tag;
        showTagSuggestions.value = false;
        searchBooru(true);
    };

    const openBooruModal = (post) => {
        selectedBooruPost.value = post;
        // За замовчуванням у модалці відкриваємо оригінал або sample, але не чіпаємо booruViewMode стрічки
        booruModalViewMode.value = 'original';
    };

    const quickDownloadBooru = async (post) => {
        if (booruDownloadingIds.value[post.id]) return;
        booruDownloadingIds.value[post.id] = true;
        try {
            const postTags = (post.tags || '').split(' ').filter(Boolean).slice(0, 12);
            const shortTags = postTags.slice(0, 4).join('_');
            const cleanTitle = `yande.re_${post.id}${shortTags ? '_' + shortTags : ''}`;

            const res = await fetch('/api/v1/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: post.file_url,
                    title: cleanTitle,
                    tags: ['yande.re', ...postTags],
                    image_format: booruDownloadOpts.value.format,
                    image_max_side: booruDownloadOpts.value.max_side
                })
            });
            if (res.ok) {
                booruSavedIds.value[post.id] = true;
            }
        } catch (e) {
            alert('Помилка завантаження: ' + e);
        } finally {
            delete booruDownloadingIds.value[post.id];
        }
    };

    const downloadBooruBatchByTag = async () => {
        const tags = booruQuery.value.trim() || 'order:score';
        const isAll = booruDownloadOpts.value.batchPreset === 'all';
        const limit = booruDownloadOpts.value.batchPreset === 'custom'
            ? Number(booruDownloadOpts.value.customBatchLimit || 10)
            : Number(booruDownloadOpts.value.batchPreset || 10);

        booruDownloadOpts.value.isBatchRunning = true;
        try {
            const res = await fetch('/api/v1/booru/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tags: tags,
                    limit: isAll ? 500 : Math.max(1, Math.min(500, limit)),
                    download_all: isAll,
                    max_pages: isAll ? 15 : 1,
                    image_format: booruDownloadOpts.value.format,
                    image_max_side: booruDownloadOpts.value.max_side,
                    user_tags: ['yande.re', ...tags.split(' ').filter(Boolean)]
                })
            });
            if (res.ok) {
                currentTab.value = 'active';
            }
        } catch (e) {
            alert('Помилка пакетного завантаження: ' + e);
        } finally {
            booruDownloadOpts.value.isBatchRunning = false;
        }
    };


    let scrollObserver = null;
    const initInfiniteScroll = () => {
        if (scrollObserver) scrollObserver.disconnect();
        scrollObserver = new IntersectionObserver((entries) => {
            if (
                entries[0] &&
                entries[0].isIntersecting &&
                infiniteScrollEnabled.value &&
                currentTab.value === 'booru' &&
                !isBooruLoading.value &&
                hasMoreBooru.value
            ) {
                loadNextBooruPage();
            }
        }, { rootMargin: '350px' });

        if (booruScrollSentinel.value) {
            scrollObserver.observe(booruScrollSentinel.value);
        }
    };

    // Отримання CSS-класів для контейнера картки Booru залежно від налаштувань
    const getBooruCardBoxClass = () => {
        const classes = [];
        if (booruPreviewAspect.value !== 'auto') {
            classes.push(`aspect-box-${booruPreviewAspect.value}`);
        } else {
            classes.push(`box-size-${booruContainerSize.value}`);
        }
        return classes.join(' ');
    };

    return {
        booruPosts,
        booruQuery,
        booruPerPage,
        booruCols,
        booruPreviewAspect,
        booruContainerSize,
        getBooruCardBoxClass,
        isBooruLoading,
        hasMoreBooru,
        infiniteScrollEnabled,
        booruScrollSentinel,
        selectedBooruPost,
        booruDownloadingIds,
        booruSavedIds,
        booruViewMode,
        booruModalViewMode,
        booruDownloadOpts,
        tagSuggestions,
        showTagSuggestions,
        activeSuggestionIdx,
        isTagSuggestLoading,
        getBooruDisplayUrl,
        handleBooruImgError,
        onBooruQueryFocus,
        onBooruQueryInput,
        closeTagSuggestions,
        selectTagSuggestion,
        onBooruQueryKeydown,
        searchBooru,
        loadNextBooruPage,
        setBooruTag,
        openBooruModal,
        quickDownloadBooru,
        downloadBooruBatchByTag,
        initInfiniteScroll
    };
};
