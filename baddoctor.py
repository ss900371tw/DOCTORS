import io
import re
import hashlib
from typing import List

import streamlit as st
from pypdf import PdfReader, PdfWriter

try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

def _clear_results():
    for k in ["hit_pages", "page_files", "base_filename", "patterns_saved", "file_sig"]:
        st.session_state.pop(k, None)

def find_pages_with_keywords(pdf_bytes: bytes, patterns: List[str], use_ocr=False, ocr_lang="chi_tra", dpi=300):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    hits, compiled = [], [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if any(c.search(text) for c in compiled):
            hits.append(i); continue
        if use_ocr and OCR_AVAILABLE:
            try:
                images = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=i+1, last_page=i+1)
                ocr_text = "\n".join(pytesseract.image_to_string(img, lang=ocr_lang) for img in images)
                if any(c.search(ocr_text) for c in compiled):
                    hits.append(i)
            except Exception:
                pass
    return hits

def export_single_page_pdf(pdf_bytes: bytes, page_index: int) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes)); writer = PdfWriter()
    writer.add_page(reader.pages[page_index]); out = io.BytesIO(); writer.write(out); out.seek(0); return out.read()

def extract_page_text(pdf_bytes: bytes, page_index: int, use_ocr=False, ocr_lang="chi_tra", dpi=300) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes)); page = reader.pages[page_index]
    txt = page.extract_text() or ""
    if use_ocr and OCR_AVAILABLE:
        try:
            images = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=page_index+1, last_page=page_index+1)
            txt = "\n".join(pytesseract.image_to_string(img, lang=ocr_lang) for img in images)
        except Exception:
            pass
    return txt

def page_image_bytes(pdf_bytes: bytes, page_index: int, dpi=200) -> bytes:
    if not OCR_AVAILABLE: return b""
    images = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=page_index+1, last_page=page_index+1)
    buf = io.BytesIO(); images[0].save(buf, format="PNG"); buf.seek(0); return buf.read()

def highlight_html(text: str, patterns: List[str]) -> str:
    html = text
    for pat in patterns:
        html = re.sub(pat, lambda m: f"<mark>{m.group(0)}</mark>", html, flags=re.IGNORECASE)
    return html.replace("\n", "<br/>")

st.set_page_config(page_title="醫事審查委員會頁面擷取", page_icon="🩺", layout="centered")
st.title("🩺 醫事審查委員會頁面擷取（政府公報 PDF）")

st.markdown("上傳 PDF → 按「開始擷取」→ 下方顯示文字高亮＋圖片預覽＋單頁下載。")

# 上傳在表單外（可用 on_change）
top_cols = st.columns([1,1,6])
with top_cols[0]:
    if st.button("清除結果"):
        _clear_results(); st.experimental_rerun()

uploaded = st.file_uploader(
    "上傳政府公報 PDF",
    type=["pdf"],
    key="pdf_file",
    on_change=_clear_results,   # 換新檔自動清空
)

# 參數表單
with st.form("extract_form"):
    default_pattern = r"(醫師懲戒委員會懲戒決議書|醫師懲戒委員會 懲戒決議書)"
    pattern_text = st.text_area("關鍵字或正則（可多個，以換行分隔）", value=default_pattern, height=90)
    c1,c2,c3,c4 = st.columns(4)
    with c1: use_ocr = st.checkbox("使用 OCR（較慢）", value=False)
    with c2: ocr_lang = st.text_input("OCR 語言代碼", value="chi_tra")
    with c3: dpi = st.number_input("OCR DPI", 150, 600, 300, 50)
    with c4: preview_dpi = st.number_input("預覽圖片 DPI", 100, 300, 200, 50)
    submitted = st.form_submit_button("開始擷取")

if submitted:
    f = st.session_state.get("pdf_file")
    if f is None:
        st.error("請先上傳 PDF 再按「開始擷取」。"); st.stop()
    if use_ocr and not OCR_AVAILABLE:
        st.warning("未安裝 pdf2image / pytesseract / poppler，OCR 與預覽將不可用。")

    pdf_bytes = f.getvalue()
    patterns = [p.strip() for p in (pattern_text or "").splitlines() if p.strip()]
    if not patterns:
        st.error("請輸入至少一個關鍵字/正則。"); st.stop()

    st.session_state.file_sig = hashlib.md5(pdf_bytes).hexdigest()
    with st.spinner("分析中…"):
        hit_pages = find_pages_with_keywords(pdf_bytes, patterns, use_ocr=use_ocr, ocr_lang=ocr_lang, dpi=dpi)

    if not hit_pages:
        st.error("找不到相關頁面。")
    else:
        st.session_state.hit_pages = hit_pages
        st.session_state.base_filename = f.name.rsplit(".pdf", 1)[0]
        st.session_state.patterns_saved = patterns
        st.session_state.page_files = {
            p: {
                "pdf": export_single_page_pdf(pdf_bytes, p),
                "text": extract_page_text(pdf_bytes, p, use_ocr=use_ocr, ocr_lang=ocr_lang, dpi=dpi),
                "img": page_image_bytes(pdf_bytes, p, dpi=preview_dpi) if OCR_AVAILABLE else None,
            }
            for p in hit_pages
        }

# 若使用者換了新檔但還沒按開始擷取，不顯示舊結果
cur_sig = None
if st.session_state.get("pdf_file") is not None:
    try:
        cur_sig = hashlib.md5(st.session_state["pdf_file"].getvalue()).hexdigest()
    except Exception:
        pass

if cur_sig and st.session_state.get("file_sig") and cur_sig != st.session_state["file_sig"]:
    st.info("已選取新檔案，請按「開始擷取」。")
elif "hit_pages" in st.session_state and st.session_state.hit_pages:
    hit_pages = st.session_state.hit_pages
    base_filename = st.session_state.get("base_filename", "output")
    patterns_saved = st.session_state.get("patterns_saved", [])
    st.success(f"找到 {len(hit_pages)} 頁包含關鍵字：{', '.join(str(p+1) for p in hit_pages)}")
    st.divider()
    for p in hit_pages:
        with st.expander(f"第 {p+1} 頁", expanded=True if len(hit_pages) <= 3 else False):
            txt = st.session_state.page_files[p]["text"] or ""
            if txt.strip():
                st.markdown("**文字內容（高亮關鍵字）**")
                st.markdown(highlight_html(txt, patterns_saved), unsafe_allow_html=True)
            else:
                st.info("此頁無可擷取文字。")
            img = st.session_state.page_files[p]["img"]
            if img:
                st.markdown("**頁面預覽**")
                st.image(img, use_column_width=True)
            st.download_button(
                label=f"下載單頁 PDF（第 {p+1} 頁）",
                data=st.session_state.page_files[p]["pdf"],
                file_name=f"{base_filename}_p{p+1}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
