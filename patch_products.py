import os

path = r"d:\Jai Agency\templates\inventory\products.html"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Pricing Form
form_start = content.find('<form id="editPriceForm"')
form_end = content.find('</form>', form_start) + 7
if form_start != -1 and form_end != -1:
    new_form = """<form id="editPriceForm" onsubmit="event.preventDefault(); updateProductPrice();">
            <input type="hidden" id="edit_code">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem;">
                <div class="f-group-modal">
                    <label>PRODUCT NAME (ENGLISH)</label>
                    <input type="text" id="edit_name" class="f-input-modal" required>
                </div>
                <div class="f-group-modal">
                    <label>PRODUCT NAME (TAMIL) <span onclick="autoTranslateName()" style="color:var(--dash-secondary); cursor:pointer; font-size: 0.6rem; margin-left:8px;"><i class="fas fa-sync-alt"></i> AUTO</span></label>
                    <input type="text" id="edit_name_ta" class="f-input-modal">
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-bottom: 2rem; padding: 1.5rem; background: rgba(0,0,0,0.2); border-radius: 24px; border: 1px solid rgba(255,255,255,0.03);">
                <div>
                    <label style="color:var(--dash-primary); font-size: 0.7rem; border-bottom: 1px solid rgba(99,102,241,0.2); padding-bottom: 8px; margin-bottom: 15px; display: block; letter-spacing: 2px;">RETAIL SETTINGS</label>
                    <div class="f-group-modal">
                        <label>RATE (TAX EXCL.)</label>
                        <div style="position: relative;">
                            <span style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #64748b;">₹</span>
                            <input type="number" step="0.01" id="edit_base_price" class="f-input-modal" style="padding-left:30px; font-size: 0.9rem;" oninput="calculateSpecificPrice('retail', 'base')">
                        </div>
                    </div>
                    <div class="f-group-modal" style="margin-bottom: 0;">
                        <label>FIXED PRICE (INCL.)</label>
                        <div class="price-hero-modal small">
                            <span style="font-size: 1.2rem;">₹</span>
                            <input type="number" step="0.01" id="edit_price" style="font-size: 1.8rem;" oninput="calculateSpecificPrice('retail', 'final')">
                        </div>
                    </div>
                </div>
                <div style="border-left: 1px solid rgba(255,255,255,0.05); padding-left: 2rem;">
                    <label style="color:#94a3b8; font-size: 0.7rem; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px; margin-bottom: 15px; display: block; letter-spacing: 2px;">WHOLESALE SETTINGS</label>
                    <div class="f-group-modal">
                        <label>RATE (TAX EXCL.)</label>
                        <div style="position: relative;">
                            <span style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #64748b;">₹</span>
                            <input type="number" step="0.01" id="edit_wholesale_base" class="f-input-modal" style="padding-left:30px; font-size: 0.9rem;" oninput="calculateSpecificPrice('wholesale', 'base')">
                        </div>
                    </div>
                    <div class="f-group-modal" style="margin-bottom: 0;">
                        <label>FIXED PRICE (INCL.)</label>
                        <div class="price-hero-modal small" style="border-color: rgba(255,255,255,0.1);">
                            <span style="font-size: 1.2rem; color: #94a3b8;">₹</span>
                            <input type="number" step="0.01" id="edit_wholesale_price" style="font-size: 1.8rem; color: #cbd5e1;" oninput="calculateSpecificPrice('wholesale', 'final')">
                        </div>
                    </div>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin-bottom: 2rem;">
                <div class="f-group-modal">
                    <label>GST TAX (%)</label>
                    <input type="number" step="0.01" id="edit_gst" class="f-input-modal" oninput="calculateBothPrices()">
                </div>
                <div class="f-group-modal">
                    <label>PURCHASE COST (₹)</label>
                    <input type="number" step="0.01" id="edit_last_cost" class="f-input-modal">
                </div>
                <div class="f-group-modal">
                    <label>LOW STOCK</label>
                    <input type="number" id="edit_reorder" class="f-input-modal">
                </div>
            </div>
            <div class="modal-footer-actions">
                <button type="button" class="btn-modal-action cancel" onclick="closeEditModal()">CANCEL</button>
                <button type="submit" class="btn-modal-action save">SAVE CHANGES</button>
            </div>
            <input type="hidden" id="edit_is_loose" value="false">
            <input type="hidden" id="edit_price_gram" value="0">
            <input type="hidden" id="edit_price_kg" value="0">
        </form>"""
    content = content[:form_start] + new_form + content[form_end:]

# 2. Update JS Functions
js_start = content.find('function openEditModal')
js_end = content.find('async function updateProductPrice')
if js_start != -1 and js_end != -1:
    # Find the end of updateProductPrice
    final_end = content.find('}', js_end)
    final_end = content.find('}', final_end + 1) # inner catch/try block... wait
    # Better: find the closing </script>
    script_end = content.find('</script>', js_start)
    
    new_js = """function openEditModal(btn) {
        const d = btn.dataset;
        const code = d.code;
        const name = d.name;
        const name_ta = d.nameTa;
        const price = parseFloat(d.price) || 0;
        const wholesale = parseFloat(d.wholesale) || 0;
        const gst = parseFloat(d.gst) || 5;
        const lastCost = parseFloat(d.lastCost) || 0;
        const reorder = parseInt(d.reorder) || 10;
        const isLoose = d.isLoose === 'true';

        document.getElementById('edit_code').value = code;
        document.getElementById('modal-product-name').innerText = `${name} [${code}]`;
        document.getElementById('edit_name').value = name;
        document.getElementById('edit_name_ta').value = name_ta || '';
        
        document.getElementById('edit_price').value = price.toFixed(2);
        document.getElementById('edit_wholesale_price').value = wholesale.toFixed(2);
        document.getElementById('edit_gst').value = gst;
        
        document.getElementById('edit_base_price').value = (price / (1 + (gst / 100))).toFixed(2);
        document.getElementById('edit_wholesale_base').value = (wholesale / (1 + (gst / 100))).toFixed(2);
        
        document.getElementById('edit_reorder').value = reorder;
        document.getElementById('edit_last_cost').value = lastCost;
        document.getElementById('edit_is_loose').value = isLoose ? 'true' : 'false';

        document.getElementById("editPriceModal").style.display = "flex";
    }

    function closeEditModal() { document.getElementById("editPriceModal").style.display = "none"; }

    function calculateSpecificPrice(mode, type) {
        const gst = parseFloat(document.getElementById('edit_gst').value) || 0;
        const baseId = mode === 'retail' ? 'edit_base_price' : 'edit_wholesale_base';
        const finalId = mode === 'retail' ? 'edit_price' : 'edit_wholesale_price';

        if (type === 'base') {
            const base = parseFloat(document.getElementById(baseId).value) || 0;
            document.getElementById(finalId).value = (base * (1 + (gst / 100))).toFixed(2);
        } else {
            const final = parseFloat(document.getElementById(finalId).value) || 0;
            document.getElementById(baseId).value = (final / (1 + (gst / 100))).toFixed(2);
        }
    }

    function calculateBothPrices() {
        calculateSpecificPrice('retail', 'base');
        calculateSpecificPrice('wholesale', 'base');
    }

    async function autoTranslateName() {
        const englishName = document.getElementById('edit_name').value;
        if (!englishName) return;
        try {
            const res = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ta&dt=t&q=${encodeURI(englishName)}`);
            const data = await res.json();
            if (data?.[0]?.[0]?.[0]) document.getElementById('edit_name_ta').value = data[0][0][0];
        } catch (e) { console.error("Translate error", e); }
    }

    async function updateProductPrice() {
        const code = document.getElementById('edit_code').value;
        const data = {
            name: document.getElementById('edit_name').value,
            name_ta: document.getElementById('edit_name_ta').value,
            is_loose: document.getElementById('edit_is_loose').value === 'true',
            price: parseFloat(document.getElementById('edit_price').value) || 0,
            wholesale_price: parseFloat(document.getElementById('edit_wholesale_price').value) || 0,
            reorder_level: parseInt(document.getElementById('edit_reorder').value) || 0,
            gst_percent: parseFloat(document.getElementById('edit_gst').value) || 0,
            last_cost: parseFloat(document.getElementById('edit_last_cost').value) || 0
        };

        try {
            const res = await fetch('/api/product/edit/' + code, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();
            if (result.success) location.reload();
            else alert('Update failed: ' + (result.error || 'Unknown error'));
        } catch (e) { alert('Cloud sync failure: ' + e.message); }
    }
"""
    content = content[:js_start] + new_js + content[script_end:]

# 3. Update Table Price Cell
cell_start = content.find('<td class="product-price-cell text-right">')
cell_end = content.find('</td>', cell_start) + 5
if cell_start != -1 and cell_end != -1:
    new_cell = """<td class="product-p-cell text-right">
                            <div class="product-p-group">
                                <span class="p-label-tag">RETAIL</span>
                                <div class="product-price-main">₹{{ "%.2f"|format(item.price) }}</div>
                            </div>
                            <div class="product-p-group" style="margin-top: 5px;">
                                <span class="p-label-tag wholesale">WHOLESALE</span>
                                <div class="product-price-main" style="color: #64748b;">₹{{ "%.2f"|format(item.wholesale_price or 0) }}</div>
                            </div>
                            <div class="product-price-sub">COST: ₹{{ "%.2f"|format(item.last_cost or 0) | replace('₹','') }} | GST: {{ item.gst_percent or 5 }}%</div>
                        </td>"""
    content = content[:cell_start] + new_cell + content[cell_end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
