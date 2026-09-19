window.posAdminMethods = {
    isCategoryDiscountAllowed(catId) { return true; },
    getCategoryName(catId) {
        const cat = this.categories.find(c => c.id === catId);
        return cat ? cat.name : 'General';
    },
    saveNewCategory(catName) {
        if (!catName || !catName.trim()) return;
        const newCat = { id: `cat-${Date.now()}`, name: catName.trim() };
        this.categories.push(newCat);
        this.showToast(`Category '${newCat.name}' created`);
        this.queuePersistentSave();
    },
    openEditCategory(cat) {
        this.editingCategory = { ...cat };
        this.showEditCategoryModal = true;
    },
    updateCategory() {
        if (!this.editingCategory || !this.editingCategory.name.trim()) return;
        const idx = this.categories.findIndex(c => c.id === this.editingCategory.id);
        if (idx !== -1) {
            this.categories[idx].name = this.editingCategory.name.trim();
            this.showToast('Category updated successfully');
            this.queuePersistentSave();
        }
        this.showEditCategoryModal = false;
    },
    deleteCategory(catId) {
        const count = this.menuItems.filter(m => m.categoryId === catId).length;
        if (count > 0) {
            this.showToast('Cannot delete category containing menu items');
            return;
        }
        this.categories = this.categories.filter(c => c.id !== catId);
        this.showToast('Category deleted');
        this.queuePersistentSave();
    },
    openAddDishModal() {
        this.editingDish = null;
        this.dishForm = { name: '', categoryId: this.categories[0]?.id || '', price: null, isAvailable: true, recipe: [] };
        this.showEditDishModal = true;
    },
    openEditDishModal(dish) {
        this.editingDish = dish;
        this.dishForm = {
            name: dish.name,
            categoryId: dish.categoryId,
            price: dish.price,
            isAvailable: dish.isAvailable,
            recipe: JSON.parse(JSON.stringify(dish.recipe || []))
        };
        this.showEditDishModal = true;
    },
    saveDish() {
        if (!this.dishForm.name.trim() || !this.dishForm.price) {
            this.showToast('Dish name and price are required');
            return;
        }
        if (this.editingDish) {
            const idx = this.menuItems.findIndex(m => m.id === this.editingDish.id);
            if (idx !== -1) {
                this.menuItems[idx] = {
                    ...this.menuItems[idx],
                    name: this.dishForm.name.trim(),
                    categoryId: this.dishForm.categoryId,
                    price: parseFloat(this.dishForm.price),
                    isAvailable: this.dishForm.isAvailable,
                    recipe: this.dishForm.recipe
                };
                this.showToast(`Dish '${this.menuItems[idx].name}' updated`);
            }
        } else {
            const newDish = {
                id: `item-${Date.now()}`,
                name: this.dishForm.name.trim(),
                categoryId: this.dishForm.categoryId,
                price: parseFloat(this.dishForm.price),
                isAvailable: this.dishForm.isAvailable,
                recipe: this.dishForm.recipe
            };
            this.menuItems.push(newDish);
            this.showToast(`Dish '${newDish.name}' created`);
        }
        this.showEditDishModal = false;
        this.queuePersistentSave();
    },
    toggleDishAvailability(dish) {
        dish.isAvailable = !dish.isAvailable;
        this.showToast(`'${dish.name}' is now ${dish.isAvailable ? 'Available' : 'Out of Stock'}`);
        this.queuePersistentSave();
    },
    deleteDish(dishId) {
        this.menuItems = this.menuItems.filter(m => m.id !== dishId);
        this.showToast('Menu item deleted');
        this.queuePersistentSave();
    },
    saveStockIngredient() {
        if (!this.newStockForm.name.trim()) return;
        const newIng = {
            id: `ing-${Date.now()}`,
            name: this.newStockForm.name.trim(),
            unit: this.newStockForm.unit || 'kg',
            inStock: parseFloat(this.newStockForm.qty) || 0,
            avgUnitCost: parseFloat(this.newStockForm.unitCost) || 0
        };
        this.ingredients.push(newIng);
        this.newStockForm = { name: '', unit: 'kg', qty: 0, unitCost: 0 };
        this.showAddStockModal = false;
        this.showToast(`Ingredient '${newIng.name}' added to inventory`);
        this.queuePersistentSave();
    },
    recordPurchase() {
        if (!this.purchaseForm.ingredientId || !this.purchaseForm.qty || !this.purchaseForm.unitCost) {
            this.showToast('Please fill all purchase details');
            return;
        }
        const ing = this.ingredients.find(i => i.id === this.purchaseForm.ingredientId);
        if (!ing) return;
        const qty = parseFloat(this.purchaseForm.qty);
        const cost = parseFloat(this.purchaseForm.unitCost);
        const total = qty * cost;

        ing.inStock += qty;
        ing.avgUnitCost = ((ing.inStock * ing.avgUnitCost) + total) / (ing.inStock + qty);

        const rec = {
            id: `PUR-${Date.now().toString().slice(-6)}`,
            ingredientName: ing.name,
            qty: qty,
            unit: ing.unit,
            unitCost: cost,
            totalCost: total,
            supplier: this.purchaseForm.supplier || 'N/A',
            date: new Date().toISOString().split('T')[0]
        };
        this.purchaseHistory.unshift(rec);
        this.purchaseForm = { ingredientId: '', qty: null, unitCost: null, supplier: '' };
        this.showToast(`Recorded purchase of ${qty} ${ing.unit} ${ing.name}`);
        this.queuePersistentSave();
    },
    saveExpense() {
        if (!this.newExpenseForm.title.trim() || !this.newExpenseForm.amount) {
            this.showToast('Expense title and amount required');
            return;
        }
        const exp = {
            id: `EXP-${Date.now().toString().slice(-6)}`,
            title: this.newExpenseForm.title.trim(),
            amount: parseFloat(this.newExpenseForm.amount),
            date: new Date().toISOString().split('T')[0],
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        this.expensesHistory.unshift(exp);
        this.newExpenseForm = { title: '', amount: null };
        this.showAddExpenseModal = false;
        this.showToast(`Expense 'Rs. ${exp.amount}' recorded`);
        this.queuePersistentSave();
    },
    openAddUserModal() {
        this.userForm = { id: null, name: '', username: '', password: '', role: 'Cashier', permissions: ['pos', 'kds'] };
        this.showAdminPanelModal = true;
    },
    openEditUserModal(user) {
        this.userForm = {
            id: user.id,
            name: user.name,
            username: user.username,
            password: '',
            role: user.role,
            permissions: [...(user.permissions || [])]
        };
        this.showAdminPanelModal = true;
    },
    async saveUser() {
        if (!this.userForm.name.trim() || !this.userForm.username.trim()) {
            this.showToast('Name and Username are required');
            return;
        }
        try {
            const res = await window.posApi.save_user(this.userForm, this.userForm.id);
            if (res.ok) {
                this.users = res.users;
                this.showAdminPanelModal = false;
                this.showToast(`User account saved successfully`);
            } else {
                this.showToast(res.error || 'Failed to save user');
            }
        } catch (err) {
            this.showToast('Network / System error saving user');
        }
    },
    async deleteUser(userId) {
        try {
            const res = await window.posApi.delete_user(userId);
            if (res.ok) {
                this.users = res.users;
                this.showToast('User account deleted');
            } else {
                this.showToast(res.error || 'Failed to delete user');
            }
        } catch (err) {
            this.showToast('Error deleting user account');
        }
    },
    saveTable() {
        if (!this.tableForm.name.trim()) return;
        if (this.editingTableId) {
            const t = this.tables.find(x => x.id === this.editingTableId);
            if (t) t.name = this.tableForm.name.trim();
        } else {
            this.tables.push({ id: `t-${Date.now()}`, name: this.tableForm.name.trim(), status: 'available', order: null });
        }
        this.showTableModal = false;
        this.tableForm.name = '';
        this.editingTableId = null;
        this.queuePersistentSave();
    },
    deleteTable(tableId) {
        const t = this.tables.find(x => x.id === tableId);
        if (t && t.status === 'occupied') {
            this.showToast('Cannot delete an occupied table');
            return;
        }
        this.tables = this.tables.filter(x => x.id !== tableId);
        this.showToast('Table removed');
        this.queuePersistentSave();
    }
};
