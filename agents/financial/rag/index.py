from functools import lru_cache
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

INDEX_PATH = str(Path(__file__).parent / "faiss_index")


@lru_cache(maxsize=1)
def _get_index() -> FAISS:
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )
    return FAISS.load_local(
        INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )


def search_cdc(query: str, k: int = 3) -> str:
    index = _get_index()
    results = index.similarity_search(query, k=k)
    if not results:
        return "Nenhuma informação encontrada na base do CDC para esta consulta."
    return "\n\n---\n\n".join(doc.page_content for doc in results)
