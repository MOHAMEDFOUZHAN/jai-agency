import re
import cv2
import numpy as np
from PIL import Image
import io
from datetime import datetime
import sys
import os
import traceback

# If running inside PyInstaller bundle, configure sys.path for RapidOCR
if getattr(sys, 'frozen', False):
    base_meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    rapid_dir = os.path.join(base_meipass, 'rapidocr_onnxruntime')
    if base_meipass not in sys.path:
        sys.path.insert(0, base_meipass)
    if rapid_dir not in sys.path:
        sys.path.insert(0, rapid_dir)

# Bind submodules in sys.modules so RapidOCR's dynamic imports find them
try:
    import rapidocr_onnxruntime.ch_ppocr_v3_det as _det
    import rapidocr_onnxruntime.ch_ppocr_v3_rec as _rec
    import rapidocr_onnxruntime.ch_ppocr_v2_cls as _cls
    sys.modules['ch_ppocr_v3_det'] = _det
    sys.modules['ch_ppocr_v3_rec'] = _rec
    sys.modules['ch_ppocr_v2_cls'] = _cls
except Exception as _sub_err:
    pass

_ocr_engine_instance = None
_ocr_init_error = None

def get_ocr_engine():
    global _ocr_engine_instance, _ocr_init_error
    if _ocr_engine_instance is not None:
        return _ocr_engine_instance
    try:
        if getattr(sys, 'frozen', False):
            base_meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            rapid_dir = os.path.join(base_meipass, 'rapidocr_onnxruntime')
            if base_meipass not in sys.path:
                sys.path.insert(0, base_meipass)
            if rapid_dir not in sys.path:
                sys.path.insert(0, rapid_dir)

        from rapidocr_onnxruntime import RapidOCR

        try:
            import rapidocr_onnxruntime.ch_ppocr_v3_det as _det
            import rapidocr_onnxruntime.ch_ppocr_v3_rec as _rec
            import rapidocr_onnxruntime.ch_ppocr_v2_cls as _cls
            sys.modules['ch_ppocr_v3_det'] = _det
            sys.modules['ch_ppocr_v3_rec'] = _rec
            sys.modules['ch_ppocr_v2_cls'] = _cls
        except Exception:
            pass

        _ocr_engine_instance = RapidOCR()
        _ocr_init_error = None
        return _ocr_engine_instance
    except Exception as e:
        _ocr_init_error = traceback.format_exc()
        print(f"RapidOCR initialization failed: {_ocr_init_error}")
        return None

ocr_engine = get_ocr_engine()

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

GST_REGEX = r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b"

def preprocess_pages(file_bytes: bytes) -> list:
    """Preprocess uploaded image or PDF bytes into a list of optimized grayscale images (one per page)."""
    pages = []
    if file_bytes.startswith(b"%PDF") and pdfium:
        try:
            pdf = pdfium.PdfDocument(file_bytes)
            for page in pdf:
                pil_img = page.render(scale=2).to_pil()
                rgb_arr = np.array(pil_img)
                gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)
                h, w = gray.shape
                if w < 1600:
                    scale = 1800.0 / w
                    gray = cv2.resize(gray, (1800, int(h * scale)), interpolation=cv2.INTER_CUBIC)
                elif w > 2400:
                    scale = 2000.0 / w
                    gray = cv2.resize(gray, (2000, int(h * scale)), interpolation=cv2.INTER_AREA)
                pages.append(gray)
            if pages:
                return pages
        except Exception as e:
            print(f"PDF rendering error: {e}")

    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image or PDF.")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    if w < 1600:
        scale = 1800.0 / w
        gray = cv2.resize(gray, (1800, int(h * scale)), interpolation=cv2.INTER_CUBIC)
    elif w > 2400:
        scale = 2000.0 / w
        gray = cv2.resize(gray, (2000, int(h * scale)), interpolation=cv2.INTER_AREA)

    return [gray]

def preprocess_bytes(file_bytes: bytes) -> np.ndarray:
    """Backward-compatible single image preprocess function."""
    pages = preprocess_pages(file_bytes)
    return pages[0] if pages else np.array([])

def auto_orient_image(gray_img: np.ndarray, engine) -> tuple:
    """Check if image is rotated (e.g. 90 deg sideways mobile photo) and auto-correct to upright."""
    results, _ = engine(gray_img)
    if not results:
        return gray_img, results

    h_count, v_count = 0, 0
    kws = ['invoice', 'tax', 'gst', 'total', 'date', 'rate', 'qty', 'amount', 'hsn', 'mrp', 'buyer', 'goods', 'snc', 'sno']
    for r in results:
        box, text, score = r
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw > bh * 1.2:
            h_count += 1
        elif bh > bw * 1.2:
            v_count += 1

    # If mostly vertical text boxes, test CCW (270 CW) and CW (90 CW) rotations
    if v_count > h_count * 1.3:
        img_ccw = cv2.rotate(gray_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        res_ccw, _ = engine(img_ccw)
        img_cw = cv2.rotate(gray_img, cv2.ROTATE_90_CLOCKWISE)
        res_cw, _ = engine(img_cw)

        score_ccw = sum(1 for r in (res_ccw or []) if any(k in r[1].lower() for k in kws))
        score_cw = sum(1 for r in (res_cw or []) if any(k in r[1].lower() for k in kws))

        if score_ccw >= score_cw and res_ccw:
            return img_ccw, res_ccw
        elif res_cw:
            return img_cw, res_cw

    return gray_img, results

def parse_date(raw_str: str) -> str:
    """Normalize date strings like '4-Aug-26', '28/08/2026', '27/09/2025', '2-8ep-26', '2026-08-04' to YYYY-MM-DD."""
    if not raw_str:
        return ""
    cleaned = str(raw_str).strip().replace(",", " ").replace(".", "-").replace("/", "-")
    cleaned = re.sub(r"^(dated|date|on|dt)[:\s\.]*", "", cleaned, flags=re.IGNORECASE).strip()
    
    cleaned = re.sub(r"\b8ep\b", "Sep", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b8ept\b", "Sept", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b0ct\b", "Oct", cleaned, flags=re.IGNORECASE)
    
    m = re.search(r"\b(\d{1,2})[-/\s]([A-Za-z]{3,9}|\d{1,2})[-/\s](\d{2,4})\b", cleaned)
    if m:
        cleaned = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    
    formats = [
        "%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y",
        "%d-%m-%Y", "%d-%m-%y",
        "%Y-%m-%d", "%Y-%b-%d",
        "%d %b %Y", "%d %b %y", "%d %B %Y", "%d %B %y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

def clean_amount(val_str: str) -> float:
    """Extract float amount from formatted string like '2,59,350.00', '1,455', '-.21', or '₹ 2,72,317.50'."""
    if not val_str:
        return 0.0
    cleaned = str(val_str).replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    
    # Handle multiple periods
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        if len(parts[-1]) in [2, 3]:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)
            
    cleaned = cleaned.replace(",", "")
    match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)", cleaned)
    if match:
        try:
            val = float(match.group(0))
            return val
        except ValueError:
            return 0.0
    return 0.0

REJECT_PATTERNS = [
    r"^state\s*name", r"tamil\s*nadu", r"code\s*:\s*\d+", r"gstin", r"uin\b",
    r"consignee", r"ship\s*to", r"buyer", r"bill\s*to", r"invoice\s*no",
    r"motor\s*vehicle", r"terms\s*of\s*delivery", r"reference\s*no", r"e-way",
    r"contact\s*:", r"e-mail", r"bank\s*name", r"kotak", r"declaration",
    r"verified\s*by", r"prepared\s*by", r"customer", r"subject\s*to",
    r"tax\s*invoice", r"e-invoice", r"ack\s*no", r"ack\s*date", r"irn",
    r"description\s*of\s*goods", r"hsn\s*/?\s*sac", r"amount\s*chargeable",
    r"consolidated\s*hsn", r"lot\s*no", r"pkd\.\s*date", r"authorised\s*signatory",
    r"jurisdiction", r"account\s*no", r"ifsc", r"total\s*weight", r"sub\s*-\s*total"
]

def clean_product_name(raw_name: str) -> str:
    """Clean product name from OCR noise, row numbers, and trailing packaging notes."""
    if not raw_name:
        return ""
    name = str(raw_name).strip()
    
    # Remove non-ascii characters (like stroke/checkmark \u4eba)
    name = re.sub(r'[^\x00-\x7F]+', ' ', name).strip()

    # Strip leading serial numbers or OCR artifacts like "1 ", "2", "3", "N", "J", "A", "5", "10"
    name = re.sub(r"^(?:[0-9]{1,2}|[NJAB])[\.\s\)\-]*(?=[A-Za-z])", "", name)
    
    # Specific invoice brand/product names
    name = re.sub(r"CPCREAMY", "CP CREAMY ", name, flags=re.IGNORECASE)
    name = re.sub(r"CPPBRF", "CP PB RF ", name, flags=re.IGNORECASE)
    name = re.sub(r"CHOCOSACHET", "CHOCO SACHET ", name, flags=re.IGNORECASE)
    name = re.sub(r"GDPLAIN", "GD PLAIN ", name, flags=re.IGNORECASE)
    name = re.sub(r"NONOFF", "NON OFF", name, flags=re.IGNORECASE)
    name = re.sub(r"CLS500M", "CLS 500M ", name, flags=re.IGNORECASE)
    name = re.sub(r"CLS500RF", "CLS 500RF ", name, flags=re.IGNORECASE)
    name = re.sub(r"CLS50ORF", "CLS 500RF ", name, flags=re.IGNORECASE)
    name = re.sub(r"RFL\+TFN", "RFL+TFN ", name, flags=re.IGNORECASE)
    name = re.sub(r"RF500G", "RF 500G ", name, flags=re.IGNORECASE)

    # Specific common invoice OCR fixes
    name = re.sub(r"\b(?:Ol|Oil|Oill|O1l)\s*Paper\s*(?:Nloe|Nice)\b", "Oil Paper Nice", name, flags=re.IGNORECASE)
    name = re.sub(r"\bHand\s*Gloves[\s\-_]*(?:26Pos|26Pcs|26Pes|26)\b", "Hand Gloves - 26 Pcs", name, flags=re.IGNORECASE)
    name = re.sub(r"\bSUN\s*1000\s*ML\b", "SUN 1000ML", name, flags=re.IGNORECASE)
    name = re.sub(r"\bSUN1000ML\b", "SUN 1000ML", name, flags=re.IGNORECASE)
    name = re.sub(r"\bSP2C\b", "SP 2C", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(?:Pot|Pet)\s*Jar\b", "Pet Jar", name, flags=re.IGNORECASE)
    name = re.sub(r"Rippletumb[a-z]*", "Ripple Tumbler", name, flags=re.IGNORECASE)
    name = re.sub(r"\bKosherKingNapkin\b", "Kosher King Napkin", name, flags=re.IGNORECASE)
    name = re.sub(r"\bColloTape\b", "Cello Tape", name, flags=re.IGNORECASE)
    name = re.sub(r"\bCollo\s*Tape\b", "Cello Tape", name, flags=re.IGNORECASE)
    name = re.sub(r"\bCollo\b", "Cello", name, flags=re.IGNORECASE)
    name = re.sub(r"\bCelloTape\b", "Cello Tape", name, flags=re.IGNORECASE)
    name = re.sub(r"\bPaperstra\s*W\b", "Paper straw", name, flags=re.IGNORECASE)
    name = re.sub(r"\bPaperstraw\b", "Paper straw", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLDCOVER\b", "LD COVER ", name, flags=re.IGNORECASE)
    name = re.sub(r"\bDR250ML\b", "DR 250ML ", name, flags=re.IGNORECASE)
    name = re.sub(r"\bDR250MLTumbler\b", "DR 250ML Tumbler", name, flags=re.IGNORECASE)
    name = re.sub(r"\bWOODENSPOONSMALL\b", "WOODEN SPOON SMALL", name, flags=re.IGNORECASE)
    name = re.sub(r"\bST\.POUCHBROWN\b", "ST. POUCH BROWN", name, flags=re.IGNORECASE)

    # Strip trailing box/package counts like '- 20Box Varkey', '- 5', '- 1 Box', '/Box'
    name = re.sub(r'[-–]\s*\d*o?\s*(?:Box|Bo|Bk|B0|Bag|Ray|NO|Nos|Roll|Pkt|IBCX|15n|1gn|IBA1|Qx|Qix|Ra|Res|Bey|Bhewhtrny|Boy|Voskey|Vokey|Varkey).*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[-+~|]+(?:Ra|Res|Qx|Qix|15n|1gn|B0|Bk|4B0|IBA1|IBCX|Boy|2o)?$', '', name)
    name = re.sub(r'[-–/]\s*\d+o?$', '', name)
    name = re.sub(r'[-–]\s*/?Box$', '', name, flags=re.IGNORECASE)

    # Insert spaces between lowercase and uppercase if merged
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = re.sub(r"(\d+ML)\s*\(", r"\1 (", name)
    name = re.sub(r"(\d+ML)", r" \1", name)
    name = re.sub(r"(\d+MM)", r" \1", name)
    name = re.sub(r"(\d+GM)", r" \1", name)
    name = re.sub(r"(\d+RS)", r" \1", name)

    # Clean multiple spaces / punctuation artifacts at ends
    name = re.sub(r"[~|]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name.strip(' -/|+')

def find_optimal_skew_slope(tokens: list, header_y: float, totals_y: float) -> float:
    """Find table skew slope automatically by minimizing within-row Y variance."""
    table_tokens = [t for t in tokens if (header_y - 10) <= t["y"] <= (totals_y + 15)]
    if len(table_tokens) < 10:
        return 0.0

    best_slope = 0.0
    min_score = float('inf')

    # Test candidate slopes from -0.10 to +0.10 (approx +/- 6 degrees)
    for slope in np.linspace(-0.10, 0.10, 81):
        y_adjs = sorted([t["y"] - slope * t["x"] for t in table_tokens])
        diffs = np.diff(y_adjs)
        within_row_gaps = diffs[diffs < 6.0]
        if len(within_row_gaps) > 0:
            variance_score = float(np.mean(within_row_gaps ** 2))
            if variance_score < min_score:
                min_score = variance_score
                best_slope = float(slope)

    return round(best_slope, 4)

def extract_invoice_data_from_bytes(file_bytes: bytes) -> dict:
    """Run OCR and robust multi-page layout extraction to parse Indian GST invoices."""
    engine = get_ocr_engine()
    if engine is None:
        err_msg = _ocr_init_error or "OCR engine failed to initialize"
        return {"success": False, "error": f"OCR Error: {err_msg}"}
    
    pages = preprocess_pages(file_bytes)
    if not pages:
        return {"success": False, "error": "No pages could be extracted from invoice."}

    all_raw_texts = []
    all_items = []
    
    seller_gst = ""
    buyer_gst = ""
    vendor_name = ""
    invoice_no = ""
    invoice_date = ""

    global_subtotal = 0.0
    global_cgst = 0.0
    global_sgst = 0.0
    global_igst = 0.0
    global_grand_total = 0.0
    global_round_off = 0.0

    saved_col_centers = {}

    for page_idx, gray_img in enumerate(pages):
        oriented_img, results = auto_orient_image(gray_img, engine)
        if not results:
            continue

        h, w = oriented_img.shape[:2]
        tokens = []
        for item in results:
            box = item[0]
            text = str(item[1]).strip()
            score = float(item[2])
            if text:
                avg_y = sum(pt[1] for pt in box) / 4.0
                avg_x = sum(pt[0] for pt in box) / 4.0
                tokens.append({
                    "text": text,
                    "x": (avg_x / w) * 1000.0,
                    "y": (avg_y / h) * 1000.0,
                    "score": score
                })

        tokens.sort(key=lambda t: (t["y"], t["x"]))
        page_texts = [t["text"] for t in tokens]
        all_raw_texts.extend(page_texts)
        full_page_text = "\n".join(page_texts)

        # -------------------------------------------------------------
        # 1. GST Numbers (Seller vs Buyer)
        # -------------------------------------------------------------
        all_gsts = re.findall(GST_REGEX, full_page_text, re.IGNORECASE)
        for t in tokens:
            m = re.search(GST_REGEX, t["text"], re.IGNORECASE)
            if m:
                gst_val = m.group(0).upper()
                near_buyer = False
                for other in tokens:
                    if abs(other["y"] - t["y"]) < 80 and abs(other["x"] - t["x"]) < 300:
                        ol = other["text"].lower()
                        if any(k in ol for k in ["to", "buyer", "consignee", "jai agencies", "bill to"]):
                            near_buyer = True
                            break
                if near_buyer and not buyer_gst:
                    buyer_gst = gst_val
                elif not seller_gst and not near_buyer:
                    seller_gst = gst_val

        if not seller_gst and all_gsts:
            seller_gst = all_gsts[0].upper()
        if not buyer_gst and len(all_gsts) > 1:
            buyer_gst = all_gsts[1].upper() if all_gsts[1].upper() != seller_gst else ""

        # -------------------------------------------------------------
        # 2. Vendor / Seller Name (Page 1 or when found)
        # -------------------------------------------------------------
        if not vendor_name:
            for t in tokens:
                txt = t["text"]
                m = re.search(r"A[o/c]?\s*Holder['’]?s\s*Name\s*:\s*([A-Za-z0-9\s&]+)", txt, re.IGNORECASE)
                if m and len(m.group(1).strip()) > 2:
                    vendor_name = m.group(1).strip()
                    vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", vendor_name)
                    break
                m2 = re.search(r"for\s+([A-Za-z0-9\s&]+)", txt, re.IGNORECASE)
                if m2:
                    cand = m2.group(1).strip()
                    if len(cand) > 3 and not any(kw in cand.lower() for kw in ["consignee", "buyer", "authorised", "signature", "recipient"]):
                        vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", cand)
                        break

            if not vendor_name:
                ignore_kws = [
                    "taxinvoice", "invoice", "gstin", "statename", "eway", "delivery", "dated", "original",
                    "billno", "irn", "ack", "ackno", "ackdate", "adk", "adkno", "ak", "akno", "akdate",
                    "recipient", "efnvolce", "einvoice", "contact", "email", "modeterms", "otherreferences",
                    "fssai", "phno", "originalfor"
                ]
                for t in tokens:
                    if t["y"] < 350 and t["x"] < 700:
                        raw_t = t["text"].strip()
                        tl_clean = re.sub(r"[^a-z0-9]", "", raw_t.lower())
                        if "consignee" in tl_clean or "buyer" in tl_clean:
                            break
                        if any(kw in tl_clean for kw in ignore_kws):
                            continue
                        if parse_date(raw_t):
                            continue
                        if len(raw_t) > 3 and not re.search(GST_REGEX, raw_t):
                            if re.search(r"[0-9a-zA-Z]{16,}", raw_t) or re.match(r"^[:0-9a-fA-F\s\-]{12,}$", raw_t):
                                continue
                            if not re.match(r"^[\d\/\#\-\s,:\.]+$", raw_t) and not re.match(r"^(MP|No|Plot|Door|Flat)\s*\d+", raw_t, re.IGNORECASE):
                                cleaned = re.sub(r"^(M\/[Ss]|Messrs\.?|M\/s\.?)\s*", "", raw_t, flags=re.IGNORECASE).strip()
                                cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
                                if len(cleaned) > 2 and any(c.isalpha() for c in cleaned):
                                    vendor_name = cleaned
                                    break

            if vendor_name:
                vendor_name = re.sub(r"VIGNESHAGENCIES", "VIGNESH AGENCIES", vendor_name, flags=re.IGNORECASE)
                vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", vendor_name).strip()

        # -------------------------------------------------------------
        # 3. Invoice Number & Date
        # -------------------------------------------------------------
        if not invoice_no:
            for t in tokens:
                txt = t["text"]
                if re.search(r"\b(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\b", txt, re.IGNORECASE) and not re.search(r"e-Way", txt, re.IGNORECASE):
                    m = re.search(r"\b(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]+([A-Za-z0-9\/\-,]+)", txt, re.IGNORECASE)
                    if m:
                        cand = m.group(1).strip().replace(",", "")
                        cand = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", cand, flags=re.IGNORECASE).strip()
                        if cand and not cand.lower() in ["e-way", "dated", "no", "date", "details", "tax", "invoice", "original", "buyer"]:
                            cand = re.sub(r"\s*(?:dt|dated|date).*$", "", cand, flags=re.IGNORECASE)
                            invoice_no = cand.strip()
                            break
                    for near in tokens:
                        if (5 < (near["y"] - t["y"]) < 60 and abs(near["x"] - t["x"]) < 120) or (abs(near["y"] - t["y"]) < 20 and 0 < (near["x"] - t["x"]) < 150):
                            cand = near["text"].strip().replace(",", "")
                            cand = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", cand, flags=re.IGNORECASE).strip()
                            if cand and not any(kw in cand.lower() for kw in ["e-way", "dated", "delivery", "invoice", "date", "reference", "ack", "irn"]):
                                invoice_no = cand
                                break
                    if invoice_no:
                        break

            if not invoice_no:
                for t in tokens:
                    m = re.search(r"(\d+)\s+dt\.?\s*\d+", t["text"], re.IGNORECASE)
                    if m:
                        invoice_no = m.group(1).strip()
                        break

            if not invoice_no:
                m = re.search(r"\b(INV[\-\/][A-Za-z0-9\-\/]+|\d{4,8})\b", full_page_text, re.IGNORECASE)
                if m and m.group(1) not in ["2024", "2025", "2026", "2027"]:
                    invoice_no = m.group(1)

            if invoice_no:
                invoice_no = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", invoice_no, flags=re.IGNORECASE).strip()

        if not invoice_date:
            for t in tokens:
                txt = t["text"]
                if re.search(r"\b(dated|date|dt)\b", txt, re.IGNORECASE) and not re.search(r"ack\s*date", txt, re.IGNORECASE):
                    d = parse_date(txt)
                    if d:
                        invoice_date = d
                        break
                    for near in tokens:
                        if abs(near["y"] - t["y"]) < 30 and abs(near["x"] - t["x"]) < 200:
                            d = parse_date(near["text"])
                            if d:
                                invoice_date = d
                                break
                    if invoice_date:
                        break

            if not invoice_date:
                for t in tokens:
                    if not re.search(r"ack\s*date", t["text"], re.IGNORECASE):
                        d = parse_date(t["text"])
                        if d:
                            invoice_date = d
                            break

        # -------------------------------------------------------------
        # 4. Detect Side-by-Side Slip Layouts (e.g., Sadhika Enterprises)
        # -------------------------------------------------------------
        max_table_x = 1000.0
        # Check if header tokens repeat on left (<650) and right (>650)
        has_left_header = any(t["x"] < 650 and any(k in t["text"].lower() for k in ["product", "description", "particular", "s.n", "sn"]) for t in tokens if 180 <= t["y"] <= 450)
        has_right_header = any(t["x"] > 650 and any(k in t["text"].lower() for k in ["product", "mrp", "s.n", "sn"]) for t in tokens if 180 <= t["y"] <= 450)
        if has_left_header and has_right_header:
            max_table_x = 660.0

        # Filter tokens for table extraction on this page
        table_search_tokens = [t for t in tokens if t["x"] <= max_table_x]

        # -------------------------------------------------------------
        # 5. Table Header & Totals Detection
        # -------------------------------------------------------------
        header_tokens = []
        col_centers = {}
        for t in table_search_tokens:
            tl = t["text"].lower().strip()
            if 150 <= t["y"] <= 600:
                if any(k in tl for k in ["descript", "particular", "goods", "product"]) and t["x"] < 450:
                    header_tokens.append(t)
                    col_centers["desc"] = t["x"]
                elif tl in ["hsn", "hsn/sac", "hsnisac", "sac"] or (("hsn" in tl or "sac" in tl) and (250 <= t["x"] < 560)):
                    header_tokens.append(t)
                    col_centers["hsn"] = t["x"]
                elif tl == "mrp" or ("mrp" in tl and (350 <= t["x"] < 520)):
                    header_tokens.append(t)
                    col_centers["mrp"] = t["x"]
                elif tl in ["case", "pkg", "pkgs", "uom"] or ("case" in tl and (420 <= t["x"] < 580)):
                    header_tokens.append(t)
                    col_centers["case"] = t["x"]
                elif any(k in tl for k in ["quantity", "qty"]) and (250 <= t["x"] < 700):
                    header_tokens.append(t)
                    col_centers["qty"] = t["x"]
                elif ("rate" in tl or "price" in tl) and (380 <= t["x"] < 800):
                    header_tokens.append(t)
                    col_centers["rate"] = t["x"]
                elif ("disamt" in tl or "discount" in tl or tl == "dis" or "dis%" in tl) and (420 <= t["x"] < 820):
                    header_tokens.append(t)
                    col_centers["dis"] = t["x"]
                elif any(k in tl for k in ["tax%", "gst%", "lax%", "rax%", "ax%", "tax %", "gst rate", "tax rate"]) and (500 <= t["x"] < 880):
                    header_tokens.append(t)
                    col_centers["tax_pct"] = t["x"]
                elif ("amount" in tl or tl == "amount" or tl == "total" or "taxable" in tl) and t["x"] >= 550:
                    header_tokens.append(t)
                    col_centers["amount"] = t["x"]

        if header_tokens:
            header_y = float(np.median([t["y"] for t in header_tokens]))
            saved_col_centers = col_centers
        else:
            header_y = 350.0 if page_idx == 0 else 180.0
            col_centers = saved_col_centers

        totals_start_y = 950.0
        for t in table_search_tokens:
            tl = t["text"].lower()
            if any(k in tl for k in ["cgst", "sgst", "igst", "rounded off", "round off", "r.o.d", "grand total", "bill amount", "rupees", "amount chargeable", "total amount before tax"]) and t["y"] > (header_y + 20):
                if t["y"] < totals_start_y:
                    totals_start_y = t["y"]

        skew_slope = find_optimal_skew_slope(table_search_tokens, header_y, totals_start_y)
        
        for t in tokens:
            t["y_adj"] = t["y"] - skew_slope * t["x"]

        header_y_adj = header_y - skew_slope * 200.0
        totals_start_y_adj = totals_start_y - skew_slope * 500.0

        # -------------------------------------------------------------
        # 6. Extract Line Items on this Page
        # -------------------------------------------------------------
        item_tokens = [t for t in tokens if t["x"] <= max_table_x and (header_y_adj + 8) <= t["y_adj"] < (totals_start_y_adj - 10)]
        
        # Check if page is a pure batch/lot table without rates (e.g., SGR Foods Page 2/3 Lot No table)
        is_batch_table = any("lot no" in t["text"].lower() or "pkd. date" in t["text"].lower() for t in tokens if t["y"] < 400)
        is_consolidated_hsn = any("consolidated hsn" in t["text"].lower() or "e-way bill generation" in t["text"].lower() for t in tokens if t["y"] < 600)

        if not is_batch_table and not is_consolidated_hsn:
            rows = []
            curr_row = []
            for t in sorted(item_tokens, key=lambda x: x["y_adj"]):
                if not curr_row:
                    curr_row.append(t)
                elif abs(t["y_adj"] - sum(x["y_adj"] for x in curr_row) / len(curr_row)) <= 8.5:
                    curr_row.append(t)
                else:
                    rows.append(curr_row)
                    curr_row = [t]
            if curr_row:
                rows.append(curr_row)

            for row in rows:
                row_sorted = sorted(row, key=lambda x: x["x"])
                desc_parts = []
                hsn_code = ""
                gst_pct = 0.0
                qty = 0.0
                unit = "Nos"
                rate = 0.0
                discount = 0.0
                mrp = 0.0
                amount = 0.0

                for t in row_sorted:
                    x = t["x"]
                    txt = t["text"].strip()
                    tl = txt.lower()

                    if col_centers:
                        dists = {col: abs(x - cx) for col, cx in col_centers.items()}
                        closest_col = min(dists, key=dists.get)

                        if closest_col == "desc":
                            desc_parts.append(txt)
                        elif closest_col == "hsn":
                            m = re.search(r"\d{4,8}", txt)
                            if m:
                                hsn_code = m.group(0)
                            elif any(c.isalpha() for c in txt):
                                desc_parts.append(txt)
                        elif closest_col == "mrp":
                            mrp = clean_amount(txt)
                        elif closest_col == "case":
                            if "ctn" in tl: unit = "CTN"
                            elif "box" in tl: unit = "Box"
                        elif closest_col == "qty":
                            q_val = clean_amount(txt)
                            if q_val > 0:
                                qty = q_val
                            if "pkt" in tl or "pack" in tl: unit = "Pkt"
                            elif "kg" in tl: unit = "Kg"
                            elif "ltr" in tl or "litre" in tl: unit = "Ltr"
                            elif "roll" in tl: unit = "Roll"
                            elif "box" in tl: unit = "Box"
                            elif "ctn" in tl: unit = "CTN"
                            elif "nos" in tl: unit = "Nos"
                        elif closest_col == "rate":
                            r_val = clean_amount(txt)
                            if r_val > 0:
                                rate = r_val
                        elif closest_col == "dis":
                            d_val = clean_amount(txt)
                            if d_val > 0:
                                discount = d_val
                        elif closest_col == "tax_pct":
                            pct_m = re.search(r"(\d+(?:\.\d+)?)", txt)
                            if pct_m:
                                gst_pct = float(pct_m.group(1))
                        elif closest_col == "amount":
                            a_val = clean_amount(txt)
                            if a_val > 0:
                                amount = a_val
                    else:
                        if x < 350:
                            desc_parts.append(txt)
                        elif 350 <= x < 450:
                            hsn_m = re.search(r"\d{4,8}", txt)
                            if hsn_m:
                                hsn_code = hsn_m.group(0)
                            elif any(c.isalpha() for c in txt):
                                desc_parts.append(txt)
                        elif 450 <= x < 550:
                            q_val = clean_amount(txt)
                            if q_val > 0:
                                qty = q_val
                        elif 550 <= x < 750:
                            r_val = clean_amount(txt)
                            if r_val > 0:
                                rate = r_val
                        elif x >= 750:
                            amount = clean_amount(txt)

                raw_desc = " ".join(desc_parts).strip()
                if any(re.search(pat, raw_desc, re.IGNORECASE) for pat in REJECT_PATTERNS):
                    continue

                cleaned_desc = clean_product_name(raw_desc)
                if any(re.search(pat, cleaned_desc, re.IGNORECASE) for pat in REJECT_PATTERNS):
                    continue

                if not cleaned_desc and hsn_code:
                    cleaned_desc = f"Item {hsn_code}"

                if (amount > 0 or qty > 0) and (cleaned_desc or hsn_code):
                    final_unit_price = rate if rate > 0 else (round(amount / qty, 3) if qty else 0.0)
                    gross_item = qty * final_unit_price
                    disc_pct = 0.0
                    if discount > 0 and gross_item > 0:
                        disc_pct = round((discount / gross_item) * 100, 2)

                    all_items.append({
                        "name": cleaned_desc,
                        "hsn": hsn_code,
                        "quantity": qty,
                        "unit": unit,
                        "unit_price": final_unit_price,
                        "discount": discount,
                        "discount_percent": disc_pct,
                        "mrp": mrp,
                        "amount": amount,
                        "igst_percent": 0.0,
                        "gst_percent": gst_pct
                    })

        # -------------------------------------------------------------
        # 7. Financial Totals (Page or Global)
        # -------------------------------------------------------------
        totals_tokens = [t for t in tokens if t["y_adj"] >= (totals_start_y_adj - 30)]

        for t in totals_tokens:
            tl = t["text"].lower()
            if "cgst" in tl and "total" not in tl:
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 20:
                        val = clean_amount(near["text"])
                        if val > 0:
                            global_cgst = max(global_cgst, val)
                            break
            elif "sgst" in tl and "total" not in tl:
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 20:
                        val = clean_amount(near["text"])
                        if val > 0:
                            global_sgst = max(global_sgst, val)
                            break
            elif "igst" in tl and "total" not in tl:
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 20:
                        val = clean_amount(near["text"])
                        if val > 0:
                            global_igst = max(global_igst, val)
                            break
            elif "round" in tl or "r.o.d" in tl:
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 20:
                        val = clean_amount(near["text"])
                        if abs(val) >= 5 and "." not in near["text"]:
                            val = val / 100.0
                        if val != 0.0:
                            global_round_off = val
                        break
            elif any(k in tl for k in ["bill amount", "total amount after tax", "grand total", "invoice total", "amount chargeable"]):
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 25:
                        val = clean_amount(near["text"])
                        if val > global_grand_total:
                            global_grand_total = val

            elif any(k in tl for k in ["sub total", "total amount before tax"]):
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 25:
                        val = clean_amount(near["text"])
                        if val > global_subtotal:
                            global_subtotal = val

    if not invoice_date:
        invoice_date = datetime.now().strftime("%Y-%m-%d")

    total_gst = global_cgst + global_sgst

    if global_subtotal == 0.0 and all_items:
        global_subtotal = sum(it["amount"] for it in all_items)

    if global_grand_total == 0.0 and global_subtotal > 0:
        global_grand_total = global_subtotal + total_gst + global_igst + global_round_off

    return {
        "success": True,
        "data": {
            "invoice_no": invoice_no,
            "date": invoice_date,
            "vendor": vendor_name,
            "gst_number": seller_gst,
            "buyer_gst": buyer_gst,
            "subtotal": f"{global_subtotal:.2f}",
            "cgst_percent": f"{global_cgst:.2f}",
            "sgst_percent": f"{global_sgst:.2f}",
            "total_gst": f"{total_gst:.2f}",
            "total_igst": f"{global_igst:.2f}",
            "round_off": f"{global_round_off:.2f}",
            "grand_total": f"{global_grand_total:.2f}",
            "items": all_items,
            "raw_lines": all_raw_texts
        }
    }
