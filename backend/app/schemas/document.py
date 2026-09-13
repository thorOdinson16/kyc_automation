from pydantic import BaseModel


class DocumentReclassify(BaseModel):
    document_type: str
