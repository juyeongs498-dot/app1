"""둘의 하루 · Streamlit 커플 다이어리
배포: 이 파일과 requirements.txt를 GitHub에 올리고 Streamlit Community Cloud에서
app.py를 선택합니다. Supabase SQL Editor에서 아래 SETUP_SQL을 한 번 실행하고,
Streamlit 앱 Settings > Secrets에 아래 값을 입력합니다(키를 GitHub에 올리지 마세요).
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_SECRET_KEY"
APP_URL = "https://YOUR_APP.streamlit.app"

서버 전용 service_role/secret key를 사용합니다. 브라우저에는 전달하지 않습니다.
커플 초대 문구는 12자 이상으로 만들고 상대에게만 전달하세요.
먼저 A가 방을 만들고 B가 같은 초대 문구로 가입합니다. 각자 비밀번호는 별도입니다.
같은 날짜에는 각자 일기 하나를 저장하며 수정하면 상대의 읽음 표시가 초기화됩니다.
QR은 앱을 여는 링크일 뿐, 로그인 정보나 초대 문구를 포함하지 않습니다.
"""
import hashlib
import hmac
import io
import secrets
from datetime import datetime, timedelta, timezone

import qrcode
import requests
import streamlit as st

SETUP_SQL = """-- Supabase SQL Editor에서 한 번 실행
create table public.couple_rooms (
 id text primary key,
 a_name text not null, a_hash text not null,
 b_name text, b_hash text
);
create table public.couple_diaries (
 room_id text not null references public.couple_rooms(id) on delete cascade,
 day date not null,
 author text not null check (author in ('a','b')),
 mood text not null,
 body text not null check (char_length(body) between 1 and 600),
 revision text not null,
 read_at timestamptz,
 primary key (room_id, day, author)
);
alter table public.couple_rooms enable row level security;
alter table public.couple_diaries enable row level security;
-- 공개/로그인 클라이언트 접근 금지. 서버의 service_role 키만 사용합니다.
revoke all on public.couple_rooms from anon, authenticated;
revoke all on public.couple_diaries from anon, authenticated;
"""

st.set_page_config(page_title='둘의 하루', page_icon='💌', layout='centered', initial_sidebar_state='collapsed')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap');
html,body,[class*="css"]{font-family:'Noto Sans KR',sans-serif}
.stApp{background:#fff9f7;color:#403436}
.block-container{max-width:460px;padding:1rem .85rem .5rem!important}
header[data-testid="stHeader"]{height:0;background:transparent}
[data-testid="stToolbar"],#MainMenu,footer{display:none}
[data-testid="stVerticalBlock"]{gap:.35rem}
h1{font-size:1.5rem!important;padding:0!important;margin:0!important}
p{margin-bottom:.25rem} .stCaption{font-size:.75rem}
[data-testid="stTextArea"] textarea{font-size:14px;min-height:86px!important}
.stButton button,.stFormSubmitButton button{min-height:36px;border-radius:12px}
[data-testid="stForm"]{border-color:#f0d9d6;border-radius:16px;padding:.65rem}
[data-testid="stDateInput"]{max-width:100%}
@media(max-width:480px){.block-container{padding-top:.5rem!important}}
</style>''', unsafe_allow_html=True)

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()
MOODS = ['🥰 행복', '🙂 평온', '🥺 보고파', '😴 피곤', '😔 우울', '😤 속상']


def config(key):
    try:
        return str(st.secrets.get(key, '')).strip()
    except Exception:
        return ''


URL = config('SUPABASE_URL').rstrip('/')
KEY = config('SUPABASE_SERVICE_ROLE_KEY')


def api(method, table, params=None, data=None, prefer=None):
    headers = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    response = requests.request(method, f'{URL}/rest/v1/{table}', headers=headers,
                                params=params, json=data, timeout=15)
    if not response.ok:
        # 원문 응답에는 개인정보가 있을 수 있어 사용자 화면에 출력하지 않습니다.
        raise RuntimeError(f'저장소 요청 실패 ({response.status_code})')
    return response.json() if response.content else []


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 300000).hex()
    return f'{salt}${digest}'


def verify(password, stored):
    try:
        salt, digest = stored.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 300000).hex()
        return hmac.compare_digest(digest, actual)
    except (ValueError, TypeError, AttributeError):
        return False


st.title('💌 둘의 하루')
st.caption('오늘의 마음을 남기고, 서로의 하루를 안아주세요.')

if not URL or not KEY:
    st.info('처음 한 번만 저장소를 연결해주세요. 일기는 서버 재시작 후에도 유지됩니다.')
    with st.expander('① Supabase 테이블 만들기', expanded=True):
        st.code(SETUP_SQL, language='sql')
    with st.expander('② Streamlit Secrets 설정'):
        st.code('SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\nSUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_SECRET_KEY"\nAPP_URL = "https://YOUR_APP.streamlit.app"', language='toml')
        st.caption('Supabase의 서버 전용 service_role 또는 secret key를 입력하세요. 공개용 anon/publishable key가 아닙니다. Secrets는 GitHub가 아닌 Streamlit 설정에 저장하세요.')
    st.stop()

if 'login' not in st.session_state:
    with st.form('login_form'):
        mode = st.selectbox('접속 방법', ['로그인', '처음 시작 · A 방 만들기', '초대받았어요 · B 가입'])
        invite = st.text_input('우리만의 초대 문구 (12자 이상)', type='password', max_chars=100)
        who = st.selectbox('내 자리 (로그인할 때 선택)', ['A', 'B'])
        name = st.text_input('내 애칭 (가입할 때만)', max_chars=12)
        password = st.text_input('내 비밀번호 (8자 이상)', type='password', max_chars=128)
        submitted = st.form_submit_button('함께 시작하기', use_container_width=True, type='primary')
    st.caption('A가 먼저 방 생성 → 초대 문구를 상대에게 전달 → B가 가입. 각자 비밀번호는 다르게 설정하세요.')
    if submitted:
        if len(invite.strip()) < 12 or len(password) < 8:
            st.warning('초대 문구는 12자 이상, 비밀번호는 8자 이상 입력해주세요.')
        elif mode != '로그인' and not name.strip():
            st.warning('가입할 때 사용할 애칭을 입력해주세요.')
        else:
            last = st.session_state.get('last_attempt')
            now = datetime.now(timezone.utc)
            if last and (now - last).total_seconds() < 2:
                st.warning('잠시 후 다시 시도해주세요.')
                st.stop()
            st.session_state.last_attempt = now
            room_id = hashlib.sha256(invite.strip().encode()).hexdigest()
            try:
                rows = api('GET', 'couple_rooms', {'id': f'eq.{room_id}', 'select': '*'})
                room = rows[0] if rows else None
                role = who.lower()
                if mode == '처음 시작 · A 방 만들기':
                    if room:
                        st.warning('이미 사용 중인 초대 문구입니다. 로그인하거나 다른 문구로 생성해주세요.')
                        st.stop()
                    role = 'a'
                    api('POST', 'couple_rooms', data={'id': room_id, 'a_name': name.strip(), 'a_hash': password_hash(password)})
                elif mode == '초대받았어요 · B 가입':
                    if not room or room.get('b_hash'):
                        st.warning('초대 문구를 확인해주세요. 이미 B로 가입했다면 로그인해주세요.')
                        st.stop()
                    role = 'b'
                    claimed = api('PATCH', 'couple_rooms', {'id': f'eq.{room_id}', 'b_hash': 'is.null'},
                                  {'b_name': name.strip(), 'b_hash': password_hash(password)}, 'return=representation')
                    if not claimed:
                        st.warning('이미 가입 처리되었습니다. 로그인해주세요.')
                        st.stop()
                elif not room or not verify(password, room.get(f'{role}_hash')):
                    st.warning('초대 문구, 내 자리 또는 비밀번호를 확인해주세요.')
                    st.stop()
                st.session_state.login = {'room': room_id, 'role': role}
                st.rerun()
            except (requests.RequestException, RuntimeError):
                st.error('연결 또는 가입에 실패했어요. 테이블·서버 키·네트워크를 확인한 후 다시 시도해주세요.')
    st.stop()

login = st.session_state.login
room_id, role = login['room'], login['role']
other = 'b' if role == 'a' else 'a'
try:
    rooms = api('GET', 'couple_rooms', {'id': f'eq.{room_id}', 'select': 'a_name,b_name'})
    if not rooms:
        st.session_state.clear()
        st.rerun()
    room = rooms[0]
except (requests.RequestException, RuntimeError):
    st.error('저장소에 연결하지 못했어요. 잠시 후 새로고침해주세요.')
    st.stop()

c1, c2, c3 = st.columns([5, 1.3, 1.3])
with c1:
    day = st.date_input('기록 날짜', value=TODAY, max_value=TODAY, label_visibility='collapsed')
with c2:
    if st.button('↻', help='상대의 새 일기와 읽음 상태 확인', use_container_width=True):
        st.rerun()
with c3:
    with st.popover('⋯', use_container_width=True):
        st.caption(f"{room.get(role + '_name') or role.upper()}의 자리 · {role.upper()}")
        app_url = config('APP_URL')
        if app_url.startswith('https://'):
            image = qrcode.make(app_url)
            output = io.BytesIO()
            image.save(output, format='PNG')
            st.image(output.getvalue(), caption='카메라로 스캔하면 앱이 열려요', width=180)
            st.download_button('QR 이미지 저장', output.getvalue(), 'couple-diary-qr.png', 'image/png')
        else:
            st.caption('배포 후 Secrets에 APP_URL을 https:// 주소로 설정하면 QR이 표시됩니다.')
        if st.button('로그아웃'):
            st.session_state.clear()
            st.rerun()

try:
    entries = api('GET', 'couple_diaries', {'room_id': f'eq.{room_id}', 'day': f'eq.{day.isoformat()}', 'select': '*'})
except (requests.RequestException, RuntimeError):
    st.error('일기를 불러오지 못했어요. ↻ 버튼으로 다시 시도해주세요.')
    st.stop()
by_author = {row['author']: row for row in entries}
mine, theirs = by_author.get(role), by_author.get(other)

with st.form(f'write_{day.isoformat()}', clear_on_submit=False):
    st.caption('✏️ 내 하루 · ' + ('상대가 확인했어요 ✓' if mine and mine['read_at'] else '아직 확인 전' if mine else '짧게 남겨도 좋아요'))
    old_mood = mine['mood'] if mine else MOODS[0]
    mood = st.selectbox('오늘의 기분', MOODS, index=MOODS.index(old_mood) if old_mood in MOODS else 0, label_visibility='collapsed')
    body = st.text_area('오늘의 이야기', value=mine['body'] if mine else '', height=90,
                        max_chars=600, placeholder='오늘 너에게 들려주고 싶은 이야기…', label_visibility='collapsed')
    save = st.form_submit_button('💗 수정 저장' if mine else '💗 마음 남기기', use_container_width=True, type='primary')
if save:
    if not body.strip():
        st.warning('오늘의 이야기를 한 줄 남겨주세요.')
    elif mine and mine['body'] == body.strip() and mine['mood'] == mood:
        st.toast('이미 저장된 내용이에요 💗')
    else:
        try:
            api('POST', 'couple_diaries', {'on_conflict': 'room_id,day,author'},
                {'room_id': room_id, 'day': day.isoformat(), 'author': role, 'mood': mood,
                 'body': body.strip(), 'revision': secrets.token_hex(16), 'read_at': None},
                'resolution=merge-duplicates')
            st.rerun()
        except (requests.RequestException, RuntimeError):
            st.error('저장하지 못했어요. 작성한 글은 그대로 있으니 다시 시도해주세요.')

with st.container(border=True):
    # 애칭과 본문은 HTML에 삽입하지 않고 일반 텍스트로만 출력합니다.
    partner_name = room.get(other + '_name') or '상대'
    st.caption(f'💌 {partner_name}의 하루' + (f" · {theirs['mood']}" if theirs else ''))
    if theirs:
        # 긴 글은 페이지 전체 대신 카드 안에서만 스크롤합니다.
        with st.container(height=110, border=False):
            st.text(theirs['body'])
        if theirs['read_at']:
            st.caption('✓ 확인한 마음이에요')
        elif st.button('✓ 읽었어요 · 내 마음 전달하기', use_container_width=True):
            try:
                updated = api('PATCH', 'couple_diaries',
                    {'room_id': f'eq.{room_id}', 'day': f'eq.{day.isoformat()}',
                     'author': f'eq.{other}', 'revision': f"eq.{theirs['revision']}"},
                    {'read_at': datetime.now(timezone.utc).isoformat()}, 'return=representation')
                if updated:
                    st.rerun()
                else:
                    st.warning('상대가 글을 수정했어요. ↻로 최신 글을 읽어주세요.')
            except (requests.RequestException, RuntimeError):
                st.error('읽음 표시를 저장하지 못했어요. 다시 눌러주세요.')
    else:
        st.caption('상대가 아직 마음을 남기지 않았어요 🌷')
        st.caption('B가 아직 가입 전이라면 초대 문구를 전달해주세요.' if not room.get('b_name') else '새 글은 ↻ 버튼으로 확인할 수 있어요.')
st.caption('우리만의 작은 기록 · 수정하면 읽음 표시가 초기화돼요')
