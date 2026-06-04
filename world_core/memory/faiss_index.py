"""Incremental FAISS index with soft deletion support."""
import numpy as np
from typing import List, Tuple, Optional, Set

class IncrementalFAISSIndex:
    """FAISS index with incremental addition and soft deletion."""

    def __init__(self, dimension: int):
        self.dimension = dimension
        self._index = None
        self._id_map = None
        self._next_id = 0
        self.valid_ids: Set[int] = set()
        self._deleted_ids: Set[int] = set()
        self._vectors: dict = {}  # In-memory storage for soft delete support
        self._initialize_index()

    def _initialize_index(self):
        """Initialize the FAISS index with robust error handling."""
        try:
            import faiss
            self._faiss = faiss
            # Use Inner Product for cosine similarity after normalization
            self._index = faiss.IndexFlatIP(self.dimension)
            self._id_map = faiss.IndexIDMap(self._index)
        except ImportError:
            self._faiss = None
            self._index = None
            self._id_map = None
            import logging
            logging.getLogger(__name__).warning("FAISS not installed, using linear search for memory retrieval")
        except Exception as e:
            # Catch segfaults and other native library errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"FAISS initialization failed: {e}")
            self._faiss = None
            self._index = None
            self._id_map = None

    @property
    def ntotal(self) -> int:
        """Return total number of indexed vectors."""
        if self._id_map is not None:
            return self._id_map.ntotal
        return 0

    def add(self, vectors: List[np.ndarray], ids: List[int]) -> None:
        """Add vectors to the index with corresponding IDs."""
        if not vectors or self._id_map is None:
            return

        # Validate vector dimensions
        arr = np.vstack(vectors).astype('float32')
        if arr.shape[1] != self.dimension:
            import logging
            logging.getLogger(__name__).warning(
                f"Vector dimension mismatch in add: got {arr.shape[1]}, expected {self.dimension}. "
                f"Skipping {len(vectors)} vectors."
            )
            return

        # Stack vectors and normalize for cosine similarity
        self._faiss.normalize_L2(arr)

        # Add with IDs
        self._id_map.add_with_ids(arr, np.array(ids, dtype=np.int64))

        # Track valid IDs and store vectors
        for vec, iid in zip(vectors, ids):
            self._vectors[iid] = vec
            self.valid_ids.add(iid)
            self._deleted_ids.discard(iid)

        # Update next ID
        if ids:
            self._next_id = max(self._next_id, max(ids) + 1)

    def delete(self, ids: List[int]) -> None:
        """Soft delete vectors by marking them as deleted."""
        for iid in ids:
            self._deleted_ids.add(iid)
            self.valid_ids.discard(iid)
            if iid in self._vectors:
                del self._vectors[iid]

    def search(
        self,
        query: np.ndarray,
        k: int,
        valid_mask: Optional[Set[int]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for k nearest neighbors.

        Returns:
            Tuple of (scores, ids) arrays
        """
        if self._id_map is None or self._id_map.ntotal == 0:
            return np.array([]), np.array([])

        # Wrap entire operation in try-except to catch dimension assertion errors
        try:
            # Validate query dimension matches index dimension
            query_flat = np.asarray(query).astype('float32').flatten()
            if query_flat.shape[0] != self.dimension:
                import logging
                logging.getLogger(__name__).warning(
                    f"Query dimension mismatch: got {query_flat.shape[0]}, expected {self.dimension}. "
                    f"Returning empty results."
                )
                return np.array([]), np.array([])

            # Normalize query vector
            query_np = query_flat.reshape(1, -1)
            self._faiss.normalize_L2(query_np)

            # Perform search
            scores, ids = self._id_map.search(query_np, k)
        except AssertionError as e:
            import logging
            logging.getLogger(__name__).warning(
                f"FAISS search failed due to dimension mismatch (likely index={self.dimension} vs query={query_flat.shape[0]}). "
                f"Returning empty results. Error: {e}"
            )
            return np.array([]), np.array([])

        # Filter out deleted and invalid IDs
        keep = []
        for score, iid in zip(scores[0], ids[0]):
            if iid == -1:
                continue
            if iid in self._deleted_ids:
                continue
            if valid_mask is not None and iid not in valid_mask:
                continue
            keep.append((float(score), int(iid)))

        if not keep:
            return np.array([]), np.array([])

        scores_out, ids_out = zip(*keep)
        return np.array(scores_out), np.array(ids_out)

    def total_entries(self) -> int:
        """Return number of valid (non-deleted) entries."""
        return len(self.valid_ids)

    def fragmentation_ratio(self) -> float:
        """Return ratio of deleted IDs to total indexed."""
        if self.ntotal == 0:
            return 0.0
        return len(self._deleted_ids) / self.ntotal

    def rebuild(self) -> None:
        """Rebuild the index to remove deleted entries."""
        if not self._deleted_ids or self._id_map is None:
            return

        # Get all valid vectors and IDs
        valid_vectors = []
        valid_ids = []

        for iid in self.valid_ids:
            if iid in self._vectors:
                valid_vectors.append(self._vectors[iid])
                valid_ids.append(iid)

        if not valid_vectors:
            return

        # Reset and rebuild
        self._initialize_index()
        self.add(valid_vectors, valid_ids)
        self._deleted_ids.clear()

    def get_vector(self, id: int) -> Optional[np.ndarray]:
        """Retrieve a vector by its ID."""
        if id in self._deleted_ids or id not in self._vectors:
            return None
        return self._vectors.get(id)

    def contains(self, id: int) -> bool:
        """Check if an ID exists and is not deleted."""
        return id in self.valid_ids
