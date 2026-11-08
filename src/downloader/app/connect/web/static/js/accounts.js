// ============================================================================
// Модуль керування акаунтами, API-ключами, прив'язкою до ботів та сховищами
// ============================================================================

window.createAccountsModule = function ({ ref, onAccountSwitched }) {
    const accounts = ref([]);
    const activeAccountId = ref('default');
    const isAccountModalOpen = ref(false);
    const isAccountsLoading = ref(false);
    const editingAccount = ref(null);
    const isSavingAccount = ref(false);
    const accountSaveSuccess = ref(false);

    // NSFW теги
    const nsfwTagsList = ref([]);
    const newNsfwTagInput = ref('');
    const isNsfwTagsLoading = ref(false);

    const fetchAccounts = async () => {
        isAccountsLoading.value = true;
        try {
            const res = await fetch('/api/v1/accounts');
            if (res.ok) {
                const data = await res.json();
                accounts.value = data.accounts || [];
                activeAccountId.value = data.active_account_id || 'default';
            }
        } catch (e) {
            console.error('Failed to load accounts:', e);
        } finally {
            isAccountsLoading.value = false;
        }
    };

    const switchAccount = async (accId) => {
        try {
            const res = await fetch('/api/v1/accounts/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ account_id: accId })
            });
            if (res.ok) {
                activeAccountId.value = accId;
                await fetchAccounts();
                if (onAccountSwitched) onAccountSwitched(accId);
            }
        } catch (e) {
            console.error('Failed to switch account:', e);
        }
    };

    const openAccountModal = (acc = null) => {
        if (acc) {
            editingAccount.value = JSON.parse(JSON.stringify(acc));
        } else {
            const current = accounts.value.find(a => a.id === activeAccountId.value) || accounts.value[0];
            editingAccount.value = current ? JSON.parse(JSON.stringify(current)) : null;
        }
        accountSaveSuccess.value = false;
        isAccountModalOpen.value = true;
        fetchNsfwTags();
    };

    const closeAccountModal = () => {
        isAccountModalOpen.value = false;
        accountSaveSuccess.value = false;
    };

    const saveCurrentEditingAccount = async () => {
        if (!editingAccount.value) return;
        isSavingAccount.value = true;
        accountSaveSuccess.value = false;
        try {
            const res = await fetch('/api/v1/accounts/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(editingAccount.value)
            });
            if (res.ok) {
                accountSaveSuccess.value = true;
                await fetchAccounts();
                setTimeout(() => { accountSaveSuccess.value = false; }, 3000);
            }
        } catch (e) {
            alert('Помилка збереження: ' + e);
        } finally {
            isSavingAccount.value = false;
        }
    };

    const fetchNsfwTags = async () => {
        isNsfwTagsLoading.value = true;
        try {
            const res = await fetch('/api/v1/booru/nsfw-tags');
            if (res.ok) {
                const data = await res.json();
                nsfwTagsList.value = data.nsfw_tags || [];
            }
        } catch (e) {
            console.error('Failed to load nsfw tags:', e);
        } finally {
            isNsfwTagsLoading.value = false;
        }
    };

    const addNsfwTag = async () => {
        const val = newNsfwTagInput.value.trim().toLowerCase();
        if (!val) return;
        if (!nsfwTagsList.value.includes(val)) {
            nsfwTagsList.value.push(val);
            await saveNsfwTags();
        }
        newNsfwTagInput.value = '';
    };

    const removeNsfwTag = async (tag) => {
        nsfwTagsList.value = nsfwTagsList.value.filter(t => t !== tag);
        await saveNsfwTags();
    };

    const saveNsfwTags = async () => {
        try {
            await fetch('/api/v1/booru/nsfw-tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tags: nsfwTagsList.value })
            });
        } catch (e) {
            console.error('Failed to save nsfw tags:', e);
        }
    };

    const createNewAccountPrompt = async () => {
        const name = prompt('Введіть назву нового акаунта:');
        if (!name || !name.trim()) return;
        const cleanName = name.trim();
        const newId = 'account_' + Date.now().toString(36);
        try {
            const res = await fetch('/api/v1/accounts/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: newId,
                    username: newId,
                    display_name: cleanName,
                    avatar_emoji: '👤',
                    storage: { backend: 's3', s3_prefix: newId }
                })
            });
            if (res.ok) {
                await fetchAccounts();
                await switchAccount(newId);
                const created = accounts.value.find(a => a.id === newId);
                openAccountModal(created);
            }
        } catch (e) {
            alert('Помилка створення акаунта: ' + e);
        }
    };

    const deleteCurrentAccount = async () => {
        if (!editingAccount.value) return;
        const targetId = editingAccount.value.id;
        if (!confirm(`Видалити акаунт «${editingAccount.value.display_name}»?`)) return;
        try {
            const res = await fetch(`/api/v1/accounts/${targetId}`, { method: 'DELETE' });
            if (res.ok) {
                await fetchAccounts();
                openAccountModal();
            }
        } catch (e) {
            alert('Помилка видалення: ' + e);
        }
    };

    const activeAccount = () => {
        return accounts.value.find(a => a.id === activeAccountId.value) || accounts.value[0] || {
            id: 'account_1',
            display_name: 'Акаунт 1',
            avatar_emoji: '👤'
        };
    };

    return {
        accounts,
        activeAccountId,
        activeAccount,
        isAccountModalOpen,
        isAccountsLoading,
        editingAccount,
        isSavingAccount,
        accountSaveSuccess,
        nsfwTagsList,
        newNsfwTagInput,
        isNsfwTagsLoading,
        fetchAccounts,
        switchAccount,
        openAccountModal,
        closeAccountModal,
        saveCurrentEditingAccount,
        createNewAccountPrompt,
        deleteCurrentAccount,
        fetchNsfwTags,
        addNsfwTag,
        removeNsfwTag
    };
};
