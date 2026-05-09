"""Build FAISS index from cdc.md. Run once as an init container."""
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import MarkdownTextSplitter

INDEX_PATH = Path(__file__).parent / "faiss_index"
CDC_PATH = Path(__file__).parent / "cdc.md"


def build():
    print("Building RAG index from cdc.md...")
    cdc_text = CDC_PATH.read_text(encoding="utf-8")

    splitter = MarkdownTextSplitter(chunk_size=400, chunk_overlap=50)
    docs = splitter.create_documents([cdc_text])
    print(f"  {len(docs)} chunks created")

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )

    index = FAISS.from_documents(docs, embeddings)
    index.save_local(str(INDEX_PATH))
    print(f"  Index saved to {INDEX_PATH}")
    print("Done.")


if __name__ == "__main__":
    build()
