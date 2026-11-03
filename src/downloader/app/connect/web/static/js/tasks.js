// Ізольований модуль моніторингу задач у реальному часі (WebSocket) та історії
window.createTasksModule = function ({ ref, computed, onTaskCompleted }) {
    const wsConnected = ref(false);
    const tasks = ref({});
    const historySearch = ref('');
    const historyStatusFilter = ref('all');
    let ws = null;

    const connectWs = () => {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${proto}//${location.host}/ws/progress`);

        ws.onopen = () => {
            wsConnected.value = true;
        };
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                tasks.value[data.task_id] = data;
                if (data.status === 'completed' && typeof onTaskCompleted === 'function') {
                    onTaskCompleted();
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };
        ws.onclose = () => {
            wsConnected.value = false;
            setTimeout(connectWs, 3000);
        };
    };

    const fetchTasks = async () => {
        try {
            const res = await fetch('/api/v1/tasks');
            if (res.ok) {
                const list = await res.json();
                list.forEach(t => {
                    tasks.value[t.task_id] = t;
                });
            }
        } catch (e) {
            console.error('Fetch tasks error:', e);
        }
    };

    const activeTasks = computed(() => {
        return Object.values(tasks.value)
            .filter(t => ['queued', 'extracting', 'downloading', 'processing'].includes(t.status))
            .reverse();
    });

    const allTasksList = computed(() => {
        let list = Object.values(tasks.value).reverse();
        if (historyStatusFilter.value !== 'all') {
            list = list.filter(t => t.status === historyStatusFilter.value);
        }
        if (historySearch.value.trim()) {
            const q = historySearch.value.trim().toLowerCase();
            list = list.filter(t =>
                (t.title && t.title.toLowerCase().includes(q)) ||
                (t.url && t.url.toLowerCase().includes(q)) ||
                (t.source_platform && t.source_platform.toLowerCase().includes(q)) ||
                (t.tags && t.tags.some(tag => tag.toLowerCase().includes(q)))
            );
        }
        return list;
    });

    const hasActiveHistoryFilters = computed(() => {
        return historyStatusFilter.value !== 'all' || historySearch.value.trim().length > 0;
    });

    const resetHistoryFilters = () => {
        historyStatusFilter.value = 'all';
        historySearch.value = '';
    };

    return {
        wsConnected,
        tasks,
        activeTasks,
        allTasksList,
        historySearch,
        historyStatusFilter,
        hasActiveHistoryFilters,
        resetHistoryFilters,
        connectWs,
        fetchTasks
    };
};
