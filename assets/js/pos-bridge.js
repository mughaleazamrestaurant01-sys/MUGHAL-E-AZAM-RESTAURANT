// The POS starts through the bundled loopback service, not the optional
// WebView JavaScript bridge. This means the database is reachable even
// when a Windows WebView runtime delays or omits `pywebviewready`.
(() => {
    const request = async (method, payload, verb = 'POST') => {
        const response = await fetch(`/api/${method}`, {
            method: verb,
            headers: { 'Content-Type': 'application/json' },
            body: verb === 'GET' ? undefined : JSON.stringify(payload || {})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'The local POS service could not complete the request.');
        return data;
    };
    window.posApi = {
        get_boot_data: () => request('boot', null, 'GET'),
        get_printer_config: () => request('printer-config', null, 'GET'),
        get_backup_directory: async () => (await request('backup-directory', null, 'GET')).directory || '',
        get_system_printers: () => request('system-printers', null, 'GET'),
        save_state: (state) => request('save-state', { state }),
        save_printer_config: (config) => request('save-printer-config', { config }),
        authenticate: (username, password) => request('authenticate', { username, password }),
        save_user: (user, userId) => request('save-user', { user, userId }),
        delete_user: (userId) => request('delete-user', { userId }),
        print_direct: (printerName, receiptData) => request('print-direct', { printerName, receiptData }),
        test_printer: (printerName, receiptType, cutMode) => request('test-printer', { printerName, receiptType, cutMode }),
        create_backup_now: () => request('create-backup'),
        select_backup_folder: () => window.pywebview?.api?.select_backup_folder
            ? window.pywebview.api.select_backup_folder()
            : Promise.resolve({ ok: false, error: 'Folder selection is unavailable in this WebView runtime.' }),
        restore_from_directory: () => window.pywebview?.api?.restore_from_directory
            ? window.pywebview.api.restore_from_directory()
            : Promise.resolve({ ok: false, error: 'Backup restore is unavailable in this WebView runtime.' })
    };
})();
