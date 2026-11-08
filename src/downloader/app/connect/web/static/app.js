const { createApp, ref, computed, onMounted, watch, nextTick } = Vue;

createApp({
    setup() {
        const i18nModule = window.createI18nModule({ ref, computed });
        const currentTab = ref('active');
        const isNavVisible = ref(true);
        let lastScrollY = 0;

        // Єдине глобальне налаштування масштабування/заповнення прев'ю для всіх вкладок
        // За замовчуванням 'contain' - розтягування по більшій стороні під розмір контейнера без обрізання
        const savedFit = localStorage.getItem('app_global_image_fit_v2') || 'contain';
        const globalImageFit = ref(savedFit);

        const setGlobalImageFit = (mode) => {
            globalImageFit.value = mode;
            try {
                localStorage.setItem('app_global_image_fit_v2', mode);
            } catch (e) {}
        };

        const onWindowScroll = () => {
            const currentY = window.pageYOffset || document.documentElement.scrollTop;
            if (currentY < 60) {
                // Якщо біля самого верху — шапка завжди на місці
                isNavVisible.value = true;
                document.body.classList.remove('nav-hidden');
            } else if (currentY < lastScrollY - 6) {
                // Користувач гортає ВГОРУ (хоча б на 6px) — миттєво показуємо шапку і вкладки!
                isNavVisible.value = true;
                document.body.classList.remove('nav-hidden');
            } else if (currentY > lastScrollY + 12) {
                // Користувач активно гортає ВНИЗ — ховаємо, і фільтри підіймаються до самого верху!
                isNavVisible.value = false;
                document.body.classList.add('nav-hidden');
            }
            lastScrollY = Math.max(0, currentY);
        };

        const vaultModule = window.createVaultModule({ ref, computed, watch });
        const accountsModule = window.createAccountsModule({
            ref,
            onAccountSwitched: () => {
                vaultModule.fetchVaultFiles();
                booruModule.searchBooru(true);
            }
        });
        const tasksModule = window.createTasksModule({
            ref,
            computed,
            onTaskCompleted: () => vaultModule.fetchVaultFiles()
        });
        const downloadsModule = window.createDownloadsModule({
            ref,
            onFilesUploaded: () => vaultModule.fetchVaultFiles()
        });
        const booruModule = window.createBooruModule({
            ref,
            computed,
            watch,
            currentTab,
            vaultFiles: vaultModule.vaultFiles
        });

        watch(currentTab, async (newTab) => {
            if (vaultModule.isMobileVaultFiltersOpen) vaultModule.isMobileVaultFiltersOpen.value = false;
            if (booruModule.isMobileBooruFiltersOpen) booruModule.isMobileBooruFiltersOpen.value = false;

            if (newTab === 'booru') {
                if (booruModule.booruPosts.value.length === 0) {
                    await booruModule.searchBooru(true);
                }
                await nextTick();
                booruModule.initInfiniteScroll();
            } else if (newTab === 'vault') {
                vaultModule.fetchVaultFiles();
            }
        });

        // Блокування фонового скролу сторінки, коли відкрито мобільне меню або модальне вікно
        watch(
            () => Boolean(
                vaultModule.isMobileVaultFiltersOpen?.value ||
                booruModule.isMobileBooruFiltersOpen?.value ||
                vaultModule.modalFile?.value ||
                booruModule.selectedBooruPost?.value ||
                accountsModule.isAccountModalOpen?.value
            ),
            (isOpen) => {
                document.body.style.overflow = isOpen ? 'hidden' : '';
            }
        );

        // Автоматичний точний розрахунок висоти закріпленого хедера для уникнення накладання
        const updateNavbarHeight = () => {
            const navbar = document.querySelector('.sticky-navbar');
            if (navbar) {
                const h = Math.round(navbar.getBoundingClientRect().height);
                document.documentElement.style.setProperty('--navbar-height', `${h}px`);
            }
        };

        const onGlobalKeydown = (e) => {
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
            if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) {
                return;
            }

            if (vaultModule.modalFile.value) {
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    vaultModule.prevModalFile();
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    vaultModule.nextModalFile();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    vaultModule.closeModal();
                }
            } else if (booruModule.selectedBooruPost.value) {
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    booruModule.prevBooruPost();
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    booruModule.nextBooruPost();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    booruModule.selectedBooruPost.value = null;
                }
            }
        };

        const refreshAll = () => {
            tasksModule.fetchTasks();
            vaultModule.fetchVaultFiles();
            if (currentTab.value === 'booru') {
                booruModule.searchBooru(true);
            }
            nextTick(updateNavbarHeight);
        };

        onMounted(() => {
            window.addEventListener('scroll', onWindowScroll, { passive: true });
            window.addEventListener('resize', updateNavbarHeight, { passive: true });
            window.addEventListener('keydown', onGlobalKeydown);
            nextTick(updateNavbarHeight);
            setTimeout(updateNavbarHeight, 150);
            setTimeout(updateNavbarHeight, 600);

            tasksModule.connectWs();
            tasksModule.fetchTasks();
            vaultModule.fetchVaultFiles();
            booruModule.fetchBooruCount();
            accountsModule.fetchAccounts();
        });

        watch(currentTab, () => {
            nextTick(updateNavbarHeight);
            setTimeout(updateNavbarHeight, 100);
        });

        return {
            currentTab,
            isNavVisible,
            globalImageFit,
            setGlobalImageFit,
            refreshAll,
            ...i18nModule,
            ...window.AppUtils,
            ...accountsModule,
            ...tasksModule,
            ...downloadsModule,
            ...booruModule,
            ...vaultModule
        };
    }
}).mount('#app');
