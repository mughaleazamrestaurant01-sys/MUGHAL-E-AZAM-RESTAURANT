window.posData = function() {
    return {
        currentUser: null,
        bootReady: false,
        bootError: '',
        bootLoading: false,
        toastTimer: null,
        persistenceTimer: null,
        persistenceChain: Promise.resolve(),
        persistenceReady: false,
        loginForm: { username: '', password: '' },
        loginError: '',
        setupForm: { name: '', username: '', password: '' },
        setupError: '',

        users: [],

        currentTab: 'pos',
        searchQuery: '',
        selectedCategory: 'all',
        orderType: 'Dine-In',
        currentOrderId: '1001',
        currentTime: '',
        selectedTable: null,

        dailyOpeningCash: 0,
        paymentMethod: 'Cash',
        cashTendered: null,

        activeCustomerName: '',
        activeCustomerPhone: '',
        activeCustomerAddress: '',
        deliveryFeeInput: null,

        availablePrinters: [],
        printerScanError: '',
        backupDirectory: '',

        printerConfig: {
            counterPrinterName: '',
            kitchenPrinterName: '',
            receiptHeader: 'MUGHAL-E-AZAM RESTAURANT',
            restaurantName: 'MUGHAL-E-AZAM RESTAURANT',
            restaurantTagline: 'Authentic Taste. Royal Hospitality.',
            restaurantAddress: '',
            restaurantPhone: '',
            receiptFooter: 'Thank you for choosing Mughal-E-Azam. We look forward to serving you again!',
            receiptCutMode: 'star_full',
            paperWidth: '80mm',
            autoPrintKitchen: true
        },

        printableReceipt: {
            title: 'COUNTER RECEIPT',
            orderId: '',
            time: '',
            customerName: '',
            customerPhone: '',
            tableName: '',
            items: [],
            subtotal: 0,
            discount: 0,
            tax: 0,
            grandTotal: 0
        },

        showCheckoutModal: false,
        showDiscountModal: false,
        showAddExpenseModal: false,
        showAddStockModal: false,
        showOpeningBalanceModal: false,
        showPrinterSettingsModal: false,
        showBackupModal: false,
        showRecipeModal: false,
        showAdminPanelModal: false,
        showEditCategoryModal: false,
        showEditDishModal: false,
        showTableModal: false,

        editingTableId: null,
        tableForm: { name: '' },

        menuSearchQuery: '',
        recordSearchQuery: '',
        discountPercent: 0,
        toastMessage: '',
        selectedHistoryDate: new Date().toISOString().split('T')[0],

        purchaseSearchQuery: '',
        purchasingIngredientSearch: '',
        purchaseForm: { ingredientId: '', qty: null, unitCost: null, supplier: '' },
        purchaseHistory: [],
        activeRecipeDish: null,

        newExpenseForm: { title: '', amount: null },
        newStockForm: { name: '', unit: 'kg', qty: 0, unitCost: 0 },

        userForm: { id: null, name: '', username: '', password: '', role: 'Cashier', permissions: [] },
        availablePermissions: [
            { id: 'pos', name: 'POS & Billing' },
            { id: 'kds', name: 'Kitchen KDS Queue' },
            { id: 'menu', name: 'Menu & Categories' },
            { id: 'stock', name: 'Inventory & Stock' },
            { id: 'purchasing', name: 'Purchasing & Expenses' },
            { id: 'records', name: 'Order Records & Analytics' },
            { id: 'crm', name: 'Customer Database' },
            { id: 'tables', name: 'Table Management' },
            { id: 'admin', name: 'Admin Control Center' }
        ],

        categories: [
            { id: 'cat-1', name: 'Starter & BBQ' },
            { id: 'cat-2', name: 'Mughlai Main Course' },
            { id: 'cat-3', name: 'Rice & Biryani' },
            { id: 'cat-4', name: 'Naan & Bread' },
            { id: 'cat-5', name: 'Beverages & Desserts' }
        ],

        menuItems: [
            { id: 'item-1', name: 'Chicken Malai Boti', categoryId: 'cat-1', price: 850, isAvailable: true, recipe: [{ ingredientId: 'ing-1', qtyNeeded: 0.25 }] },
            { id: 'item-2', name: 'Mutton Seekh Kabab', categoryId: 'cat-1', price: 950, isAvailable: true, recipe: [{ ingredientId: 'ing-2', qtyNeeded: 0.3 }] },
            { id: 'item-3', name: 'Chicken Karahi (Full)', categoryId: 'cat-2', price: 1600, isAvailable: true, recipe: [{ ingredientId: 'ing-1', qtyNeeded: 1.0 }] },
            { id: 'item-4', name: 'Mutton Handi (Half)', categoryId: 'cat-2', price: 1450, isAvailable: true, recipe: [{ ingredientId: 'ing-2', qtyNeeded: 0.5 }] },
            { id: 'item-5', name: 'Special Chicken Biryani', categoryId: 'cat-3', price: 450, isAvailable: true, recipe: [{ ingredientId: 'ing-1', qtyNeeded: 0.2 }, { ingredientId: 'ing-3', qtyNeeded: 0.25 }] },
            { id: 'item-6', name: 'Rogan Naan', categoryId: 'cat-4', price: 60, isAvailable: true, recipe: [] },
            { id: 'item-7', name: 'Garlic Naan', categoryId: 'cat-4', price: 80, isAvailable: true, recipe: [] },
            { id: 'item-8', name: 'Royal Kulfa Ice Cream', categoryId: 'cat-5', price: 250, isAvailable: true, recipe: [] },
            { id: 'item-9', name: 'Mint Margareta', categoryId: 'cat-5', price: 180, isAvailable: true, recipe: [] }
        ],

        cart: [],
        currentOrderNumber: 101,

        tables: [
            { id: 't1', name: 'Table 1', status: 'available', order: null },
            { id: 't2', name: 'Table 2', status: 'available', order: null },
            { id: 't3', name: 'Table 3', status: 'available', order: null },
            { id: 't4', name: 'Table 4', status: 'available', order: null },
            { id: 't5', name: 'Table 5', status: 'available', order: null },
            { id: 't6', name: 'Table 6', status: 'available', order: null }
        ],

        kdsQueue: [],
        completedKdsOrders: [],
        ordersHistory: [],
        expensesHistory: [],

        ingredients: [
            { id: 'ing-1', name: 'Fresh Chicken', unit: 'kg', inStock: 12.5, avgUnitCost: 450 },
            { id: 'ing-2', name: 'Mutton Meat', unit: 'kg', inStock: 8.0, avgUnitCost: 1650 },
            { id: 'ing-3', name: 'Basmati Rice', unit: 'kg', inStock: 45.0, avgUnitCost: 280 }
        ],

        customers: [
            { id: 'c1', name: 'Chaudhry Tanveer', phone: '0300-1234567', totalSpent: 12450, orderCount: 5, address: 'Gulberg III, Block B, Lahore' },
            { id: 'c2', name: 'Malik Usman', phone: '0321-9876543', totalSpent: 8900, orderCount: 3, address: 'DHA Phase 5, Street 12, Lahore' }
        ],

        editingCategory: null,
        editingDish: null,
        dishForm: { name: '', categoryId: '', price: null, isAvailable: true, recipe: [] }
    };
};
