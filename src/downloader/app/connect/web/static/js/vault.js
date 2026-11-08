// Ізольований модуль локального сховища (Vault): ліва панель фільтрів, підкатегорії, вибір колонок, пошук, сортування та плеєр
window.createVaultModule = function ({ ref, computed, watch }) {
    const vaultFiles = ref([]);
    const vaultSearch = ref('');
    const vaultCols = ref(Number(localStorage.getItem('app_vault_cols')) || 3); // Кількість колонок у рядку для сховища (1..8)
    const previewAspect = ref('auto'); // auto, 16-9, 4-3, 1-1, 3-4, 9-16
    const containerHeight = ref(Number(localStorage.getItem('app_vault_container_height')) || 280);
    const containerSize = ref('normal');
    const selectedFilePaths = ref([]); // Вибрані чекбоксами файли для масових дій
    const isExportingZip = ref(false);

    if (watch) {
        watch(vaultCols, (val) => {
            try { localStorage.setItem('app_vault_cols', String(val)); } catch (e) {}
        });
        watch(containerHeight, (val) => {
            try { localStorage.setItem('app_vault_container_height', String(val)); } catch (e) {}
        });
    }
    const selectedCategories = ref([]);
    const selectedExts = ref([]);
    const selectedPlatforms = ref([]);
    const selectedVaultTags = ref([]);
    const vaultTagSearch = ref(''); // Пошук/фільтрація збережених тегів у лівій панелі
    const sortBy = ref('date_desc');
    const selectedOrientation = ref('all'); // all, landscape, portrait, square
    const modalFile = ref(null);
    const isMobileVaultFiltersOpen = ref(false); // Стан мобільного висувного меню фільтрів

    const categoryTree = [
        {
            id: 'image',
            label: 'Зображення',
            icon: '🖼️',
            subExts: ['jpg', 'png', 'webp', 'gif', 'avif']
        },
        {
            id: 'video',
            label: 'Відео',
            icon: '🎬',
            subExts: ['mp4', 'mkv', 'webm', 'mov']
        },
        {
            id: 'audio',
            label: 'Аудіо',
            icon: '🎵',
            subExts: ['mp3', 'm4a', 'flac', 'ogg', 'wav']
        },
        {
            id: 'document',
            label: 'Документи та інше',
            icon: '📄',
            subExts: ['pdf', 'epub', 'zip', 'rar', '7z']
        }
    ];

    const fetchVaultFiles = async () => {
        try {
            const res = await fetch('/api/v1/files');
            if (res.ok) {
                vaultFiles.value = await res.json();
            }
        } catch (e) {
            console.error('Fetch vault files error:', e);
        }
    };

    const getCategoryCount = (catId) => {
        return vaultFiles.value.filter(f => f.media_type === catId).length;
    };

    const getExtCount = (ext) => {
        return vaultFiles.value.filter(f => (f.extension || '').toLowerCase() === ext.toLowerCase()).length;
    };

    const availableExtensions = computed(() => {
        const set = new Set();
        vaultFiles.value.forEach(f => {
            const ext = (f.extension || f.name.split('.').pop() || '').toLowerCase();
            if (ext && ext.length <= 6) set.add(ext);
        });
        return Array.from(set).sort();
    });

    const availablePlatforms = computed(() => {
        const counts = {};
        vaultFiles.value.forEach(f => {
            if (f.source_platform) {
                counts[f.source_platform] = (counts[f.source_platform] || 0) + 1;
            }
        });
        return Object.entries(counts).map(([name, count]) => ({ name, count }));
    });

    const availableVaultTags = computed(() => {
        const counts = {};
        vaultFiles.value.forEach(f => {
            (f.tags || []).forEach(t => {
                const clean = String(t).trim().toLowerCase().lstrip ? String(t).trim().toLowerCase().replace(/^#+/, '') : String(t).trim().toLowerCase();
                if (clean) {
                    counts[clean] = (counts[clean] || 0) + 1;
                }
            });
        });

        let list = Object.entries(counts).map(([name, count]) => ({ name, count }));

        // Якщо введено пошуковий запит у поле тегів — фільтруємо за збігом
        if (vaultTagSearch.value.trim()) {
            const q = vaultTagSearch.value.trim().toLowerCase().replace(/^#+/, '');
            list = list.filter(item => item.name.includes(q));
        }

        // Сортуємо: спочатку обрані теги, потім за спаданням популярності
        return list.sort((a, b) => {
            const aSel = selectedVaultTags.value.includes(a.name);
            const bSel = selectedVaultTags.value.includes(b.name);
            if (aSel && !bSel) return -1;
            if (!aSel && bSel) return 1;
            return b.count - a.count;
        });
    });

    const totalVaultSizeMb = computed(() => {
        const sum = vaultFiles.value.reduce((acc, f) => acc + (f.size_mb || 0), 0);
        return sum.toFixed(2);
    });

    const activeFiltersList = computed(() => {
        const list = [];
        selectedCategories.value.forEach(catId => {
            const cat = categoryTree.find(c => c.id === catId);
            const label = cat ? `${cat.icon} ${window.t ? (window.t('cat_' + cat.id) || cat.label) : cat.label}` : catId;
            list.push({ key: 'cat_' + catId, type: 'category', value: catId, label });
        });
        selectedExts.value.forEach(ext => {
            list.push({ key: 'ext_' + ext, type: 'ext', value: ext, label: `.${ext}` });
        });
        selectedPlatforms.value.forEach(plat => {
            list.push({ key: 'plat_' + plat, type: 'platform', value: plat, label: plat });
        });
        selectedVaultTags.value.forEach(tag => {
            list.push({ key: 'tag_' + tag, type: 'tag', value: tag, label: `#${tag}` });
        });
        if (selectedOrientation.value !== 'all') {
            const labelMap = {
                landscape: '🖼️ ' + (window.t ? window.t('orientation_landscape') : 'Альбомна'),
                portrait: '📱 ' + (window.t ? window.t('orientation_portrait') : 'Портретна'),
                square: '⏹️ ' + (window.t ? window.t('orientation_square') : 'Квадратна')
            };
            list.push({
                key: 'orientation',
                type: 'orientation',
                value: selectedOrientation.value,
                label: labelMap[selectedOrientation.value] || selectedOrientation.value
            });
        }
        if (vaultSearch.value.trim()) {
            list.push({ key: 'search', type: 'search', value: vaultSearch.value.trim(), label: `🔍 "${vaultSearch.value.trim()}"` });
        }
        return list;
    });

    const activeFiltersCount = computed(() => activeFiltersList.value.length);

    const removeFilter = (item) => {
        if (!item) return;
        if (item.type === 'category') {
            selectedCategories.value = selectedCategories.value.filter(c => c !== item.value);
        } else if (item.type === 'ext') {
            selectedExts.value = selectedExts.value.filter(e => e !== item.value);
        } else if (item.type === 'orientation') {
            selectedOrientation.value = 'all';
        } else if (item.type === 'platform') {
            selectedPlatforms.value = selectedPlatforms.value.filter(p => p !== item.value);
        } else if (item.type === 'tag') {
            selectedVaultTags.value = selectedVaultTags.value.filter(t => t !== item.value);
        } else if (item.type === 'search') {
            vaultSearch.value = '';
        }
    };

    const hasActiveVaultFilters = computed(() => {
        return activeFiltersCount.value > 0;
    });

    const resetAllVaultFilters = () => {
        selectedCategories.value = [];
        selectedExts.value = [];
        selectedOrientation.value = 'all';
        selectedPlatforms.value = [];
        selectedVaultTags.value = [];
        vaultSearch.value = '';
    };

    // Точкове скидання окремих секцій фільтрів
    const resetCategoryFilters = () => {
        selectedCategories.value = [];
        selectedExts.value = [];
    };

    const resetPlatformFilters = () => {
        selectedPlatforms.value = [];
    };

    const resetTagFilters = () => {
        selectedVaultTags.value = [];
    };

    const deleteVaultFile = async (file) => {
        if (!file || !file.relative_path) return;
        const confirmMsg = window.t ? window.t('confirm_delete_single', { name: file.name }) : `Видалити файл "${file.name}" зі сховища назавжди?`;
        if (!window.confirm(confirmMsg)) return;

        try {
            const encPath = file.relative_path.split('/').map(encodeURIComponent).join('/');
            const res = await fetch(`/api/v1/files/${encPath}`, { method: 'DELETE' });
            if (res.ok) {
                // Видаляємо зі списку локально та закриваємо модалку, якщо цей файл відкрито
                vaultFiles.value = vaultFiles.value.filter(f => f.relative_path !== file.relative_path);
                if (modalFile.value && modalFile.value.relative_path === file.relative_path) {
                    modalFile.value = null;
                }
            } else {
                alert(window.t ? window.t('err_delete_single') : 'Помилка при видаленні файлу');
            }
        } catch (e) {
            console.error('Delete file error:', e);
            alert(window.t ? window.t('err_delete_network') : 'Помилка мережі при видаленні');
        }
    };

    const filteredVaultFiles = computed(() => {
        let list = vaultFiles.value;

        if (selectedCategories.value.length > 0) {
            list = list.filter(f => selectedCategories.value.includes(f.media_type));
        }

        if (selectedExts.value.length > 0) {
            list = list.filter(f => {
                const ext = (f.extension || f.name.split('.').pop() || '').toLowerCase();
                return selectedExts.value.includes(ext);
            });
        }

        if (selectedOrientation.value !== 'all') {
            list = list.filter(f => {
                const w = f.width;
                const h = f.height;
                if (!w || !h) {
                    return true;
                }
                if (selectedOrientation.value === 'landscape') {
                    return w > h;
                } else if (selectedOrientation.value === 'portrait') {
                    return h > w;
                } else if (selectedOrientation.value === 'square') {
                    return w === h;
                }
                return true;
            });
        }

        if (selectedPlatforms.value.length > 0) {
            list = list.filter(f => f.source_platform && selectedPlatforms.value.includes(f.source_platform));
        }

        if (selectedVaultTags.value.length > 0) {
            list = list.filter(f => {
                const fTags = f.tags || [];
                return selectedVaultTags.value.some(t => fTags.includes(t));
            });
        }

        if (vaultSearch.value.trim()) {
            const q = vaultSearch.value.trim().toLowerCase();
            list = list.filter(f =>
                f.name.toLowerCase().includes(q) ||
                (f.title && f.title.toLowerCase().includes(q)) ||
                (f.source_platform && f.source_platform.toLowerCase().includes(q)) ||
                (f.tags && f.tags.some(t => t.toLowerCase().includes(q)))
            );
        }

        return [...list].sort((a, b) => {
            switch (sortBy.value) {
                case 'date_asc':
                    return a.modified_ts - b.modified_ts;
                case 'size_desc':
                    return b.size_bytes - a.size_bytes;
                case 'size_asc':
                    return a.size_bytes - b.size_bytes;
                case 'name_asc':
                    return a.name.localeCompare(b.name);
                case 'date_desc':
                default:
                    return b.modified_ts - a.modified_ts;
            }
        });
    });

    const onVaultImageLoad = (event, file) => {
        const img = event.target;
        if (img && img.naturalWidth && img.naturalHeight) {
            file.width = img.naturalWidth;
            file.height = img.naturalHeight;
        }
    };

    const isEditingTags = ref(false);
    const editingTagInput = ref('');
    const modalFileTags = ref([]);

    const openModal = (file) => {
        modalFile.value = file;
        isEditingTags.value = false;
        editingTagInput.value = '';
        modalFileTags.value = [...(file.tags || [])];
    };

    const closeModal = () => {
        modalFile.value = null;
        isEditingTags.value = false;
    };

    const modalFileIndex = computed(() => {
        if (!modalFile.value) return -1;
        return filteredVaultFiles.value.findIndex(f => f.relative_path === modalFile.value.relative_path);
    });

    const prevModalFile = () => {
        const idx = modalFileIndex.value;
        if (idx > 0) {
            openModal(filteredVaultFiles.value[idx - 1]);
        }
    };

    const nextModalFile = () => {
        const idx = modalFileIndex.value;
        if (idx >= 0 && idx < filteredVaultFiles.value.length - 1) {
            openModal(filteredVaultFiles.value[idx + 1]);
        }
    };

    let vaultTouchStartX = 0;
    let vaultTouchStartY = 0;

    const onVaultTouchStart = (e) => {
        if (e.touches && e.touches.length === 1) {
            vaultTouchStartX = e.touches[0].clientX;
            vaultTouchStartY = e.touches[0].clientY;
        }
    };

    const onVaultTouchEnd = (e) => {
        if (e.changedTouches && e.changedTouches.length === 1) {
            const deltaX = e.changedTouches[0].clientX - vaultTouchStartX;
            const deltaY = e.changedTouches[0].clientY - vaultTouchStartY;
            if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
                if (deltaX < 0) {
                    nextModalFile();
                } else {
                    prevModalFile();
                }
            }
        }
    };

    const startEditingTags = () => {
        isEditingTags.value = true;
        modalFileTags.value = [...(modalFile.value ? (modalFile.value.tags || []) : [])];
        editingTagInput.value = '';
    };

    const addTagToModalFile = () => {
        const val = editingTagInput.value.trim();
        if (!val) return;
        const parts = val.split(/[,\s]+/).map(t => t.trim().toLowerCase().replace(/^#+/, '')).filter(Boolean);
        for (const p of parts) {
            if (p.length >= 2 && !modalFileTags.value.includes(p)) {
                modalFileTags.value.push(p);
            }
        }
        editingTagInput.value = '';
    };

    const removeTagFromModalFile = (tag) => {
        modalFileTags.value = modalFileTags.value.filter(t => t !== tag);
    };

    const cancelEditingTags = () => {
        isEditingTags.value = false;
        modalFileTags.value = [...(modalFile.value ? (modalFile.value.tags || []) : [])];
        editingTagInput.value = '';
    };

    const saveModalFileTags = async () => {
        if (!modalFile.value || !modalFile.value.relative_path) return;
        try {
            const res = await fetch('/api/v1/files/tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    relative_path: modalFile.value.relative_path,
                    tags: modalFileTags.value
                })
            });
            if (res.ok) {
                const data = await res.json();
                const updated = data.tags || modalFileTags.value;
                modalFile.value.tags = [...updated];
                const target = vaultFiles.value.find(f => f.relative_path === modalFile.value.relative_path);
                if (target) {
                    target.tags = [...updated];
                }
                isEditingTags.value = false;
            } else {
                alert(window.t ? window.t('err_save_tags') : 'Помилка збереження тегів');
            }
        } catch (e) {
            console.error('Save tags error:', e);
            alert(window.t ? window.t('err_save_tags') : 'Помилка мережі при збереженні тегів');
        }
    };

    const isAllFilteredSelected = computed(() => {
        if (filteredVaultFiles.value.length === 0) return false;
        return filteredVaultFiles.value.every(f => selectedFilePaths.value.includes(f.relative_path));
    });

    const toggleSelectAllFiltered = () => {
        if (isAllFilteredSelected.value) {
            const set = new Set(filteredVaultFiles.value.map(f => f.relative_path));
            selectedFilePaths.value = selectedFilePaths.value.filter(p => !set.has(p));
        } else {
            const current = new Set(selectedFilePaths.value);
            filteredVaultFiles.value.forEach(f => current.add(f.relative_path));
            selectedFilePaths.value = Array.from(current);
        }
    };

    const downloadZip = async (paths, customName) => {
        if (!paths || paths.length === 0) return;
        isExportingZip.value = true;
        try {
            const res = await fetch('/api/v1/files/batch-zip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ relative_paths: paths })
            });
            if (res.ok) {
                const blob = await res.blob();
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = customName || `vault_export_${paths.length}_files.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(blobUrl);
            } else {
                alert(window.t ? window.t('err_zip_failed') : 'Не вдалося сформувати ZIP-архів');
            }
        } catch (e) {
            console.error('Batch zip download error:', e);
            alert(window.t ? window.t('err_zip_network') : 'Помилка мережі при завантаженні архіву');
        } finally {
            isExportingZip.value = false;
        }
    };

    const downloadSelectedZip = () => {
        downloadZip(selectedFilePaths.value, `vault_selected_${selectedFilePaths.value.length}_files.zip`);
    };

    const downloadAllFilteredZip = () => {
        const paths = filteredVaultFiles.value.map(f => f.relative_path);
        downloadZip(paths, `vault_filtered_${paths.length}_files.zip`);
    };

    const isDeletingBatch = ref(false);

    const deleteSelectedFiles = async () => {
        if (!selectedFilePaths.value.length) return;
        const count = selectedFilePaths.value.length;
        const confirmMsg = window.t ? window.t('confirm_delete_batch', { count }) : `Видалити обрані ${count} файлів зі сховища назавжди?`;
        if (!window.confirm(confirmMsg)) return;

        isDeletingBatch.value = true;
        try {
            const res = await fetch('/api/v1/files/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ relative_paths: selectedFilePaths.value })
            });
            if (res.ok) {
                const data = await res.json();
                const deletedSet = new Set(data.deleted || selectedFilePaths.value);
                vaultFiles.value = vaultFiles.value.filter(f => !deletedSet.has(f.relative_path));
                selectedFilePaths.value = [];
                if (modalFile.value && deletedSet.has(modalFile.value.relative_path)) {
                    modalFile.value = null;
                }
            } else {
                alert(window.t ? window.t('err_delete_batch') : 'Помилка при масовому видаленні файлів');
            }
        } catch (e) {
            console.error('Batch delete error:', e);
            alert(window.t ? window.t('err_delete_network') : 'Помилка мережі при видаленні');
        } finally {
            isDeletingBatch.value = false;
        }
    };

    // Отримання CSS-класів та інлайн-стилів для контейнера картки залежно від налаштувань
    const getCardBoxClass = () => {
        const classes = [];
        if (previewAspect.value !== 'auto') {
            classes.push(`aspect-box-${previewAspect.value}`);
        } else {
            classes.push('aspect-box-auto');
        }
        return classes.join(' ');
    };

    const getCardBoxStyle = () => {
        if (previewAspect.value === 'auto') {
            return {
                height: `${containerHeight.value}px`,
                maxHeight: `${containerHeight.value}px`,
                '--card-box-height': `${containerHeight.value}px`
            };
        }
        return {};
    };

    return {
        vaultFiles,
        vaultSearch,
        vaultCols,
        previewAspect,
        containerSize,
        containerHeight,
        selectedFilePaths,
        isExportingZip,
        isAllFilteredSelected,
        toggleSelectAllFiltered,
        downloadSelectedZip,
        downloadAllFilteredZip,
        isDeletingBatch,
        deleteSelectedFiles,
        getCardBoxClass,
        getCardBoxStyle,
        selectedCategories,
        selectedExts,
        selectedPlatforms,
        selectedVaultTags,
        vaultTagSearch,
        categoryTree,
        availableExtensions,
        availablePlatforms,
        availableVaultTags,
        totalVaultSizeMb,
        activeFiltersList,
        activeFiltersCount,
        removeFilter,
        hasActiveVaultFilters,
        resetAllVaultFilters,
        resetCategoryFilters,
        resetPlatformFilters,
        resetTagFilters,
        deleteVaultFile,
        sortBy,
        selectedOrientation,
        onVaultImageLoad,
        modalFile,
        filteredVaultFiles,
        fetchVaultFiles,
        getCategoryCount,
        getExtCount,
        openModal,
        closeModal,
        modalFileIndex,
        prevModalFile,
        nextModalFile,
        onVaultTouchStart,
        onVaultTouchEnd,
        isMobileVaultFiltersOpen,
        isEditingTags,
        editingTagInput,
        modalFileTags,
        startEditingTags,
        addTagToModalFile,
        removeTagFromModalFile,
        cancelEditingTags,
        saveModalFileTags
    };

};
