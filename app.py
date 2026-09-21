import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
from PIL import Image
from google import genai
from google.genai import types

# Cấu hình giao diện Streamlit
st.set_page_config(page_title="Dò Vé Số AI", page_icon="🎫", layout="centered")

st.title("🎫 Dò Vé Số Tự Động Bằng AI")
st.caption("Tải ảnh vé số -> AI đọc thông tin -> Dò tất cả các giải thưởng tự động")

# Lấy Gemini API Key từ cấu hình bí mật Streamlit
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    st.error("⚠️ Chưa cài đặt GEMINI_API_KEY! Vui lòng kiểm tra lại cấu hình Secrets trên Streamlit.")
    st.stop()

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
    """
    Thuật toán dò vé số:
    - Kiểm tra LẦN LƯỢT TẤT CẢ CÁC GIẢI.
    - Một vé số có thể trúng NHIỀU GIẢI CÙNG LÚC (ví dụ vừa trúng Giải 8 vừa trúng Giải 7).
    """
    results = []
    ticket_num = str(ticket_num).zfill(6)
    
    # 1. Tìm Giải Đặc Biệt để xét nhóm Đặc Biệt / An Ủi / Khuyến Khích
    gdb = None
    for k in kqxs.keys():
        if "Đặc biệt" in k or "ĐB" in k or "DB" in k:
            if kqxs[k]:
                gdb = kqxs[k][0]
            break

    if gdb and len(gdb) == 6:
        # Giải Đặc Biệt (6 số)
        if ticket_num == gdb:
            results.append("🏆 **GIẢI ĐẶC BIỆT** (2 Tỷ đồng)")
        # Giải Phụ Đặc Biệt / An Ủi (Sai số đầu, 5 số cuối giống GĐB)
        elif ticket_num[0] != gdb[0] and ticket_num[1:] == gdb[1:]:
            results.append("🎁 **GIẢI PHỤ ĐẶC BIỆT (AN ỦI)** (50 Triệu đồng)")
        # Giải Khuyến Khích (Đúng số đầu, sai đúng 1 số trong 5 số còn lại)
        elif ticket_num[0] == gdb[0]:
            mismatch = sum(1 for i in range(1, 6) if ticket_num[i] != gdb[i])
            if mismatch == 1:
                results.append("🎁 **GIẢI KHUYẾN KHÍCH** (6 Triệu đồng)")

    # 2. Kiểm tra tất cả các Giải còn lại (G1 đến G8)
    for prize_name, nums in kqxs.items():
        if "Đặc biệt" in prize_name or "ĐB" in prize_name or "DB" in prize_name:
            continue
            
        for num in nums:
            num = str(num).strip()
            length = len(num)
            if length in [2, 3, 4, 5, 6]:
                # So sánh đuôi của vé số với các dãy số trúng thưởng
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
    res = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[image, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(res.text)

# --- GIAO DIỆN WEB ---
uploaded_file = st.file_uploader("📸 Chọn ảnh chụp vé số của bạn", type=["jpg", "jpeg", "png", "webp"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Ảnh vé số đã tải lên", use_container_width=True)
    
    with st.spinner("🤖 AI đang đọc thông tin vé số..."):
        try:
            tickets = extract_from_image(image)
            st.success(f"Phát hiện {len(tickets)} vé số trong ảnh!")
            
            for i, ticket in enumerate(tickets, 1):
                st.write("---")
                st.subheader(f"🎫 Vé số #{i}")
                
                # Cho phép người dùng kiểm tra lại và chỉnh sửa nếu muốn
                col1, col2, col3 = st.columns(3)
                prov = col1.text_input("Nhà đài", value=ticket.get("province", ""), key=f"p_{i}")
                date_str = col2.text_input("Ngày xổ (DD-MM-YYYY)", value=ticket.get("draw_date", ""), key=f"d_{i}")
                num = col3.text_input("Số dự thưởng", value=ticket.get("ticket_number", ""), key=f"n_{i}")
                
                slug = get_slug(prov)
                if not slug:
                    st.warning(f"Chưa hỗ trợ hoặc không tìm thấy mã đường dẫn cho nhà đài: **{prov}**")
                    continue
                
                with st.spinner(f"🔍 Đang truy cập KQXS đài {prov} ngày {date_str}..."):
                    kqxs = fetch_kqxs(slug, date_str)
                    
                    if not kqxs:
                        st.error(f"Khônng tìm thấy KQXS đài {prov} ngày {date_str}. Có thể do chưa tới giờ xổ hoặc sai ngày!")
                    else:
                        # Thực hiện dò giải
                        winning_list = check_ticket_all_prizes(num, kqxs)
                        
                        if winning_list:
                            st.balloons() # Bắn bóng bay ăn mừng
                            st.success(f"🎊 **CHÚC MỪNG! VÉ SỐ {num} TRÚNG {len(winning_list)} GIẢI THƯỞNG:**")
                            for win in winning_list:
                                st.write(f"- {win}")
                        else:
                            st.info(f"❌ Vé `{num}` không trúng giải nào. Chúc bạn may mắn lần sau!")
                            
                        # Hiển thị bảng KQXS chi tiết để người dùng đối soát
                        with st.expander("📄 Bấm để xem Bảng KQXS chi tiết của đài này"):
                            st.json(kqxs)
                            
        except Exception as e:
            st.error(f"Có lỗi khi xử lý ảnh: {e}")
