// ============================================================================
// Модуль інтернаціоналізації (i18n) — Українська (uk) та English (en)
// ============================================================================

window.I18N_DICTIONARY = {
    uk: {
        // Загальні та шапка
        app_title: "Downloader",
        app_subtitle: "YouTube • Twitter/X • Pinterest • Reddit • Booru • S3 Сховище",
        ws_connected: "Live WebSocket підключено",
        ws_reconnecting: "Перепідключення...",
        status_online: "Онлайн",
        status_offline: "Офлайн",
        btn_refresh: "Оновити",
        display_label: "Відображення:",
        fit_contain: "Вписати",
        fit_cover: "Заповнити",
        fit_contain_tip: "Вписати пропорційно без обрізання",
        fit_cover_tip: "Заповнити контейнер з обрізанням країв",

        // Вкладки навігації
        tab_active: "Завантаження",
        tab_booru: "Booru",
        tab_vault: "Сховище",
        tab_history: "Історія",

        // Розміри та пропорції
        aspect_ratio_title: "Пропорції контейнера:",
        orientation_title: "Орієнтація зображення",
        orientation_all: "Всі",
        orientation_landscape: "Альбомна",
        orientation_portrait: "Портретна",
        orientation_square: "Квадратна",
        orientation_landscape_tip: "Горизонтальна (ширина > висота)",
        orientation_portrait_tip: "Вертикальна (висота > ширина)",
        orientation_square_tip: "Квадратна (ширина = висота)",
        container_size_title: "Розмір контейнера:",
        size_s: "S",
        size_m: "M",
        size_l: "L",
        size_xl: "XL",
        size_s_tip: "Компактний",
        size_m_tip: "Звичайний",
        size_l_tip: "Великий",
        size_xl_tip: "Максимальний",
        columns_in_row: "Колонок у рядку:",
        in_row: "в ряд",
        cols_tip: "Менше колонок = більший масштаб на екрані.",

        // Дії та кнопки загальні
        btn_close: "Закрити",
        btn_preview: "Перегляд",
        btn_prev: "Попереднє",
        btn_next: "Наступне",
        btn_open_tab: "Відкрити",
        btn_download: "Завантажити",
        btn_delete: "Видалити",
        btn_apply: "Застосувати",
        btn_reset: "Скинути",
        btn_reset_all: "Скинути всі",
        btn_clear: "очистити",
        btn_select_all: "Вибрати всі",
        btn_deselect_all: "Зняти вибір",
        btn_cancel: "Скасувати",
        selected_count: "Обрано:",
        search: "Пошук",

        // Вкладка 1: Завантаження (Active)
        download_by_links_title: "Завантаження за посиланнями",
        batch_mixed_supported: "Підтримується одиночний та пакетний режим",
        links_textarea_placeholder: "Вставте одне або декілька посилань (з нового рядка або через пробіл): YouTube, TikTok, Twitter/X, Pinterest, Reddit, прямі лінки...",
        video_quality_label: "Відео:",
        video_quality_best: "Оригінал (Найкраща якість)",
        audio_only_label: "Тільки аудіо (MP3)",
        playlist_label: "Плейлист",
        playlist_tip: "Завантажувати всі елементи, якщо посилання на плейлист",
        tags_input_placeholder: "Теги через кому (напр. музика, арт)",
        img_processing_title: "Налаштування обробки зображень (для лінків та файлів)",
        img_processing_tip: "Якщо «Оригінал» — зберігає максимальну якість без змін",
        target_img_format: "Цільовий формат зображення:",
        format_original: "Оригінал (без перекодування)",
        format_webp: "WebP (оптимальне стиснення)",
        format_jpeg: "JPEG (.jpg)",
        format_png: "PNG (без втрат)",
        format_avif: "AVIF (сучасний формат)",
        max_side_label: "Обмеження по більшій стороні (збереження пропорцій):",
        no_max_side: "Без обмежень (оригінальний розмір)",
        max_side_1080: "До 1080 px",
        max_side_1440: "До 1440 px (2K)",
        max_side_1920: "До 1920 px (Full HD)",
        max_side_2560: "До 2560 px (QHD)",
        max_side_3840: "До 3840 px (4K UHD)",
        btn_start_links: "Завантажити",
        btn_start_all: "Завантажити все",
        btn_starting: "Запуск...",

        direct_upload_title: "Пряме завантаження файлів",
        drop_hint: "Перетягніть сюди файли або натисніть для вибору",
        drop_supported_types: "Зображення, відео, аудіо, документи",
        upload_tags_placeholder: "Теги через кому (напр. фото, мем, архів)",
        btn_save_to_vault: "Зберегти у сховище",
        btn_saving: "Збереження...",

        active_tasks_title: "Активні процеси в реальному часі",
        no_active_tasks: "Немає активних завантажень у цю секунду. Додайте посилання вище або відкрийте вкладку Booru!",

        // Вкладка 2: Booru (Yande.re, Konachan, Safebooru, Zerochan)
        booru_filters_title: "Параметри Booru",
        booru_provider_label: "Джерело Booru:",
        booru_safe_mode_label: "Безпечний режим (Safe Mode)",
        safe_mode_on: "Safe: УВІМК",
        safe_mode_off: "Safe: ВИМК",
        safe_mode_settings_btn: "Налаштування Safe / Non-Safe тегів",
        safe_tags_hint: "Теги для Safe Mode (напр. rating:safe):",
        non_safe_tags_hint: "Теги для Non-Safe (напр. -rating:explicit):",
        btn_save_safe_settings: "Зберегти",
        booru_search_placeholder: "Введіть теги через пробіл (напр. landscape sky order:score)...",
        btn_find_booru: "Пошук",
        booru_suggestions_title: "Підказки тегів Yande.re (↑↓ або клік для вибору)",
        booru_suggestions_loading: "Пошук...",
        popular_tags_label: "Популярні:",
        feed_view_quality_label: "Режим показу у стрічці:",
        feed_quality_preview: "Прев'ю",
        feed_quality_original: "Оригінал",
        feed_quality_hint: "Прев'ю оптимізовано для швидкодії без перевантаження браузера.",
        download_settings_title: "Параметри завантаження",
        file_format_label: "Формат файлу:",
        max_side_booru_label: "Макс. сторона:",
        booru_export_title: "Пакетне скачування",
        pcs: "шт.",
        all_tag: "Весь тег (All)",
        custom_amount: "Власна...",
        all_tag_warning: "Буде посторінково завантажено всі доступні ілюстрації за вказаним тегом.",
        btn_download_batch: "Скачати пакет",
        btn_download_all_tag: "Скачати ВСІ пости за тегом",
        per_page_label: "На порцію:",
        photos_word: "фото",
        infinite_scroll_label: "Нескінченний скрол",
        apply_booru_results: "Застосувати ({count} артів)",
        no_booru_posts: "За цим запитом постів не знайдено. Спробуйте інший тег (наприклад, order:score).",
        status_in_vault: "У сховищі",
        status_downloading: "Качаємо...",
        loading_booru_images: "Завантаження зображень з Yande.re...",
        load_next_page: "Завантажити ще сторінку",
        all_booru_viewed: "Ви переглянули всі доступні зображення за цим запитом.",

        // Вкладка 3: Сховище (Vault)
        vault_filters_title: "Фільтри сховища",
        vault_mobile_bar_btn: "Фільтри та параметри",
        vault_search_placeholder: "Пошук за назвою, тегом (#art) або платформою...",
        sort_newest: "Спочатку новіші",
        sort_oldest: "Спочатку старіші",
        sort_size_desc: "За розміром (більші)",
        sort_size_asc: "За розміром (менші)",
        sort_name_asc: "За назвою (А → Я)",
        selected_actions_title: "Дії з обраними",
        btn_download_zip: "Скачати обрані (ZIP)",
        btn_generating_zip: "Формуємо архів...",
        btn_delete_selected: "Видалити обрані",
        btn_deleting: "Видалення...",
        btn_download_filtered_zip: "Скачати всі за фільтром ({count})",
        categories_and_formats: "Категорії та формати",
        cat_image: "Зображення",
        cat_video: "Відео",
        cat_audio: "Аудіо",
        cat_document: "Документи та інше",
        source_platform_title: "Джерело / Платформа",
        all_tags_title: "Всі теги",
        filter_tags_placeholder: "Фільтрувати теги...",
        no_tags_found: "Тегів за запитом «{query}» не знайдено",
        shown_files_stat: "Показано файлів: {filtered} з {total}",
        total_size_stat: "Загальний обсяг: {size} МБ",
        mb: "МБ",
        no_vault_files: "Сховище порожнє. Завантажте файли за посиланням або через пряме завантаження.",
        active_filter_badge: "Фільтрів: {count}",
        active_filters_title: "Активні фільтри",
        remove_filter_tip: "Видалити цей фільтр",
        btn_clear_all: "Очистити все",
        no_files_with_filters: "За обраними фільтрами не знайдено файлів",
        try_resetting_filters: "Спробуйте змінити обрані категорії, формати, теги або очистити пошуковий запит.",
        btn_reset_filters_show_all: "Скинути фільтри (показати всі {total} файлів)",
        overlay_preview: "Перегляд",
        overlay_open: "Відкрити",
        apply_vault_results: "Застосувати ({count} файлів)",

        // Підтвердження та сповіщення (Alerts/Confirms)
        confirm_delete_single: "Видалити файл «{name}» зі сховища назавжди?",
        confirm_delete_batch: "Видалити обрані файли ({count} шт.) зі сховища назавжди?",
        err_delete_single: "Помилка при видаленні файлу",
        err_delete_batch: "Помилка при масовому видаленні файлів",
        err_delete_network: "Помилка мережі при видаленні",
        err_zip_failed: "Не вдалося сформувати ZIP-архів",
        err_zip_network: "Помилка мережі при завантаженні архіву",
        err_upload_file: "Помилка завантаження файлу: ",
        err_start_task: "Помилка запуску: ",

        // Вкладка 4: Історія (History)
        history_filters_title: "Фільтри історії",
        history_search_title: "Пошук задач",
        history_search_placeholder: "Назва, посилання, тег...",
        task_status_title: "Статус задачі",
        status_all: "Усі статуси",
        status_completed: "Завершені",
        status_in_progress: "В процесі",
        status_failed: "Помилки",
        tasks_found_stat: "Знайдено задач: {count}",
        no_history_tasks: "За вказаними критеріями задач не знайдено.",
        th_id: "ID",
        th_title: "Назва / Джерело",
        th_tags: "Теги",
        th_status: "Статус",
        th_action: "Дія",

        // Редагування тегів файлу в сховищі
        edit_tags: "Редагувати теги",
        add_tag_placeholder: "Введіть тег...",
        btn_add_tag: "Додати",
        btn_save_tags: "Зберегти теги",
        btn_cancel_tags: "Скасувати",
        err_save_tags: "Помилка збереження тегів",
        no_tags_file: "Тегів немає (натисніть «Редагувати теги»)",

        // Модальні вікна (Modals)
        modal_new_tab: "Нова вкладка",
        modal_close: "Закрити",
        modal_no_preview: "Попередній перегляд для цього типу файлу недоступний",
        modal_score: "Рейтинг:",
        modal_post_on_booru: "Пост на Yande.re",
        modal_download_orig: "Скачати оригінал",
        modal_saved: "Збережено"
    },

    en: {
        // General & Header
        app_title: "Downloader",
        app_subtitle: "YouTube • Twitter/X • Pinterest • Reddit • Booru • S3 Storage",
        ws_connected: "Live WebSocket connected",
        ws_reconnecting: "Reconnecting...",
        status_online: "Online",
        status_offline: "Offline",
        btn_refresh: "Refresh",
        display_label: "Display:",
        fit_contain: "Fit",
        fit_cover: "Fill",
        fit_contain_tip: "Fit proportionally without cropping",
        fit_cover_tip: "Fill container, cropping edges if needed",

        // Navigation Tabs
        tab_active: "Downloads",
        tab_booru: "Booru",
        tab_vault: "Vault",
        tab_history: "History",

        // Dimensions & Aspect Ratios
        aspect_ratio_title: "Container aspect ratio:",
        orientation_title: "Image orientation",
        orientation_all: "All",
        orientation_landscape: "Landscape",
        orientation_portrait: "Portrait",
        orientation_square: "Square",
        orientation_landscape_tip: "Horizontal (width > height)",
        orientation_portrait_tip: "Vertical (height > width)",
        orientation_square_tip: "Square (width = height)",
        container_size_title: "Container size:",
        size_s: "S",
        size_m: "M",
        size_l: "L",
        size_xl: "XL",
        size_s_tip: "Compact",
        size_m_tip: "Normal",
        size_l_tip: "Large",
        size_xl_tip: "Huge",
        columns_in_row: "Columns per row:",
        in_row: "per row",
        cols_tip: "Fewer columns = larger cards on screen.",

        // Actions & Buttons General
        btn_close: "Close",
        btn_preview: "Preview",
        btn_prev: "Previous",
        btn_next: "Next",
        btn_open_tab: "Open",
        btn_download: "Download",
        btn_delete: "Delete",
        btn_apply: "Apply",
        btn_reset: "Reset",
        btn_reset_all: "Reset all",
        btn_clear: "clear",
        btn_select_all: "Select all",
        btn_deselect_all: "Deselect",
        btn_cancel: "Cancel",
        selected_count: "Selected:",
        search: "Search",

        // Tab 1: Downloads (Active)
        download_by_links_title: "Download via links",
        batch_mixed_supported: "Single & batch downloads supported",
        links_textarea_placeholder: "Paste one or more URLs (one per line or space-separated): YouTube, TikTok, Twitter/X, Pinterest, Reddit, direct media links...",
        video_quality_label: "Video:",
        video_quality_best: "Original (Best quality)",
        audio_only_label: "Audio only (MP3)",
        playlist_label: "Playlist",
        playlist_tip: "Download all items if link is a playlist",
        tags_input_placeholder: "Tags separated by comma (e.g. music, art)",
        img_processing_title: "Image processing settings (for links & files)",
        img_processing_tip: "'Original' preserves highest quality without re-encoding",
        target_img_format: "Target image format:",
        format_original: "Original (no re-encoding)",
        format_webp: "WebP (optimal compression)",
        format_jpeg: "JPEG (.jpg)",
        format_png: "PNG (lossless)",
        format_avif: "AVIF (modern format)",
        max_side_label: "Max side limit (preserves aspect ratio):",
        no_max_side: "No limit (original resolution)",
        max_side_1080: "Up to 1080 px",
        max_side_1440: "Up to 1440 px (2K)",
        max_side_1920: "Up to 1920 px (Full HD)",
        max_side_2560: "Up to 2560 px (QHD)",
        max_side_3840: "Up to 3840 px (4K UHD)",
        btn_start_links: "Download",
        btn_start_all: "Download all",
        btn_starting: "Starting...",

        direct_upload_title: "Direct file upload",
        drop_hint: "Drag & drop files here or click to browse",
        drop_supported_types: "Images, video, audio, documents",
        upload_tags_placeholder: "Tags separated by comma (e.g. photo, meme, work)",
        btn_save_to_vault: "Save to vault",
        btn_saving: "Saving...",

        active_tasks_title: "Live active tasks",
        no_active_tasks: "No active downloads at the moment. Add links above or browse Booru tab!",

        // Tab 2: Booru (Yande.re, Konachan, Safebooru, Zerochan)
        booru_filters_title: "Booru Settings",
        booru_provider_label: "Booru Provider:",
        booru_safe_mode_label: "Safe Mode",
        safe_mode_on: "Safe: ON",
        safe_mode_off: "Safe: OFF",
        safe_mode_settings_btn: "Configure Safe / Non-Safe tags",
        safe_tags_hint: "Tags for Safe Mode (e.g. rating:safe):",
        non_safe_tags_hint: "Tags for Non-Safe (e.g. -rating:explicit):",
        btn_save_safe_settings: "Save",
        booru_search_placeholder: "Enter tags separated by space (e.g. landscape sky order:score)...",
        btn_find_booru: "Search",
        booru_suggestions_title: "Yande.re tag suggestions (↑↓ or click to select)",
        booru_suggestions_loading: "Searching...",
        popular_tags_label: "Popular:",
        feed_view_quality_label: "Feed display quality:",
        feed_quality_preview: "Preview",
        feed_quality_original: "Original",
        feed_quality_hint: "Preview is optimized for performance without overloading browser memory.",
        download_settings_title: "Download settings",
        file_format_label: "File format:",
        max_side_booru_label: "Max side:",
        booru_export_title: "Batch download",
        pcs: "pcs",
        all_tag: "All by tag (All)",
        custom_amount: "Custom...",
        all_tag_warning: "All available illustrations for this tag will be downloaded page by page.",
        btn_download_batch: "Download batch",
        btn_download_all_tag: "Download ALL posts for tag",
        per_page_label: "Per page:",
        photos_word: "items",
        infinite_scroll_label: "Infinite scroll",
        apply_booru_results: "Apply ({count} items)",
        no_booru_posts: "No posts found for this query. Try another tag (e.g. order:score).",
        status_in_vault: "In vault",
        status_downloading: "Downloading...",
        loading_booru_images: "Loading images from Yande.re...",
        load_next_page: "Load next page",
        all_booru_viewed: "You have viewed all available images for this query.",

        // Tab 3: Vault
        vault_filters_title: "Vault filters",
        vault_mobile_bar_btn: "Filters & settings",
        vault_search_placeholder: "Search by title, tag (#art), or platform...",
        sort_newest: "Newest first",
        sort_oldest: "Oldest first",
        sort_size_desc: "Size (largest first)",
        sort_size_asc: "Size (smallest first)",
        sort_name_asc: "Name (A → Z)",
        selected_actions_title: "Selected actions",
        btn_download_zip: "Download selected (ZIP)",
        btn_generating_zip: "Creating ZIP...",
        btn_delete_selected: "Delete selected",
        btn_deleting: "Deleting...",
        btn_download_filtered_zip: "Download all filtered ({count})",
        categories_and_formats: "Categories & formats",
        cat_image: "Images",
        cat_video: "Videos",
        cat_audio: "Audio",
        cat_document: "Documents & other",
        source_platform_title: "Source / Platform",
        all_tags_title: "All tags",
        filter_tags_placeholder: "Filter tags...",
        no_tags_found: "No tags found for '{query}'",
        shown_files_stat: "Files shown: {filtered} of {total}",
        total_size_stat: "Total size: {size} MB",
        mb: "MB",
        no_vault_files: "Vault is empty. Download files via URL or direct upload.",
        active_filter_badge: "Filters: {count}",
        active_filters_title: "Active filters",
        remove_filter_tip: "Remove this filter",
        btn_clear_all: "Clear all",
        no_files_with_filters: "No files found matching selected filters",
        try_resetting_filters: "Try changing selected categories, formats, tags, or clearing the search query.",
        btn_reset_filters_show_all: "Reset filters (show all {total} files)",
        overlay_preview: "Preview",
        overlay_open: "Open",
        apply_vault_results: "Apply ({count} files)",

        // Confirms & Alerts
        confirm_delete_single: "Permanently delete file '{name}' from the vault?",
        confirm_delete_batch: "Permanently delete {count} selected files from the vault?",
        err_delete_single: "Error deleting file",
        err_delete_batch: "Error deleting batch files",
        err_delete_network: "Network error while deleting",
        err_zip_failed: "Failed to generate ZIP archive",
        err_zip_network: "Network error while downloading archive",
        err_upload_file: "Error uploading file: ",
        err_start_task: "Error starting task: ",

        // Tab 4: History
        history_filters_title: "History filters",
        history_search_title: "Search tasks",
        history_search_placeholder: "Title, URL, tag...",
        task_status_title: "Task status",
        status_all: "All statuses",
        status_completed: "Completed",
        status_in_progress: "In progress",
        status_failed: "Failed",
        tasks_found_stat: "Tasks found: {count}",
        no_history_tasks: "No tasks found matching criteria.",
        th_id: "ID",
        th_title: "Title / Source",
        th_tags: "Tags",
        th_status: "Status",
        th_action: "Action",

        // Tag editing
        edit_tags: "Edit tags",
        add_tag_placeholder: "Enter tag...",
        btn_add_tag: "Add",
        btn_save_tags: "Save tags",
        btn_cancel_tags: "Cancel",
        err_save_tags: "Error saving tags",
        no_tags_file: "No tags (click 'Edit tags')",

        // Modals
        modal_new_tab: "New tab",
        modal_close: "Close",
        modal_no_preview: "Preview not available for this file type",
        modal_score: "Score:",
        modal_post_on_booru: "Post on Yande.re",
        modal_download_orig: "Download original",
        modal_saved: "Saved"
    }
};

window.createI18nModule = function ({ ref, computed }) {
    const _computed = computed || (window.Vue ? window.Vue.computed : (fn => ({ get value() { return fn(); } })));
    const isLangMenuOpen = ref(false);

    const supportedLanguages = [
        { code: 'uk', name: 'Українська', flag: '🇺🇦' },
        { code: 'en', name: 'English', flag: '🇬🇧' },
        { code: 'es', name: 'Español', flag: '🇪🇸' },
        { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
        { code: 'fr', name: 'Français', flag: '🇫🇷' },
        { code: 'it', name: 'Italiano', flag: '🇮🇹' },
        { code: 'pt', name: 'Português', flag: '🇵🇹' },
        { code: 'pl', name: 'Polski', flag: '🇵🇱' },
        { code: 'ja', name: '日本語', flag: '🇯🇵' },
        { code: 'zh', name: '简体中文', flag: '🇨🇳' },
        { code: 'ko', name: '한국어', flag: '🇰🇷' },
        { code: 'tr', name: 'Türkçe', flag: '🇹🇷' },
        { code: 'ar', name: 'العربية', flag: '🇸🇦' },
        { code: 'hi', name: 'हिन्दी', flag: '🇮🇳' },
        { code: 'vi', name: 'Tiếng Việt', flag: '🇻🇳' },
        { code: 'id', name: 'Bahasa Indonesia', flag: '🇮🇩' },
        { code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
        { code: 'cs', name: 'Čeština', flag: '🇨🇿' },
        { code: 'sv', name: 'Svenska', flag: '🇸🇪' },
        { code: 'ro', name: 'Română', flag: '🇷🇴' },
        { code: 'hu', name: 'Magyar', flag: '🇭🇺' },
        { code: 'el', name: 'Ελληνικά', flag: '🇬🇷' }
    ];

    const supportedCodes = supportedLanguages.map(l => l.code);
    const savedLang = localStorage.getItem('app_lang') || 'uk';
    const currentLang = ref(supportedCodes.includes(savedLang) ? savedLang : 'uk');

    const currentLangMeta = _computed(() => {
        return supportedLanguages.find(l => l.code === currentLang.value) || supportedLanguages[0];
    });

    const localesData = ref({
        uk: window.I18N_DICTIONARY?.uk || {},
        en: window.I18N_DICTIONARY?.en || {}
    });

    const loadLocaleJson = async (lang) => {
        if (!supportedCodes.includes(lang)) return;
        try {
            const res = await fetch(`/static/locales/${lang}.json?v=` + Date.now());
            if (res.ok) {
                const data = await res.json();
                localesData.value[lang] = data;
                if (!window.I18N_DICTIONARY) window.I18N_DICTIONARY = {};
                window.I18N_DICTIONARY[lang] = data;
            }
        } catch (e) {
            console.error(`Failed to load locale ${lang}:`, e);
        }
    };

    // Завантажуємо активну локалізацію та базову українську/англійську для фолбеків
    loadLocaleJson('uk');
    loadLocaleJson('en');
    if (currentLang.value !== 'uk' && currentLang.value !== 'en') {
        loadLocaleJson(currentLang.value);
    }

    const setLanguage = (lang) => {
        if (supportedCodes.includes(lang)) {
            currentLang.value = lang;
            try {
                localStorage.setItem('app_lang', lang);
                document.documentElement.lang = lang;
                // Підтримка RTL для арабської мови
                document.documentElement.dir = (lang === 'ar') ? 'rtl' : 'ltr';
            } catch (e) {}
            loadLocaleJson(lang);
        }
    };

    const toggleLanguage = () => {
        setLanguage(currentLang.value === 'uk' ? 'en' : 'uk');
    };

    const t = (key, params = {}) => {
        const dict = localesData.value[currentLang.value] || window.I18N_DICTIONARY?.[currentLang.value] || window.I18N_DICTIONARY?.uk || {};
        let text = dict[key] !== undefined ? dict[key] : (localesData.value.uk?.[key] || window.I18N_DICTIONARY?.uk?.[key] || key);
        if (params && typeof params === 'object') {
            for (const [pKey, pVal] of Object.entries(params)) {
                text = text.replace(new RegExp(`\\{${pKey}\\}`, 'g'), pVal);
            }
        }
        return text;
    };

    // Глобальний доступ до t для утиліт
    window.t = t;

    return {
        currentLang,
        currentLangMeta,
        supportedLanguages,
        isLangMenuOpen,
        setLanguage,
        toggleLanguage,
        loadLocaleJson,
        t
    };
};
