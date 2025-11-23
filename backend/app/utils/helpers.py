import os
from uuid import uuid4

def generate_file_name(application_id: str, document_type: str, original_filename: str) -> str:
    """Generate unique filenames for uploaded documents."""
    extension = original_filename.split(".")[-1]
    unique_id = uuid4().hex
    return f"{application_id}_{document_type}_{unique_id}.{extension}"

def ensure_dir(path: str):
    """Ensure directory exists."""
    if not os.path.exists(path):
        os.makedirs(path)