from .libs.file_reader import extract_text

RESUME_PATH = "resume/Resume_Luis_Alberto_Bolanos_Salazar.docx.pdf"

def main() -> None:
    print(extract_text(RESUME_PATH))


if __name__ == "__main__":
    main()
