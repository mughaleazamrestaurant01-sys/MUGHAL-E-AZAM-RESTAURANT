window.posPrintMethods = {
    async scanPrinters() {
        this.printerScanError = '';
        try {
            const res = await window.posApi.get_system_printers();
            if (res && Array.isArray(res.printers)) {
                this.availablePrinters = res.printers;
                if (res.error) this.printerScanError = res.error;
            } else {
                this.availablePrinters = [];
                this.printerScanError = res.error || 'Failed to detect printers.';
            }
        } catch (err) {
            this.availablePrinters = [];
            this.printerScanError = 'System printer discovery error: ' + err.message;
        }
    },
    async savePrinterSettings() {
        try {
            const res = await window.posApi.save_printer_config(this.printerConfig);
            if (res.ok) {
                this.showPrinterSettingsModal = false;
                this.showToast('Printer settings saved successfully');
            } else {
                this.showToast(res.error || 'Error saving printer configuration');
            }
        } catch (err) {
            this.showToast('Error communicating with POS system service');
        }
    },
    async testPrinter(printerName, type) {
        if (!printerName) {
            this.showToast('Select a printer queue first');
            return;
        }
        try {
            const res = await window.posApi.test_printer(printerName, type, this.printerConfig.receiptCutMode || 'star_full');
            if (res.status === 'success') {
                this.showToast(`Test page sent to ${printerName}`);
            } else {
                this.showToast(res.message || 'Printer test failed');
            }
        } catch (err) {
            this.showToast('Printer service communication error');
        }
    },
    async printKot(order) {
        const printerName = this.printerConfig.kitchenPrinterName || this.printerConfig.counterPrinterName;
        if (!printerName) {
            this.showToast('No kitchen or counter printer configured');
            return;
        }
        const kotData = {
            isKot: true,
            orderId: order.id,
            tableName: order.tableName,
            orderType: order.type,
            time: order.time,
            items: order.items,
            paperWidth: this.printerConfig.paperWidth || '80mm',
            cutMode: this.printerConfig.receiptCutMode || 'star_full'
        };
        try {
            const res = await window.posApi.print_direct(printerName, kotData);
            if (res.status !== 'success') {
                this.showToast(`KOT Print Error: ${res.message}`);
            }
        } catch (err) {
            this.showToast('KOT printing failed: Network/System error');
        }
    },
    async printReceiptDirectly(record) {
        const printerName = this.printerConfig.counterPrinterName;
        const receiptPayload = {
            restaurantName: this.printerConfig.restaurantName || 'MUGHAL-E-AZAM RESTAURANT',
            restaurantTagline: this.printerConfig.restaurantTagline || '',
            restaurantAddress: this.printerConfig.restaurantAddress || '',
            restaurantPhone: this.printerConfig.restaurantPhone || '',
            receiptFooter: this.printerConfig.receiptFooter || 'THANK YOU FOR YOUR VISIT!',
            paperWidth: this.printerConfig.paperWidth || '80mm',
            cutMode: this.printerConfig.receiptCutMode || 'star_full',
            orderId: record.orderId || record.id,
            orderType: record.orderType || 'Dine-In',
            tableName: record.tableName || null,
            customerName: record.customerName || null,
            customerPhone: record.customerPhone || null,
            customerAddress: record.customerAddress || null,
            paymentMethod: record.paymentMethod || 'Cash',
            items: record.items || [],
            subtotal: record.subtotal || 0,
            discount: record.discount || 0,
            deliveryFee: record.deliveryFee || 0,
            grandTotal: record.grandTotal || 0,
            time: record.time || new Date().toLocaleTimeString(),
            title: record.title || null,
            isPreview: record.isPreview || false
        };

        this.printableReceipt = receiptPayload;

        if (!printerName) {
            this.showToast('No counter printer configured; displaying on screen');
            return;
        }

        try {
            const res = await window.posApi.print_direct(printerName, receiptPayload);
            if (res.status === 'success') {
                this.showToast('Receipt printed successfully');
            } else {
                this.showToast(`Print error: ${res.message}`);
            }
        } catch (err) {
            this.showToast('Direct printing communication failure');
        }
    },
    async selectBackupFolder() {
        try {
            const res = await window.posApi.select_backup_folder();
            if (res.ok) {
                this.backupDirectory = res.directory;
                this.showToast('Backup folder set successfully');
            } else if (!res.cancelled) {
                this.showToast(res.error || 'Failed to set backup directory');
            }
        } catch (err) {
            this.showToast('Error setting backup folder');
        }
    },
    async createBackupNow() {
        try {
            const res = await window.posApi.create_backup_now();
            if (res.ok) {
                this.showToast(`Backup created at: ${res.path}`);
            } else {
                this.showToast(res.error || 'Backup creation failed');
            }
        } catch (err) {
            this.showToast('Error generating database backup');
        }
    },
    async restoreBackup() {
        try {
            const res = await window.posApi.restore_from_directory();
            if (res.ok) {
                this.showToast('Database restored successfully! Reloading...');
                setTimeout(() => window.location.reload(), 1000);
            } else if (!res.cancelled) {
                this.showToast(res.error || 'Restore operation failed');
            }
        } catch (err) {
            this.showToast('Error restoring backup file');
        }
    }
};
