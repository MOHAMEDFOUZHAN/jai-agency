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
                max_dim = max(h, w)
                if max_dim > 1800:
                    scale = 1800.0 / max_dim
                    gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                elif max_dim < 1100:
                    scale = 1400.0 / max_dim
                    gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
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

    max_dim = max(h, w)
    if max_dim > 1800:
        scale = 1800.0 / max_dim
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    elif max_dim < 1100:
        scale = 1400.0 / max_dim
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    return [gray]

def preprocess_bytes(file_bytes: bytes) -> np.ndarray:
    """Backward-compatible single image preprocess function."""
    pages = preprocess_pages(file_bytes)
    return pages[0] if pages else np.array([])

def auto_orient_image(gray_img: np.ndarray, engine) -> tuple:
    """Check if image is rotated (e.g. 90 deg sideways mobile photo or upside-down) and auto-correct to upright."""
    results, _ = engine(gray_img)
    if not results:
        return gray_img, results

    h, w = gray_img.shape[:2]

    def score_orientation(res_list, img_h):
        if not res_list:
            return -999
        score = 0
        head_kws = ["tax invoice", "taxinvoice", "invoice no", "inv no", "bill no", "dated", "supplier", "e-invoice", "irn"]
        foot_kws = ["total", "sub total", "subtotal", "signatory", "signature", "seal", "round off", "roundoff", "receiver", "amount in words"]
        for r in res_list:
            txt = str(r[1]).lower()
            box_y = sum(pt[1] for pt in r[0]) / (4.0 * max(img_h, 1))
            for kw in head_kws:
                if kw in txt:
                    score += 3 if box_y < 0.45 else -3
            for kw in foot_kws:
                if kw in txt:
                    score += 3 if box_y > 0.55 else -3
        return score

    h_count, v_count = 0, 0
    for r in results:
        box = r[0]
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw > bh * 1.2:
            h_count += 1
        elif bh > bw * 1.2:
            v_count += 1

    curr_score = score_orientation(results, h)

    # 1. If mostly vertical text boxes (landscape photo of portrait invoice), test CW (90 deg) and CCW (270 deg)
    if v_count > h_count * 1.3:
        img_cw = cv2.rotate(gray_img, cv2.ROTATE_90_CLOCKWISE)
        res_cw, _ = engine(img_cw)
        score_cw = score_orientation(res_cw, img_cw.shape[0])

        img_ccw = cv2.rotate(gray_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        res_ccw, _ = engine(img_ccw)
        score_ccw = score_orientation(res_ccw, img_ccw.shape[0])

        if score_cw >= score_ccw and score_cw > curr_score:
            return img_cw, res_cw
        elif score_ccw > curr_score:
            return img_ccw, res_ccw

    # 2. If horizontal text but upside down (negative score), test 180 rotation
    elif curr_score < 0:
        img_180 = cv2.rotate(gray_img, cv2.ROTATE_180)
        res_180, _ = engine(img_180)
        score_180 = score_orientation(res_180, h)
        if score_180 > curr_score:
            return img_180, res_180

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
    cleaned = cleaned.replace("(-)", "-").replace("(", "").replace(")", "").strip()
    
    # Handle multiple periods
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        if len(parts[-1]) in [2, 3]:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)
            
    # Handle missing decimal point in Indian thousands format, e.g. "1,01116" -> "1,011.16"
    if "." not in cleaned:
        m_comma5 = re.search(r"(\d{1,3},\d{3})(\d{2})\b", cleaned)
        if m_comma5:
            cleaned = cleaned.replace(m_comma5.group(0), m_comma5.group(1) + "." + m_comma5.group(2))

    cleaned = cleaned.replace(",", "")
    match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)", cleaned)
    if match:
        try:
            val = float(match.group(0))
            return val
        except ValueError:
            return 0.0
    return 0.0

def reconcile_item_math(qty: float, rate: float, amount: float) -> tuple:
    """
    Deterministically validate and cross-check Qty, Rate, and Amount using Qty * Rate = Amount.
    Recovers missing decimal points in rate (e.g. 15398 -> 153.98, 72986 -> 729.86) or amount.
    """
    # 1. If qty is missing/zero but rate and amount exist
    if (qty <= 0.0 or qty is None) and rate > 0 and amount > 0:
        qty = round(amount / rate, 2)
        return qty, rate, amount

    # 2. If rate is missing/zero but qty and amount exist
    if (rate <= 0.0 or rate is None) and qty > 0 and amount > 0:
        rate = round(amount / qty, 2)
        return qty, rate, amount

    # 3. If amount is missing/zero but qty and rate exist
    if (amount <= 0.0 or amount is None) and qty > 0 and rate > 0:
        amount = round(qty * rate, 2)
        return qty, rate, amount

    if qty <= 0.0:
        return qty, rate, amount

    calc_amount = qty * rate
    tol = max(0.15, amount * 0.015)
    # If consistent, return
    if abs(calc_amount - amount) <= tol:
        return qty, rate, amount

    # 4. Check if rate dropped decimal point (e.g. 15398 -> 153.98 or 72986 -> 729.86)
    for div in [100.0, 10.0, 1000.0, 10000.0]:
        cand_rate = rate / div
        if abs((qty * cand_rate) - amount) <= tol:
            return qty, round(cand_rate, 2), amount

    # 5. Check if amount dropped decimal point
    for div in [100.0, 10.0, 1000.0, 10000.0]:
        cand_amount = amount / div
        if abs(calc_amount - cand_amount) <= max(0.15, cand_amount * 0.015):
            return qty, rate, round(cand_amount, 2)

    # 6. Fallback: if amount is known and reasonable, recalculate rate from amount / qty
    if amount > 0 and qty > 0:
        rate = round(amount / qty, 2)

    return qty, rate, amount

REJECT_PATTERNS = [
    r"^state\s*name", r"tamil\s*nadu", r"code\s*:\s*\d+", r"gstin", r"uin\b",
    r"consignee", r"ship\s*to", r"buyer", r"bill\s*to", r"invoice\s*no",
    r"motor\s*vehicle", r"terms\s*of\s*delivery", r"reference\s*no", r"e-way",
    r"contact\s*:", r"e-mail", r"bank\s*name", r"kotak", r"declaration",
    r"verified\s*by", r"prepared\s*by", r"customer", r"subject\s*to",
    r"tax\s*invoice", r"e-invoice", r"ack\s*no", r"ack\s*date", r"irn",
    r"description\s*of\s*goods", r"hsn\s*/?\s*sac", r"amount\s*chargeable",
    r"consolidated\s*hsn", r"lot\s*no", r"pkd\.\s*date", r"authorised\s*signatory",
    r"jurisdiction", r"account\s*no", r"ifsc", r"total\s*weight", r"sub\s*-?\s*total",
    r"^\s*less\b", r"cash\s*discount", r"trade\s*discount", r"^\s*discount\b",
    r"amount\s*in\s*words", r"rupees\s*in\s*words", r"total\s*tax", r"total\s*amount",
    r"taxable\s*value", r"central\s*tax", r"state\s*tax", r"integrated\s*tax",
    r"cgst\b", r"sgst\b", r"igst\b", r"round\s*off", r"rounded\s*off"
]

def clean_product_name(raw_name: str) -> str:
    """Clean product name from OCR noise, row numbers, and trailing packaging notes."""
    if not raw_name:
        return ""
    raw_str = str(raw_name).replace('\uff08', '(').replace('\uff09', ')').replace('\uff1a', ':').replace('\u2013', '-').replace('\u2014', '-')
    name = raw_str.strip()
    
    # Remove non-ascii characters (like stroke/checkmark \u4eba)
    name = re.sub(r'[^\x00-\x7F]+', ' ', name).strip()

    # Units and packaging patterns
    UNITS_PAT = r'(?:LITRE|LITRES|LIT|LTR|ML|KG|KGS|GM|GMS|GRAM|GRAMS|MM|CM|INCH|PLY|PCS|NOS)'

    # Split number + unit + container if directly concatenated, e.g. '15LITTIN' -> '15 LIT TIN'
    name = re.sub(r'(\d+)\s*(LITRE|LITRES|LIT|LTR|ML|KG|KGS|GM|GMS|GRAM|GRAMS|MM|CM)\s*(TIN|JAR|CAN|BOTTLE|PACK|PKT|BAG|BOX)\b', r'\1 \2 \3', name, flags=re.IGNORECASE)
    # Split number + unit when ending at boundary, e.g. '1LIT JAR' -> '1 LIT JAR'
    name = re.sub(r'(\d+)\s*(' + UNITS_PAT + r')\b', r'\1 \2', name, flags=re.IGNORECASE)
    # Split unit + container when word boundary at end
    name = re.sub(r'\b(' + UNITS_PAT + r')\s*(TIN|JAR|CAN|BOTTLE|PACK|PKT|BAG|BOX)\b', r'\1 \2', name, flags=re.IGNORECASE)

    # 1. Strip composite leading serial numbers and package counts:
    # e.g., "1 1box ", "2 3box ", "3 3box ", "1 10ctn ", "12 Nos) "
    name = re.sub(r"^\s*\(?\s*\d{0,3}\s*(?:box|boxes|ctn|tin|tins|case|pkg|pkgs|nos?|bag|bags|jar|jars|dz)\s*[\.\)\-]+\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\s*\d{1,2}\s+\d{1,3}\s*(?:box|boxes|ctn|tin|tins|case|pkg|pkgs|nos?|bag|bags|jar|jars)\b[\s\-]*", "", name, flags=re.IGNORECASE)

    # 2. Strip standard leading row numbers with delimiters: "1. ", "2) ", "3 - ", "01. "
    name = re.sub(r"^\s*(?:[0-9]{1,2}|[NJAB])[\.\)\-]+[\s\-]*", "", name)

    # 3. Strip standalone container prefix: "1box ", "3 box ", "15 tin " (only if followed by another quantity or description)
    name = re.sub(r"^\s*\d{1,3}\s*(?:box|boxes|ctn|case|pkg|pkgs)\b[\s\-]*", "", name, flags=re.IGNORECASE)

    # 4. Strip leading single/double digit serial number ONLY if NOT followed by a unit of measure (e.g. keep '1 LIT', '15 LIT', '200 ML')
    name = re.sub(r"^\s*(?:[0-9]{1,2}|[NJAB])\s+(?!(?:" + UNITS_PAT + r")\b)(?=[A-Za-z])", "", name, flags=re.IGNORECASE)

    # Specific brand abbreviations
    name = re.sub(r"\bU\.K\.([A-Za-z])", r"U.K. \1", name, flags=re.IGNORECASE)
    name = re.sub(r"\bUK([A-Za-z])", r"UK \1", name, flags=re.IGNORECASE)

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
    name = re.sub(r"\bBROOKBOND\b", "BROOK BOND", name, flags=re.IGNORECASE)
    name = re.sub(r"\bTEAPOWDER\b", "TEA POWDER", name, flags=re.IGNORECASE)
    name = re.sub(r"\bNaari\b", "Nannari", name, flags=re.IGNORECASE)
    name = re.sub(r"\bGaric\b", "Garlic", name, flags=re.IGNORECASE)
    name = re.sub(r"\bGaic\b", "Garlic", name, flags=re.IGNORECASE)
    name = re.sub(r"\b77emon\b", "777 Lemon", name, flags=re.IGNORECASE)
    name = re.sub(r"\b\(77Galic\b", "777 Garlic", name, flags=re.IGNORECASE)
    name = re.sub(r"\b77Galic\b", "777 Garlic", name, flags=re.IGNORECASE)

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
        all_gsts_raw = re.findall(GST_REGEX, full_page_text, re.IGNORECASE)
        all_gsts = []
        for g in all_gsts_raw:
            gu = g.upper()
            if gu not in all_gsts:
                all_gsts.append(gu)

        JAI_AGENCIES_GST = "33ADAPJ8701G1ZZ"
        if JAI_AGENCIES_GST in all_gsts:
            buyer_gst = JAI_AGENCIES_GST

        GST_VENDOR_MAP = {
            "33ESQPR9113B1ZM": "SHRI PARVATHY FOOD PRODUCTS",
            "33DYPPP7887G1ZJ": "NATHAN AND CO",
            "33AAHCS2205F1ZV": "SRI GANESHRAM (777 BRAND)",
            "33AABFH7868Q1Z0": "HOMANAF TRADERS"
        }

        # Check if any detected GST matches our known supplier database
        for g in all_gsts:
            if g in GST_VENDOR_MAP:
                seller_gst = g
                vendor_name = GST_VENDOR_MAP[g]
                break

        for t in tokens:
            m = re.search(GST_REGEX, t["text"], re.IGNORECASE)
            if m:
                gst_val = m.group(0).upper()
                near_buyer = False
                for other in tokens:
                    if -60 < (other["y"] - t["y"]) < 25 and abs(other["x"] - t["x"]) < 300:
                        ol = other["text"].lower()
                        if any(k in ol for k in ["bill to", "buyer", "consignee", "ship to", "billed to", "shipped to", "jai agencies"]):
                            near_buyer = True
                            break
                if (near_buyer or gst_val == JAI_AGENCIES_GST) and not buyer_gst:
                    buyer_gst = gst_val
                elif not seller_gst and not near_buyer and gst_val != JAI_AGENCIES_GST and t["y"] < 350:
                    seller_gst = gst_val

        if not seller_gst and all_gsts:
            for g in all_gsts:
                if g != buyer_gst and g != JAI_AGENCIES_GST:
                    seller_gst = g
                    break
            if not seller_gst:
                seller_gst = all_gsts[0]

        if not buyer_gst and len(all_gsts) > 1:
            for g in all_gsts:
                if g != seller_gst:
                    buyer_gst = g
                    break

        if seller_gst in GST_VENDOR_MAP:
            vendor_name = GST_VENDOR_MAP[seller_gst]

        # -------------------------------------------------------------
        # 2. Vendor / Seller Name (Page 1 or when found)
        # -------------------------------------------------------------
        if not vendor_name:
            if any("777" in t["text"] for t in tokens if t["y"] < 400):
                vendor_name = "SRI GANESHRAM (777 BRAND)"

        if not vendor_name:
            for t in tokens:
                txt = t["text"]
                m = re.search(r"A[o/c]?\s*Holder['’]?s\s*Name\s*:\s*([A-Za-z0-9\s&]+)", txt, re.IGNORECASE)
                if m and len(m.group(1).strip()) > 2:
                    cand = m.group(1).strip()
                    if not any(kw in cand.lower() for kw in ["consignee", "buyer", "transporter", "triplicate", "duplicate", "original", "orginal", "copy", "name:", "name"]):
                        vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", cand)
                        break
                m2 = re.search(r"for\s+([A-Za-z0-9\s&]+)", txt, re.IGNORECASE)
                if m2:
                    cand = m2.group(1).strip()
                    if len(cand) > 3 and not any(kw in cand.lower() for kw in ["consignee", "buyer", "authorised", "signature", "recipient", "transporter", "duplicate", "triplicate", "original", "orginal", "copy"]):
                        vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", cand)
                        break

            if not vendor_name:
                ignore_kws = [
                    "taxinvoice", "invoice", "gstin", "statename", "eway", "delivery", "dated", "original",
                    "orginal", "transporter", "triplicate", "duplicate", "billno", "irn", "ack", "ackno",
                    "ackdate", "adk", "adkno", "ak", "akno", "akdate", "recipient", "efnvolce", "einvoice",
                    "contact", "email", "modeterms", "otherreferences", "fssai", "phno", "originalfor",
                    "fortransporter", "detailsof", "receiver", "billedto", "shippedto", "road", "colony",
                    "street", "nagar", "puram"
                ]
                for t in tokens:
                    if t["y"] < 350 and t["x"] < 700:
                        raw_t = t["text"].strip()
                        tl_clean = re.sub(r"[^a-z0-9]", "", raw_t.lower())
                        if "consignee" in tl_clean or "buyer" in tl_clean or "receiver" in tl_clean or "billedto" in tl_clean:
                            continue
                        if any(kw in tl_clean for kw in ignore_kws):
                            continue
                        if parse_date(raw_t):
                            continue
                        if len(raw_t) > 3 and not re.search(GST_REGEX, raw_t):
                            if re.search(r"\b[0-9a-fA-F]{32,}\b", raw_t) or re.match(r"^\d{16,}$", raw_t):
                                continue
                            if not re.match(r"^[\d\/\#\-\s,:\.]+$", raw_t) and not re.match(r"^(?:MP|No|Plot|Door|Flat|D\.NO|S\.F|SF|SY|SURVEY|SHOP)\b", raw_t, re.IGNORECASE) and not re.search(r"\b(?:colony|nagar|road|street)\b", raw_t, re.IGNORECASE):
                                cleaned = re.sub(r"^(M\/[Ss]|Messrs\.?|M\/s\.?)\s*", "", raw_t, flags=re.IGNORECASE).strip()
                                cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
                                if len(cleaned) > 2 and any(c.isalpha() for c in cleaned) and cleaned.lower() not in ["name", "name:"]:
                                    vendor_name = cleaned
                                    break

            if vendor_name:
                vendor_name = re.sub(r"VIGNESHAGENCIES", "VIGNESH AGENCIES", vendor_name, flags=re.IGNORECASE)
                vendor_name = re.sub(r"SHRIPARVATHYFOODPRODUCTS.*", "SHRI PARVATHY FOOD PRODUCTS", vendor_name, flags=re.IGNORECASE)
                vendor_name = re.sub(r"HOMANAF TRADERS.*", "HOMANAF TRADERS", vendor_name, flags=re.IGNORECASE)
                vendor_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", vendor_name).strip()

        # -------------------------------------------------------------
        # 3. Invoice Number & Date
        # -------------------------------------------------------------
        if not invoice_no:
            # 1. Priority 1: token containing both explicit label and number (e.g. "Invoice No:S1/26-27/2934", "Invoice No.:67488")
            for t in tokens:
                txt = t["text"].strip()
                m = re.search(r"\b(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)[:\.\s]+([A-Za-z0-9\/\-_]+)", txt, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip().replace(",", "")
                    if any(c.isdigit() for c in cand) and not parse_date(cand) and not any(kw in cand.lower() for kw in ["e-way", "eway", "transporter", "duplicate", "triplicate", "original", "recipient", "buyer", "consignee", "date", "dated", "details"]):
                        if 2 <= len(cand) <= 30:
                            invoice_no = cand
                            break

            # 2. Priority 2: candidate token vertically right below 'Invoice No.' or horizontally to the right
            if not invoice_no:
                for t in tokens:
                    txt = t["text"].strip()
                    if re.search(r"\b(?:Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)", txt, re.IGNORECASE) and not re.search(r"e-Way", txt, re.IGNORECASE):
                        # First check strictly vertically below (e.g. 483/26-27 under Invoice No.)
                        for near in tokens:
                            if 4 < (near["y"] - t["y"]) < 45 and abs(near["x"] - t["x"]) < 60:
                                cand = near["text"].strip().replace(",", "")
                                cand = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", cand, flags=re.IGNORECASE).strip()
                                if any(c.isdigit() for c in cand) and not parse_date(cand) and not any(kw in cand.lower() for kw in ["e-way", "eway", "transporter", "duplicate", "triplicate", "original", "recipient", "buyer", "consignee", "dated", "date", "delivery", "details", "tax", "invoice"]):
                                    if 2 <= len(cand) <= 30:
                                        invoice_no = cand
                                        break
                        if invoice_no:
                            break

                        # Next check horizontally to the right
                        for near in tokens:
                            if abs(near["y"] - t["y"]) < 20 and 0 < (near["x"] - t["x"]) < 160:
                                cand = near["text"].strip().replace(",", "")
                                cand = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", cand, flags=re.IGNORECASE).strip()
                                if any(c.isdigit() for c in cand) and not parse_date(cand) and not any(kw in cand.lower() for kw in ["e-way", "eway", "transporter", "duplicate", "triplicate", "original", "recipient", "buyer", "consignee", "dated", "date", "delivery", "details", "tax", "invoice"]):
                                    if 2 <= len(cand) <= 30:
                                        invoice_no = cand
                                        break
                        if invoice_no:
                            break

            # 3. Priority 3: standard Indian invoice patterns (e.g. S1/26-27/2934, 483/26-27, NAC/26-27/302)
            if not invoice_no:
                for t in tokens:
                    txt = t["text"].strip()
                    m = re.search(r"\b([A-Za-z0-9]{1,6}\/\d{2}-\d{2}\/\d{1,6})\b", txt)
                    if m and not parse_date(m.group(1)):
                        invoice_no = m.group(1)
                        break
                    m2 = re.search(r"\b(\d{1,5}\/\d{2}-\d{2})\b", txt)
                    if m2 and not parse_date(m2.group(1)):
                        invoice_no = m2.group(1)
                        break

            if not invoice_no:
                m = re.search(r"\b(INV[\-\/][A-Za-z0-9\-\/]+|\d{4,8})\b", full_page_text, re.IGNORECASE)
                if m and m.group(1) not in ["2024", "2025", "2026", "2027"] and not parse_date(m.group(1)):
                    invoice_no = m.group(1)

            if invoice_no:
                invoice_no = re.sub(r"^(?:(?:Tax\s*)?Invoice|Inv\.?|Bill)\s*(?:No|Number|\#|\.)?[:\.\s]*", "", invoice_no, flags=re.IGNORECASE).strip()
                invoice_no = re.sub(r"^SI\/", "S1/", invoice_no)

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
        has_left_header = any(t["x"] < 650 and any(k in t["text"].lower() for k in ["product", "description", "particular", "s.n", "sn"]) for t in tokens if 180 <= t["y"] <= 450)
        has_right_header = any(t["x"] > 650 and any(k in t["text"].lower() for k in ["product", "mrp", "s.n", "sn"]) for t in tokens if 180 <= t["y"] <= 450)
        if has_left_header and has_right_header:
            max_table_x = 660.0

        # Filter tokens for table extraction on this page
        table_search_tokens = [t for t in tokens if t["x"] <= max_table_x]

        # -------------------------------------------------------------
        # 5. Table Header & Column Centers Detection (First-Cluster Logic)
        # -------------------------------------------------------------
        candidate_headers = []
        for t in table_search_tokens:
            tl = t["text"].lower().strip()
            if 150 <= t["y"] <= 535:
                col_type = None
                if any(k in tl for k in ["s.no", "sl no", "sl.no", "si no", "si.no", "sno", "sino", "snc"]) or (tl == "sn" and t["x"] < 200):
                    col_type = "sno"
                elif any(k in tl for k in ["marks", "container", "pkg", "case"]) and t["x"] < 250:
                    col_type = "marks"
                elif any(k in tl for k in ["descript", "particular", "goods", "product", "item"]) and t["x"] < 500:
                    col_type = "desc"
                elif (tl in ["hsn", "hsn/sac", "hsnisac", "sac"] or ("hsn" in tl or "sac" in tl)) and (240 <= t["x"] < 585):
                    col_type = "hsn"
                elif tl == "mrp" or ("mrp" in tl and (350 <= t["x"] < 520)) or ("inclof" in tl):
                    col_type = "mrp"
                elif (any(k in tl for k in ["quantity", "qty", "ntitunit"]) and (250 <= t["x"] < 700)) or (tl in ["qty", "qnty"]):
                    col_type = "qty"
                elif tl in ["case", "pkg", "pkgs", "uom"] or ("case" in tl and (320 <= t["x"] < 580)) or (tl == "uom"):
                    col_type = "case"
                elif ("rate" in tl or "price" in tl) and (350 <= t["x"] < 760) and not any(k in tl for k in ["cgst", "sgst", "igst", "gst rate"]):
                    col_type = "rate"
                elif ("dis" in tl or "disc" in tl or "discount" in tl) and (420 <= t["x"] < 520) and not ("cgst" in tl or "sgst" in tl):
                    col_type = "dis"
                elif any(k in tl for k in ["taxable", "taxable value", "taxable val"]):
                    col_type = "amount"
                elif any(k in tl for k in ["tax%", "gst%", "lax%", "rax%", "ax%", "tax %", "gst rate", "tax rate"]) or ("cgst" in tl and 550 <= t["x"] < 650) or (tl in ["gst", "tax"] and 700 <= t["x"] < 800):
                    col_type = "tax_pct"
                elif tl == "total" or "total amount" in tl or "gross amount" in tl or "total val" in tl or (("total" in tl or "tot." in tl) and t["x"] >= 750):
                    col_type = "total"
                elif ("amount" in tl or tl == "amount" or "aniount" in tl) and t["x"] >= 500 and not any(k in tl for k in ["tax amount", "cgst", "sgst"]):
                    col_type = "amount"

                if col_type:
                    candidate_headers.append((t, col_type))

        # Group candidate headers into horizontal clusters (|y1 - y2| < 22)
        clusters = []
        for t, ctype in sorted(candidate_headers, key=lambda item: item[0]["y"]):
            placed = False
            for c in clusters:
                if abs(t["y"] - c["avg_y"]) < 22:
                    c["tokens"].append((t, ctype))
                    c["avg_y"] = sum(x[0]["y"] for x in c["tokens"]) / len(c["tokens"])
                    placed = True
                    break
            if not placed:
                clusters.append({"avg_y": t["y"], "tokens": [(t, ctype)]})

        # Pick the UPPERMOST cluster that contains >= 2 distinct columns
        best_cluster = None
        for c in clusters:
            unique_cols = set(ctype for _, ctype in c["tokens"])
            if len(unique_cols) >= 3 or (len(unique_cols) >= 2 and any(k in unique_cols for k in ["desc", "hsn"])):
                best_cluster = c
                break

        header_tokens = []
        col_centers = {}
        if best_cluster:
            header_y = best_cluster["avg_y"]
            for t, ctype in candidate_headers:
                if abs(t["y"] - header_y) < 22:
                    header_tokens.append(t)
                    if ctype not in col_centers:
                        col_centers[ctype] = t["x"]
                    elif ctype == "rate" and t["x"] < col_centers["rate"]:
                        # Keep the first/leftmost rate column (item unit price)
                        col_centers[ctype] = t["x"]
                    elif ctype == "amount" and t["x"] < col_centers["amount"]:
                        col_centers[ctype] = t["x"]
                    elif ctype == "total" and t["x"] > col_centers["total"]:
                        col_centers[ctype] = t["x"]
            saved_col_centers = col_centers
        else:
            header_y = 350.0 if page_idx == 0 else 180.0
            col_centers = saved_col_centers

        STOP_KEYWORDS = [
            "less :", "less:", "cash discount", "trade discount", "sub total", "sub-total",
            "subtotal", "sub-total-5%", "cgst", "sgst", "igst", "rounded off", "round off", "roundoff", "r.o.d",
            "grand total", "bill amount", "net amount", "rupees", "amount chargeable",
            "total amount before tax", "total amount after tax", "total taxable", "taxable value",
            "tax amount", "central tax", "state tax", "total quantity", "output cgst", "output sgst"
        ]

        totals_start_y = 950.0
        for t in table_search_tokens:
            tl = t["text"].lower().strip()
            if any(k in tl for k in STOP_KEYWORDS) and t["y"] > (header_y + 15):
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
        item_tokens = [t for t in tokens if t["x"] <= max_table_x and (header_y_adj + 4) <= t["y_adj"] < (totals_start_y_adj - 4)]
        
        # Check if page is a pure batch/lot table without rates (e.g., SGR Foods Page 2/3 Lot No table)
        is_batch_table = any("lot no" in t["text"].lower() or "pkd. date" in t["text"].lower() for t in tokens if t["y"] < 400)
        is_consolidated_hsn = any("consolidated hsn" in t["text"].lower() or "e-way bill generation" in t["text"].lower() for t in tokens if t["y"] < 600)

        if not is_batch_table and not is_consolidated_hsn:
            rows = []
            curr_row = []
            for t in sorted(item_tokens, key=lambda x: x["y_adj"]):
                if not curr_row:
                    curr_row.append(t)
                elif abs(t["y_adj"] - sum(x["y_adj"] for x in curr_row) / len(curr_row)) <= 10.2:
                    curr_row.append(t)
                else:
                    rows.append(curr_row)
                    curr_row = [t]
            if curr_row:
                rows.append(curr_row)

            for row in rows:
                # Discard rows that belong to summary/discounts
                row_text = " ".join(t["text"].lower() for t in row)
                if any(k in row_text for k in ["less :", "less:", "cash discount", "trade discount", "sub total", "sub-total", "total quantity", "amount chargeable", "total weight"]):
                    continue

                row_sorted = sorted(row, key=lambda x: x["x"])
                desc_parts = []
                hsn_code = ""
                gst_pct = 0.0
                qty = 0.0
                unit = "Nos"
                rate = 0.0
                discount = 0.0
                disc_pct = 0.0
                mrp = 0.0
                amount = 0.0
                total_val = 0.0

                for t in row_sorted:
                    x = t["x"]
                    txt = t["text"].strip()
                    tl = txt.lower()

                    # Check for merged GST% + Quantity, e.g. "5%20.000 dz" or "5%40.000dz"
                    merged_m = re.match(r"^(\d+(?:\.\d+)?)\s*%\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$", txt)
                    if merged_m:
                        gst_pct = float(merged_m.group(1))
                        q_val = float(merged_m.group(2))
                        if q_val > 0:
                            qty = q_val
                        u_m = merged_m.group(3).strip()
                        if u_m:
                            unit = u_m
                        continue

                    if col_centers:
                        dists = {col: abs(x - cx) for col, cx in col_centers.items()}
                        closest_col = min(dists, key=dists.get)

                        if closest_col in ["sno", "marks"]:
                            # If text contains container/measurement or is clearly a description token, rescue it!
                            if x >= 180 or any(k in tl for k in ["lit", "tin", "jar", "can", "ghee", "oil", "tea", "powder", "nos", "pack", "bottle"]) or (len(txt) > 4 and any(c.isalpha() for c in txt)):
                                desc_parts.append(txt)
                            continue
                        elif closest_col == "desc":
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
                            elif "dz" in tl: unit = "dz"
                            elif "nos" in tl: unit = "Nos"
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
                            elif "dz" in tl: unit = "dz"
                            elif "nos" in tl: unit = "Nos"
                        elif closest_col == "rate":
                            if "%" in txt:
                                pct_m = re.search(r"(\d+(?:\.\d+)?)", txt)
                                if pct_m:
                                    gst_pct = float(pct_m.group(1))
                            else:
                                r_val = clean_amount(txt)
                                if r_val > 0:
                                    rate = r_val
                        elif closest_col == "dis":
                            if "%" in txt:
                                pm = re.search(r"(\d+(?:\.\d+)?)", txt)
                                if pm:
                                    disc_pct = float(pm.group(1))
                            else:
                                d_val = clean_amount(txt)
                                if d_val > 0:
                                    discount = d_val
                        elif closest_col == "tax_pct" or ("%" in txt and x >= 500):
                            pct_m = re.search(r"(\d+(?:\.\d+)?)", txt)
                            if pct_m:
                                gst_pct = float(pct_m.group(1))
                        elif closest_col in ["amount", "taxable"]:
                            if "%" not in txt:
                                a_val = clean_amount(txt)
                                if a_val > 0:
                                    amount = a_val
                        elif closest_col == "total":
                            if "%" not in txt:
                                tot_v = clean_amount(txt)
                                if tot_v > 0:
                                    total_val = tot_v
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
                if any(k in raw_desc.lower() for k in ["less :", "less:", "cash discount", "sub total", "sub-total", "total amount"]):
                    continue

                cleaned_desc = clean_product_name(raw_desc)
                if any(re.search(pat, cleaned_desc, re.IGNORECASE) for pat in REJECT_PATTERNS):
                    continue
                if cleaned_desc.lower() in ["less", "less:", "discount", "cash discount", "total", "sub total", "subtotal", "round off", "rounded off"]:
                    continue

                # Filter out buyer address lines and metadata rows
                if any(k in cleaned_desc.lower() for k in ["jai agencies", "12/e/3", "coonoor", "the nilgiris", "terms and conditions", "bank details", "declaration", "india", "receiver's seal", "signatory", "authorized signatory"]):
                    continue

                if not cleaned_desc and hsn_code:
                    cleaned_desc = f"Item {hsn_code}"

                # Numerical reconciliation for Rate, Qty, Amount
                if qty > 0 and rate > 0 and amount > 0:
                    for div in [100.0, 10.0]:
                        if abs((amount / div) - (qty * rate)) <= max(0.5, (amount / div) * 0.02):
                            amount = round(amount / div, 2)
                            break
                elif 0 < amount < 100.0 and rate > 500.0:
                    if disc_pct > 0:
                        amount = round(rate * (1.0 - disc_pct / 100.0), 2)
                    else:
                        amount = rate

                # Missing decimal points in rate
                if rate > 20000.0:
                    for div in [100.0, 10.0]:
                        if 50.0 <= rate / div <= 15000.0:
                            rate = rate / div
                            break
                elif 0.0 < rate < 10.0 and amount > 500.0:
                    for mul in [1000.0, 100.0]:
                        cand_r = rate * mul
                        cand_net = cand_r * (1.0 - disc_pct / 100.0) if disc_pct > 0 else cand_r
                        if abs((amount / cand_net) - round(amount / cand_net)) < 0.1:
                            rate = cand_r
                            break

                # If rate was accidentally captured into qty (e.g. qty=2014, rate=0 or rate=5, amount=10070)
                if qty > 50.0 and amount > 0:
                    cand_rate = qty
                    cand_qty = round(amount / cand_rate)
                    if 1 <= cand_qty <= 50 and abs(amount - (cand_qty * cand_rate)) < 5.0:
                        rate = cand_rate
                        qty = float(cand_qty)
                    elif qty > 1000.0:
                        # Missing decimal points in rate (e.g. 1053514 -> 10535.14, amount=31605.42)
                        for div in [100.0, 1000.0]:
                            cand_r = qty / div
                            cand_q = round(amount / cand_r)
                            if 1 <= cand_q <= 50 and abs(amount - (cand_q * cand_r)) < 5.0:
                                rate = cand_r
                                qty = float(cand_q)
                                break

                if amount == 0.0 and total_val > 0.0:
                    eff_gst = gst_pct * 2.0 if (0 < gst_pct <= 2.5) else gst_pct
                    amount = round(total_val / (1.0 + eff_gst / 100.0), 2)

                # Recover missing qty
                if (qty <= 0.0 or qty is None) and rate > 0 and amount > 0:
                    if disc_pct > 0:
                        unit_net = rate * (1.0 - disc_pct / 100.0)
                        qty = max(1.0, round(amount / unit_net))
                    else:
                        qty = max(1.0, round(amount / rate))

                if disc_pct > 0 and qty > 0 and rate > 0 and discount == 0.0:
                    discount = round((qty * rate) * (disc_pct / 100.0), 2)

                # Check if amount was gross inclusive of GST (e.g. Nathan & Co)
                if qty > 0 and rate > 0 and amount > 0 and gst_pct > 0:
                    expected_taxable = round(qty * rate, 2)
                    expected_gross = round(expected_taxable * (1.0 + gst_pct / 100.0), 2)
                    if abs(amount - expected_gross) <= max(0.5, expected_gross * 0.015):
                        amount = expected_taxable

                if (qty > 0) and (amount > 0 or rate > 0) and (cleaned_desc or hsn_code):
                    # Check for 100x discrepancy between qty, rate and amount
                    if qty > 50 and rate > 100.0 and amount > 20000.0:
                        qty = 1.0
                        amount = rate

                    # Deterministically reconcile Qty, Rate, and Amount:
                    qty, rate, amount = reconcile_item_math(qty, rate, amount)
                    final_unit_price = rate if rate > 0 else (round(amount / qty, 2) if qty else 0.0)
                    if amount == 0.0 and qty > 0 and final_unit_price > 0:
                        amount = round(qty * final_unit_price, 2)

                    gross_item = qty * final_unit_price
                    if discount > 0 and gross_item > 0 and disc_pct == 0.0:
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

        cgst_pct = 0.0
        sgst_pct = 0.0
        igst_pct = 0.0
        global_cash_discount = 0.0

        for t in totals_tokens:
            tl = t["text"].lower()
            txt = t["text"]

            # Check Cash Discount / deductions
            if "less" in tl or "cash discount" in tl:
                for near in totals_tokens:
                    if near["x"] > 550 and abs(near["y_adj"] - t["y_adj"]) < 15:
                        d_val = abs(clean_amount(near["text"]))
                        if d_val > 0:
                            global_cash_discount += d_val
                            break

            elif "cgst" in tl and "total" not in tl:
                m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", txt)
                if m_pct:
                    cgst_pct = float(m_pct.group(1))
                for near in totals_tokens:
                    if near["x"] > 400 and -6 <= (near["y_adj"] - t["y_adj"]) < 38:
                        if "%" in near["text"] and not cgst_pct:
                            m2 = re.search(r"(\d+(?:\.\d+)?)", near["text"])
                            if m2: cgst_pct = float(m2.group(1))
                        val = clean_amount(near["text"])
                        if val > 0 and "%" not in near["text"]:
                            # Ignore if near looks like the total tax column
                            if any("total tax" in other["text"].lower() for other in totals_tokens) and near["x"] > 750:
                                continue
                            # Tax cannot exceed 40% of item sum (prevents picking subtotal as CGST)
                            if all_items and val > sum(it["amount"] for it in all_items) * 0.4:
                                continue
                            global_cgst = max(global_cgst, val)

            elif "sgst" in tl and "total" not in tl:
                m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", txt)
                if m_pct:
                    sgst_pct = float(m_pct.group(1))
                for near in totals_tokens:
                    if near["x"] > 400 and -6 <= (near["y_adj"] - t["y_adj"]) < 38:
                        if "%" in near["text"] and not sgst_pct:
                            m2 = re.search(r"(\d+(?:\.\d+)?)", near["text"])
                            if m2: sgst_pct = float(m2.group(1))
                        val = clean_amount(near["text"])
                        if val > 0 and "%" not in near["text"]:
                            if any("total tax" in other["text"].lower() for other in totals_tokens) and near["x"] > 750:
                                continue
                            if all_items and val > sum(it["amount"] for it in all_items) * 0.4:
                                continue
                            global_sgst = max(global_sgst, val)

            elif "igst" in tl and "total" not in tl:
                m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", txt)
                if m_pct:
                    igst_pct = float(m_pct.group(1))
                for near in totals_tokens:
                    if near["x"] > 400 and -6 <= (near["y_adj"] - t["y_adj"]) < 38:
                        if "%" in near["text"] and not igst_pct:
                            m2 = re.search(r"(\d+(?:\.\d+)?)", near["text"])
                            if m2: igst_pct = float(m2.group(1))
                        val = clean_amount(near["text"])
                        if val > 0 and "%" not in near["text"]:
                            if all_items and val > sum(it["amount"] for it in all_items) * 0.4:
                                continue
                            global_igst = max(global_igst, val)

            elif ("round" in tl or "r.o.d" in tl) and "total" not in tl:
                for near in totals_tokens:
                    if "%" in near["text"]:
                        continue
                    if near["x"] > 550 and abs(near["y_adj"] - t["y_adj"]) < 20:
                        val = clean_amount(near["text"])
                        if 0.0 < abs(val) <= 5.0:
                            global_round_off = val
                            break
                        elif abs(val) > 5.0 and "." not in near["text"]:
                            cand = val / 100.0
                            if 0.0 < abs(cand) <= 5.0:
                                global_round_off = cand
                                break

            elif any(k in tl for k in ["bill amount", "total amount after tax", "grand total", "invoice total", "amount chargeable", "total"]):
                if tl == "total" and t["y"] < 500:
                    continue
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 25:
                        val = clean_amount(near["text"])
                        if val > global_grand_total:
                            global_grand_total = val

            elif any(k in tl for k in ["sub total", "total amount before tax", "taxable value"]):
                for near in totals_tokens:
                    if near["x"] > 450 and abs(near["y_adj"] - t["y_adj"]) < 25:
                        val = clean_amount(near["text"])
                        if val > global_subtotal:
                            global_subtotal = val

    if not invoice_date:
        invoice_date = datetime.now().strftime("%Y-%m-%d")

    # In Indian GST, intrastate CGST and SGST are always equal.
    # If one of them captured the combined total tax (double the other), normalize it.
    if global_cgst > 0 and global_sgst > 0:
        if abs(global_cgst - 2 * global_sgst) < 1.0:
            global_cgst = global_sgst
        elif abs(global_sgst - 2 * global_cgst) < 1.0:
            global_sgst = global_cgst
    elif global_cgst > 0 and global_sgst == 0:
        global_sgst = global_cgst
    elif global_sgst > 0 and global_cgst == 0:
        global_cgst = global_sgst

    calculated_subtotal = sum(it["amount"] for it in all_items)
    if global_subtotal == 0.0 or (calculated_subtotal > 0 and abs(global_subtotal - calculated_subtotal) > calculated_subtotal * 0.3):
        global_subtotal = calculated_subtotal

    total_gst = global_cgst + global_sgst

    if global_grand_total == 0.0 and global_subtotal > 0:
        global_grand_total = global_subtotal + total_gst + global_igst + global_round_off - global_cash_discount
    elif global_grand_total > 0 and global_subtotal == 0.0:
        global_subtotal = global_grand_total - total_gst - global_igst - global_round_off + global_cash_discount

    # Propagate effective invoice GST percentage if items did not have explicit GST% columns
    total_invoice_gst = cgst_pct + sgst_pct + igst_pct
    if total_invoice_gst == 0.0 and (global_cgst > 0 or global_sgst > 0) and global_subtotal > 0:
        total_invoice_gst = round(((global_cgst + global_sgst + global_igst) / global_subtotal) * 100, 1)

    if total_invoice_gst > 0:
        for it in all_items:
            if it.get("gst_percent", 0.0) == 0.0:
                it["gst_percent"] = total_invoice_gst

    # If invoice has cash discounts and items lack individual discounts, apply pro-rated discount
    gross_sum = sum(it["amount"] for it in all_items)
    if global_cash_discount > 0 and gross_sum > 0:
        matched = False
        for it in all_items:
            if abs(it["amount"] - global_cash_discount) < 0.1:
                it["discount"] = global_cash_discount
                it["discount_percent"] = 100.0
                matched = True
                break
        if not matched:
            overall_disc_pct = round((global_cash_discount / gross_sum) * 100, 2)
            for it in all_items:
                if it.get("discount_percent", 0.0) == 0.0:
                    it["discount_percent"] = overall_disc_pct
                    it["discount"] = round((it["amount"] * overall_disc_pct) / 100.0, 2)

    return {
        "success": True,
        "data": {
            "invoice_no": invoice_no,
            "date": invoice_date,
            "vendor": vendor_name,
            "gst_number": seller_gst,
            "buyer_gst": buyer_gst,
            "subtotal": f"{global_subtotal:.2f}",
            "cash_discount": f"{global_cash_discount:.2f}",
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
