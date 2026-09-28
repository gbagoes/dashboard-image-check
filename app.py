import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import time
import csv

# Konfigurasi User-Agent untuk simulasi perangkat
UA_DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
UA_MOBILE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'

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
    # Menangani Lazy Loading (prioritas pada data-src atau atribut khusus lainnya)
    src = img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('src') or ''
    
    # Jika gambar berupa base64 (placeholder inline), coba cari di srcset
    if src.startswith('data:image'):
        srcset = img_tag.get('srcset') or img_tag.get('data-srcset')
        if srcset:
            # Ambil URL pertama dari daftar srcset
            src = srcset.split(',')[0].split(' ')[0]
        else:
            return None
            
    if not src:
        return None
        
    return urljoin(base_url, src.strip())

def check_image_status(img_url):
    try:
        # Menggunakan HEAD request agar lebih cepat karena tidak mengunduh fisik gambar
        resp = requests.head(img_url, headers={'User-Agent': UA_DESKTOP}, timeout=5, allow_redirects=True)
        # Beberapa server memblokir HEAD, jika 403/404/405, coba gunakan GET
        if resp.status_code in [403, 404, 405]:
            resp = requests.get(img_url, headers={'User-Agent': UA_DESKTOP}, stream=True, timeout=5)
        return resp.status_code
    except requests.exceptions.Timeout:
        return "Timeout"
    except Exception as e:
        return "Error"

def process_page_images(url, device_name, user_agent):
    results = []
    try:
        response = requests.get(url, headers={'User-Agent': user_agent}, timeout=10)
        if response.status_code != 200:
            return [{"Page URL": url, "Device": device_name, "Image URL": "-", "Status": f"Page Error {response.status_code}", "Alt Text": "-"}]
            
        soup = BeautifulSoup(response.text, 'html.parser')
        images = soup.find_all('img')
        
        # Hindari mengecek gambar yang sama berulang kali di satu halaman
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
        
        # Jika halaman tidak memiliki gambar sama sekali
        if not results:
             results.append({
                "Page URL": url,
                "Device": device_name,
                "Image URL": "Tidak ada gambar",
                "Status": "-",
                "Alt Text": "-"
            })
             
        return results, soup
    except Exception as e:
        return [{"Page URL": url, "Device": device_name, "Image URL": "-", "Status": f"Page Timeout/Error", "Alt Text": "-"}], None

def run_scanner(mode, input_data, max_pages, delay):
    all_results = []
    urls_to_process = []
    
    if mode == "Manual (List URL)":
        # Bersihkan input manual dari spasi dan baris kosong
        urls_to_process = [u.strip() for u in input_data.split('\n') if u.strip().startswith('http')]
        total_target = len(urls_to_process)
    else:
        urls_to_process = [input_data.strip()] # Base URL
        total_target = max_pages
        
    visited = set()
    queue = urls_to_process.copy()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while queue and len(visited) < total_target:
        current_url = queue.pop(0)
        
        if current_url in visited:
            continue
            
        if len(visited) > 0 and delay > 0:
            time.sleep(delay)
            
        visited.add(current_url)
        status_text.text(f"Memindai ({len(visited)}/{total_target}): {current_url}")
        
        # 1. Cek versi Desktop
        desktop_results, soup_desktop = process_page_images(current_url, "Desktop", UA_DESKTOP)
        all_results.extend(desktop_results)
        
        # 2. Cek versi Mobile
        mobile_results, soup_mobile = process_page_images(current_url, "Mobile", UA_MOBILE)
        all_results.extend(mobile_results)
        
        # 3. Jika mode Crawling, cari link internal dari versi Desktop
        if mode == "Crawling (Halaman Turunan)" and soup_desktop:
            new_links = get_internal_links(current_url, soup_desktop)
            for link in new_links:
                # Pastikan tetap berada di bawah base URL awal
                if link.startswith(input_data.strip()) and link not in visited and link not in queue:
                    queue.append(link)
                    
        # Update Progress
        progress = int((len(visited) / total_target) * 100)
        progress_bar.progress(progress if progress <= 100 else 100)
        
    progress_bar.empty()
    status_text.empty()
    return all_results

# ==========================================
# UI STREAMLIT
# ==========================================
st.set_page_config(page_title="Image Load & Broken Link Checker", layout="wide")
st.title("📸 Dashboard Image Load Checker")
st.write("Memvalidasi apakah gambar pada halaman berhasil dirender dengan baik (Status 200) atau rusak (Status 404/Error), baik pada versi Desktop maupun Mobile.")

scan_mode = st.radio(
    "Pilih Metode Input:",
    ("Manual (List URL)", "Crawling (Halaman Turunan)"),
    horizontal=True
)

st.markdown("---")

with st.form("scanner_form"):
    if scan_mode == "Manual (List URL)":
        input_data = st.text_area("Masukkan daftar URL (Satu URL per baris)", value="https://www.intime.co.id/rolex/\nhttps://www.intime.co.id/rolex/kontak/")
        max_pages = 0 # Tidak digunakan di mode manual
    else:
        input_data = st.text_input("Masukkan Base URL (Awal Crawling)", value="https://www.intime.co.id/rolex/")
        max_pages = st.number_input("Batas Maksimal Halaman Di-Crawl", min_value=1, max_value=500, value=10)

    delay = st.number_input("Jeda per Halaman (Detik)", min_value=0.0, max_value=10.0, value=1.0, step=0.5, help="Penting agar server tidak mengira proses ini sebagai serangan DDoS.")
    submit_button = st.form_submit_button("Mulai Validasi Gambar")

if submit_button:
    if not input_data.strip():
        st.error("Input URL tidak boleh kosong!")
    else:
        with st.spinner('Sistem sedang memvalidasi satu per satu gambar. Ini mungkin memakan waktu, harap tunggu...'):
            data = run_scanner(scan_mode, input_data, max_pages, delay)
            
            if data:
                df = pd.DataFrame(data)
                
                # Filter untuk menyorot gambar yang rusak (Status bukan 200)
                broken_images = df[~df['Status'].astype(str).isin(['200', '-'])]
                
                st.success(f"✅ Selesai! Memeriksa total {len(df)} file gambar dari halaman yang diproses.")
                
                if not broken_images.empty:
                    st.error(f"⚠️ Ditemukan {len(broken_images)} indikasi gambar bermasalah atau rusak (Broken Link).")
                else:
                    st.info("🎉 Semua gambar berhasil dimuat dengan baik (Status 200 OK).")
                
                # Tampilkan Tabel
                st.dataframe(df, use_container_width=True)
                
                # Export CSV
                csv_data = df.to_csv(index=False, sep=';', quoting=csv.QUOTE_ALL).encode('utf-8')
                st.download_button(
                    label="📥 Download Laporan Validasi Gambar (CSV)",
                    data=csv_data,
                    file_name='hasil_validasi_gambar.csv',
                    mime='text/csv',
                )