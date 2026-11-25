"""Elemen tampilan PilahPintar: ikon SVG, warna tong, gaya CSS, dan potongan HTML.

File ini tidak memakai Streamlit, jadi isinya bisa diperiksa sendiri.
Gagasan desain: aplikasi ini disusun di sekitar tiga tong sampah yang sudah
dikenal orang Indonesia: hijau (organik), kuning (anorganik), merah (B3).
"""
from urllib.parse import quote

INK, MUTED, LINE, PAPER, BRAND = "#14231D", "#5C6B63", "#E1E7DF", "#F4F6F2", "#0B5D44"
WARNA_TONG = {"organik": "#2E7D32", "anorganik": "#F2B01E", "b3": "#C62828"}
NAMA_TONG = {"organik": "hijau", "anorganik": "kuning", "b3": "merah"}  # pola umum di Indonesia

IKON = {
    "beranda": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "panduan": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H12v16H5.5A1.5 1.5 0 0 0 4 21.5z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H12v16h6.5a1.5 1.5 0 0 1 1.5 1.5z"/>',
    "pindai": '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8"/><path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8"/><path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><circle cx="12" cy="12" r="3"/>',
    "misi": '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5.5A1.5 1.5 0 0 0 4 7.5 3.5 3.5 0 0 0 8 11"/><path d="M16 6h2.5A1.5 1.5 0 0 1 20 7.5 3.5 3.5 0 0 1 16 11"/><path d="M12 13v4"/><path d="M10 17h4"/><path d="M8.5 20h7"/>',
    "riwayat": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "daun": '<path d="M5 19C5 10 10 5 20 4c0 10-5 15-13 15"/><path d="M5 19c2-5 5-8 9-10"/>',
    "botol": '<path d="M10 3h4v3l1.5 3v10.5a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5V9L10 6z"/><path d="M8.5 13h7"/>',
    "bahaya": '<path d="M12 3.5 2.8 19.5h18.4z"/><path d="M12 10v4.5"/><path d="M12 17.2v.3"/>',
    "cek": '<path d="M5 12.5 10 17.5 19 7.5"/>',
    "tong": '<path d="M4 7h16"/><path d="M9.5 7V4h5v3"/><path d="M6.5 7 7.5 20h9L17.5 7"/><path d="M10 11v5"/><path d="M14 11v5"/>',
}
IKON_KATEGORI = {"organik": "daun", "anorganik": "botol", "b3": "bahaya"}


def ikon(nama, ukuran=20, warna="currentColor", tebal=2):
    """Membuat elemen SVG untuk ikon bernama."""
    return (f'<svg width="{ukuran}" height="{ukuran}" viewBox="0 0 24 24" fill="none" stroke="{warna}" '
            f'stroke-width="{tebal}" stroke-linecap="round" stroke-linejoin="round" '
            f'style="vertical-align:-4px; flex:none">{IKON[nama]}</svg>')


def terang(warna):
    """Menentukan apakah warna cukup terang untuk dipasangkan dengan teks gelap."""
    r, g, b = (int(warna[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b > 150


def teks_di(warna):
    """Warna teks yang terbaca di atas warna latar tertentu."""
    return INK if terang(warna) else "#FFFFFF"


def teks_aksen(warna):
    """Warna kategori untuk teks di atas putih. Kuning terlalu pucat, jadi dipakai teks gelap."""
    return INK if terang(warna) else warna


def css():
    """Menghasilkan stylesheet aplikasi dan ikon untuk navigasi."""
    ikon_nav = ""
    for kode in ("beranda", "panduan", "pindai", "misi", "riwayat"):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" '
               f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{IKON[kode]}</svg>')
        ikon_nav += f'.st-key-nav_{kode} {{--ikon: url("data:image/svg+xml,{quote(svg)}");}}\n'
    return """
@font-face {font-family: 'Poppins'; font-weight: 400; src: url(app/static/Poppins-Regular.ttf);}
@font-face {font-family: 'Poppins'; font-weight: 500; src: url(app/static/Poppins-Medium.ttf);}
@font-face {font-family: 'Poppins'; font-weight: 700; src: url(app/static/Poppins-Bold.ttf);}
@font-face {font-family: 'Lora'; font-weight: 400 700; src: url(app/static/Lora-Variable.ttf);}
html {font-size: 15px;}
.stApp {font-family: 'Poppins', 'Segoe UI', Roboto, system-ui, sans-serif; color: #14231D; line-height: 1.5;}
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] *, .stButton button p,
[data-testid="stWidgetLabel"] p, [data-testid="stMetric"] *, [data-testid="stTabs"] button p,
[data-testid="stAlert"] p, [data-testid="stCaptionContainer"] * {font-family: 'Poppins', 'Segoe UI', Roboto, system-ui, sans-serif;}
#MainMenu, footer, header {visibility: hidden;}
.block-container {max-width: 720px; padding: 1.2rem 1rem 7rem;}
.tampil {font-family: 'Lora', Georgia, serif !important; font-weight: 700; letter-spacing: -0.01em;}
.judul {font-size: 1.3rem; font-weight: 700; margin: 0.4rem 0 0.8rem; line-height: 1.25;}
.kecil {color: #5C6B63; font-size: 0.85rem;}
.angka {font-family: 'Lora', Georgia, serif !important; font-size: 2rem; font-weight: 700; line-height: 1.1; font-variant-numeric: lining-nums;}
.tengah {text-align: center;}
.stButton > button {border-radius: 14px; min-height: 3rem; font-weight: 500; width: 100%; background: #FFFFFF; border: 1px solid #D5DDD3; color: #14231D;}
.stButton > button:active {transform: scale(0.98);}
[data-testid="stBaseButton-primary"] {background: #0B5D44; border-color: #0B5D44; color: #FFFFFF;}
[data-testid="stBaseButton-primary"] p {color: #FFFFFF;}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primary"] span {color: #FFFFFF !important; opacity: 1 !important;}
[data-testid="stBaseButton-secondary"] p, [data-testid="stBaseButton-secondary"] span {color: #14231D !important; opacity: 1 !important;}
[data-testid="stBaseButton-primary"] {background: #0B5D44 !important; border-color: #0B5D44 !important;}
[data-testid="stBaseButton-secondary"] {background: #FFFFFF !important; border-color: #D5DDD3 !important;}
[data-testid="stImage"] img {border-radius: 22px; width: 100%; height: auto;}
[class*="st-key-kartu_"] {background: #FFFFFF; border: 1px solid #E1E7DF; border-radius: 18px; padding: 16px;}
.chip {display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 4px 12px; font-size: 0.8rem; font-weight: 500;}
.mint {background: #DDEFE5; color: #0B5D44;} .peach {background: #FBE7C6; color: #6B4300;} .abu {background: #E8EDE6; color: #14231D;}
.lav {background: #EBF1EA; border-radius: 14px; padding: 12px 14px; margin: 8px 0;}
.bar {height: 8px; background: #DCE5DA; border-radius: 6px; overflow: hidden; margin: 8px 0;}
.bar i {display: block; height: 100%; background: #0B5D44; border-radius: 6px;}
.baris {display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #E1E7DF;}
.baris img, .thumb {width: 54px; height: 54px; border-radius: 12px; object-fit: cover; background: #DDEFE5; flex: none;}
.kat {background: #FFFFFF; border: 1px solid #E1E7DF; border-radius: 16px; padding: 14px 16px; margin: 8px 0;}
.kat ul {margin: 6px 0 0; padding-left: 1.2rem;}
.scan-category {background:#FFFFFF; border:1px solid #E1E7DF; border-radius:18px; padding:14px; min-height:86px;}
.scan-category b {display:block; margin-top:6px;}
.hasil-status {display:flex; align-items:center; gap:12px; background:#EAF4EC; border:1px solid #D5E5D9;
 border-radius:18px; padding:14px; margin:12px 0;}
.hasil-status-ragu {background:#FFF5E4; border-color:#F0DFB9;}
.hasil-check {width:40px; height:40px; flex:none; border-radius:12px; background:#2E7D32; color:#FFFFFF;
 display:flex; align-items:center; justify-content:center; font-size:1.35rem; font-weight:700;}
.hasil-status-ragu .hasil-check {background:#A66A00;}
.hasil-grid {display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:8px 0 16px;}
.hasil-score {background:#FFFFFF; border:1px solid #E1E7DF; border-radius:18px; padding:14px; min-width:0;}
.hasil-score-head {font-weight:700; margin-bottom:10px;}
.hasil-score-content {display:flex; align-items:center; gap:10px;}
.hasil-score-content .kecil {font-size:.77rem;}
.hasil-type-unknown {font-weight:700; color:#5C6B63; font-size:.95rem;}
.hasil-type-note {font-size:.76rem; color:#5C6B63; margin-top:5px;}
.langkah {display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid #E1E7DF;}
.langkah .no {flex: none; width: 30px; height: 30px; border-radius: 50%; background: #0B5D44; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem;}
.hero {background: #0B5D44; border-radius: 28px; padding: 22px; color: #FFFFFF; margin-bottom: 12px;}
.tong {display: flex; align-items: center; gap: 16px; border-radius: 28px; padding: 20px 22px; margin: 14px 0 8px; animation: muncul 0.3s ease both;}
.tong .kecil-t {font-size: 0.85rem; opacity: 0.85;}
.tong .nama {font-family: 'Lora', Georgia, serif !important; font-size: 2.3rem; font-weight: 700; line-height: 1.05; margin: 2px 0 4px;}
.st-key-banner {background: #0B5D44; border-radius: 28px; padding: 22px; color: #FFFFFF;}
.st-key-banner [data-testid="stMarkdownContainer"] * {color: #FFFFFF;}
.st-key-banner .stButton button {background: #FFFFFF; border: 0;}
.st-key-banner .stButton button p {color: #0B5D44; font-weight: 700;}
.st-key-dampak_isi [data-testid="stHorizontalBlock"], .st-key-daftar_riwayat [data-testid="stHorizontalBlock"] {flex-wrap: nowrap; gap: 0.4rem; align-items: center;}
.st-key-dampak_isi [data-testid="stColumn"], .st-key-daftar_riwayat [data-testid="stColumn"] {min-width: 0;}
.st-key-nav {position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; max-width: 720px; margin: 0 auto; background: #FFFFFF;
 border-radius: 22px 22px 0 0; border-top: 1px solid #E1E7DF; padding: 8px 6px calc(8px + env(safe-area-inset-bottom, 0px));}
.st-key-nav [data-testid="stHorizontalBlock"] {flex-wrap: nowrap; align-items: flex-end; gap: 0.2rem;}
.st-key-nav [data-testid="stColumn"] {flex: 1 1 0 !important; min-width: 0 !important; width: auto !important;}
.st-key-nav .stButton button {display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
 min-height: 3.4rem; padding: 0.3rem 0; border: 0; border-radius: 14px; background: transparent; color: #5C6B63; box-shadow: none;}
.st-key-nav .stButton button::before {content: ""; width: 24px; height: 24px; background: currentColor;
 -webkit-mask: var(--ikon) center / contain no-repeat; mask: var(--ikon) center / contain no-repeat;}
.st-key-nav .stButton button p {font-size: 0.68rem; font-weight: 500; line-height: 1.1; color: inherit;}
.st-key-nav [data-testid="stBaseButton-primary"] {background: #DDEFE5; color: #0B5D44;}
.st-key-nav [data-testid="stBaseButton-primary"] p {color: #0B5D44; font-weight: 700;}
.st-key-nav_pindai {display: flex; justify-content: center;}
.st-key-nav .st-key-nav_pindai button {width: 68px !important; height: 68px !important; min-height: 68px !important; margin-top: -32px;
 border-radius: 50% !important; background: #0B5D44 !important; color: #FFFFFF !important; border: 4px solid #FFFFFF !important;}
.st-key-nav .st-key-nav_pindai button p {color: #FFFFFF !important;}
@keyframes muncul {from {opacity: 0; transform: translateY(8px);} to {opacity: 1; transform: none;}}
@media (prefers-reduced-motion: reduce) {* {animation: none !important; transition: none !important;}}
@media (max-width: 640px) {
 .block-container {padding: 0.9rem 0.75rem 7rem;} .judul {font-size: 1.2rem;} .angka {font-size: 1.6rem;}
 .tong {padding: 16px 16px;} .tong .nama {font-size: 1.9rem;} .hero, .st-key-banner {padding: 18px; border-radius: 24px;}
 [class*="st-key-kartu_"] {padding: 14px;} .chip {font-size: 0.75rem; padding: 3px 10px;}
 .st-key-dampak_isi .lav {padding: 8px 10px;} .st-key-dampak_isi .angka {font-size: 1.25rem !important;}
 .hasil-grid {gap:8px;} .hasil-score {padding:10px;} .hasil-score-content {flex-direction:column; align-items:flex-start;}
}
/* Visual refinement */
.stApp {background: linear-gradient(180deg, #F8FAF7 0%, #F4F6F2 240px, #F4F6F2 100%);}
.block-container {padding-top: 1.5rem; padding-bottom: 7.5rem;}
h1, h2, h3 {letter-spacing: -0.025em; color: #14231D;}
h1 {font-size: clamp(1.7rem, 5vw, 2.2rem) !important; line-height: 1.15 !important;}
h2 {font-size: 1.5rem !important;}
h3 {font-size: 1.15rem !important;}
[data-testid="stMarkdownContainer"] p {line-height: 1.6;}
[data-testid="stCaptionContainer"] {color: #5C6B63;}
.stButton > button {
 transition: transform .16s ease, box-shadow .16s ease, background-color .16s ease, border-color .16s ease;
 box-shadow: 0 1px 2px #14231D0A;
}
.stButton > button:hover {border-color: #9AB6A5; box-shadow: 0 4px 12px #14231D12; transform: translateY(-1px);}
.stButton > button:active {transform: translateY(0) scale(.985);}
[data-testid="stBaseButton-primary"] {box-shadow: 0 4px 12px #0B5D4426;}
[data-testid="stBaseButton-primary"]:hover {background: #084A36; border-color: #084A36;}
button:focus-visible, input:focus-visible, textarea:focus-visible {outline: 3px solid #78B99A !important; outline-offset: 2px;}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea {
 border-radius: 12px; border-color: #D5DDD3; background: #FFFFFF;
}
[data-baseweb="select"] > div {border-radius: 12px; border-color: #D5DDD3;}
[data-testid="stTabs"] [role="tablist"] {gap: 6px; border-bottom-color: #E1E7DF;}
[data-testid="stTabs"] button[role="tab"] {border-radius: 12px 12px 0 0; padding: .55rem .9rem;}
[data-testid="stTabs"] button[aria-selected="true"] {color: #0B5D44; font-weight: 700;}
[data-testid="stAlert"] {border-radius: 16px; border-width: 1px; box-shadow: 0 2px 8px #14231D08;}
[data-testid="stExpander"] {border: 1px solid #E1E7DF; border-radius: 14px; background: #FFFFFF;}
[data-testid="stExpander"] summary {padding: .2rem .25rem; font-weight: 500;}
[data-testid="stFileUploader"] section {border: 1.5px dashed #A9BDAE; border-radius: 16px; background: #FAFCF9;}
[data-testid="stMetric"] {
 background: #FFFFFF; border: 1px solid #E1E7DF; border-radius: 16px; padding: 14px 16px;
 box-shadow: 0 2px 8px #14231D08;
}
[data-testid="stImage"] img {box-shadow: 0 5px 18px #14231D12;}
[class*="st-key-kartu_"], .kat, .hasil-score, .scan-category {
 box-shadow: 0 2px 10px #14231D08; transition: box-shadow .18s ease, transform .18s ease;
}
.st-key-banner {box-shadow: 0 10px 24px #0B5D4420;}
.hero {box-shadow: 0 10px 24px #0B5D4420;}
.st-key-nav {
 box-shadow: 0 -8px 24px #14231D0D; border-color: #E1E7DF;
 background: #FFFFFFF2; backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.st-key-nav .stButton button {transition: background-color .16s ease, color .16s ease;}
.st-key-nav .stButton button:hover {background: #F1F6F2;}
.st-key-nav .st-key-nav_pindai button {box-shadow: 0 5px 14px #0B5D4433;}
@media (max-width: 640px) {
 .block-container {padding: 1rem .8rem 7.5rem;}
 .st-key-banner {padding: 18px;}
 [data-testid="stTabs"] button[role="tab"] {padding: .5rem .65rem; font-size: .9rem;}
 [data-testid="stMetric"] {padding: 11px 12px;}
 .st-key-nav {padding-left: 8px; padding-right: 8px;}
 .st-key-nav .stButton button {min-height: 3.2rem;}
}
@media (prefers-reduced-motion: reduce) {
 .stButton > button, [class*="st-key-kartu_"], .kat, .hasil-score, .scan-category {transition: none;}
}
.st-key-auth_page {max-width: 520px; margin: 0 auto; padding: 1.1rem 0 2rem;}
.st-key-auth_page > [data-testid="stVerticalBlock"] {gap: .75rem;}
.auth-brand {display:flex; align-items:center; gap:11px; margin:0 0 6px; color:#14231D;}
.auth-brand-mark {display:flex; align-items:center; justify-content:center; width:42px; height:42px; border-radius:15px;
 background:#DDEFE5; color:#0B5D44; font-size:25px; line-height:1;}
.auth-brand strong {display:block; font-size:1.04rem; letter-spacing:-.02em;}
.auth-brand small {display:block; margin-top:1px; color:#5C6B63; font-size:.75rem;}
.st-key-auth_page [data-testid="stMarkdownContainer"] svg[aria-label^="Tiga tong"] {max-width:245px !important; height:auto;}
.st-key-auth_page h1 {margin:.15rem 0 0 !important; text-align:center; font-size:clamp(1.8rem, 5vw, 2.15rem) !important;}
.st-key-auth_page > [data-testid="stVerticalBlock"] > [data-testid="stMarkdownContainer"] + [data-testid="stHeading"] + [data-testid="stCaptionContainer"] {
 text-align:center; margin-top:-.55rem; margin-bottom:.35rem;
}
.st-key-auth_card {padding:18px 22px 22px; background:#FFFFFF; border:1px solid #E1E7DF; border-radius:24px;
 box-shadow:0 12px 34px #14231D0D;}
.st-key-auth_card [data-testid="stTabs"] [role="tablist"] {display:flex; gap:4px; padding:4px; border:0;
 border-radius:14px; background:#F1F5F1;}
.st-key-auth_card [data-testid="stTabs"] [role="tab"] {flex:1; justify-content:center; padding:.62rem .4rem;
 border:0; border-radius:10px; color:#5C6B63; font-size:.86rem;}
.st-key-auth_card [data-testid="stTabs"] [role="tab"][aria-selected="true"] {background:#FFFFFF; color:#0B5D44;
 box-shadow:0 1px 5px #14231D14;}
.st-key-auth_card [data-testid="stTabs"] [role="tabpanel"] {padding-top:1rem;}
.auth-section-title {margin:0 0 2px; color:#14231D; font-size:1.05rem; font-weight:700; letter-spacing:-.015em;}
.auth-section-copy {margin:0 0 14px; color:#5C6B63; font-size:.83rem; line-height:1.55;}
.st-key-auth_card [data-testid="stTextInput"] label p {font-size:.84rem; font-weight:500; color:#263A30;}
.st-key-auth_card [data-testid="stTextInput"] input {min-height:2.9rem; border-radius:12px; background:#FCFDFC;}
.st-key-auth_card .stForm {border:0; padding:0; background:transparent;}
.st-key-auth_card .stForm [data-testid="stFormSubmitButton"] button {min-height:3rem; margin-top:.3rem; border-radius:13px;}
.st-key-auth_card [data-testid="stTabs"] [data-testid="stTabs"] [role="tablist"] {background:#EAF2EC;}
.st-key-auth_card [data-testid="stTabs"] [data-testid="stTabs"] [role="tab"] {font-size:.78rem;}
.auth-step {display:flex; align-items:flex-start; gap:10px; margin:3px 0 10px; padding:11px 12px;
 border:1px solid #E1EAE2; border-radius:14px; background:#F7FAF7;}
.auth-step > span {display:flex; flex:none; align-items:center; justify-content:center; width:25px; height:25px;
 border-radius:50%; background:#DDEFE5; color:#0B5D44; font-size:.78rem; font-weight:700;}
.auth-step strong, .auth-step small {display:block;}
.auth-step strong {color:#14231D; font-size:.84rem;}
.auth-step small {margin-top:2px; color:#5C6B63; font-size:.75rem; line-height:1.4;}
.auth-recovery-note {padding:11px 12px; border-radius:12px; background:#F1F6F2;}
.st-key-auth_page > [data-testid="stVerticalBlock"] > [data-testid="stCaptionContainer"]:last-child {
 margin-top:.15rem; text-align:center; font-size:.72rem;
}
@media (max-width: 640px) {
 .st-key-auth_page {padding-top:.35rem;}
 .st-key-auth_card {padding:14px 14px 18px; border-radius:20px;}
 .st-key-auth_card [data-testid="stTabs"] [role="tab"] {font-size:.77rem; padding:.58rem .2rem;}
 .st-key-auth_card [data-testid="stTabs"] [role="tabpanel"] {padding-top:.8rem;}
}
""" + ikon_nav


def html_tiga_tong():
    """Ilustrasi onboarding: tiga tong dengan warna yang sudah dikenal."""
    isi = ""
    data = [("Organik", WARNA_TONG["organik"], "daun", "#FFFFFF"), ("Anorganik", WARNA_TONG["anorganik"], "botol", INK),
            ("B3", WARNA_TONG["b3"], "bahaya", "#FFFFFF")]
    for i, (nama, warna, simbol, tinta) in enumerate(data):
        x = 12 + i * 108
        isi += (f'<rect x="{x}" y="38" width="88" height="14" rx="6" fill="{warna}"/>'
                f'<rect x="{x + 32}" y="30" width="24" height="10" rx="4" fill="{warna}"/>'
                f'<path d="M{x + 6} 56H{x + 82}L{x + 75} 144a6 6 0 0 1-6 5H{x + 19}a6 6 0 0 1-6-5z" fill="{warna}"/>'
                f'<svg x="{x + 28}" y="78" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="{tinta}" '
                f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{IKON[simbol]}</svg>'
                f'<text x="{x + 44}" y="174" text-anchor="middle" font-size="12" font-weight="500" fill="{INK}">{nama}</text>')
    return (f'<svg viewBox="0 0 330 184" width="100%" style="max-width:360px; display:block; margin:0 auto" role="img" '
            f'aria-label="Tiga tong sampah: hijau, kuning, merah">{isi}</svg>')


def html_lensa(ukuran=96):
    """Motif pemindai untuk banner."""
    return (f'<svg width="{ukuran}" height="{ukuran}" viewBox="0 0 96 96" fill="none" stroke="#FFFFFF" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true"><circle cx="48" cy="48" r="42" stroke-opacity="0.25" stroke-width="2"/>'
            f'<circle cx="48" cy="48" r="28" stroke-opacity="0.5" stroke-width="2"/>'
            f'<path d="M22 34v-8a4 4 0 0 1 4-4h8M62 22h8a4 4 0 0 1 4 4v8M74 62v8a4 4 0 0 1-4 4h-8M34 74h-8a4 4 0 0 1-4-4v-8" stroke-width="4"/>'
            f'<circle cx="48" cy="48" r="6" fill="#FFFFFF" stroke="none"/></svg>')


def html_cincin(skor, tinta):
    """Membuat indikator lingkaran untuk skor keyakinan model."""
    keliling = 2 * 3.14159 * 34
    return (f'<svg width="84" height="84" viewBox="0 0 84 84" role="img" aria-label="Keyakinan model {skor:.0%}">'
            f'<circle cx="42" cy="42" r="34" fill="none" stroke="{tinta}" stroke-opacity="0.25" stroke-width="8"/>'
            f'<circle cx="42" cy="42" r="34" fill="none" stroke="{tinta}" stroke-width="8" stroke-linecap="round" '
            f'stroke-dasharray="{skor * keliling:.1f} {keliling:.1f}" transform="rotate(-90 42 42)"/>'
            f'<text x="42" y="47" text-anchor="middle" font-size="17" font-weight="700" fill="{tinta}">{skor:.0%}</text></svg>')


def html_tong_hasil(label, skor, warna, ms):
    """Kartu utama halaman hasil: tong mana yang dipakai, dengan lingkaran keyakinan."""
    tinta = teks_di(warna)
    nama_tong = NAMA_TONG.get(label.lower())
    judul = f"Tong {nama_tong}" if nama_tong else label
    return (f'<div class="tong" style="background:{warna}; color:{tinta}"><div style="flex:1; min-width:0">'
            f'<div class="kecil-t">Buang ke</div><div class="nama">{judul}</div>'
            f'<div style="font-weight:500">{ikon(IKON_KATEGORI.get(label.lower(), "tong"), 18, tinta)} {label}</div>'
            f'<div class="kecil-t" style="margin-top:4px">Dianalisis dalam {ms} ms</div></div>{html_cincin(skor, tinta)}</div>')