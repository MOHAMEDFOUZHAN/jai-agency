import os
import sys
import json

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, r"d:\projects\Jai Agency")
from ocr_invoice_parser import extract_invoice_data_from_bytes

test_dir = r"d:\projects\Jai Agency\testing"
files = [f for f in os.listdir(test_dir) if f.lower().endswith(('.jpeg', '.jpg', '.png', '.pdf'))]

print(f"Found {len(files)} test invoice files in {test_dir}\n" + "="*80, flush=True)

results = {}

for idx, fname in enumerate(files, 1):
    fpath = os.path.join(test_dir, fname)
    print(f"\n[{idx}/{len(files)}] Testing: {fname}", flush=True)
    print("-" * 80, flush=True)
    
    with open(fpath, "rb") as f:
        file_bytes = f.read()
        
    res = extract_invoice_data_from_bytes(file_bytes)
    
    if not res.get("success"):
        print(f"FAILED: {res.get('error')}", flush=True)
        results[fname] = {"status": "FAILED", "error": res.get("error")}
        continue
        
    data = res.get("data", {})
    results[fname] = {
        "status": "SUCCESS",
        "vendor": data.get("vendor"),
        "invoice_no": data.get("invoice_no"),
        "date": data.get("date"),
        "seller_gst": data.get("gst_number"),
        "buyer_gst": data.get("buyer_gst"),
        "subtotal": data.get("subtotal"),
        "cash_discount": data.get("cash_discount"),
        "cgst": data.get("cgst_percent"),
        "sgst": data.get("sgst_percent"),
        "total_gst": data.get("total_gst"),
        "round_off": data.get("round_off"),
        "grand_total": data.get("grand_total"),
        "item_count": len(data.get("items", [])),
        "items": data.get("items", [])
    }
    
    print(f"  Supplier/Vendor : {data.get('vendor')}", flush=True)
    print(f"  Invoice No      : {data.get('invoice_no')}", flush=True)
    print(f"  Date            : {data.get('date')}", flush=True)
    print(f"  Seller GSTIN    : {data.get('gst_number')}", flush=True)
    print(f"  Buyer GSTIN     : {data.get('buyer_gst')}", flush=True)
    print(f"  Subtotal        : Rs. {data.get('subtotal')}", flush=True)
    print(f"  Cash Discount   : Rs. {data.get('cash_discount')}", flush=True)
    print(f"  CGST / SGST     : Rs. {data.get('cgst_percent')} / Rs. {data.get('sgst_percent')} (Total GST: Rs. {data.get('total_gst')})", flush=True)
    print(f"  Round Off       : Rs. {data.get('round_off')}", flush=True)
    print(f"  Grand Total     : Rs. {data.get('grand_total')}", flush=True)
    print(f"  Items Extracted : {len(data.get('items', []))}", flush=True)
    
    for i, it in enumerate(data.get("items", []), 1):
        print(f"    Item #{i:02d}: {it.get('name')[:35]:<35} | HSN: {it.get('hsn', ''):<8} | Qty: {it.get('quantity'):<5} {it.get('unit', ''):<4} | Rate: {it.get('unit_price'):<8} | Dis%: {it.get('discount_percent', 0):<4} | GST%: {it.get('gst_percent', 0):<3} | Amt: {it.get('amount')}", flush=True)

out_json = r"d:\projects\Jai Agency\testing\test_results.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n" + "="*80, flush=True)
print(f"Testing complete. Detailed JSON saved to {out_json}", flush=True)
