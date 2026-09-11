"""
RAG Layer — Day 5 build. This is your most important interview talking point.

Pipeline: chunk policy docs -> embed -> store in ChromaDB -> retrieve top-k
relevant chunks for a query -> generate an answer grounded in those chunks.

Be ready to explain each step individually if asked, and to explain WHY RAG
over fine-tuning here: policy documents change (new policy versions, new
coverage terms), and RAG lets you update the knowledge base by just
re-indexing documents — no retraining needed. That's the answer to
"why did you choose RAG."
"""

import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

POLICY_DOCS_DIR = Path(__file__).parent.parent / "data" / "policy_docs"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_store"

COLLECTION_NAME = "policy_docs"


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Simple sliding-window chunking by words. Overlap prevents losing context
    that straddles a chunk boundary — mention this trade-off if asked about
    chunking strategy (bigger chunks = more context per chunk but less precise
    retrieval; more overlap = redundancy but fewer boundary losses)."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start = end - overlap
    return chunks


def build_index(reset: bool = True):
    """Chunk + embed all policy docs and store in a local Chroma collection.
    Run once (or whenever policy docs change): python src/rag.py --build
    """
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    if reset:
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"), model_name="text-embedding-3-small"
    )
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=embed_fn
    )

    ids, documents, metadatas = [], [], []
    for doc_path in POLICY_DOCS_DIR.glob("*.md"):
        text = doc_path.read_text(encoding="utf-8")
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            ids.append(f"{doc_path.stem}_{i}")
            documents.append(chunk)
            metadatas.append({"source": doc_path.stem})

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Indexed {len(ids)} chunks from {len(list(POLICY_DOCS_DIR.glob('*.md')))} policy docs.")
    return collection


def get_collection():
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"), model_name="text-embedding-3-small"
    )
    return chroma_client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)


RAG_SYSTEM_PROMPT = """You are a policy coverage assistant. Answer the user's question
using ONLY the provided policy excerpts below. If the excerpts don't contain enough
information to answer confidently, say so explicitly instead of guessing — never
invent coverage terms that aren't in the excerpts.

Policy excerpts:
{context}
"""


def answer_policy_question(question: str, k: int = 3) -> dict:
    collection = get_collection()
    results = collection.query(query_texts=[question], n_results=k)

    retrieved_chunks = results["documents"][0]
    sources = [m["source"] for m in results["metadatas"][0]]
    context = "\n\n---\n\n".join(retrieved_chunks)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )

    return {
        "answer": response.choices[0].message.content.strip(),
        "sources": list(set(sources)),
        "retrieved_chunks": retrieved_chunks,
    }


if __name__ == "__main__":
    import sys

    if "--build" in sys.argv:
        build_index()
    else:
        q = "Is water damage from a burst pipe covered under my home policy?"
        result = answer_policy_question(q)
        print("Q:", q)
        print("A:", result["answer"])
        print("Sources:", result["sources"])
