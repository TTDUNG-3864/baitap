import streamlit as st
import os
import json
import hashlib
import shutil
import uuid
import base64
import re  # Import thêm regex để xử lý link Drive
from datetime import datetime, timedelta

# Thử import mammoth
try:
    import mammoth
    HAS_MAMMOTH = True
except ImportError:
    HAS_MAMMOTH = False

# --- CẤU HÌNH ---
st.set_page_config(page_title="ÔN TẬP", page_icon="🏫", layout="wide")

BASE_DIR = "du_lieu_nha_truong"
CLASSES_DIR = os.path.join(BASE_DIR, "danh_sach_lop")
USER_DB_FILE = os.path.join(BASE_DIR, "users.json")       
ADMIN_DB_FILE = os.path.join(BASE_DIR, "admins.json")     
SESSION_DB_FILE = os.path.join(BASE_DIR, "sessions.json")

DEFAULT_PASS = "HocSinh@2025" 

if not os.path.exists(CLASSES_DIR): os.makedirs(CLASSES_DIR)

# --- XỬ LÝ DATA ---
def load_json(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

if not os.path.exists(ADMIN_DB_FILE):
    default_admins = {
        "admin": { 
            "password": hash_password("admin123"), 
            "fullname": "Thầy Giáo Chủ Nhiệm",
            "role": "teacher"
        }
    }
    save_json(ADMIN_DB_FILE, default_admins)

# --- SESSION ---
def create_session(username, role, fullname):
    token = str(uuid.uuid4())
    expiry = (datetime.now() + timedelta(hours=12)).isoformat()
    sessions = load_json(SESSION_DB_FILE)
    clean_sessions = {k: v for k, v in sessions.items() if v['username'] != username}
    clean_sessions[token] = {
        "username": username, "role": role, "fullname": fullname, "expiry": expiry
    }
    save_json(SESSION_DB_FILE, clean_sessions)
    return token

def validate_session(token):
    if not token: return None
    sessions = load_json(SESSION_DB_FILE)
    if token in sessions:
        sess = sessions[token]
        if datetime.now() < datetime.fromisoformat(sess['expiry']):
            return sess
        else:
            del sessions[token]
            save_json(SESSION_DB_FILE, sessions)
    return None

def logout_session(token):
    sessions = load_json(SESSION_DB_FILE)
    if token in sessions:
        del sessions[token]
        save_json(SESSION_DB_FILE, sessions)

def reset_password_logic(username, fullname):
    new_hash = hash_password(DEFAULT_PASS)
    admins = load_json(ADMIN_DB_FILE)
    if username in admins and admins[username]['fullname'] == fullname:
        admins[username]['password'] = new_hash
        save_json(ADMIN_DB_FILE, admins)
        return True
    students = load_json(USER_DB_FILE)
    if username in students and students[username]['fullname'] == fullname:
        students[username]['password'] = new_hash
        save_json(USER_DB_FILE, students)
        return True
    return False

def change_password_logic(username, role, new_pass):
    hashed_new = hash_password(new_pass)
    db = load_json(ADMIN_DB_FILE) if role == 'teacher' else load_json(USER_DB_FILE)
    file = ADMIN_DB_FILE if role == 'teacher' else USER_DB_FILE
    if username in db:
        db[username]['password'] = hashed_new
        save_json(file, db)
        return True
    return False

# --- HÀM HỖ TRỢ GOOGLE DRIVE ---
def extract_drive_id(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match: return match.group(1)
    match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match: return match.group(1)
    return None

def generate_preview_link(drive_url, drive_id):
    if "docs.google.com" in drive_url:
        if "presentation" in drive_url: 
            return f"https://docs.google.com/presentation/d/{drive_id}/preview"
        elif "spreadsheets" in drive_url: 
            return f"https://docs.google.com/spreadsheets/d/{drive_id}/preview"
        else: 
            return f"https://docs.google.com/document/d/{drive_id}/preview"
    else:
        return f"https://drive.google.com/file/d/{drive_id}/preview"

# --- HÀM HỖ TRỢ FILE PREVIEW ---
def preview_file(file_path):
    if not os.path.exists(file_path):
        st.error("File không tồn tại!")
        return

    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.gdrive':
        with open(file_path, 'r', encoding='utf-8') as f:
            drive_url = f.read().strip()
        
        drive_id = extract_drive_id(drive_url)
        if drive_id:
            preview_link = generate_preview_link(drive_url, drive_id)
            st.markdown("### 📄 Đề bài (Google Drive):")
            st.markdown(
                f'''
                <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                    <iframe 
                        src="{preview_link}" 
                        width="100%" 
                        height="800" 
                        allow="autoplay; encrypted-media; fullscreen"
                        allowfullscreen="true"
                        style="border: 1px solid #ccc; border-radius: 5px;">
                    </iframe>
                </div>
                ''', 
                unsafe_allow_html=True
            )
        else:
            st.error("Link Google Drive không hợp lệ.")

    elif file_ext == '.pdf':
        try:
            with open(file_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'''
                <object data="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="800px">
                    <div style="text-align: center; padding: 20px; background-color: #f0f2f6; border-radius: 10px;">
                        <p style="margin-bottom: 10px;">⚠️ Trình duyệt không hiển thị được khung xem trước.</p>
                        <a href="data:application/pdf;base64,{base64_pdf}" target="_blank" style="text-decoration: none;">
                            <button style="padding: 10px 20px; background-color: #ff4b4b; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                                📄 Nhấn vào đây để mở PDF trong Tab mới
                            </button>
                        </a>
                    </div>
                </object>
            '''
            st.markdown("### 📄 Xem trước đề bài (PDF):")
            st.markdown(pdf_display, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Không thể đọc file PDF: {e}")
    
    elif file_ext in ['.docx', '.doc']:
        if HAS_MAMMOTH:
            with open(file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value
            st.markdown("### 📄 Xem trước đề bài (Word):")
            st.markdown(f"""<div style="background-color: white; color: black; padding: 30px; border-radius: 5px; border: 1px solid #ccc;">{html}</div>""", unsafe_allow_html=True)
        else:
            st.warning("Server chưa cài thư viện 'mammoth'. Vui lòng tải về.")

    elif file_ext == '.txt':
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        st.markdown("### 📄 Xem trước đề bài (Text):")
        st.code(content)
        
    else:
        st.info(f"Định dạng {file_ext} chưa hỗ trợ xem trước. Vui lòng tải về.")

# --- HELPERS ---
def get_classes():
    if not os.path.exists(CLASSES_DIR): return []
    return [d for d in os.listdir(CLASSES_DIR) if os.path.isdir(os.path.join(CLASSES_DIR, d))]

def get_assignments(class_name):
    path = os.path.join(CLASSES_DIR, class_name, "bai_tap")
    if not os.path.exists(path): return []
    return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]

# --- UI: LOGIN ---
def login_screen():
    st.markdown("<h1 style='text-align: center; color: #4A90E2;'>Cổng Đăng Nhập</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab_login, tab_register, tab_forgot = st.tabs(["🔐 ĐĂNG NHẬP", "📝 ĐĂNG KÍ ", "❓ QUÊN MẬT KHẨU"])
        
        with tab_login:
            st.write("")
            with st.form("login_form"):
                user_in = st.text_input("Tên đăng nhập")
                pass_in = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("ĐĂNG NHẬP", use_container_width=True):
                    hashed = hash_password(pass_in)
                    admins = load_json(ADMIN_DB_FILE)
                    students = load_json(USER_DB_FILE)
                    found = None
                    if user_in in admins and admins[user_in]['password'] == hashed: found = admins[user_in]
                    elif user_in in students and students[user_in]['password'] == hashed: found = students[user_in]
                    
                    if found:
                        token = create_session(user_in, found['role'], found['fullname'])
                        st.query_params["token"] = token
                        st.rerun()
                    else: st.error("Sai thông tin đăng nhập!")

        with tab_register:
            with st.form("reg_form"):
                new_u = st.text_input("Tên tài khoản mới")
                new_p = st.text_input("Mật khẩu mới", type="password")
                new_name = st.text_input("Họ và tên học sinh")
                if st.form_submit_button("TẠO TÀI KHOẢN", use_container_width=True):
                    stds, ads = load_json(USER_DB_FILE), load_json(ADMIN_DB_FILE)
                    if new_u in stds or new_u in ads: st.error("Tên tài khoản đã tồn tại!")
                    elif not new_u or not new_p or not new_name: st.warning("Điền thiếu thông tin!")
                    else:
                        stds[new_u] = { "password": hash_password(new_p), "fullname": new_name, "role": "student" }
                        save_json(USER_DB_FILE, stds)
                        st.success("Đăng kí thành công! Hãy đăng nhập.")

        with tab_forgot:
            with st.form("forgot_form"):
                f_user = st.text_input("Tên đăng nhập")
                f_name = st.text_input("Họ tên đầy đủ")
                if st.form_submit_button("CẤP LẠI MẬT KHẨU", use_container_width=True):
                    if reset_password_logic(f_user, f_name):
                        st.success(f"Mật khẩu mới: {DEFAULT_PASS}")
                    else: st.error("Không tìm thấy thông tin!")

# --- UI: GIÁO VIÊN ---
def teacher_interface(user_data):
    st.sidebar.title(f"GV: {user_data['fullname']}")
    st.sidebar.header("Quản Lý")
    with st.sidebar.expander("Tạo Lớp Mới"):
        new_class = st.text_input("Mã lớp")
        if st.button("Thêm"):
            path = os.path.join(CLASSES_DIR, new_class, "bai_tap")
            if not os.path.exists(path):
                os.makedirs(path)
                st.success(f"Đã tạo {new_class}")
                st.rerun()
            else: st.warning("Đã có lớp này")

    classes = get_classes()
    if not classes:
        st.info("Chưa có lớp nào.")
        return

    selected_class = st.sidebar.selectbox("Chọn lớp:", classes)
    st.title(f"Lớp: {selected_class}")
    
    # 1. GIAO BÀI TẬP
    with st.expander("➕ Giao Bài Tập Mới", expanded=True):
        st.write("Chọn cách đăng đề bài:")
        upload_type = st.radio("Nguồn đề bài:", ["📂 Tải file từ máy tính", "☁️ Dán link Google Drive"], horizontal=True)
        
        c1, c2 = st.columns([2, 2])
        title = c1.text_input("Tên bài tập")
        
        file_content = None
        file_name = None
        is_drive_link = False
        
        if upload_type == "📂 Tải file từ máy tính":
            uploaded_file = c2.file_uploader("Chọn file (docx, pdf)", label_visibility="collapsed")
            if uploaded_file:
                file_content = uploaded_file.getbuffer()
                file_name = uploaded_file.name
        else:
            drive_link = c2.text_input("Dán link Google Drive vào đây")
            if drive_link:
                file_content = drive_link
                file_name = f"{title}.gdrive"
                is_drive_link = True

        if st.button("Đăng Bài"):
            if title and file_name and file_content:
                assign_dir = os.path.join(CLASSES_DIR, selected_class, "bai_tap", title)
                if not os.path.exists(assign_dir):
                    os.makedirs(os.path.join(assign_dir, "de_bai"))
                    os.makedirs(os.path.join(assign_dir, "bai_nop"))
                    os.makedirs(os.path.join(assign_dir, "bai_cham")) # Tạo thêm folder bài chấm
                    
                    save_path = os.path.join(assign_dir, "de_bai", file_name)
                    
                    if is_drive_link:
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(file_content)
                    else:
                        with open(save_path, "wb") as f:
                            f.write(file_content)
                            
                    st.success("Đã giao bài thành công!")
                    st.rerun()
                else: st.warning("Tên bài tập này đã tồn tại!")
            else:
                st.warning("Vui lòng nhập đầy đủ thông tin.")

    # 2. KIỂM TRA TIẾN ĐỘ
    st.write("---")
    st.subheader("📊 Kiểm Tra Tiến Độ")
    all_users = load_json(USER_DB_FILE)
    students = {u: d['fullname'] for u, d in all_users.items() if d.get('role') == 'student'}
    if students:
        selected_stu = st.selectbox("Chọn học sinh:", list(students.keys()), format_func=lambda x: f"{students[x]} ({x})")
        if selected_stu:
            assigns = get_assignments(selected_class)
            prog_data = []
            for asn in assigns:
                subs_path = os.path.join(CLASSES_DIR, selected_class, "bai_tap", asn, "bai_nop")
                graded_path = os.path.join(CLASSES_DIR, selected_class, "bai_tap", asn, "bai_cham")
                
                status, time_sub = "❌ Chưa nộp", "-"
                graded_status = "Chưa chấm"
                
                # Check nộp
                if os.path.exists(subs_path):
                    for f in os.listdir(subs_path):
                        if f.startswith(f"{selected_stu}_"):
                            status, time_sub = "✅ Đã nộp", datetime.fromtimestamp(os.path.getctime(os.path.join(subs_path, f))).strftime("%H:%M %d/%m")
                            break
                
                # Check chấm
                if os.path.exists(graded_path):
                     for f in os.listdir(graded_path):
                        if f.startswith(f"GRADED_{selected_stu}_"):
                            graded_status = "✅ Đã trả bài"
                            break

                prog_data.append({
                    "Bài Tập": asn, 
                    "Trạng Thái": status, 
                    "Thời Gian Nộp": time_sub,
                    "Tình Trạng Chấm": graded_status
                })
            st.table(prog_data)

    # 3. DANH SÁCH BÀI NỘP VÀ CHẤM ĐIỂM
    st.write("---")
    st.subheader("Danh sách bài nộp & Chấm điểm")
    assigns = get_assignments(selected_class)
    
    for asn in assigns:
        asn_dir = os.path.join(CLASSES_DIR, selected_class, "bai_tap", asn)
        subs_dir = os.path.join(asn_dir, "bai_nop")
        graded_dir = os.path.join(asn_dir, "bai_cham")
        if not os.path.exists(graded_dir): os.makedirs(graded_dir) # Đảm bảo folder tồn tại
        
        # Gom nhóm bài nộp theo học sinh
        student_submissions = {} # {username: [file1, file2]}
        if os.path.exists(subs_dir):
            for f in os.listdir(subs_dir):
                parts = f.split('_')
                if len(parts) >= 1:
                    u_name = parts[0]
                    if u_name not in student_submissions: student_submissions[u_name] = []
                    student_submissions[u_name].append(f)

        total_files = len(os.listdir(subs_dir)) if os.path.exists(subs_dir) else 0

        with st.expander(f"{asn} (Tổng file: {total_files})"):
            c_del, c_space = st.columns([1, 5])
            if c_del.button("🗑️ Xóa bài tập này", key=f"del_{asn}"): 
                shutil.rmtree(asn_dir)
                st.rerun()

            if not student_submissions:
                st.info("Chưa có học sinh nào nộp bài.")
            else:
                for stu_user, files in student_submissions.items():
                    stu_fullname = students.get(stu_user, stu_user)
                    
                    st.markdown(f"#### 👤 Học sinh: {stu_fullname} ({stu_user})")
                    
                    # Hiển thị file đã nộp
                    cols = st.columns(4)
                    for idx, file_name in enumerate(files):
                        file_path = os.path.join(subs_dir, file_name)
                        display_name = file_name.split('_')[-1] # Tên gốc
                        
                        with cols[idx % 4]:
                            if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                                st.image(file_path, caption=display_name)
                            else:
                                st.info(f"📄 {display_name}")
                            
                            with open(file_path, "rb") as f:
                                st.download_button("⬇️ Tải", f, file_name=display_name, key=f"dl_{asn}_{file_name}")

                    # --- KHU VỰC CHẤM BÀI (MỚI) ---
                    st.caption("👉 Gửi kết quả chấm / nhận xét cho học sinh này:")
                    uploaded_graded = st.file_uploader(
                        f"Tải lên file đã chấm cho {stu_fullname}", 
                        type=['png','jpg','jpeg','pdf','docx','txt'],
                        key=f"grade_{asn}_{stu_user}"
                    )
                    
                    if uploaded_graded:
                        # Lưu file với prefix GRADED_username_timestamp_filename
                        ts = datetime.now().strftime("%Y%m%d%H%M%S")
                        graded_name = f"GRADED_{stu_user}_{ts}_{uploaded_graded.name}"
                        with open(os.path.join(graded_dir, graded_name), "wb") as f:
                            f.write(uploaded_graded.getbuffer())
                        st.success(f"Đã gửi bài chấm cho {stu_fullname}!")
                        # st.rerun() # Có thể rerun nếu muốn cập nhật ngay lập tức

                    st.divider()

# --- UI: HỌC SINH ---
def student_interface(user_data, username):
    st.sidebar.title(f"HS: {user_data['fullname']}")
    st.title("Góc Học Tập")
    classes = get_classes()
    if not classes: st.warning("Chưa có lớp nào mở."); return
    my_class = st.selectbox("Chọn lớp:", classes)
    assigns = get_assignments(my_class)
    if not assigns: st.info("Chưa có bài tập."); return
    cur_assign = st.selectbox("Chọn bài:", assigns)
    
    assign_path = os.path.join(CLASSES_DIR, my_class, "bai_tap", cur_assign)
    prompt_path = os.path.join(assign_path, "de_bai")
    save_path = os.path.join(assign_path, "bai_nop")
    graded_path = os.path.join(assign_path, "bai_cham")
    
    # 1. ĐỀ BÀI
    if os.path.exists(prompt_path) and os.listdir(prompt_path):
        fname = os.listdir(prompt_path)[0]
        fpath = os.path.join(prompt_path, fname)
        preview_file(fpath)
        if not fname.endswith('.gdrive'):
            with open(fpath, "rb") as f:
                st.download_button(f"⬇️ Tải file đề gốc ({fname})", f, file_name=fname)
            
    st.write("---")
    
    # 2. BÀI ĐÃ CHẤM (MỚI)
    if os.path.exists(graded_path):
        my_graded = [f for f in os.listdir(graded_path) if f.startswith(f"GRADED_{username}_")]
        if my_graded:
            st.success("🎉 Giáo viên đã trả bài chấm cho bạn!")
            st.write("📂 **File nhận xét / chấm điểm:**")
            for g_file in my_graded:
                # Tên hiển thị: Bỏ prefix GRADED_username_timestamp_
                # Format: GRADED_user_ts_filename
                parts = g_file.split('_')
                disp_name = "_".join(parts[3:]) if len(parts) > 3 else g_file
                
                c1, c2 = st.columns([4, 1])
                c1.text(f"📝 {disp_name}")
                with open(os.path.join(graded_path, g_file), "rb") as f:
                    c2.download_button("⬇️ Tải về", f, file_name=disp_name, key=f"dl_graded_{g_file}")
            st.write("---")

    # 3. NỘP BÀI
    st.write("**Nộp bài làm:**")
    uploaded_files = st.file_uploader(
        "Chọn bài làm (Có thể chọn nhiều file):", 
        type=['png','jpg','jpeg', 'pdf', 'docx', 'doc', 'pptx', 'ppt', 'txt'],
        accept_multiple_files=True
    )
    
    if st.button("Gửi Bài"):
        if uploaded_files:
            if not os.path.exists(save_path): os.makedirs(save_path)
            
            count = 0
            for up in uploaded_files:
                # Thêm timestamp vào tên file
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                safe_name = "".join([c for c in user_data['fullname'] if c.isalnum() or c==' ']).replace(' ', '-')
                final_name = f"{username}_{safe_name}_{timestamp}_{up.name}"
                
                with open(os.path.join(save_path, final_name), "wb") as f:
                    f.write(up.getbuffer())
                count += 1
                
            st.success(f"Đã nộp thành công {count} file!")
            st.balloons()
            st.rerun() 
        else: st.error("Chưa chọn file nào!")

    # 4. DANH SÁCH ĐÃ NỘP
    if os.path.exists(save_path):
        my_files = [f for f in os.listdir(save_path) if f.startswith(f"{username}_")]
        if my_files:
            st.caption("📂 Các file bạn đã nộp:")
            for f_name in my_files:
                col1, col2 = st.columns([4, 1])
                display_name = f_name.split('_')[-1] 
                col1.text(f"📄 {display_name}")
                
                f_path = os.path.join(save_path, f_name)
                with open(f_path, "rb") as f:
                    col2.download_button("Tải xuống", f, file_name=display_name, key=f"dl_student_{f_name}")

# --- MAIN ---
def main():
    token = st.query_params.get("token")
    session = validate_session(token)
    if session:
        default_hash = hash_password(DEFAULT_PASS)
        current_db = load_json(ADMIN_DB_FILE) if session['role'] == 'teacher' else load_json(USER_DB_FILE)
        
        if session['username'] in current_db and current_db[session['username']]['password'] == default_hash:
            st.toast(f"⚠️ Đang dùng pass mặc định: {DEFAULT_PASS}", icon="🔒")

        c1, c2, c3 = st.columns([5, 1.5, 1])
        with c2.popover("🔐 Đổi mật khẩu"):
            new_p = st.text_input("Pass mới", type="password")
            conf_p = st.text_input("Nhập lại", type="password")
            if st.button("Đổi"):
                if new_p != conf_p or not new_p: st.error("Lỗi mật khẩu")
                elif change_password_logic(session['username'], session['role'], new_p):
                    st.success("Xong! Đăng nhập lại.")
                    logout_session(token); st.query_params.clear(); st.rerun()

        if c3.button("Đăng Xuất"):
            logout_session(token); st.query_params.clear(); st.rerun()

        st.divider()
        if session['role'] == 'teacher': teacher_interface(session)
        else: student_interface(session, session['username'])
    else:
        if token: st.query_params.clear(); st.rerun()
        login_screen()

if __name__ == "__main__":
    main()