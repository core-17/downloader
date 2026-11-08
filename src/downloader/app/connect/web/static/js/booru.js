// ============================================================================
// Модуль вітрини Booru (Yande.re, Konachan, Safebooru, Zerochan)
// Підтримка вибору провайдера, Safe Mode, кастомних тегів, перегляду та експорту
// ============================================================================

window.createBooruModule = function ({ ref, computed, watch, currentTab, vaultFiles }) {
    const _computed = computed || (window.Vue ? window.Vue.computed : (fn => ({ get value() { return fn(); } })));
    const booruPosts = ref([]);
    const booruQuery = ref('');
    const booruPage = ref(1);
    const booruPerPage = ref(24);
    const booruCols = ref(Number(localStorage.getItem('app_booru_cols')) || 4); // Кількість колонок у рядку (1..8)
    const isBooruLoading = ref(false);
    const hasMoreBooru = ref(true);
    const booruTotalCount = ref(null); // Загальна кількість знайдених постів на Booru
    const isCountLoading = ref(false);
    const infiniteScrollEnabled = ref(true);
    const booruScrollSentinel = ref(null);
    const selectedBooruPost = ref(null);
    const booruDownloadingIds = ref({});
    const booruSavedIds = ref({});

    // Перевірка, чи вже є цей пост Booru у сховищі Vault
    const isPostInVault = (post) => {
        if (!post) return false;
        const prov = (post.provider || selectedBooruProvider.value || 'yande.re').replace('.', '_');
        const key = `${prov}_${post.id}`;
        if (booruSavedIds.value[key] || booruSavedIds.value[post.id]) return true;

        if (vaultFiles && Array.isArray(vaultFiles.value)) {
            const idStr = String(post.id);
            return vaultFiles.value.some(f => {
                const name = (f.name || f.filename || '').toLowerCase();
                return name.includes(idStr);
            });
        }
        return false;
    };

    // Провайдери Booru (підтримка вибору кількох одночасно)
    const booruProviders = [
        { id: 'yande.re', name: 'Yande.re', icon: '🌸', hasSafeMode: true },
        { id: 'konachan', name: 'Konachan', icon: '🎨', hasSafeMode: true },
        { id: 'safebooru', name: 'Safebooru', icon: '🛡️', hasSafeMode: false, isAlwaysSafe: true },
        { id: 'zerochan', name: 'Zerochan', icon: '⚡', hasSafeMode: false, isAlwaysSafe: true },
        { id: 'gelbooru', name: 'Gelbooru', icon: '🔷', hasSafeMode: true },
    ];

    let initialProviders = ['yande.re'];
    try {
        const stored = localStorage.getItem('app_booru_providers');
        if (stored) {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed) && parsed.length > 0) {
                initialProviders = parsed.filter(id => booruProviders.some(p => p.id === id));
            }
        } else {
            const single = localStorage.getItem('app_booru_provider');
            if (single && booruProviders.some(p => p.id === single)) {
                initialProviders = [single];
            }
        }
    } catch (e) {}
    if (initialProviders.length === 0) initialProviders = ['yande.re'];

    const selectedBooruProviders = ref(initialProviders);
    const selectedBooruProvider = _computed(() => selectedBooruProviders.value[0] || 'yande.re');

    // Safe Mode (Безпечний режим)
    const booruSafeMode = ref(localStorage.getItem('app_booru_safe_mode') === 'true');
    const booruSafeTags = ref(localStorage.getItem('app_booru_safe_tags') || '');
    const booruNonSafeTags = ref(localStorage.getItem('app_booru_non_safe_tags') || '');
    const showSafeSettings = ref(false);

    // Тумблер відображення у загальній стрічці: 'preview' або 'original'
    const booruViewMode = ref('preview');

    // Пропорції та розмір контейнера прев'ю (16:9, 4:3, 1:1, 3:4, 9:16 або Auto)
    const booruPreviewAspect = ref('auto');
    const booruContainerHeight = ref(Number(localStorage.getItem('app_booru_container_height')) || 280);
    const booruContainerSize = ref('normal');
    const booruOrientation = ref('all');
    const isMobileBooruFiltersOpen = ref(false);

    if (watch) {
        watch(booruCols, (val) => {
            try { localStorage.setItem('app_booru_cols', String(val)); } catch (e) {}
        });
        watch(booruContainerHeight, (val) => {
            try { localStorage.setItem('app_booru_container_height', String(val)); } catch (e) {}
        });
    }

    // Окремий тумблер для модального вікна
    const booruModalViewMode = ref('original');
    const isModalImgLoading = ref(false);

    // Автодоповнення при вводі тегів
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

    const isProviderSelected = (pId) => {
        return selectedBooruProviders.value.includes(pId);
    };

    const toggleBooruProvider = (pId) => {
        if (selectedBooruProviders.value.includes(pId)) {
            if (selectedBooruProviders.value.length > 1) {
                selectedBooruProviders.value = selectedBooruProviders.value.filter(id => id !== pId);
            }
        } else {
            selectedBooruProviders.value.push(pId);
        }
        try {
            localStorage.setItem('app_booru_providers', JSON.stringify(selectedBooruProviders.value));
            localStorage.setItem('app_booru_provider', selectedBooruProviders.value[0] || 'yande.re');
        } catch (e) {}
        searchBooru(true);
    };

    const selectSingleProvider = (pId) => {
        selectedBooruProviders.value = [pId];
        try {
            localStorage.setItem('app_booru_providers', JSON.stringify(selectedBooruProviders.value));
            localStorage.setItem('app_booru_provider', pId);
        } catch (e) {}
        searchBooru(true);
    };

    const selectAllProviders = () => {
        selectedBooruProviders.value = booruProviders.map(p => p.id);
        try {
            localStorage.setItem('app_booru_providers', JSON.stringify(selectedBooruProviders.value));
        } catch (e) {}
        searchBooru(true);
    };

    const setBooruProvider = (pId) => {
        toggleBooruProvider(pId);
    };

    const toggleSafeMode = () => {
        booruSafeMode.value = !booruSafeMode.value;
        try {
            localStorage.setItem('app_booru_safe_mode', String(booruSafeMode.value));
        } catch (e) {}
        searchBooru(true);
    };

    const saveSafeTags = () => {
        try {
            localStorage.setItem('app_booru_safe_tags', booruSafeTags.value);
            localStorage.setItem('app_booru_non_safe_tags', booruNonSafeTags.value);
        } catch (e) {}
        searchBooru(true);
    };

    const getBooruDisplayUrl = (post, isModal = false) => {
        if (!post) return '';
        const currentMode = isModal ? booruModalViewMode.value : booruViewMode.value;
        let url = '';
        if (currentMode === 'original') {
            url = post.file_url || post.sample_url || post.preview_url;
        } else if (isModal) {
            url = post.sample_url || post.preview_url || post.file_url;
        } else {
            url = post.preview_url || post.sample_url || post.file_url;
        }
        if (!url) return '';

        // Провайдери із захистом від хотлінку (Gelbooru) скеровуємо одразу через безпечний проксі,
        // щоб браузер не отримував text/html замість зображення
        const prov = (post.provider || '').toLowerCase();
        if (prov === 'gelbooru' || url.includes('gelbooru.com')) {
            if (!url.startsWith('/api/v1/booru/proxy')) {
                return `/api/v1/booru/proxy?url=${encodeURIComponent(url)}`;
            }
        }
        return url;
    };

    const getBooruOriginalLink = (post) => {
        if (!post) return '#';
        const raw = post.file_url || post.sample_url || post.preview_url;
        if (!raw) return '#';
        const prov = (post.provider || '').toLowerCase();
        if (prov === 'gelbooru' || raw.includes('gelbooru.com')) {
            return `/api/v1/booru/proxy?url=${encodeURIComponent(raw)}`;
        }
        return raw;
    };

    const handleBooruImgError = (event, post, isModal = false) => {
        const imgEl = event.target;
        if (!imgEl || !post) return;
        const step = parseInt(imgEl.dataset.errorStep || '0', 10);

        if (step === 0) {
            imgEl.dataset.errorStep = '1';
            const rawUrl = getBooruDisplayUrl(post, isModal);
            if (rawUrl && !rawUrl.startsWith('/api/v1/booru/proxy')) {
                imgEl.src = `/api/v1/booru/proxy?url=${encodeURIComponent(rawUrl)}`;
                return;
            }
        }
        if (step === 1) {
            imgEl.dataset.errorStep = '2';
            if (post.sample_url) {
                const sampleUrl = (post.provider === 'gelbooru' || post.sample_url.includes('gelbooru.com'))
                    ? `/api/v1/booru/proxy?url=${encodeURIComponent(post.sample_url)}`
                    : post.sample_url;
                imgEl.src = sampleUrl;
                return;
            }
        }
        if (step <= 2) {
            imgEl.dataset.errorStep = '3';
            if (post.file_url) {
                imgEl.src = `/api/v1/booru/proxy?url=${encodeURIComponent(post.file_url)}`;
            }
        }
    };

    const handleBooruModalImgError = (event, post) => {
        isModalImgLoading.value = false;
        const imgEl = event.target;
        if (!imgEl || !post) return;
        const step = parseInt(imgEl.dataset.errorStep || '0', 10);

        if (step === 0) {
            // Крок 1: пробуємо оригінал через проксі
            imgEl.dataset.errorStep = '1';
            const origUrl = post.file_url || post.sample_url;
            if (origUrl && !origUrl.startsWith('/api/v1/booru/proxy')) {
                imgEl.src = `/api/v1/booru/proxy?url=${encodeURIComponent(origUrl)}`;
                return;
            }
        }
        if (step === 1) {
            // Крок 2: якщо file_url відсутній або 404, перемикаємося на якісний семпл
            imgEl.dataset.errorStep = '2';
            if (post.sample_url && post.sample_url !== post.file_url) {
                const sUrl = (post.provider === 'gelbooru' || post.sample_url.includes('gelbooru.com'))
                    ? `/api/v1/booru/proxy?url=${encodeURIComponent(post.sample_url)}`
                    : post.sample_url;
                imgEl.src = sUrl;
                return;
            }
        }
        if (step <= 2) {
            // Крок 3: гарантований фолбек на preview_url (який вже точно завантажився у стрічці)
            imgEl.dataset.errorStep = '3';
            if (post.preview_url) {
                const pUrl = (post.provider === 'gelbooru' || post.preview_url.includes('gelbooru.com'))
                    ? `/api/v1/booru/proxy?url=${encodeURIComponent(post.preview_url)}`
                    : post.preview_url;
                imgEl.src = pUrl;
            }
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
            const provs = encodeURIComponent(selectedBooruProviders.value.join(','));
            const q = encodeURIComponent(prefix);
            const res = await fetch(`/api/v1/booru/tags?provider=${provs}&q=${q}&limit=12`);
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

    const fetchBooruCount = async () => {
        isCountLoading.value = true;
        try {
            const provs = selectedBooruProviders.value.join(',');
            const params = new URLSearchParams({
                provider: provs,
                tags: booruQuery.value.trim(),
                safe_mode: String(booruSafeMode.value),
            });
            if (booruSafeTags.value.trim()) params.set('safe_tags', booruSafeTags.value.trim());
            if (booruNonSafeTags.value.trim()) params.set('non_safe_tags', booruNonSafeTags.value.trim());

            const res = await fetch(`/api/v1/booru/count?${params.toString()}`);
            if (res.ok) {
                const data = await res.json();
                if (typeof data.total === 'number') {
                    booruTotalCount.value = data.total;
                }
            }
        } catch (e) {
            console.error('Failed to fetch booru total count:', e);
        } finally {
            isCountLoading.value = false;
        }
    };

    const searchBooru = async (reset = false) => {
        if (reset) {
            booruPage.value = 1;
            booruPosts.value = [];
            hasMoreBooru.value = true;
            showTagSuggestions.value = false;
            fetchBooruCount();
        }
        if (isBooruLoading.value || !hasMoreBooru.value) return;
        isBooruLoading.value = true;

        try {
            const perPage = Number(booruPerPage.value) || 24;
            const provs = selectedBooruProviders.value.join(',');
            const params = new URLSearchParams({
                provider: provs,
                tags: booruQuery.value.trim(),
                limit: String(perPage),
                page: String(booruPage.value),
                safe_mode: String(booruSafeMode.value),
            });
            if (booruSafeTags.value.trim()) params.set('safe_tags', booruSafeTags.value.trim());
            if (booruNonSafeTags.value.trim()) params.set('non_safe_tags', booruNonSafeTags.value.trim());

            const res = await fetch(`/api/v1/booru/posts?${params.toString()}`);
            if (res.ok) {
                const data = await res.json();
                if (!Array.isArray(data) || data.length < perPage) {
                    hasMoreBooru.value = false;
                }
                if (Array.isArray(data)) {
                    if (reset) {
                        booruPosts.value = data;
                    } else {
                        const existingIds = new Set(booruPosts.value.map(p => `${p.provider || ''}_${p.id}`));
                        const fresh = data.filter(p => !existingIds.has(`${p.provider || ''}_${p.id}`));
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
        booruModalViewMode.value = 'original';
        isModalImgLoading.value = true;
    };

    const filteredBooruPosts = computed(() => {
        if (booruOrientation.value === 'all') {
            return booruPosts.value;
        }
        return booruPosts.value.filter(post => {
            const w = Number(post.width) || 0;
            const h = Number(post.height) || 0;
            if (!w || !h) return true;
            if (booruOrientation.value === 'landscape') return w > h;
            if (booruOrientation.value === 'portrait') return h > w;
            if (booruOrientation.value === 'square') return w === h;
            return true;
        });
    });

    const selectedBooruPostIndex = computed(() => {
        if (!selectedBooruPost.value) return -1;
        const curId = selectedBooruPost.value.id;
        const curProv = selectedBooruPost.value.provider || '';
        return filteredBooruPosts.value.findIndex(p => p.id === curId && (p.provider || '') === curProv);
    });

    const prevBooruPost = () => {
        const idx = selectedBooruPostIndex.value;
        if (idx > 0) {
            openBooruModal(filteredBooruPosts.value[idx - 1]);
        }
    };

    const nextBooruPost = async () => {
        const idx = selectedBooruPostIndex.value;
        if (idx >= 0) {
            if (idx >= filteredBooruPosts.value.length - 2 && hasMoreBooru.value && !isBooruLoading.value) {
                await searchBooru(false);
            }
            if (idx < filteredBooruPosts.value.length - 1) {
                openBooruModal(filteredBooruPosts.value[idx + 1]);
            }
        }
    };

    let booruTouchStartX = 0;
    let booruTouchStartY = 0;

    const onBooruTouchStart = (e) => {
        if (e.touches && e.touches.length === 1) {
            booruTouchStartX = e.touches[0].clientX;
            booruTouchStartY = e.touches[0].clientY;
        }
    };

    const onBooruTouchEnd = (e) => {
        if (e.changedTouches && e.changedTouches.length === 1) {
            const deltaX = e.changedTouches[0].clientX - booruTouchStartX;
            const deltaY = e.changedTouches[0].clientY - booruTouchStartY;
            if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
                if (deltaX < 0) {
                    nextBooruPost();
                } else {
                    prevBooruPost();
                }
            }
        }
    };

    const quickDownloadBooru = async (post) => {
            const prov = post.provider || selectedBooruProvider.value;
            const provName = post.provider_name || (prov.charAt(0).toUpperCase() + prov.slice(1));
            const uniqueKey = `${prov}_${post.id}`;
            if (booruDownloadingIds.value[uniqueKey] || isPostInVault(post)) return;
            booruDownloadingIds.value[uniqueKey] = true;
            try {
                const postTags = (post.tags || '').split(' ').filter(Boolean).slice(0, 12);
                const shortTags = postTags.slice(0, 4).join('_');
                const cleanTitle = `${prov.replace('.', '_')}_${post.id}${shortTags ? '_' + shortTags : ''}`;

                const res = await fetch('/api/v1/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: post.file_url,
                        title: cleanTitle,
                        source_platform: provName,
                        tags: ['web', 'booru', prov.replace('.', '_'), ...(booruSafeMode.value ? ['safe_mode'] : []), ...postTags],
                        image_format: booruDownloadOpts.value.format,
                        image_max_side: booruDownloadOpts.value.max_side
                    })
                });
            if (res.ok) {
                booruSavedIds.value[uniqueKey] = true;
                booruSavedIds.value[post.id] = true;
            }
        } catch (e) {
            const prefix = window.t ? window.t('err_upload_file') : 'Помилка завантаження: ';
            alert(prefix + e);
        } finally {
            delete booruDownloadingIds.value[uniqueKey];
        }
    };

    const downloadBooruBatchByTag = async () => {
        const tags = booruQuery.value.trim();
        const isAll = booruDownloadOpts.value.batchPreset === 'all';
        const limit = booruDownloadOpts.value.batchPreset === 'custom'
            ? Number(booruDownloadOpts.value.customBatchLimit || 10)
            : Number(booruDownloadOpts.value.batchPreset || 10);

        booruDownloadOpts.value.isBatchRunning = true;
        try {
            const prov = selectedBooruProvider.value;
            const res = await fetch('/api/v1/booru/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider: prov,
                    tags: tags,
                    limit: isAll ? 500 : Math.max(1, Math.min(500, limit)),
                    download_all: isAll,
                    max_pages: isAll ? 15 : 1,
                    image_format: booruDownloadOpts.value.format,
                    image_max_side: booruDownloadOpts.value.max_side,
                    safe_mode: booruSafeMode.value,
                    safe_tags: booruSafeTags.value || undefined,
                    non_safe_tags: booruNonSafeTags.value || undefined,
                    user_tags: ['web', 'booru', prov.replace('.', '_'), ...(booruSafeMode.value ? ['safe_mode'] : []), ...tags.split(' ').filter(Boolean)]
                })
            });
            if (res.ok) {
                currentTab.value = 'active';
            }
        } catch (e) {
            const prefix = window.t ? window.t('err_start_task') : 'Помилка пакетного завантаження: ';
            alert(prefix + e);
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

    const getBooruCardBoxClass = () => {
        const classes = [];
        if (booruPreviewAspect.value !== 'auto') {
            classes.push(`aspect-box-${booruPreviewAspect.value}`);
        } else {
            classes.push('aspect-box-auto');
        }
        return classes.join(' ');
    };

    const getBooruCardBoxStyle = () => {
        if (booruPreviewAspect.value === 'auto') {
            return {
                height: `${booruContainerHeight.value}px`,
                maxHeight: `${booruContainerHeight.value}px`,
                '--card-box-height': `${booruContainerHeight.value}px`
            };
        }
        return {};
    };

    return {
        booruPosts,
        booruQuery,
        booruPerPage,
        booruCols,
        booruPreviewAspect,
        booruContainerSize,
        booruContainerHeight,
        booruOrientation,
        filteredBooruPosts,
        getBooruCardBoxClass,
        getBooruCardBoxStyle,
        isBooruLoading,
        booruTotalCount,
        isCountLoading,
        fetchBooruCount,
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
        booruProviders,
        selectedBooruProviders,
        selectedBooruProvider,
        isProviderSelected,
        toggleBooruProvider,
        selectAllProviders,
        selectSingleProvider,
        setBooruProvider,
        booruSafeMode,
        booruSafeTags,
        booruNonSafeTags,
        showSafeSettings,
        toggleSafeMode,
        saveSafeTags,
        getBooruDisplayUrl,
        getBooruOriginalLink,
        handleBooruImgError,
        handleBooruModalImgError,
        isModalImgLoading,
        onBooruQueryFocus,
        onBooruQueryInput,
        closeTagSuggestions,
        selectTagSuggestion,
        onBooruQueryKeydown,
        searchBooru,
        loadNextBooruPage,
        setBooruTag,
        isPostInVault,
        openBooruModal,
        selectedBooruPostIndex,
        prevBooruPost,
        nextBooruPost,
        onBooruTouchStart,
        onBooruTouchEnd,
        quickDownloadBooru,
        downloadBooruBatchByTag,
        initInfiniteScroll,
        isMobileBooruFiltersOpen
    };
};
