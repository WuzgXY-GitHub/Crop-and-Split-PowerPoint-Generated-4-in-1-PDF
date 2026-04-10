yimport sys
import fitz  # PyMuPDF
import pikepdf

def discover_slide_boxes(page):
    """
    Intelligently discover the exact bounding boxes of the 4 slides on a PPT handout page.
    It looks at the vector drawings (rectangles) on the page.
    """
    page_rect = page.rect
    w_min = page_rect.width * 0.20
    h_min = page_rect.height * 0.15
    w_max = page_rect.width * 0.50
    h_max = page_rect.height * 0.50

    candidate_rects = []
    
    # Extract all vector drawings
    for path in page.get_drawings():
        rect = path['rect']
        # Filter drawings by reasonable dimensions roughly corresponding to a 1/4 slide
        if w_min < rect.width < w_max and h_min < rect.height < h_max:
            # Check if we already have this rect (handling slight duplicate overlays)
            is_new = True
            for crect in candidate_rects:
                if abs(rect.x0 - crect.x0) < 5 and abs(rect.y0 - crect.y0) < 5:
                    is_new = False
                    break
            if is_new:
                candidate_rects.append(rect)

    # We expect exactly 4 boxes for a 2x2 handout. 
    # Let's sort them in reading order: top-to-bottom, then left-to-right
    if len(candidate_rects) >= 4:
        # Sort by y0 first (top vs bottom row), then inside each row by x0
        candidate_rects.sort(key=lambda r: (round(r.y0 / 50) * 50, r.x0))
        # Take the top 4 and return along with page height (needed for coordinate conversion)
        return candidate_rects[:4], page_rect.height
    
    raise Exception("Could not detect 4 distinct slide borders via vector graphics.")

def split_pdf_smart(input_path, output_path):
    print(f"Analyzing {input_path} with PyMuPDF to find exact borders...")
    # 1. Use PyMuPDF just to read the geometric properties
    doc = fitz.open(input_path)
    if len(doc) == 0:
        print("Error: The PDF is empty.")
        return

    try:
        crop_boxes_fitz, page_height = discover_slide_boxes(doc[0])
    except Exception as e:
        print(f"Detection error: {e}")
        return
    finally:
        doc.close()
    
    # 2. Convert from PyMuPDF's coordinate system (top-left origin)
    #    to standard PDF / pikepdf's coordinate system (bottom-left origin)
    print("Discovered exact slide bounding boxes:")
    pdf_crop_boxes = []
    for i, b in enumerate(crop_boxes_fitz):
        # Native PDF coordinates: [llx, lly, urx, ury]
        # lly = page_height - y1 (bottom y), ury = page_height - y0 (top y)
        llx = b.x0
        lly = page_height - b.y1
        urx = b.x1
        ury = page_height - b.y0
        
        pdf_box = [llx, lly, urx, ury]
        pdf_crop_boxes.append(pdf_box)
        print(f"  Slide {i+1}: PyMuPDF {b}  ->  Native PDF Box {pdf_box}")

    # 3. Use pikepdf to perform the actual splitting losslessly to prevent file bloat
    print(f"Processing pages with pikepdf for minimal file size...")
    pdf = pikepdf.Pdf.open(input_path)
    output_pdf = pikepdf.Pdf.new()

    for i, page in enumerate(pdf.pages):
        for c_box in pdf_crop_boxes:
            # pikepdf append simply references the same internal page object
            # meaning 4 copies of a page takes no extra space!
            output_pdf.pages.append(page)
            new_page = output_pdf.pages[-1]
            
            # Set the crop box and media box to perfectly align with the border
            new_page.cropbox = c_box
            new_page.mediabox = c_box

    output_pdf.save(output_path)
    print(f"Successfully saved cleanly split and optimized PDF to {output_path}")

if __name__ == "__main__":
    input_pdf_name = "input.pdf"
    output_pdf_name = "output.pdf"

    if len(sys.argv) > 1:
        input_pdf_name = sys.argv[1]
    if len(sys.argv) > 2:
        output_pdf_name = sys.argv[2]
        
    try:
        split_pdf_smart(input_pdf_name, output_pdf_name)
    except Exception as e:
        print(f"Error occurred: {e}")
