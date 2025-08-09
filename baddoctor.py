import io
import re
from typing import List

import streamlit as st
from pypdf import PdfReader, PdfWriter

# 可選：OCR 依賴（掃描影像 PDF 才需要）
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


def find_pages_with_keywords(
    pdf_bytes: bytes,
    patterns: List[str],
    use_ocr: bool = False,
    ocr_lang: str = "chi_tra",
    dpi: int = 300,
) -> List[int]:
    """回傳符合關鍵字的 0-based 頁碼清單。"""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    hits = []

    compiled = [re.compile(p, flags=re.IGNORECASE) for p in patterns]

    for i, page in enumerate(reader.pages):
        # 1) 文字擷取（適用文字型 PDF）
        text = page.extract_text() or ""
        if any(c.search(text) for c in compiled):
            hits.append(i)
            continue

        # 2) OCR（可選，適用掃描影像 PDF）
        if use_ocr and OCR_AVAILABLE:
            try:
                images = convert_from_bytes(
                    pdf_bytes, dpi=dpi, first_page=i + 1, last_page=i + 1
                )
                ocr_text_all = []
                for img in images:
                    ocr_text_all.append(pytesseract.image_to_string(img, lang=ocr_lang))
                ocr_text = "\n".join(ocr_text_all)
                if any(c.search(ocr_text) for c in compiled):
                    hits.append(i)
                    continue
            except Exception:
                # OCR 失敗時跳過，不中斷整體流程
                pass

    return hits


def export_single_page_pdf(pdf_bytes: bytes, page_index: int) -> bytes:
    """把指定頁輸出為單頁 PDF（回傳 bytes）。"""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    out_buf = io.BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return out_buf.read()


# -------------------- Streamlit UI --------------------
st.set_page_config(page_title="醫事審查委員會頁面擷取", page_icon="🩺", layout="centered")
st.title("🩺 醫事審查委員會頁面擷取（政府公報 PDF）")

st.markdown(
    """
上傳一份政府公報 PDF，本工具會：
1. 搜尋是否包含 **醫師懲戒** 相關頁面  
2. 將符合的每一頁各自匯出為 **單頁 PDF** 供下載  
若找不到則顯示「找不到醫事審查委員會文件」
"""
)

uploaded = st.file_uploader("上傳政府公報 PDF", type=["pdf"])

default_pattern = r"(懲戒決議)"
pattern_text = st.text_input(
    "關鍵字或正則（可多個，以換行分隔）",
    value=default_pattern,
    help="支援正則表達式，預設會匹配『醫師懲戒』。",
)

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    use_ocr = st.checkbox(
        "使用 OCR（掃描影像 PDF 時勾選，較慢）",
        value=False,
        help="需要本機安裝 Tesseract 與中文字庫。文字型 PDF 無需勾選。",
    )
with col2:
    ocr_lang = st.text_input(
        "OCR 語言代碼",
        value="chi_tra",
        help="常用：chi_tra（繁中）、chi_sim（簡中）、eng（英文）。多語可用如 'chi_tra+eng'。",
    )
with col3:
    dpi = st.number_input("OCR 解析度 (DPI)", min_value=150, max_value=600, value=300, step=50)

if use_ocr and not OCR_AVAILABLE:
    st.warning("尚未安裝 OCR 依賴（pdf2image / pytesseract）。請參考下方安裝說明。")

if uploaded is not None:
    pdf_bytes = uploaded.read()
    patterns = [p.strip() for p in pattern_text.splitlines() if p.strip()]

    with st.spinner("分析中，請稍候…"):
        hit_pages = find_pages_with_keywords(
            pdf_bytes, patterns, use_ocr=use_ocr, ocr_lang=ocr_lang, dpi=dpi
        )

    if hit_pages:
        st.success(f"找到 {len(hit_pages)} 頁包含關鍵字：{', '.join(str(p+1) for p in hit_pages)}")
        st.divider()
        for p in hit_pages:
            one_page_pdf = export_single_page_pdf(pdf_bytes, p)
            fname = f"{uploaded.name.rsplit('.pdf',1)[0]}_p{p+1}.pdf"
            st.download_button(
                label=f"下載單頁 PDF：第 {p+1} 頁",
                data=one_page_pdf,
                file_name=fname,
                mime="application/pdf",
            )
    else:
        st.error("該公報找不到醫事審查委員會文件。")
