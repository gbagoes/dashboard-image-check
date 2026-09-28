import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import time
import csv

# Konfigurasi User-Agent
UA_DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
UA_MOBILE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'

# ==========================================
# KONFIGURASI KATEGORI & LOGIKA CRAWLING
# ==========================================
# Daftar 17 Collection
collections_list = [
    "Land-Dweller", "Day-Date", "Sky-Dweller", "Lady-Datejust", "Datejust", 
    "Oyster Perpetual", "Cosmograph Daytona", "Submariner", "Sea-Dweller", 
    "Deepsea", "GMT-Master II", "Yacht-Master", "Yacht-Master II", 
    "Explorer", "Explorer II", "Air-King", "1908"
]

CATEGORIES = {
    "Home Page (Tanpa Turunan)": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/", "https://www.rolexboutique-marinabay.com/rolex"],
        "allow_descendants": False,
        "allowed_prefixes": []
    },
    "Rolex New Watches": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/new-watches"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/new-watches"]
    }
}

# Generate aturan (rules) otomatis untuk 17 Collection
for coll in collections_list:
    # Mengubah spasi menjadi strip dan huruf kecil (contoh: "GMT-Master II" -> "gmt-master-ii")
    slug = coll.lower().replace(" ", "-")
    CATEGORIES[f"Collection: {coll}"] = {
        "start_urls": [f"https://www.rolexboutique-marinabay.com/rolex/rolex-watches/rolex-{slug}"],
        "allow_descendants": True,
        "allowed_prefixes": [
            f"https://www.rolexboutique-marinabay.com/rolex/rolex-watches/rolex-{slug}", # Halaman utama kategori
            f"https://www.rolexboutique-marinabay.com/rolex/rolex-watches/{slug}/"       # Halaman spesifik produk (tanpa 'rolex-')
        ]
    }

# Tambahkan sisa kategori lainnya
CATEGORIES.update({
    "Accessories": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/accessories/"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/accessories/"]
    },
    "Watchmaking": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/watchmaking/"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/watchmaking/"]
    },
    "Servicing": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/servicing/"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/servicing/"]
    },
    "Oyster Story": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/oyster-story/"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/oyster-story/"]
    },
    "Rolex at Marina Bay": {
        "start_urls": [
            "https://www.rolexboutique-marinabay.com/rolex/rolex-boutique-marina-bay/",
            "https://www.rolexboutique-marinabay.com/rolex/showroom/",
            "https://www.rolexboutique-marinabay.com/rolex/team/",
            "https://www.rolexboutique-marinabay.com/rolex/history/"
        ],
        "allow_descendants": True,
        "allowed_prefixes": [
            "https://www.rolexboutique-marinabay.com/rolex/rolex-boutique-marina-bay/",
            "https://www.rolexboutique-marinabay.com/rolex/showroom/",
            "https://www.rolexboutique-marinabay.com/rolex/team/",
            "https://www.rolexboutique-marinabay.com/rolex/history/"
        ]
    },
    "Contact Us": {
        "start_urls": ["https://www.rolexboutique-marinabay.com/rolex/contact/"],
        "allow_descendants": True,
        "allowed_prefixes": ["https://www.rolexboutique-marinabay.com/rolex/contact/"]
    }
})


# ==========================================
# FUNGSI SCRAPING & VALIDASI
# ==========================================
def get_internal_links(base_url, soup):
    internal_links = set()
    domain = urlparse(base_url).netloc
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href")
        if href:
            full_url = urljoin(base_url, href)
            if domain in urlparse(full_url).netloc:
                full_url = full_url.split('#')[0]
                internal_links.add(full_url)
    return internal_links

def extract_actual_image_url(img_tag, base_url):
    src = img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('src') or ''
    if src.startswith('data:image'):
        srcset = img_tag.get('srcset') or img_tag.get('data-srcset')
        if srcset:
            src = srcset.split(',')[0].split(' ')[0]
        else:
            return None
    if not src: return None
    return urljoin(base_url, src.strip())

def check_image_status(img_url):
    try:
        resp = requests.head(img_url, headers={'User-Agent': UA_DESKTOP}, timeout=5, allow_redirects=True)
        if resp.status_code in [403, 404, 405]:
            resp = requests.get(img_url, headers={'User-Agent': UA_DESKTOP}, stream=True, timeout=5)
        return resp.status_code
    except Exception:
        return "Error/Timeout"

def process_page_images(url, device_name, user_agent):
    results = []
    try:
        response = requests.get(url, headers={'User-Agent': user_agent}, timeout=10)
        if response.status_code != 200:
            return [{"Page URL": url, "Device": device_name, "Image URL": "-", "Status": f"Page Error {response.status_code}", "Alt Text": "-"}], None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        images = soup.find_all('img')
        checked_images = set() 
        
        for img in images:
            img_url = extract_actual_image_url(img, url)
            alt_text = img.get('alt', '').strip() or "Kosong"
            
            if img_url and img_url not in checked_images:
                checked_images.add(img_url)
                status = check_image_status(img_url)
                results.append({
                    "Page URL": url,
                    "Device": device_name,
                    "Image URL": img_url,
                    "Status": status,
                    "Alt Text": alt_text
                })
        
        if not results:
             results.append({
                "Page URL": url, "Device": device_name, "Image URL": "Tidak ada gambar", "Status": "-", "Alt Text": "-"
            })
        return results, soup
    except Exception:
        return [{"Page URL": url, "Device": device_name, "Image URL": "-", "Status": "Page Timeout/Error", "Alt Text": "-"}], None

def run_scanner(category_name, max_pages, delay):
    config = CATEGORIES[category_name]
    all_results = []
    
    visited = set()
    queue = config["start_urls"].copy()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while queue and len(visited) < max_pages:
        current_url = queue.pop(0)
        if current_url in visited:
            continue
            
        if len(visited) > 0 and delay > 0:
            time.sleep(delay)
            
        visited.add(current_url)
        status_text.text(f"Memindai ({len(visited)}/{max_pages}): {current_url}")
        
        # 1. Desktop Check
        desktop_results, soup_desktop = process_page_images(current_url, "Desktop", UA_DESKTOP)
        all_results.extend(desktop_results)
        
        # 2. Mobile Check
        mobile_results, _ = process_page_images(current_url, "Mobile", UA_MOBILE)
        all_results.extend(mobile_results)
        
        # 3. Cari turunan jika diizinkan oleh kategori
        if config["allow_descendants"] and soup_desktop:
            new_links = get_internal_links(current_url, soup_desktop)
            for link in new_links:
                # PASTIKAN link mengandung salah satu Prefix (awalan) yang diizinkan untuk kategori ini
                is_allowed = any(link.startswith(prefix) for prefix in config["allowed_prefixes"])
                if is_allowed and link not in visited and link not in queue:
                    queue.append(link)
                    
        progress = int((len(visited) / max_pages) * 100)
        progress_bar.progress(progress if progress <= 100 else 100)
        
    progress_bar.empty()
    status_text.empty()
    return all_results

# ==========================================
# UI STREAMLIT
# ==========================================
st.set_page_config(page_title="Marina Bay Rolex | Image Checker", layout="wide")
st.title("📸 Dashboard Image Load Checker")
st.write("Alat validasi *rendering* gambar (Desktop & Mobile) yang dikategorikan berdasarkan struktur *website* Marina Bay.")

with st.form("scanner_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        # Dropdown Kategori
        selected_category = st.selectbox(
            "Pilih Kategori Halaman yang Akan Diaudit:", 
            options=list(CATEGORIES.keys())
        )
    with col2:
        max_pages = st.number_input("Batas Maksimal Halaman", min_value=1, max_value=500, value=20)

    delay = st.number_input("Jeda per Halaman (Detik)", min_value=0.0, max_value=10.0, value=1.0, step=0.5)
    submit_button = st.form_submit_button("Mulai Validasi Gambar")

if submit_button:
    with st.spinner(f'Sedang memvalidasi gambar pada kategori "{selected_category}"...'):
        data = run_scanner(selected_category, int(max_pages), float(delay))
        
        if data:
            df = pd.DataFrame(data)
            broken_images = df[~df['Status'].astype(str).isin(['200', '-'])]
            
            st.success(f"✅ Selesai! Memeriksa gambar pada {len(df['Page URL'].unique())} halaman.")
            
            if not broken_images.empty:
                st.error(f"⚠️ Ditemukan {len(broken_images)} indikasi gambar bermasalah (Status selain 200).")
            else:
                st.info("🎉 Semua gambar berhasil dimuat dengan baik (Status 200 OK).")
            
            st.dataframe(df, use_container_width=True)
            
            csv_data = df.to_csv(index=False, sep=';', quoting=csv.QUOTE_ALL).encode('utf-8')
            st.download_button(
                label="📥 Download Laporan (CSV)",
                data=csv_data,
                file_name=f'audit_gambar_{selected_category.replace(" ", "_").lower()}.csv',
                mime='text/csv',
            )
