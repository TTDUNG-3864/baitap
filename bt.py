import streamlit as st
import streamlit.components.v1 as components  
import json
import hashlib
import os
import io
import datetime
import uuid
import re
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

try:
    import mammoth
    HAS_MAMMOTH = True
except ImportError:
    HAS_MAMMOTH = False

st.set_page_config(page_title="ÔN TẬP", page_icon="🏫", layout="wide")

ROOT_FOLDER_NAME = "DU_LIEU_LOP_HOC" 
DEFAULT_PASS = "hocSinh2025"
SCOPES = ['https://www.googleapis.com/auth/drive']

class DriveManager:
    def __init__(self):
        self.creds = None
        self.service = None
        self.root_id = None
        self.db_file_id = None
        self.db = {"users": {}, "admins": {}, "sessions": {}, "classes": {}}
        self.init_drive()

    def init_drive(self):
        if os.path.exists("token.json"):
            try:
                self.creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc file token.json: {e}")
                st.stop()
        
        elif getattr(st, "secrets", None) and "gcp_token" in st.secrets:
            try:
                self.creds = Credentials.from_authorized_user_info(json.loads(st.secrets["gcp_token"]), SCOPES)
            except Exception as e:
                st.error(f"Lỗi đọc Secrets: {e}")
                st.stop()
        
        else:
            st.error("⚠️ CHƯA CÓ TOKEN XÁC THỰC!")
            st.info("👉 Laptop: Cần file `token.json` cùng thư mục.")
            st.info("👉 Render: Cần upload nội dung `token.json` vào Secret Files.")
            st.stop()

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
        admin_pass = hashlib.sha256("TTD2006".encode()).hexdigest()
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
        return file 

    def delete_file(self, file_id):
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            st.error(f"Không thể xóa trên Drive: {e}")
            return False

    def share_file_public(self, file_id):
        try:
            self.service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'},
                fields='id'
            ).execute()
        except Exception as e:
            pass

if 'drive_mgr' not in st.session_state:
    with st.spinner("Đang kết nối Google Drive..."):
        st.session_state.drive_mgr = DriveManager()
mgr = st.session_state.drive_mgr

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(username, role, fullname):
    token = str(uuid.uuid4())
    expiry = (datetime.datetime.now() + datetime.timedelta(hours=6)).isoformat()
    
    mgr.db['sessions'] = {k:v for k,v in mgr.db['sessions'].items() if v['username'] != username}
    
    mgr.db['sessions'][token] = {"username": username, "role": role, "fullname": fullname, "expiry": expiry}
    mgr.save_db()
    return token

def validate_session(token):
    if not token or token not in mgr.db['sessions']: return None
    sess = mgr.db['sessions'][token]
    
    now = datetime.datetime.now()
    expiry_time = datetime.datetime.fromisoformat(sess['expiry'])
    
    if now > expiry_time: 
        del mgr.db['sessions'][token]
        mgr.save_db()
        return None
    
    remaining_seconds = (expiry_time - now).total_seconds()
    if remaining_seconds < 5 * 3600: 
        new_expiry = (now + datetime.timedelta(hours=6)).isoformat()
        sess['expiry'] = new_expiry
        mgr.db['sessions'][token] = sess
        mgr.save_db()
        
    return sess

def logout_session(token):
    if token in mgr.db['sessions']: del mgr.db['sessions'][token]; mgr.save_db()

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_file_content(file_id):
    """Hàm tải file có sử dụng bộ nhớ đệm (Cache)"""
    try:
        service = st.session_state.drive_mgr.service 
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read() 
    except: return None

def get_file_content_from_drive(file_id):
    """Wrapper chuyển bytes từ cache thành BytesIO"""
    data = get_cached_file_content(file_id)
    if data:
        return io.BytesIO(data)
    return None

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

        if ext in ['.docx', '.doc']:
            c_view, c_dummy = st.columns([2, 3])
            with c_view:
                view_mode = st.radio("Chế độ xem:", ["Giao diện gốc (Drive)", "Chỉ hiện chữ (Nhanh)"], horizontal=True, key=f"vm_{prompt['id']}")
            
            if view_mode == "Giao diện gốc (Drive)":
                p_link = f"https://drive.google.com/file/d/{prompt['id']}/preview"
                st.markdown(f'<iframe src="{p_link}" width="100%" height="800" style="border: 1px solid #ccc; border-radius: 5px;"></iframe>', unsafe_allow_html=True)
                st.markdown(f'<a href="{p_link}" target="_blank" style="display:inline-block;margin-top:10px;text-decoration:none;background:#f0f2f6;padding:8px 12px;border-radius:5px;color:black;">🔗 Mở file gốc trong tab mới (Nếu bị lỗi hiển thị)</a>', unsafe_allow_html=True)
            
            else:
                if HAS_MAMMOTH and content:
                    res = mammoth.convert_to_html(content)
                    st.markdown(f'<div style="background:white;color:black;padding:20px;border:1px solid #ddd;">{res.value}</div>', unsafe_allow_html=True)
                else:
                    st.warning("Không thể trích xuất văn bản (Thiếu thư viện Mammoth hoặc file lỗi).")

        elif ext in ['.pptx', '.ppt', '.xlsx', '.xls']:
            p_link = f"https://drive.google.com/file/d/{prompt['id']}/preview"
            st.markdown(f'<iframe src="{p_link}" width="100%" height="800" style="border: 1px solid #ccc; border-radius: 5px;"></iframe>', unsafe_allow_html=True)
            st.markdown(f'<a href="{p_link}" target="_blank" style="display:inline-block;margin-top:10px;text-decoration:none;background:#f0f2f6;padding:8px 12px;border-radius:5px;color:black;">🔗 Mở file trong tab mới</a>', unsafe_allow_html=True)
            
        elif ext in ['.png','.jpg','.jpeg'] and content:
            st.image(content)
            
        elif ext == '.pdf' and content:
            b64 = base64.b64encode(content.getvalue()).decode()
            st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="800"></iframe>', unsafe_allow_html=True)

def login_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        t1, t2, t3 = st.tabs(["Đăng Nhập", "Đăng Ký", "Quên Mật Khẩu"])
        
        with t1:
            st.markdown("<h2 style='text-align: center; color: #4A90E2;'>Đăng Nhập</h2>", unsafe_allow_html=True)
            with st.form("login"):
                u = st.text_input("Tên đăng nhập")
                p = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Xác nhận", use_container_width=True):
                    hp = hash_password(p)
                    user = mgr.db['admins'].get(u) or mgr.db['users'].get(u)
                    if user and user['password'] == hp:
                        tk = create_session(u, user['role'], user['fullname'])
                        st.query_params["token"] = tk; st.rerun()
                    else: st.error("Sai thông tin!")
        
        with t2:
            st.markdown("<h2 style='text-align: center; color: #4A90E2;'>Đăng Ký Tài Khoản</h2>", unsafe_allow_html=True)
            with st.form("reg"):
                nn = st.text_input("Họ và tên")
                nu = st.text_input("Tên đăng nhập")
                np = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Đăng Ký", use_container_width=True):
                    if nu in mgr.db['users'] or nu in mgr.db['admins']: st.error("Trùng tên!")
                    elif nu and np:
                        mgr.db['users'][nu] = {"password": hash_password(np), "fullname": nn, "role": "student"}
                        mgr.save_db(); st.success("Xong!"); st.rerun()
        
        with t3:
            st.markdown("<h2 style='text-align: center; color: #4A90E2;'>Khôi Phục Mật Khẩu</h2>", unsafe_allow_html=True)
            with st.form("forgot"):
                fu = st.text_input("Tên đăng nhập")
                fn = st.text_input("Họ và tên")
                if st.form_submit_button("Lấy Lại", use_container_width=True):
                    if reset_password_logic(fu, fn): st.success(f"Mật khẩu mới: {DEFAULT_PASS}")
                    else: st.error("Không tìm thấy!")

def teacher_interface(sess):
    st.sidebar.title(f"GV: {sess['fullname']}")
    
    with st.sidebar.expander("Tạo Lớp Mới"):
        new_cl = st.text_input("Mã lớp")
        if st.button("Thêm"):
            if new_cl not in mgr.db['classes']:
                with st.spinner("Đang tạo lớp..."):
                    fid = mgr.create_folder(new_cl, mgr.root_id)
                    mgr.db['classes'][new_cl] = {"id": fid, "assignments": {}}
                    mgr.save_db()
                st.success("Xong!")
                st.rerun()

    classes = list(mgr.db['classes'].keys())
    if not classes: st.info("Chưa có lớp nào."); return
    
    sel_cl = st.sidebar.selectbox("Chọn lớp", classes)
    
    with st.sidebar.popover("🗑️ Xóa lớp này", use_container_width=True):
        st.write(f"Bạn chắc chắn muốn xóa lớp **{sel_cl}**?")
        st.warning("Toàn bộ bài tập và bài làm của học sinh sẽ bị xóa vĩnh viễn!")
        if st.button("Xác nhận Xóa Lớp", type="primary"):
            with st.spinner("Đang xóa dữ liệu trên Drive..."):
                cl_id = mgr.db['classes'][sel_cl]['id']
                if mgr.delete_file(cl_id):
                    del mgr.db['classes'][sel_cl]
                    mgr.save_db()
                    st.success("Đã xóa lớp!")
                    st.rerun()
                else:
                    st.error("Lỗi khi xóa folder trên Drive")

    cl_data = mgr.db['classes'][sel_cl]
    st.title(f"Lớp: {sel_cl}")

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
                    with st.spinner("Đang tải lên Drive..."):
                        ass_fid = mgr.create_folder(title, cl_data['id'])
                        sub_fid = mgr.create_folder("Bai_Nop", ass_fid)
                        grad_fid = mgr.create_folder("Da_Cham", ass_fid)
                        fname = f"{title}.gdrive" if is_link else f_content.name
                        f_drive = mgr.upload_file(f_content, fname, ass_fid)
                        
                        if not is_link:
                            mgr.share_file_public(f_drive['id'])

                        cl_data['assignments'][title] = {
                            "id": ass_fid, "sub_id": sub_fid, "grad_id": grad_fid,
                            "prompt": {"id": f_drive['id'], "name": fname, "is_link": is_link},
                            "submissions": [], "graded_files": []
                        }
                        mgr.save_db()
                        st.success("Đã giao!")
                        st.rerun()
                else: st.warning("Trùng tên bài!")

    st.divider()
    assigns = cl_data['assignments']
    if not assigns: st.info("Lớp này chưa có bài tập."); return
    
    col_sel, col_del = st.columns([5, 1])
    with col_sel:
        sel_ass = st.selectbox("Chọn bài tập chấm:", list(assigns.keys()))
    
    with col_del:
        st.write("") 
        st.write("") 
        with st.popover("🗑️", help="Xóa bài tập này"):
            st.write(f"Xóa bài **{sel_ass}**?")
            if st.button("Xóa ngay", type="primary"):
                with st.spinner("Đang xóa bài tập..."):
                    ass_id = assigns[sel_ass]['id']
                    if mgr.delete_file(ass_id):
                        del cl_data['assignments'][sel_ass]
                        mgr.save_db()
                        st.success("Đã xóa!")
                        st.rerun()
                    else:
                        st.error("Lỗi Drive")

    ass_data = assigns[sel_ass]
    
    if 'graded_files' not in ass_data:
        ass_data['graded_files'] = []

    subs_by_stu = {}
    submissions = ass_data.get('submissions', [])
    if isinstance(submissions, list): 
        for s in submissions:
            if isinstance(s, dict): 
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
                    if isinstance(f, dict):
                        f_name = f.get('name', 'Unknown')
                        f_id = f.get('id')
                        st.write(f"📄 {f_name}")
                        if f_id:
                            content = get_file_content_from_drive(f_id)
                            if content: st.download_button("⬇️ Tải", content, file_name=f_name, key=f"dl_{f_id}")
            
            st.caption("Trả bài chấm:")
            c1, c2 = st.columns([3, 1])
            fg = c1.file_uploader("File chấm", key=f"gu_{stu}_{sel_ass}", label_visibility="collapsed")
            if c2.button("Gửi", key=f"gb_{stu}_{sel_ass}") and fg:
                with st.spinner("Đang gửi bài chấm..."):
                    fname = f"CHAM_{stu}_{fg.name}"
                    res = mgr.upload_file(fg, fname, ass_data['grad_id'])
                    
                    ass_data['graded_files'].append({"student": stu, "id": res['id'], "name": fname})
                    mgr.save_db()
                    st.success("Đã trả bài!")

def student_interface(sess, u):
    st.sidebar.title(f"HS: {sess['fullname']}")
    
    st.sidebar.info("💡 **Mẹo:** Bookmark (Lưu) link này để lần sau vào luôn không cần đăng nhập!", icon="🔖")

    classes = list(mgr.db['classes'].keys())
    if not classes: st.warning("Chưa có lớp."); return
    sel_cl = st.sidebar.selectbox("Lớp", classes)
    cl_data = mgr.db['classes'][sel_cl]
    
    assigns = cl_data['assignments']
    if not assigns: st.info("Chưa có bài tập."); return
    sel_ass = st.selectbox("Bài tập", list(assigns.keys()))
    ass_data = assigns[sel_ass]
    
    st.write("### 📄 Đề Bài")
    preview_file_cloud(ass_data['prompt'])
    
    st.write("---")
    my_graded = [f for f in ass_data.get('graded_files', []) if f['student'] == u]
    if my_graded:
        st.success("Đã có bài chấm!")
        for g in my_graded:
            c1, c2 = st.columns([3, 1])
            c1.write(f"📝 {g['name']}")
            gc = get_file_content_from_drive(g['id'])
            if gc: c2.download_button("Tải về", gc, file_name=g['name'], key=f"gd_{g['id']}")

    st.write("---")
    uploaded = st.file_uploader("Nộp bài làm (Nhiều file)", accept_multiple_files=True)
    if st.button("Nộp Bài") and uploaded:
        with st.spinner("Đang nộp bài..."):
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
    
    if not token:
        components.html("""
        <script>
            const token = localStorage.getItem("edu_token");
            if (token) {
                // Nếu tìm thấy, tự động chuyển hướng thêm token vào URL
                window.parent.location.search = "?token=" + token;
            }
        </script>
        """, height=0)
    else:
        components.html(f"""
        <script>
            localStorage.setItem("edu_token", "{token}");
        </script>
        """, height=0)

    sess = validate_session(token) 
    
    if not sess and token:
         components.html("""<script>localStorage.removeItem("edu_token");</script>""", height=0)
         st.query_params.clear() 

    if sess: 
        default_hash = hash_password(DEFAULT_PASS)
        current_pass = mgr.db['admins'][sess['username']]['password'] if sess['role'] == 'teacher' else mgr.db['users'][sess['username']]['password']
        
        if current_pass == default_hash:
            st.toast(f"⚠️ Đang dùng pass mặc định: {DEFAULT_PASS}", icon="🔒")

        c1, c2, c3 = st.columns([5, 1.5, 1])
        with c2.popover("🔐 Đổi mật khẩu"):
            new_p = st.text_input("Pass mới", type="password")
            if st.button("Lưu"):
                if change_password_logic(sess['username'], sess['role'], new_p):
                    st.success("Xong! Đăng nhập lại.")
                    logout_session(token); st.query_params.clear(); st.rerun()

        if c3.button("Đăng xuất"):
            logout_session(token)
            st.query_params.clear()
            st.rerun()
        
        st.divider()
        if sess['role'] == 'teacher': 
            teacher_interface(sess)
        else: 
            student_interface(sess, sess['username'])
    else:
        login_screen()

if __name__ == "__main__":
    main()