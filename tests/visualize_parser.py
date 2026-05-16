import os
import argparse
import requests
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path

def visualize_pdf_parsing(pdf_path: str, parser_url: str, output_dir: str):
    print(f"==============================================")
    print(f" DOCLING PARSER VISUALIZATION (ALL PAGES)")
    print(f" PARSER_URL : {parser_url}")
    print(f" PDF_PATH   : {pdf_path}")
    print(f"==============================================")

    if not os.path.exists(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        return

    # 1. パーサーAPIにリクエスト
    print(f"[1] Sending PDF to parser...")
    try:
        filename = os.path.basename(pdf_path)
        container_pdf_path = f"/test_pdf/{filename}"
        response = requests.post(f"{parser_url}/parse", json={"file_path": container_pdf_path})
        response.raise_for_status()
        parser_result = response.json()
        print(f"    -> [PASS] HTTP {response.status_code}")
    except Exception as e:
        print(f"    -> [ERROR] Failed to connect to parser: {e}")
        return

    # 2. PDFの全ページを画像に変換
    print(f"[2] Converting PDF pages to images...")
    try:
        pages = convert_from_path(pdf_path)
        if not pages:
            print(f"    -> [ERROR] Failed to extract pages from PDF.")
            return
        print(f"    -> [PASS] Converted {len(pages)} pages to images.")
    except Exception as e:
        print(f"    -> [ERROR] Image conversion failed. Make sure poppler is installed. Details: {e}")
        return

    # 3. バウンディングボックスの描画
    COLOR_MAP = {
        "SectionHeader": (255, 0, 0, 60),   # 赤
        "Paragraph": (0, 0, 255, 40),       # 青
        "ListItem": (0, 255, 0, 40),        # 緑
        "Caption": (255, 165, 0, 60),       # オレンジ
        "Table": (128, 0, 128, 60),         # 紫
        "PageHeader": (0, 255, 255, 40),    # シアン
        "PageFooter": (255, 0, 255, 40),    # マゼンタ
    }

    print(f"[3] Drawing bounding boxes...")
    page_data_list = parser_result.get("pages", [])
    
    os.makedirs(output_dir, exist_ok=True)

    for page_num, page_img in enumerate(pages, start=1):
        print(f"    -> Processing page {page_num}...")
        page_img = page_img.convert("RGB")
        draw = ImageDraw.Draw(page_img, "RGBA")
        
        if len(page_data_list) < page_num:
            print(f"    -> [WARNING] Parser did not return data for page {page_num}.")
        else:
            page_data = page_data_list[page_num - 1]
            items = page_data.get("items", [])
            
            # DoclingのPDF座標(72dpi基準)から、変換した画像のピクセルへのスケールを計算
            pdf_width = page_data.get("width", 595.28)
            pdf_height = page_data.get("height", 841.89)
            scale_x = page_img.width / pdf_width
            scale_y = page_img.height / pdf_height

            print(f"    -> Found {len(items)} items on page {page_num}.")

            for item in items:
                el_type = item.get("element_type", "Unknown")
                bbox = item.get("bbox") # [x0, y0, x1, y1]
                
                if not bbox or len(bbox) != 4:
                    continue
                    
                pdf_x0, pdf_y0, pdf_x1, pdf_y1 = bbox
                
                # PDFの原点が「左下」で、yが上に向かって増える仕様(Doclingの仕様)のため、
                # PILの「左上」原点に合わせてY座標を反転しつつスケールを合わせる
                img_x0 = pdf_x0 * scale_x
                img_x1 = pdf_x1 * scale_x
                img_y0 = (pdf_height - pdf_y0) * scale_y
                img_y1 = (pdf_height - pdf_y1) * scale_y
                
                # 描画関数(y1 >= y0 等)のエラーを防ぐため、大小を確実にする
                rect_x0 = min(img_x0, img_x1)
                rect_x1 = max(img_x0, img_x1)
                rect_y0 = min(img_y0, img_y1)
                rect_y1 = max(img_y0, img_y1)
                
                fill_color = COLOR_MAP.get(el_type, (128, 128, 128, 40))
                outline_color = (fill_color[0], fill_color[1], fill_color[2], 255)
                
                draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=fill_color, outline=outline_color, width=2)
                
                try:
                    # 枠の左上に要素名を描画 (フォントサイズは小さめを想定)
                    draw.text((rect_x0, max(0, rect_y0 - 15)), el_type, fill=outline_color)
                except Exception:
                    pass

        # 4. 画像の保存
        filename_without_ext = os.path.splitext(os.path.basename(pdf_path))[0]
        out_name = f"{filename_without_ext}_page{page_num:02d}.png"
        out_path = os.path.join(output_dir, out_name)
        try:
            page_img.save(out_path)
            print(f"    -> [SUCCESS] Saved to: {out_path}")
        except Exception as e:
            print(f"    -> [ERROR] Failed to save image: {e}")

    print(f"==============================================")
    print(f" [DONE] All pages processed. Output dir: {output_dir}")
    print(f"==============================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize Docling Parser Output (All Pages)")
    parser.add_argument("--pdf", type=str, default="test_pdf/多田有里_deim2026_予稿.pdf", help="Path to the PDF file")
    parser.add_argument("--url", type=str, default=os.getenv("PARSER_URL", "http://localhost:8001"), help="Parser API URL")
    parser.add_argument("--outdir", type=str, default="visualized_pages", help="Output directory for images")
    
    args = parser.parse_args()
    
    visualize_pdf_parsing(
        pdf_path=args.pdf,
        parser_url=args.url,
        output_dir=args.outdir
    )