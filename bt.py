import streamlit as st
import json
import hashlib
import os
import io
import datetime
import uuid
import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# Thử import mammoth
try:
    import mammoth
    HAS_MAMMOTH = True
except ImportError:
    HAS_MAMMOTH = False

# --- CẤU HÌNH ---
st.set_page_config(page_title="ÔN TẬP", page_icon="🏫", layout="wide")

# Tên thư mục gốc trên Drive
ROOT_FOLDER_NAME = "DU_LIEU_LOP_HOC" 
DEFAULT_PASS = "hocSinh2025"
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- GOOGLE DRIVE MANAGER ---
class DriveManager:
    def __init__(self):
        self.creds = None
        self.service = None
        self.root_id = None
        self.db_file_id = None
        self.db = {"users": {}, "admins": {}, "sessions": {}, "classes": {}}
        self.init_drive()

    def init_drive(self):
        # 1. Tìm file token.json (Local)
        if os.path.exists("token.json"):
            try:
                self.creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc file token.json: {e}")
                st.stop()
        
        # 2. Tìm trong Secrets (Render)
        elif getattr(st, "secrets", None) and "gcp_token" in st.secrets:
            try:
                self.creds = Credentials.from_authorized_user_info(json.loads(st.secrets["gcp_token"]), SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc Secrets: {e}")
                st.stop()
        
        # 3. Không tìm thấy
        else:
            st.error("⚠️ CHƯA CÓ TOKEN XÁC THỰC!")
            st.info("👉 Laptop: Cần file `token.json` cùng thư mục.")
            st.info("👉 Render: Cần upload nội dung `token.json` vào Secret Files.")
            st.stop()

        # Kết nối API
        try:
            self.service = build('drive', 'v3', credentials=self.creds)
            self.check_setup()
        except Exception as e:
            st.error(f"Lỗi kết nối Google Drive: {e}")
            st.stop()

    def check_setup(self):
        try:
            query = f"name = '{ROOT_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
            
            if not files:
                file_metadata = {
                    'name': ROOT_FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                file = self.service.files().create(body=file_metadata, fields='id').execute()
                self.root_id = file.get('id')
            else:
                self.root_id = files[0]['id']

            query = f"name = 'database.json' and '{self.root_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])

            if files:
                self.db_file_id = files[0]['id']
                self.load_db()
            else:
                self.init_default_admin()
                self.save_db(create_new=True)
        except Exception as e:
            st.error(f"Lỗi setup hệ thống: {e}")
            st.stop()

    def init_default_admin(self):
        admin_pass = hashlib.sha256("TTD2006@".encode()).hexdigest()
        self.db["admins"] = {
            "TTD2006": { "password": admin_pass, "fullname": "TRẦN TIẾN DŨNG", "role": "teacher" }
        }

    def load_db(self):
        try:
            request = self.service.files().get_media(fileId=self.db_file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            fh.seek(0)
            self.db = json.load(fh)
        except:
            self.init_default_admin()

    def save_db(self, create_new=False):
        fh = io.BytesIO(json.dumps(self.db, ensure_ascii=False, indent=2).encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='application/json')
        if create_new:
            meta = {'name': 'database.json', 'parents': [self.root_id]}
            file = self.service.files().create(body=meta, media_body=media, fields='id').execute()
            self.db_file_id = file.get('id')
        else:
            self.service.files().update(fileId=self.db_file_id, media_body=media).execute()

    def create_folder(self, name, parent_id):
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
        file = self.service.files().create(body=meta, fields='id').execute()
        return file.get('id')

    def upload_file(self, file_obj, name, parent_id):
        media = MediaIoBaseUpload(file_obj, mimetype='application/octet-stream', resumable=True)
        meta = {'name': name, 'parents': [parent_id]}
        # SỬA LỖI TẠI ĐÂY: Trả về cả object file thay vì chỉ ID
        file = self.service.files().create(body=meta, media_body=media, fields='id, webViewLink').execute()
        return file 

# --- KHỞI TẠO SINGLETON ---
if 'drive_mgr' not in st.session_state:
    st.session_state.drive_mgr = DriveManager()
mgr = st.session_state.drive_mgr

# --- CÁC HÀM LOGIC ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(username, role, fullname):
    token = str(uuid.uuid4())
    expiry = (datetime.datetime.now() + datetime.timedelta(hours=12)).isoformat()
    mgr.db['sessions'] = {k:v for k,v in mgr.db['sessions'].items() if v['username'] != username}
    mgr.db['sessions'][token] = {"username": username, "role": role, "fullname": fullname, "expiry": expiry}
    mgr.save_db()
    return token

def validate_session(token):
    if not token or token not in mgr.db['sessions']: return None
    sess = mgr.db['sessions'][token]
    if datetime.datetime.now() < datetime.datetime.fromisoformat(sess['expiry']): return sess
    del mgr.db['sessions'][token]; mgr.save_db(); return None

def logout_session(token):
    if token in mgr.db['sessions']: del mgr.db['sessions'][token]; mgr.save_db()

def get_file_content_from_drive(file_id):
    try:
        request = mgr.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except: return None

def get_preview_link(drive_url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
    if not match: match = re.search(r'id=([a-zA-Z0-9_-]+)', drive_url)
    drive_id = match.group(1) if match else None
    if drive_id:
        if "docs.google.com" in drive_url:
            if "presentation" in drive_url: return f"https://docs.google.com/presentation/d/{drive_id}/preview"
            elif "spreadsheets" in drive_url: return f"https://docs.google.com/spreadsheets/d/{drive_id}/preview"
            return f"https://docs.google.com/document/d/{drive_id}/preview"
        return f"https://drive.google.com/file/d/{drive_id}/preview"
    return None

def change_password_logic(username, role, new_pass):
    hashed = hash_password(new_pass)
    db = mgr.db['admins'] if role == 'teacher' else mgr.db['users']
    if username in db:
        db[username]['password'] = hashed
        mgr.save_db(); return True
    return False

def reset_password_logic(username, fullname):
    new_hash = hash_password(DEFAULT_PASS)
    if username in mgr.db['admins'] and mgr.db['admins'][username]['fullname'] == fullname:
        mgr.db['admins'][username]['password'] = new_hash
        mgr.save_db(); return True
    if username in mgr.db['users'] and mgr.db['users'][username]['fullname'] == fullname:
        mgr.db['users'][username]['password'] = new_hash
        mgr.save_db(); return True
    return False

# --- HÀM PREVIEW FILE ---
def preview_file_cloud(prompt):
    if prompt['is_link']:
        content = get_file_content_from_drive(prompt['id'])
        if content:
            link = content.read().decode('utf-8')
            p_link = get_preview_link(link)
            if p_link: st.markdown(f'<iframe src="{p_link}" width="100%" height="600" style="border: 1px solid #ccc;"></iframe>', unsafe_allow_html=True)
            else: st.warning("Link không xem trước được.")
    else:
        content = get_file_content_from_drive(prompt['id'])
        if content:
            st.download_button(f"⬇️ Tải đề: {prompt['name']}", content, file_name=prompt['name'])
            ext = os.path.splitext(prompt['name'])[1].lower()
            if ext in ['.png','.jpg','.jpeg']: st.image(content)
            elif ext == '.pdf':
                b64 = base64.b64encode(content.getvalue()).decode()
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="800"></iframe>', unsafe_allow_html=True)
            elif ext in ['.docx','.doc'] and HAS_MAMMOTH:
                res = mammoth.convert_to_html(content)
                st.markdown(f'<div style="background:white;color:black;padding:20px;">{res.value}</div>', unsafe_allow_html=True)

# --- UI ---
def login_screen():
    st.markdown("<h1 style='text-align: center; color: #4A90E2;'>Cổng Đăng Nhập</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        t1, t2, t3 = st.tabs(["Đăng Nhập", "Đăng Ký", "Quên Mật Khẩu"])
        with t1:
            with st.form("login"):
                u = st.text_input("User")
                p = st.text_input("Pass", type="password")
                if st.form_submit_button("Vào Lớp", use_container_width=True):
                    hp = hash_password(p)
                    user = mgr.db['admins'].get(u) or mgr.db['users'].get(u)
                    if user and user['password'] == hp:
                        tk = create_session(u, user['role'], user['fullname'])
                        st.query_params["token"] = tk; st.rerun()
                    else: st.error("Sai thông tin!")
        with t2:
            with st.form("reg"):
                nn = st.text_input("Họ tên")
                nu = st.text_input("User mới")
                np = st.text_input("Pass mới", type="password")
                if st.form_submit_button("Đăng Ký", use_container_width=True):
                    if nu in mgr.db['users'] or nu in mgr.db['admins']: st.error("Trùng tên!")
                    elif nu and np:
                        mgr.db['users'][nu] = {"password": hash_password(np), "fullname": nn, "role": "student"}
                        mgr.save_db(); st.success("Xong!"); st.rerun()
        with t3:
            with st.form("forgot"):
                fu = st.text_input("User")
                fn = st.text_input("Họ tên")
                if st.form_submit_button("Lấy Lại"):
                    if reset_password_logic(fu, fn): st.success(f"Mật khẩu mới: {DEFAULT_PASS}")
                    else: st.error("Không tìm thấy!")

def teacher_interface(sess):
    st.sidebar.title(f"GV: {sess['fullname']}")
    
    with st.sidebar.expander("Tạo Lớp Mới"):
        new_cl = st.text_input("Mã lớp")
        if st.button("Thêm"):
            if new_cl not in mgr.db['classes']:
                fid = mgr.create_folder(new_cl, mgr.root_id)
                mgr.db['classes'][new_cl] = {"id": fid, "assignments": {}}
                mgr.save_db()
                st.success("Xong!")
                st.rerun()

    classes = list(mgr.db['classes'].keys())
    if not classes: st.info("Chưa có lớp nào."); return
    sel_cl = st.sidebar.selectbox("Chọn lớp", classes)
    cl_data = mgr.db['classes'][sel_cl]
    st.title(f"Lớp: {sel_cl}")

    # Giao bài
    with st.expander("➕ Giao Bài Tập Mới", expanded=True):
        atype = st.radio("Nguồn:", ["Upload File", "Link Drive"], horizontal=True)
        title = st.text_input("Tên bài tập")
        f_content, is_link = None, False
        
        if atype == "Upload File":
            uf = st.file_uploader("Chọn file", label_visibility="collapsed")
            if uf: f_content = uf
        else:
            dl = st.text_input("Link Drive:")
            if dl: f_content = io.BytesIO(dl.encode()); is_link = True

        if st.button("Đăng Bài"):
            if title and f_content:
                if title not in cl_data['assignments']:
                    with st.spinner("Đang tải lên..."):
                        ass_fid = mgr.create_folder(title, cl_data['id'])
                        sub_fid = mgr.create_folder("Bai_Nop", ass_fid)
                        grad_fid = mgr.create_folder("Da_Cham", ass_fid)
                        fname = f"{title}.gdrive" if is_link else f_content.name
                        f_drive = mgr.upload_file(f_content, fname, ass_fid)
                        
                        cl_data['assignments'][title] = {
                            "id": ass_fid, "sub_id": sub_fid, "grad_id": grad_fid,
                            "prompt": {"id": f_drive['id'], "name": fname, "is_link": is_link},
                            "submissions": [], "graded_files": []
                        }
                        mgr.save_db()
                        st.success("Đã giao!")
                        st.rerun()
                else: st.warning("Trùng tên bài!")

    # Chấm bài
    st.divider()
    assigns = cl_data['assignments']
    if not assigns: st.info("Lớp này chưa có bài tập."); return
    
    sel_ass = st.selectbox("Chọn bài tập chấm:", list(assigns.keys()))
    ass_data = assigns[sel_ass]
    
    # --- PHẦN SỬA LỖI Ở ĐÂY: Kiểm tra kỹ cấu trúc dữ liệu ---
    # Đảm bảo graded_files là list
    if 'graded_files' not in ass_data:
        ass_data['graded_files'] = []

    # Gom bài
    subs_by_stu = {}
    submissions = ass_data.get('submissions', [])
    if isinstance(submissions, list): # Kiểm tra submissions có phải là list không
        for s in submissions:
            if isinstance(s, dict): # Kiểm tra từng phần tử có phải dict không
                u = s.get('student')
                if u:
                    if u not in subs_by_stu: subs_by_stu[u] = []
                    subs_by_stu[u].append(s)
    
    for stu, files in subs_by_stu.items():
        user_info = mgr.db['users'].get(stu, {})
        stu_name = user_info.get('fullname', stu) if isinstance(user_info, dict) else stu
        
        with st.expander(f"👤 {stu_name} (Đã nộp {len(files)} file)"):
            cols = st.columns(4)
            for i, f in enumerate(files):
                with cols[i%4]:
                    # Kiểm tra f là dict trước khi truy cập
                    if isinstance(f, dict):
                        f_name = f.get('name', 'Unknown')
                        f_id = f.get('id')
                        st.write(f"📄 {f_name}")
                        if f_id:
                            content = get_file_content_from_drive(f_id)
                            if content: st.download_button("⬇️ Tải", content, file_name=f_name, key=f"dl_{f_id}")
            
            st.caption("Trả bài chấm:")
            c1, c2 = st.columns([3, 1])
            fg = c1.file_uploader("", key=f"gu_{stu}_{sel_ass}", label_visibility="collapsed")
            if c2.button("Gửi", key=f"gb_{stu}_{sel_ass}") and fg:
                with st.spinner("Đang gửi..."):
                    fname = f"CHAM_{stu}_{fg.name}"
                    res = mgr.upload_file(fg, fname, ass_data['grad_id'])
                    
                    ass_data['graded_files'].append({"student": stu, "id": res['id'], "name": fname})
                    mgr.save_db()
                    st.success("Đã trả bài!")

def student_interface(sess, u):
    st.sidebar.title(f"HS: {sess['fullname']}")
    classes = list(mgr.db['classes'].keys())
    if not classes: st.warning("Chưa có lớp."); return
    sel_cl = st.sidebar.selectbox("Lớp", classes)
    cl_data = mgr.db['classes'][sel_cl]
    
    assigns = cl_data['assignments']
    if not assigns: st.info("Chưa có bài tập."); return
    sel_ass = st.selectbox("Bài tập", list(assigns.keys()))
    ass_data = assigns[sel_ass]
    
    # Xem đề
    st.write("### 📄 Đề Bài")
    preview_file_cloud(ass_data['prompt'])
    
    st.write("---")
    # Xem bài chấm
    my_graded = [f for f in ass_data.get('graded_files', []) if f['student'] == u]
    if my_graded:
        st.success("Đã có bài chấm!")
        for g in my_graded:
            c1, c2 = st.columns([3, 1])
            c1.write(f"📝 {g['name']}")
            gc = get_file_content_from_drive(g['id'])
            if gc: c2.download_button("Tải về", gc, file_name=g['name'], key=f"gd_{g['id']}")

    st.write("---")
    # Nộp bài
    uploaded = st.file_uploader("Nộp bài làm (Nhiều file)", accept_multiple_files=True)
    if st.button("Nộp Bài") and uploaded:
        with st.spinner("Đang nộp..."):
            count = 0
            for f in uploaded:
                fname = f"{sess['fullname']}_{f.name}"
                res = mgr.upload_file(f, fname, ass_data['sub_id'])
                ass_data['submissions'].append({
                    "student": u, "id": res['id'], "name": fname, 
                    "time": datetime.datetime.now().isoformat()
                })
                count += 1
            mgr.save_db()
            st.success(f"Đã nộp {count} file!")
            st.rerun()
            
    my_subs = [s for s in ass_data['submissions'] if s['student'] == u]
    if my_subs:
        st.caption("Các file đã nộp:")
        for s in my_subs: st.text(f"✅ {s['name']}")

def main():
    token = st.query_params.get("token")
    sess = validate_session(token) # Lấy session và gán vào biến 'sess'
    
    if sess: # Kiểm tra sess có tồn tại không
        # Check mật khẩu mặc định
        default_hash = hash_password(DEFAULT_PASS)
        # Sửa lỗi ở đây: Dùng 'sess' thay vì 'session'
        current_pass = mgr.db['admins'][sess['username']]['password'] if sess['role'] == 'teacher' else mgr.db['users'][sess['username']]['password']
        
        if current_pass == default_hash:
            st.toast(f"⚠️ Đang dùng pass mặc định: {DEFAULT_PASS}", icon="🔒")

        c1, c2, c3 = st.columns([5, 1.5, 1])
        with c2.popover("🔐 Đổi mật khẩu"):
            new_p = st.text_input("Pass mới", type="password")
            if st.button("Lưu"):
                # Sửa lỗi ở đây: Dùng 'sess' thay vì 'session'
                if change_password_logic(sess['username'], sess['role'], new_p):
                    st.success("Xong! Đăng nhập lại.")
                    logout_session(token); st.query_params.clear(); st.rerun()

        if c3.button("Logout"):
            logout_session(token); st.query_params.clear(); st.rerun()
        
        st.divider()
        # Sửa lỗi ở đây: Dùng 'sess' thay vì 'session'
        if sess['role'] == 'teacher': 
            teacher_interface(sess)
        else: 
            student_interface(sess, sess['username'])
    else:
        login_screen()

if __name__ == "__main__":
    main()