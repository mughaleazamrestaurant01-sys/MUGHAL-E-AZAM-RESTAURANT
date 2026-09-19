window.posCoreMethods = {
    receiptMoney(val) { return `Rs. ${parseFloat(val || 0).toFixed(2)}`; },
    isCashPayment(method) { return String(method || '').toLowerCase().includes('cash'); },
    updateClock() {
        const now = new Date();
        this.currentTime = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    },
    selectOrderType(type) {
        this.orderType = type;
        if (type !== 'Dine-In') this.selectedTable = null;
    },
    addToCart(item) {
        if (!item.isAvailable) {
            this.showToast('Item is currently out of stock');
            return;
        }
        const existing = this.cart.find(i => i.id === item.id);
        if (existing) {
            existing.qty++;
        } else {
            this.cart.push({ id: item.id, name: item.name, price: item.price, qty: 1, notes: '' });
        }
        this.queuePersistentSave();
    },
    updateQty(index, change) {
        const item = this.cart[index];
        if (!item) return;
        item.qty += change;
        if (item.qty <= 0) this.cart.splice(index, 1);
        this.queuePersistentSave();
    },
    clearCart() {
        this.cart = [];
        this.discountPercent = 0;
        this.queuePersistentSave();
    },
    selectCustomer(cust) {
        this.activeCustomerName = cust.name;
        this.activeCustomerPhone = cust.phone;
        this.activeCustomerAddress = cust.address || '';
    },
    sendOrderToQueue() {
        if (this.cart.length === 0) return;
        if (this.orderType === 'Dine-In' && !this.selectedTable) {
            this.showToast('Please select a Table for Dine-In order');
            return;
        }
        const newOrder = {
            id: `ORD-${this.currentOrderNumber++}`,
            type: this.orderType,
            tableName: this.selectedTable ? this.selectedTable.name : null,
            customerName: this.activeCustomerName || null,
            customerPhone: this.activeCustomerPhone || null,
            items: JSON.parse(JSON.stringify(this.cart)),
            status: 'Pending',
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            date: new Date().toISOString().split('T')[0]
        };
        this.kdsQueue.push(newOrder);
        if (this.selectedTable) {
            this.selectedTable.status = 'occupied';
            this.selectedTable.order = newOrder;
        }
        if (this.printerConfig.autoPrintKitchen) {
            this.printKot(newOrder);
        }
        this.clearCart();
        this.showToast(`Order #${newOrder.id} sent to Kitchen KDS Queue`);
        this.queuePersistentSave();
    },
    printProvisionalBill() {
        if (!this.selectedTable || !this.selectedTable.order) {
            this.showToast('No active order on this table to preview bill');
            return;
        }
        const ord = this.selectedTable.order;
        this.printReceiptDirectly({
            orderId: ord.id,
            tableName: ord.tableName,
            orderType: ord.type,
            items: ord.items,
            subtotal: ord.items.reduce((sum, i) => sum + (i.price * i.qty), 0),
            discount: 0,
            grandTotal: ord.items.reduce((sum, i) => sum + (i.price * i.qty), 0),
            time: ord.time,
            title: 'PROVISIONAL CHECK',
            isPreview: true
        });
    },
    updateKdsStatus(orderId, newStatus) {
        const order = this.kdsQueue.find(o => o.id === orderId);
        if (order) {
            order.status = newStatus;
            if (newStatus === 'Completed') {
                this.kdsQueue = this.kdsQueue.filter(o => o.id !== orderId);
                this.completedKdsOrders.unshift(order);
            }
            this.queuePersistentSave();
        }
    },
    processCheckout() {
        if (this.cart.length === 0) return;
        const total = this.cartGrandTotal;
        if (this.isCashPayment(this.paymentMethod) && (this.cashTendered === null || this.cashTendered < total)) {
            this.showToast(`Cash tendered must be at least ${this.receiptMoney(total)}`);
            return;
        }
        const newOrderRecord = {
            id: `INV-${Date.now().toString().slice(-6)}`,
            orderType: this.orderType,
            tableName: this.selectedTable ? this.selectedTable.name : null,
            customerName: this.activeCustomerName,
            customerPhone: this.activeCustomerPhone,
            customerAddress: this.activeCustomerAddress,
            deliveryFee: this.orderType === 'Delivery' ? (parseFloat(this.deliveryFeeInput) || 0) : 0,
            items: JSON.parse(JSON.stringify(this.cart)),
            subtotal: this.cartSubtotal,
            discount: this.cartDiscountAmount,
            grandTotal: total,
            paymentMethod: this.paymentMethod,
            cashTendered: this.isCashPayment(this.paymentMethod) ? parseFloat(this.cashTendered) : total,
            changeDue: this.isCashPayment(this.paymentMethod) ? (parseFloat(this.cashTendered) - total) : 0,
            date: new Date().toISOString().split('T')[0],
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };

        this.deductIngredientsForOrder(newOrderRecord.items);
        this.ordersHistory.unshift(newOrderRecord);

        if (this.activeCustomerName && this.activeCustomerPhone) {
            let cust = this.customers.find(c => c.phone === this.activeCustomerPhone);
            if (cust) {
                cust.totalSpent += newOrderRecord.grandTotal;
                cust.orderCount++;
                if (this.activeCustomerAddress) cust.address = this.activeCustomerAddress;
            } else {
                this.customers.push({
                    id: `c-${Date.now()}`,
                    name: this.activeCustomerName,
                    phone: this.activeCustomerPhone,
                    address: this.activeCustomerAddress || '',
                    totalSpent: newOrderRecord.grandTotal,
                    orderCount: 1
                });
            }
        }

        if (this.selectedTable) {
            this.selectedTable.status = 'available';
            this.selectedTable.order = null;
        }

        this.printReceiptDirectly(newOrderRecord);
        this.clearCart();
        this.showCheckoutModal = false;
        this.cashTendered = null;
        this.activeCustomerName = '';
        this.activeCustomerPhone = '';
        this.activeCustomerAddress = '';
        this.deliveryFeeInput = null;
        this.showToast(`Payment successful! Receipt sent to printer.`);
        this.queuePersistentSave();
    },
    deductIngredientsForOrder(items) {
        items.forEach(cartItem => {
            const menuItem = this.menuItems.find(m => m.id === cartItem.id);
            if (menuItem && menuItem.recipe) {
                menuItem.recipe.forEach(r => {
                    const ing = this.ingredients.find(i => i.id === r.ingredientId);
                    if (ing) {
                        ing.inStock = Math.max(0, ing.inStock - (r.qtyNeeded * cartItem.qty));
                    }
                });
            }
        });
    }
};
