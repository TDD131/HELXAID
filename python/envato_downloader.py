import os
import requests
import re
from urllib.parse import urlparse

def download_envato_preview(url, output_dir=None):
    """
    Fungsi untuk mendownload video preview dari Envato (Elements / VideoHive).
    
    Args:
        url (str): URL halaman Envato
        output_dir (str): Direktori tempat menyimpan video (default: folder Downloads Windows)
    """
    if output_dir is None:
        # Mengambil lokasi folder default 'Downloads' di Windows
        output_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        
    try:
        # Gunakan User-Agent agar tidak diblokir karena dianggap bot
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        
        print(f"Mencari informasi dari: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Mencari URL berakhiran .mp4 di dalam source code HTML menggunakan Regex
        video_urls = re.findall(r'(https?://[^"\'\s]+\.mp4)', response.text)
        
        if not video_urls:
            print("Video preview tidak ditemukan di halaman ini.")
            return False
            
        # Mengambil URL video yang valid (biasanya ada beberapa versi, ambil yang pertama)
        video_url = list(set(video_urls))[0]
        print(f"Video URL ditemukan: {video_url}")
        
        # Membuat nama file berdasarkan URL halaman
        parsed_url = urlparse(url)
        # Ambil bagian terakhir dari path URL sebagai nama file
        base_name = parsed_url.path.strip("/").split("/")[-1]
        if not base_name:
            base_name = "envato_video"
        
        filename = f"{base_name}.mp4"
        
        # Pastikan direktori output ada
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, filename)
        
        print(f"Mulai mendownload ke: {filepath}")
        
        # Download file secara streaming agar tidak memenuhi memori RAM
        with requests.get(video_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        print("Download selesai!")
        return filepath
        
    except requests.exceptions.RequestException as e:
        print(f"Gagal mengakses URL: {e}")
        return False
    except Exception as e:
        print(f"Terjadi kesalahan yang tidak terduga: {e}")
        return False

if __name__ == "__main__":
    print("=== Envato Preview Video Downloader ===")
    test_url = input("Masukkan URL video Envato: ").strip()
    
    if test_url:
        download_envato_preview(test_url)
    else:
        print("URL tidak boleh kosong.")
