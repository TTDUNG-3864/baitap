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

# Thử import mammoth (để đọc file Word)
try:
    import mammoth
    HAS_MAMMOTH = True
except ImportError:
    HAS_MAMMOTH = False

# --- CẤU HÌNH ---
st.set_page_config(page_title="ÔN TẬP", page_icon="🏫", layout="wide")

# Tên thư mục gốc trên Drive (Nơi chứa mọi dữ liệu)
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
        # 1. Tìm file token.json (Chạy được cả Local và Render nếu dùng Secret Files)
        if os.path.exists("token.json"):
            try:
                self.creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc file token.json: {e}")
                st.stop()
        
        # 2. Dự phòng: Tìm trong st.secrets
        elif getattr(st, "secrets", None) and "gcp_token" in st.secrets:
            try:
                self.creds = Credentials.from_authorized_user_info(json.loads(st.secrets["gcp_token"]), SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc Secrets: {e}")
                st.stop()
        
        # 3. Không tìm thấy gì cả
        else:
            st.error("⚠️ CHƯA CÓ TOKEN XÁC THỰC!")
            st.info("👉 Trên Laptop: Hãy đảm bảo file `token.json` nằm cùng thư mục với file này.")
            st.info("👉 Trên Render: Hãy vào Environment > Secret Files > Upload file `token.json` lên với tên chính xác là `token.json`.")
            st.stop()

        # Kết nối API
        try:
            self.service = build('drive', 'v3', credentials=self.creds)
            self.check_setup()
        except Exception as e:
            st.error(f"Lỗi kết nối Google Drive: {e}")
            st.info("Mẹo: File token.json có thể đã hết hạn. Hãy chạy lại `get_token.py` để lấy file mới.")
            st.stop()

    def check_setup(self):
        try:
            # Tìm thư mục gốc
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

            # Tìm file database.json
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
        # Admin mặc định của bạn
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
        file = self.service.files().create(body=meta, media_body=media, fields='id, webViewLink').execute()
        return file.get('id')

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

# --- LOGIC RESET PASS (Thêm mới) ---
def reset_password_logic(username, fullname):
    new_hash = hash_password(DEFAULT_PASS)
    # Check Admin
    if username in mgr.db['admins'] and mgr.db['admins'][username]['fullname'] == fullname:
        mgr.db['admins'][username]['password'] = new_hash
        mgr.save_db(); return True
    # Check User
    if username in mgr.db['users'] and mgr.db['users'][username]['fullname'] == fullname:
        mgr.db['users'][username]['password'] = new_hash
        mgr.save_db(); return True
    return False

# --- HÀM HIỂN THỊ FILE ---
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

# --- UI: MÀN HÌNH CHÍNH ---
def login_screen():
    st.markdown("<h1 style='text-align: center; color: #4A90E2;'>Cổng Đăng Nhập</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        # THÊM TAB QUÊN MẬT KHẨU VÀO ĐÂY
        t1, t2, t3 = st.tabs(["Đăng Nhập", "Đăng Ký", "Quên Mật Khẩu"])
        
        # 1. Đăng Nhập
        with t1:
            with st.form("login"):
                u = st.text_input("Nhập tên đăng nhập")
                p = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Xác nhận", use_container_width=True):
                    hp = hash_password(p)
                    user = mgr.db['admins'].get(u) or mgr.db['users'].get(u)
                    if user and user['password'] == hp:
                        tk = create_session(u, user['role'], user['fullname'])
                        st.query_params["token"] = tk; st.rerun()
                    else: st.error("Sai thông tin!")
        
        # 2. Đăng Ký
        with t2:
            with st.form("reg"):
                nn = st.text_input("Họ tên")
                nu = st.text_input("Tên đăng nhập")
                np = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Đăng Ký", use_container_width=True):
                    if nu in mgr.db['users'] or nu in mgr.db['admins']: st.error("Trùng tên!")
                    elif nu and np:
                        mgr.db['users'][nu] = {"password": hash_password(np), "fullname": nn, "role": "student"}
                        mgr.save_db(); st.success("Xong!"); st.rerun()

        # 3. Quên Mật Khẩu (Đã thêm vào)
        with t3:
            with st.form("forgot"):
                f_u = st.text_input("Tên đăng nhập")
                f_n = st.text_input("Họ tên đầy đủ")
                if st.form_submit_button("Lấy lại Mật Khẩu", use_container_width=True):
                    if reset_password_logic(f_u, f_n):
                        st.success(f"Thành công! Mật khẩu mới là: {DEFAULT_PASS}")
                        st.info("Hãy quay lại tab Đăng Nhập để vào.")
                    else:
                        st.error("Không tìm thấy thông tin trùng khớp!")

def teacher_interface(sess):
    st.sidebar.title(f"GV: {sess['fullname']}")
    with st.sidebar.expander("Tạo Lớp"):
        nc = st.text_input("Tên lớp")
        if st.button("Thêm"):
            if nc not in mgr.db['classes']:
                fid = mgr.create_folder(nc, mgr.root_id)
                mgr.db['classes'][nc] = {"id": fid, "assignments": {}}
                mgr.save_db(); st.success("Xong!"); st.rerun()
    
    classes = list(mgr.db['classes'].keys())
    if not classes: st.info("Chưa có lớp."); return
    sel_cl = st.sidebar.selectbox("Lớp", classes)
    cl_data = mgr.db['classes'][sel_cl]
    st.title(f"Lớp: {sel_cl}")

    with st.expander("➕ Giao Bài"):
        typ = st.radio("Loại:", ["File", "Link Drive"], horizontal=True)
        ttl = st.text_input("Tên bài")
        cnt, is_lk = None, False
        if typ == "File": 
            uf = st.file_uploader("Chọn file")
            if uf: cnt = uf
        else: 
            lk = st.text_input("Link:")
            if lk: cnt = io.BytesIO(lk.encode()); is_lk = True
        
        if st.button("Đăng") and ttl and cnt:
            if ttl not in cl_data['assignments']:
                with st.spinner("Đang đăng..."):
                    aid = mgr.create_folder(ttl, cl_data['id'])
                    sid = mgr.create_folder("Bai_Nop", aid)
                    gid = mgr.create_folder("Da_Cham", aid)
                    fn = f"{ttl}.gdrive" if is_lk else cnt.name
                    res = mgr.upload_file(cnt, fn, aid)
                    cl_data['assignments'][ttl] = {
                        "id": aid, "sub_id": sid, "grad_id": gid,
                        "prompt": {"id": res['id'], "name": fn, "is_link": is_lk},
                        "submissions": [], "graded_files": []
                    }
                    mgr.save_db(); st.success("Xong!"); st.rerun()

    st.divider()
    assigns = cl_data['assignments']
    if not assigns: st.info("Chưa có bài tập."); return
    sel_ass = st.selectbox("Chọn bài:", list(assigns.keys()))
    adata = assigns[sel_ass]

    subs = {}
    for s in adata.get('submissions', []):
        subs.setdefault(s['student'], []).append(s)
    
    for stu, files in subs.items():
        sname = mgr.db['users'].get(stu, {}).get('fullname', stu)
        with st.expander(f"👤 {sname} ({len(files)} file)"):
            cols = st.columns(4)
            for i, f in enumerate(files):
                with cols[i%4]:
                    st.write(f"📄 {f['name']}")
                    c = get_file_content_from_drive(f['id'])
                    if c: st.download_button("⬇️", c, f['name'], key=f"d_{f['id']}")
            
            fg = st.file_uploader("Chấm:", key=f"g_{stu}_{sel_ass}")
            if fg and st.button("Gửi", key=f"b_{stu}_{sel_ass}"):
                fn = f"CHAM_{stu}_{fg.name}"
                res = mgr.upload_file(fg, fn, adata['grad_id'])
                if 'graded_files' not in adata: adata['graded_files'] = []
                adata['graded_files'].append({"student": stu, "id": res['id'], "name": fn})
                mgr.save_db(); st.success("Đã trả bài!")

def student_interface(sess, u):
    st.sidebar.title(f"HS: {sess['fullname']}")
    classes = list(mgr.db['classes'].keys())
    if not classes: st.warning("Chưa có lớp."); return
    sel_cl = st.sidebar.selectbox("Lớp", classes)
    adata = mgr.db['classes'][sel_cl]['assignments']
    if not adata: st.info("Chưa có bài."); return
    sel_ass = st.selectbox("Bài tập", list(adata.keys()))
    data = adata[sel_ass]

    st.write("### 📄 Đề Bài")
    preview_file_cloud(data['prompt'])
    
    st.write("---")
    my_g = [f for f in data.get('graded_files', []) if f['student'] == u]
    if my_g:
        st.success("Đã có bài chấm!")
        for g in my_g:
            c = get_file_content_from_drive(g['id'])
            if c: st.download_button(f"⬇️ {g['name']}", c, g['name'], key=f"dg_{g['id']}")

    st.write("---")
    up = st.file_uploader("Nộp bài (Nhiều file):", accept_multiple_files=True)
    if st.button("Nộp") and up:
        with st.spinner("Đang nộp..."):
            cnt = 0
            for f in up:
                fn = f"{sess['fullname']}_{f.name}"
                res = mgr.upload_file(f, fn, data['sub_id'])
                data['submissions'].append({
                    "student": u, "id": res['id'], "name": fn, 
                    "time": datetime.datetime.now().isoformat()
                })
                cnt += 1
            mgr.save_db(); st.success(f"Nộp {cnt} file!"); st.rerun()
            
    mys = [s for s in data['submissions'] if s['student'] == u]
    if mys:
        st.caption("Đã nộp:"); 
        for s in mys: st.text(f"✅ {s['name']}")

def main():
    token = st.query_params.get("token")
    sess = validate_session(token)
    if sess:
        if mgr.db['admins'].get(sess['username'], {}).get('password') == hash_password(DEFAULT_PASS):
            st.toast("⚠️ Hãy đổi mật khẩu mặc định!", icon="🔒")
        
        c1, c2 = st.columns([6, 1])
        with c1.popover("Đổi mật khẩu"):
            np = st.text_input("Mới", type="password")
            if st.button("Lưu"):
                if change_password_logic(sess['username'], sess['role'], np):
                    st.success("Xong! Đăng nhập lại."); logout_session(token); st.rerun()
        if c2.button("Logout"): logout_session(token); st.query_params.clear(); st.rerun()
        
        st.divider()
        if sess['role'] == 'teacher': teacher_interface(sess)
        else: student_interface(session, session['username'])
    else: login_screen()

if __name__ == "__main__":
    main()