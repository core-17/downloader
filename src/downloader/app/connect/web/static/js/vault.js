// Ізольований модуль локального сховища (Vault): ліва панель фільтрів, підкатегорії, вибір колонок, пошук, сортування та плеєр
window.createVaultModule = function ({ ref, computed }) {
    const vaultFiles = ref([]);
    const vaultSearch = ref('');
    const vaultCols = ref(3); // Кількість колонок у рядку для сховища (2, 3, 4, 5, 6)
    const previewAspect = ref('auto'); // auto, 16-9, 4-3, 1-1, 3-4, 9-16
    const containerSize = ref('normal'); // compact, normal, large, huge
    const selectedFilePaths = ref([]); // Вибрані чекбоксами файли для масових дій
    const isExportingZip = ref(false);
    const selectedCategories = ref([]);
    const selectedExts = ref([]);
    const selectedPlatforms = ref([]);
    const selectedVaultTags = ref([]);
    const vaultTagSearch = ref(''); // Пошук/фільтрація збережених тегів у лівій панелі
    const sortBy = ref('date_desc');
    const modalFile = ref(null);

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

    const hasActiveVaultFilters = computed(() => {
        return (
            selectedCategories.value.length > 0 ||
            selectedExts.value.length > 0 ||
            selectedPlatforms.value.length > 0 ||
            selectedVaultTags.value.length > 0 ||
            vaultSearch.value.trim().length > 0
        );
    });

    const resetAllVaultFilters = () => {
        selectedCategories.value = [];
        selectedExts.value = [];
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
        const confirmMsg = `Видалити файл "${file.name}" зі сховища назавжди?`;
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
                alert('Помилка при видаленні файлу');
            }
        } catch (e) {
            console.error('Delete file error:', e);
            alert('Помилка мережі при видаленні');
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

    const openModal = (file) => {
        modalFile.value = file;
    };

    const closeModal = () => {
        modalFile.value = null;
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
                alert('Не вдалося сформувати ZIP-архів');
            }
        } catch (e) {
            console.error('Batch zip download error:', e);
            alert('Помилка мережі при завантаженні архіву');
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

    // Отримання CSS-класів для контейнера картки залежно від налаштувань
    const getCardBoxClass = () => {
        const classes = [];
        if (previewAspect.value !== 'auto') {
            classes.push(`aspect-box-${previewAspect.value}`);
        } else {
            classes.push(`box-size-${containerSize.value}`);
        }
        return classes.join(' ');
    };

    return {
        vaultFiles,
        vaultSearch,
        vaultCols,
        previewAspect,
        containerSize,
        selectedFilePaths,
        isExportingZip,
        isAllFilteredSelected,
        toggleSelectAllFiltered,
        downloadSelectedZip,
        downloadAllFilteredZip,
        getCardBoxClass,
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
        hasActiveVaultFilters,
        resetAllVaultFilters,
        resetCategoryFilters,
        resetPlatformFilters,
        resetTagFilters,
        deleteVaultFile,
        sortBy,
        modalFile,
        filteredVaultFiles,
        fetchVaultFiles,
        getCategoryCount,
        getExtCount,
        openModal,
        closeModal
    };

};
