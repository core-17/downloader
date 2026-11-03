// Ізольовані чисті функції форматування та утиліти інтерфейсу
window.AppUtils = {
    toggleArrayItem(arrRef, item) {
        const idx = arrRef.indexOf(item);
        if (idx >= 0) arrRef.splice(idx, 1);
        else arrRef.push(item);
    },

    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (evt) => {
                const res = evt.target.result || '';
                const b64 = res.includes(',') ? res.split(',')[1] : res;
                resolve(b64);
            };
            reader.onerror = (err) => reject(err);
            reader.readAsDataURL(file);
        });
    },

    getMediaIcon(mtype) {
        switch (mtype) {
            case 'video': return '🎬';
            case 'image': return '🖼️';
            case 'gallery': return '🖼️';
            case 'audio': return '🎵';
            case 'document': return '📄';
            default: return '📦';
        }
    },

    getStatusBadgeClass(status) {
        switch (status) {
            case 'completed': return 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
            case 'failed': return 'bg-rose-500/20 text-rose-400 border border-rose-500/30';
            case 'downloading': return 'bg-blue-500/20 text-blue-400 border border-blue-500/30';
            default: return 'bg-amber-500/20 text-amber-400 border border-amber-500/30';
        }
    },

    getTagTypeBadgeClass(typeCode) {
        switch (typeCode) {
            case -1: return 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30';
            case 1: return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
            case 3: return 'bg-pink-500/20 text-pink-300 border-pink-500/30';
            case 4: return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
            default: return 'bg-slate-800 text-slate-400 border-slate-700';
        }
    },

    formatDate(ts) {
        if (!ts) return '';
        const d = new Date(ts * 1000);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    encodeVaultPath(relPath) {
        if (!relPath) return '';
        return relPath.split('/').map(encodeURIComponent).join('/');
    }
};


