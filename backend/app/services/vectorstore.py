import os
from typing import Any, Optional


class VectorStoreNotConfiguredError(RuntimeError):
    pass


class PineconeVectorStore:
    def __init__(self) -> None:
        self._pc = None
        self._index = None

    def is_configured(self) -> bool:
        return bool((os.getenv("PINECONE_API_KEY") or "").strip()) and bool(
            (os.getenv("PINECONE_INDEX") or "").strip()
        )

    def _get_index(self):
        if not self.is_configured():
            raise VectorStoreNotConfiguredError(
                "Pinecone is not configured. Set PINECONE_API_KEY and PINECONE_INDEX."
            )

        if self._index is not None:
            return self._index

        api_key = (os.getenv("PINECONE_API_KEY") or "").strip()
        index_name = (os.getenv("PINECONE_INDEX") or "").strip()

        try:
            from pinecone import Pinecone
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Pinecone SDK is not installed. Add 'pinecone' to requirements.txt. "
                f"(raw: {e})"
            )

        self._pc = Pinecone(api_key=api_key)
        self._index = self._pc.Index(index_name)
        return self._index

    def upsert(
        self,
        *,
        namespace: str,
        vector_id: str,
        values: list[float],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        index = self._get_index()
        index.upsert(
            vectors=[
                {
                    "id": str(vector_id),
                    "values": values,
                    "metadata": metadata or {},
                }
            ],
            namespace=str(namespace),
        )

    def delete(self, *, namespace: str, vector_id: str) -> None:
        index = self._get_index()
        index.delete(ids=[str(vector_id)], namespace=str(namespace))

    def query(
        self,
        *,
        namespace: str,
        values: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        index = self._get_index()
        res = index.query(
            vector=values,
            top_k=int(top_k),
            include_metadata=True,
            namespace=str(namespace),
        )
        matches = res.get("matches") if isinstance(res, dict) else getattr(res, "matches", None)
        if not matches:
            return []

        out: list[dict[str, Any]] = []
        for m in matches:
            if isinstance(m, dict):
                out.append(m)
            else:
                out.append(
                    {
                        "id": getattr(m, "id", None),
                        "score": getattr(m, "score", None),
                        "metadata": getattr(m, "metadata", None),
                    }
                )
        return out


_vectorstore: PineconeVectorStore | None = None


def get_vectorstore() -> PineconeVectorStore:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = PineconeVectorStore()
    return _vectorstore
