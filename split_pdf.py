from pypdf import PdfReader, PdfWriter

reader = PdfReader("solution.pdf")
writer = PdfWriter()

for i in range(min(5, len(reader.pages))):
    writer.add_page(reader.pages[i])

with open("output_first5.pdf", "wb") as f:
    writer.write(f)