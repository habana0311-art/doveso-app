import streamlit as st
import json
import requests
import time
from bs4 import BeautifulSoup
from PIL import Image
from google import genai
from google.genai import types

# Cấu hình giao diện Streamlit
st.set_page_config(page_title="Dò Vé Số Tự Động", page_icon="🎫", layout="centered")

st.title("🎫 Dò Vé Số Tự Động bằng Gemini AI")

# Lấy API Key từ Streamlit Secrets hoặc ô nhập tay trên giao diện
api_key = st.secrets.get("GEMINI_API_KEY", None)

if not api_key:
    api_key = st.sidebar.text_input("🔑 Nhập Google Gemini API Key:", type="password")
    if not api_key:
        st.info("💡 Bạn cần nhập Gemini API Key ở thanh bên (Sidebar) để ứng dụng hoạt động.")
        st.stop()

# Khởi tạo client Gemini
client = genai.Client(api_key=api_key)

# Bảng quy đổi tên nhà đài sang mã đường dẫn web
PROVINCE_MAP = {
    "TP.HCM": "tphcm", "TPHCM": "tphcm", "HỒ CHÍ MINH": "tphcm", "SÀI GÒN": "tphcm",
    "LONG AN": "long-an", "HẬU GIANG": "hau-giang", "BÌNH DƯƠNG": "binh-duong",
    "VĨNH LONG": "vinh-long", "TRÀ VINH": "tra-vinh", "BÌNH PHƯỚC": "binh-phuoc",
    "CÀ MAU": "ca-mau", "ĐỒNG THÁP": "dong-thap", "BẾN TRE": "ben-tre",
    "VŨNG TÀU": "vung-tau", "BẠC LIÊU": "bac-lieu", "ĐỒNG NAI": "dong-nai",
    "CẦN THƠ": "can-tho", "SÓC TRĂNG": "soc-trang", "TÂY NINH": "tay-ninh",
    "AN GIANG": "an-giang", "BÌNH THUẬN": "binh-thuan", "TIỀN GIANG": "tien-giang",
    "KIÊN GIANG": "kien-giang", "ĐÀ LẠT": "da-lat", "LÂM ĐỒNG": "da-lat"
}

def get_slug(province_name):
    if not province_name:
        return None
    clean = province_name.strip().upper()
    for key, slug in PROVINCE_MAP.items():
        if key in clean:
            return slug
    return None

def fetch_kqxs(slug, date_str):
    """Cào dữ liệu KQXS từ xskt.com.vn theo đài và ngày"""
    url = f"https://xskt.com.vn/{slug}/{date_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", class_="vtable")
        if not table:
            return None
        
        kq = {}
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all(["th", "td"])
            if len(cols) >= 2:
                prize_name = cols[0].text.strip()
                nums = [p.text.strip() for p in cols[1].find_all(["p", "span", "div"]) if p.text.strip()]
                if not nums:
                    nums = cols[1].text.strip().split()
                if prize_name and nums:
                    kq[prize_name] = nums
        return kq
    except Exception:
        return None

def check_ticket_all_prizes(ticket_num, kqxs):
    results = []
    ticket_num = str(ticket_num).zfill(6)
    
    gdb = None
    for k in kqxs.keys():
        if "Đặc biệt" in k or "ĐB" in k or "DB" in k:
            if kqxs[k]:
                gdb = kqxs[k][0]
            break

    if gdb and len(gdb) == 6:
        if ticket_num == gdb:
            results.append("🏆 **GIẢI ĐẶC BIỆT** (2 Tỷ đồng)")
        elif ticket_num[0] != gdb[0] and ticket_num[1:] == gdb[1:]:
            results.append("🎁 **GIẢI PHỤ ĐẶC BIỆT (AN ỦI)** (50 Triệu đồng)")
        elif ticket_num[0] == gdb[0]:
            mismatch = sum(1 for i in range(1, 6) if ticket_num[i] != gdb[i])
            if mismatch == 1:
                results.append("🎁 **GIẢI KHUYẾN KHÍCH** (6 Triệu đồng)")

    for prize_name, nums in kqxs.items():
        if "Đặc biệt" in prize_name or "ĐB" in prize_name or "DB" in prize_name:
            continue
            
        for num in nums:
            num = str(num).strip()
            length = len(num)
            if length in [2, 3, 4, 5, 6]:
                if ticket_num.endswith(num):
                    results.append(f"🎉 **{prize_name.upper()}** (Trùng dãy số `{num}`)")
                    
    return results

def extract_from_image(image):
    prompt = """
    Phân tích ảnh vé số Việt Nam và trích xuất danh sách TẤT CẢ các vé số trong ảnh.
    Trả về định dạng JSON thuần túy gồm danh sách dạng:
    [
      {
        "province": "Tên tỉnh/nhà đài (VD: TP.HCM, Long An, Hậu Giang...)",
        "draw_date": "Ngày xổ số dạng DD-MM-YYYY (VD: 19-09-2026)",
        "ticket_number": "Dãy số dự thưởng 6 chữ số (VD: 452029)"
      }
    ]
    """
    
    # Tự động thử lại 3 lần nếu máy chủ Google báo bận/quá tải (503)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = client.models.generate_content(
                model='gemini-2.0-flash',  # Mô hình chuẩn, nhanh và ổn định nhất
                contents=[image, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(res.text)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)  # Đợi 2 giây rồi tự động thử lại
            else:
                raise e

# --- GIAO DIỆN CHÍNH ---
uploaded_file = st.file_uploader("📸 Chọn ảnh chụp vé số của bạn", type=["jpg", "jpeg", "png", "webp"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Ảnh vé số đã tải lên", use_container_width=True)
    
    with st.spinner("🔍 AI đang phân tích vé số..."):
        try:
            tickets = extract_from_image(image)
            st.success(f"Phân tích thành công! Nhận diện được {len(tickets)} vé số.")
            
            for i, ticket in enumerate(tickets, 1):
                st.write("---")
                st.subheader(f"🎫 Vé số #{i}")
                
                col1, col2, col3 = st.columns(3)
                prov = col1.text_input("Nhà đài", value=ticket.get("province", ""), key=f"p_{i}")
                date_str = col2.text_input("Ngày xổ (DD-MM-YYYY)", value=ticket.get("draw_date", ""), key=f"d_{i}")
                num = col3.text_input("Số dự thưởng (6 chữ số)", value=ticket.get("ticket_number", ""), key=f"n_{i}")
                
                if not num or len(num) != 6:
                    st.warning("Vui lòng kiểm tra lại dãy số (phải đủ 6 chữ số).")
                    continue
                    
                slug = get_slug(prov)
                if not slug:
                    st.warning("Vui lòng gõ tên đài chính xác (Ví dụ: TP.HCM, Hậu Giang, Long An...)")
                    continue
                
                if not date_str:
                    st.warning("Vui lòng nhập ngày xổ (Ví dụ: 19-09-2026)")
                    continue
                    
                with st.spinner(f"🔍 Đang tra cứu KQXS đài {prov} ngày {date_str}..."):
                    kqxs = fetch_kqxs(slug, date_str)
                    
                    if not kqxs:
                        st.error(f"Không tìm thấy KQXS đài {prov} ngày {date_str}. Vui lòng kiểm tra lại ngày/đài!")
                    else:
                        winning_list = check_ticket_all_prizes(num, kqxs)
                        
                        if winning_list:
                            st.balloons()
                            st.success(f"🎊 **CHÚC MỪNG! VÉ SỐ {num} TRÚNG {len(winning_list)} GIẢI THƯỞNG:**")
                            for win in winning_list:
                                st.write(f"- {win}")
                        else:
                            st.info(f"❌ Vé `{num}` không trúng giải nào. Chúc bạn may mắn lần sau!")
                            
                        with st.expander("📄 Xem Bảng KQXS chi tiết"):
                            st.json(kqxs)
                            
        except Exception as e:
            st.error(f"⚠️ Máy chủ Google Gemini đang quá tải tạm thời. Bạn vui lòng đợi 3-5 giây rồi tải lại ảnh nhé!\nChi tiết: {e}")
