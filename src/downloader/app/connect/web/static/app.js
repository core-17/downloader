const { createApp, ref, computed, onMounted, watch, nextTick } = Vue;

createApp({
    setup() {
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

        const vaultModule = window.createVaultModule({ ref, computed });
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
            currentTab
        });

        watch(currentTab, async (newTab) => {
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

        const refreshAll = () => {
            tasksModule.fetchTasks();
            vaultModule.fetchVaultFiles();
            if (currentTab.value === 'booru') {
                booruModule.searchBooru(true);
            }
        };

        onMounted(() => {
            window.addEventListener('scroll', onWindowScroll, { passive: true });
            tasksModule.connectWs();
            tasksModule.fetchTasks();
            vaultModule.fetchVaultFiles();
        });

        return {
            currentTab,
            isNavVisible,
            globalImageFit,
            setGlobalImageFit,
            refreshAll,
            ...window.AppUtils,
            ...tasksModule,
            ...downloadsModule,
            ...booruModule,
            ...vaultModule
        };
    }
}).mount('#app');
