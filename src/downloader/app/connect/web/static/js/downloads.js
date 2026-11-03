// Ізольований модуль завантаження посилань (одиночних/пакетних) та прямого завантаження файлів у сховище
window.createDownloadsModule = function ({ ref, onFilesUploaded }) {
    const isSubmitting = ref(false);
    const isUploading = ref(false);
    const isDragOver = ref(false);
    const selectedFiles = ref([]);
    const uploadTags = ref('');

    const form = ref({
        urls: '',
        max_height: 1080,
        audio_only: false,
        tagsInput: '',
        image_format: 'original',
        image_max_side: null
    });

    const handleFileSelected = (e) => {
        if (e.target.files && e.target.files.length) {
            selectedFiles.value.push(...Array.from(e.target.files));
        }
    };

    const handleDropFiles = (e) => {
        isDragOver.value = false;
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
            selectedFiles.value.push(...Array.from(e.dataTransfer.files));
        }
    };

    const removeSelectedFile = (idx) => {
        selectedFiles.value.splice(idx, 1);
    };

    const submitFileUpload = async () => {
        if (!selectedFiles.value.length) return;
        isUploading.value = true;
        try {
            for (const file of selectedFiles.value) {
                const base64Data = await window.AppUtils.readFileAsBase64(file);
                await fetch('/api/v1/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filename: file.name,
                        content_b64: base64Data,
                        tags: uploadTags.value || form.value.tagsInput,
                        image_format: form.value.image_format,
                        image_max_side: form.value.image_max_side
                    })
                });
            }
            selectedFiles.value = [];
            uploadTags.value = '';
            if (typeof onFilesUploaded === 'function') {
                await onFilesUploaded();
            }
        } catch (e) {
            alert('Помилка завантаження файлу: ' + e);
        } finally {
            isUploading.value = false;
        }
    };

    const submitDownload = async () => {
        const rawText = form.value.urls.trim();
        if (!rawText && selectedFiles.value.length === 0) return;

        isSubmitting.value = true;
        const tags = form.value.tagsInput
            .split(',')
            .map(t => t.trim().replace(/^#/, ''))
            .filter(Boolean);

        try {
            if (rawText) {
                const lines = rawText
                    .split(/[\r\n\s]+/)
                    .map(s => s.trim())
                    .filter(Boolean);

                const items = lines.map(targetUrl => ({
                    url: targetUrl,
                    max_height: form.value.max_height,
                    audio_only: form.value.audio_only,
                    tags: tags,
                    image_format: form.value.image_format,
                    image_max_side: form.value.image_max_side
                }));

                await fetch('/api/v1/download/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                form.value.urls = '';
            }

            if (selectedFiles.value.length > 0) {
                if (!uploadTags.value && form.value.tagsInput) {
                    uploadTags.value = form.value.tagsInput;
                }
                await submitFileUpload();
            }

            form.value.tagsInput = '';
        } catch (e) {
            alert('Помилка запуску: ' + e);
        } finally {
            isSubmitting.value = false;
        }
    };

    return {
        form,
        isSubmitting,
        isUploading,
        isDragOver,
        selectedFiles,
        uploadTags,
        submitDownload,
        handleFileSelected,
        handleDropFiles,
        removeSelectedFile,
        submitFileUpload
    };
};

