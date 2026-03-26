@app.route('/api/billing/prepare-reprocess', methods=['POST'])
def prepare_reprocess():
    if session.get('role') != 'sales':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    return_item_id = str(data.get('item_id'))
    qty_to_return = float(data.get('qty', 0))
    
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale: return jsonify({'success': False, 'message': 'Bill not found'})
    
    if sale.get('status') == 'CANCELLED':
        return jsonify({'success': False, 'message': 'Bill is already cancelled'})

    # 1. Restock the RETURNED quantity
    now = datetime.datetime.now()
    agg = get_aggregated_inventory()
    p_agg = next((x for x in agg if x['code'] == return_item_id), None)
    cost = p_agg['last_cost'] if p_agg else 0.0

    STORAGE.append({
        'batch_id': f"REPROC-#{bill_id}",
        'code': return_item_id,
        'qty': qty_to_return,
        'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
        'arrival_date': now.strftime("%Y-%m-%d"),
        'expiry': None,
        'cost': cost,
        'invoice_no': f"RETURN-REPROC-#{bill_id}"
    })

    # 2. Add to Returns Log
    return_date = now.strftime("%Y-%m-%d %H:%M:%S")
    item_in_bill = next((i for i in sale['details'] if str(i['id']) == return_item_id), None)
    RETURNS_LOG.append({
        'date': return_date,
        'type': 'REPROCESS_RETURN',
        'bill_id': bill_id,
        'product_code': return_item_id,
        'product_name': item_in_bill.get('name', 'Unknown') if item_in_bill else 'Unknown',
        'qty': qty_to_return,
        'refund_amount': qty_to_return * (item_in_bill.get('price', 0) if item_in_bill else 0)
    })

    # 3. Create the "Remaining items" cart for POS
    new_cart = []
    for item in sale['details']:
        # IMPORTANT: 'id' in sale['details'] is currently the product code (see mapping in load logic)
        item_code = str(item['id'])
        rem_qty = item['qty']
        
        if item_code == return_item_id:
            rem_qty -= qty_to_return
        
        if rem_qty > 0:
            # Re-fetch full product data for POS
            prod = next((p for p in PRODUCTS if p['code'] == item_code), None)
            if prod:
                # We need to map it back to the structure expected by pos.html:
                # { id, code, name, category, price, stock, unit, qty }
                new_cart.append({
                    'id': prod['id'], # DB ID or unique numerical ID
                    'code': prod['code'],
                    'name': prod['name'],
                    'category': prod['category'],
                    'price': prod['price'],
                    'stock': prod['stock'], 
                    'unit': prod.get('unit', 'PCS'),
                    'qty': rem_qty
                })

    # 4. Mark old bill as RETURNED (Archive state)
    sale['status'] = 'RETURNED'
    # Clear total/balance as the transaction is effectively being "moved" to a new bill
    sale['total'] = 0
    sale['balance'] = 0

    # DB Persistence
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE sales_log SET status = ?, total = 0, balance = 0 WHERE id = ?', ('RETURNED', bill_id))
        
        # Log the specific return item to DB
        cur.execute('INSERT INTO returns_log (date, product_code, product_name, qty, refund_amount, bill_id, type) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (return_date, return_item_id, item_in_bill.get('name', 'Unknown') if item_in_bill else 'Unknown', qty_to_return, qty_to_return * (item_in_bill.get('price', 0) if item_in_bill else 0), bill_id, 'REPROCESS_RETURN'))

        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no')))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f"DB Error: {str(e)}"})
    finally:
        conn.close()

    # 5. Store in session for POS to pick up
    session['reprocess_cart'] = new_cart
    return jsonify({'success': True, 'redirect': '/billing'})
