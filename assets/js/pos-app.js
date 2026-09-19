const { createApp } = Vue;

createApp({
    data() {
        return window.posData();
    },
    computed: {
        currentCategoryName() {
            if (this.selectedCategory === 'all') return 'All Menu Items';
            const cat = this.categories.find(c => c.id === this.selectedCategory);
            return cat ? cat.name : 'Category';
        },
        filteredMenuItems() {
            return this.menuItems.filter(item => {
                const matchesCategory = this.selectedCategory === 'all' || item.categoryId === this.selectedCategory;
                const matchesSearch = !this.searchQuery || item.name.toLowerCase().includes(this.searchQuery.toLowerCase());
                return matchesCategory && matchesSearch;
            });
        },
        cartSubtotal() {
            return this.cart.reduce((sum, item) => sum + (item.price * item.qty), 0);
        },
        cartDiscountAmount() {
            if (!this.discountPercent) return 0;
            return (this.cartSubtotal * this.discountPercent) / 100;
        },
        cartGrandTotal() {
            const sub = this.cartSubtotal - this.cartDiscountAmount;
            const delivery = (this.orderType === 'Delivery' && this.deliveryFeeInput) ? parseFloat(this.deliveryFeeInput) || 0 : 0;
            return Math.max(0, sub + delivery);
        },
        cartTotalItemsCount() {
            return this.cart.reduce((sum, item) => sum + item.qty, 0);
        },
        todaysOrders() {
            const today = new Date().toISOString().split('T')[0];
            return this.ordersHistory.filter(o => o.date === today);
        },
        todaysTotalSales() {
            return this.todaysOrders.reduce((sum, o) => sum + o.grandTotal, 0);
        },
        todaysTotalExpenses() {
            const today = new Date().toISOString().split('T')[0];
            return this.expensesHistory.filter(e => e.date === today).reduce((sum, e) => sum + e.amount, 0);
        },
        filteredHistoryOrders() {
            return this.ordersHistory.filter(o => {
                const matchesDate = !this.selectedHistoryDate || o.date === this.selectedHistoryDate;
                const q = (this.recordSearchQuery || '').toLowerCase();
                const matchesSearch = !q || (o.id || '').toLowerCase().includes(q) ||
                    (o.customerName || '').toLowerCase().includes(q) ||
                    (o.customerPhone || '').toLowerCase().includes(q);
                return matchesDate && matchesSearch;
            });
        },
        filteredCustomers() {
            const q = (this.searchQuery || '').toLowerCase();
            return this.customers.filter(c => !q || c.name.toLowerCase().includes(q) || c.phone.includes(q));
        },
        filteredPurchasingIngredients() {
            const q = (this.purchasingIngredientSearch || '').toLowerCase();
            return this.ingredients.filter(i => !q || i.name.toLowerCase().includes(q));
        },
        filteredPurchaseHistory() {
            const q = (this.purchaseSearchQuery || '').toLowerCase();
            return this.purchaseHistory.filter(p => !q || p.ingredientName.toLowerCase().includes(q) || (p.supplier || '').toLowerCase().includes(q));
        }
    },
    methods: {
        ...window.posCoreMethods,
        ...window.posAdminMethods,
        ...window.posPrintMethods,

        showToast(msg) {
            this.toastMessage = msg;
            if (this.toastTimer) clearTimeout(this.toastTimer);
            this.toastTimer = setTimeout(() => { this.toastMessage = ''; }, 3000);
        },
        hasPermission(permId) {
            if (!this.currentUser) return false;
            if (this.currentUser.role === 'Admin') return true;
            return Array.isArray(this.currentUser.permissions) && this.currentUser.permissions.includes(permId);
        },
        async startBoot() {
            this.bootLoading = true;
            this.bootError = '';
            try {
                const res = await window.posApi.get_boot_data();
                this.users = res.users || [];
                if (res.state && Object.keys(res.state).length > 0) {
                    this.restoreStateFromBoot(res.state);
                }
                const printerConfig = await window.posApi.get_printer_config();
                if (printerConfig && Object.keys(printerConfig).length > 0) {
                    this.printerConfig = { ...this.printerConfig, ...printerConfig };
                }
                this.backupDirectory = await window.posApi.get_backup_directory();
                this.bootReady = true;
                this.persistenceReady = true;
                this.scanPrinters();
            } catch (err) {
                this.bootError = err.message || 'Failed to initialize local POS database.';
            } finally {
                this.bootLoading = false;
            }
        },
        restoreStateFromBoot(state) {
            if (state.categories) this.categories = state.categories;
            if (state.menuItems) this.menuItems = state.menuItems;
            if (state.cart) this.cart = state.cart;
            if (state.tables) this.tables = state.tables;
            if (state.kdsQueue) this.kdsQueue = state.kdsQueue;
            if (state.completedKdsOrders) this.completedKdsOrders = state.completedKdsOrders;
            if (state.ordersHistory) this.ordersHistory = state.ordersHistory;
            if (state.expensesHistory) this.expensesHistory = state.expensesHistory;
            if (state.ingredients) this.ingredients = state.ingredients;
            if (state.customers) this.customers = state.customers;
            if (state.purchaseHistory) this.purchaseHistory = state.purchaseHistory;
            if (state.currentOrderNumber) this.currentOrderNumber = state.currentOrderNumber;
            if (state.dailyOpeningCash) this.dailyOpeningCash = state.dailyOpeningCash;
        },
        buildPersistentState() {
            return {
                categories: this.categories,
                menuItems: this.menuItems,
                cart: this.cart,
                tables: this.tables,
                kdsQueue: this.kdsQueue,
                completedKdsOrders: this.completedKdsOrders,
                ordersHistory: this.ordersHistory,
                expensesHistory: this.expensesHistory,
                ingredients: this.ingredients,
                customers: this.customers,
                purchaseHistory: this.purchaseHistory,
                currentOrderNumber: this.currentOrderNumber,
                dailyOpeningCash: this.dailyOpeningCash
            };
        },
        queuePersistentSave() {
            if (!this.persistenceReady) return;
            if (this.persistenceTimer) clearTimeout(this.persistenceTimer);
            this.persistenceTimer = setTimeout(() => {
                const payload = this.buildPersistentState();
                this.persistenceChain = this.persistenceChain.then(async () => {
                    try {
                        const res = await window.posApi.save_state(payload);
                        if (!res.ok) console.warn('Persistence warn:', res.error);
                    } catch (err) {
                        console.error('Persistence failed:', err);
                    }
                });
            }, 300);
        },
        async handleLogin() {
            this.loginError = '';
            try {
                const res = await window.posApi.authenticate(this.loginForm.username, this.loginForm.password);
                if (res.ok) {
                    this.currentUser = res.user;
                    this.loginForm = { username: '', password: '' };
                    this.showToast(`Welcome back, ${res.user.name}`);
                } else {
                    this.loginError = res.error || 'Invalid credentials';
                }
            } catch (err) {
                this.loginError = 'System login error';
            }
        },
        async handleFirstUserSetup() {
            this.setupError = '';
            if (!this.setupForm.name.trim() || !this.setupForm.username.trim() || !this.setupForm.password) {
                this.setupError = 'All fields are required';
                return;
            }
            if (this.setupForm.password.length < 8) {
                this.setupError = 'Password must be at least 8 characters';
                return;
            }
            try {
                const res = await window.posApi.save_user({
                    name: this.setupForm.name.trim(),
                    username: this.setupForm.username.trim(),
                    password: this.setupForm.password,
                    role: 'Admin',
                    permissions: ['pos', 'kds', 'menu', 'stock', 'purchasing', 'records', 'crm', 'tables', 'admin']
                });
                if (res.ok) {
                    this.users = res.users;
                    const loginRes = await window.posApi.authenticate(this.setupForm.username, this.setupForm.password);
                    if (loginRes.ok) this.currentUser = loginRes.user;
                    this.showToast('Initial Admin Account Created!');
                } else {
                    this.setupError = res.error || 'Failed to create admin user';
                }
            } catch (err) {
                this.setupError = 'Setup execution error';
            }
        },
        handleLogout() {
            this.currentUser = null;
            this.showToast('Logged out safely');
        }
    },
    mounted() {
        this.updateClock();
        setInterval(this.updateClock, 1000);
        this.startBoot();
    }
}).mount('#app');
