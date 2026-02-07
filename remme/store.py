import json
import faiss
import numpy as np
import logging
from pathlib import Path
from datetime import datetime
import uuid
import sys

logger = logging.getLogger(__name__)


class RemmeStore:
    """FAISS-backed memory store with proper ID mapping for delete/update support."""
    
    def __init__(self, persistence_dir: str = "memory/remme_index"):
        self.root = Path(__file__).parent.parent / persistence_dir
        self.root.mkdir(parents=True, exist_ok=True)
        
        self.index_path = self.root / "index.bin"
        self.metadata_path = self.root / "memories.json"
        self.scanned_runs_path = self.root / "scanned_runs.json"
        self._embeddings_path = self.root / "embeddings.npy"
        
        self.dimension = 768  # Default for nomic-embed-text
        self.index = None
        self.memories = []
        self._embeddings = []  # Store embeddings for rebuild support
        self.scanned_run_ids = set()
        
        self.load()

    def load(self):
        """Load index, embeddings, and metadata from disk."""
        # Load metadata
        if self.metadata_path.exists():
            try:
                self.memories = json.loads(self.metadata_path.read_text())
            except Exception as e:
                logger.error(f"Failed to load memories JSON: {e}")
                self.memories = []
        else:
            self.memories = []

        # Load stored embeddings (for rebuild support)
        if self._embeddings_path.exists():
            try:
                self._embeddings = list(np.load(str(self._embeddings_path), allow_pickle=False))
            except Exception as e:
                logger.warning(f"Failed to load embeddings file: {e}")
                self._embeddings = []
        else:
            self._embeddings = []
        
        # Load or rebuild FAISS index
        if self.index_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {e}, rebuilding...")
                self._rebuild_index()
        else:
            self._rebuild_index()

        # Load scanned runs
        if self.scanned_runs_path.exists():
            try:
                self.scanned_run_ids = set(json.loads(self.scanned_runs_path.read_text()))
            except Exception as e:
                logger.error(f"Failed to load scanned runs JSON: {e}")
                self.scanned_run_ids = set()
        else:
            self.scanned_run_ids = set()
    
    def _rebuild_index(self):
        """Rebuild FAISS index from stored embeddings."""
        if self._embeddings and len(self._embeddings) > 0:
            self.dimension = len(self._embeddings[0])
            self.index = faiss.IndexFlatL2(self.dimension)
            emb_matrix = np.stack(self._embeddings).astype(np.float32)
            self.index.add(emb_matrix)
            logger.info(f"Rebuilt FAISS index with {len(self._embeddings)} vectors")
        else:
            self.index = faiss.IndexFlatL2(self.dimension)
            logger.info("Created empty FAISS index")

    def save(self):
        """Save index, embeddings, and metadata to disk."""
        if self.index:
            faiss.write_index(self.index, str(self.index_path))
        
        # Save embeddings for rebuild support
        if self._embeddings:
            np.save(str(self._embeddings_path), np.stack(self._embeddings).astype(np.float32))
        
        self.metadata_path.write_text(json.dumps(self.memories, indent=2))
        self.scanned_runs_path.write_text(json.dumps(list(self.scanned_run_ids), indent=2))

    def add(self, text: str, embedding: np.ndarray, category: str = "general", source: str = "manual"):
        """Add a new memory with deduplication."""
        if self.index is None:
            self.dimension = len(embedding)
            self.index = faiss.IndexFlatL2(self.dimension)
            
        # DEDUPLICATION CHECK
        matches = self.search(embedding, k=1, score_threshold=0.15)
        if matches:
            memory_id = matches[0]["id"]
            for m in self.memories:
                if m["id"] == memory_id:
                    m["updated_at"] = datetime.now().isoformat()
                    if source not in m.get("source", ""):
                        m["source"] = f"{m['source']}, {source}"
                    self.save()
                    return m

        # Add to FAISS and embeddings store
        self.index.add(embedding.reshape(1, -1))
        self._embeddings.append(embedding.copy())
        
        memory_id = str(uuid.uuid4())
        memory_item = {
            "id": memory_id,
            "text": text,
            "category": category,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "source": source,
            "faiss_id": self.index.ntotal - 1
        }
        self.memories.append(memory_item)
        self.save()
        return memory_item

    def search(self, query_vector: np.ndarray, query_text: str = None, k: int = 10, score_threshold: float = 1.5):
        """Search memories by vector similarity with optional keyword boosting."""
        if not self.index or self.index.ntotal == 0:
            return []
            
        distances, indices = self.index.search(query_vector.reshape(1, -1), k * 2) # Get more candidates for merging
        
        # 1. Gather Vector Results
        vector_results = {}
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            memory = next((m for m in self.memories if m.get("faiss_id") == int(idx)), None)
            if memory:
                score = float(distances[0][i])
                if score < score_threshold:
                    res = memory.copy()
                    res["score"] = score
                    vector_results[memory["id"]] = res

        # 2. Keyword Search & Boosting
        final_results = []
        if query_text:
            import re
            query_words = set(re.findall(r'\b\w+\b', query_text.lower()))
            # Expanded stop words for better precision
            stop_words = {
                "the", "a", "an", "is", "are", "was", "were", "do", "does", "did", "you", "your", 
                "have", "has", "had", "any", "about", "of", "our", "to", "what", "we", "in", 
                "with", "from", "for", "and", "or", "but", "so", "how", "when", "where", "why",
                "this", "that", "these", "those", "it", "its", "they", "them", "their",
                "be", "been", "being", "can", "could", "should", "would", "may", "might", "must",
                "shall", "will", "on", "at", "by", "at", "as", "if"
            }
            keywords = query_words - stop_words
            
            if keywords:
                for memory in self.memories:
                    text_lower = memory["text"].lower()
                    m_id = memory["id"]
                    
                    # Count whole-word matches only
                    match_count = 0
                    for kw in keywords:
                        if re.search(rf'\b{re.escape(kw)}\b', text_lower):
                            match_count += 1
                    
                    if match_count > 0:
                        # Success! This memory has a keyword match.
                        if m_id in vector_results:
                            # 🚀 BOOST: If found in both, slash the score (lower is better)
                            boost = 1.0 + (match_count * 0.7) # Slightly stronger boost
                            vector_results[m_id]["score"] /= (boost * 2.0)
                            vector_results[m_id]["source"] = f"{vector_results[m_id].get('source', '')} (hybrid_boost)"
                        else:
                            # 💡 INJECT: If only found via keyword, add with competitive score
                            res = memory.copy()
                            res["score"] = 0.6 / (1.0 + match_count) # Competitive synthetic score
                            res["source"] = f"{res.get('source', '')} (keyword_only)"
                            vector_results[m_id] = res

        # 3. Final Sort and Trim
        final_results = sorted(vector_results.values(), key=lambda x: x["score"])
        return final_results[:k]

    def get_all(self):
        """Return all memories."""
        return self.memories

    def get_scanned_run_ids(self):
        """Return a set of run IDs that have already been scanned."""
        # 1. Start with dedicated tracking file (Best source)
        ids = set(self.scanned_run_ids)
        
        # 2. Backfill from existing memories if not already there (Legacy support)
        for m in self.memories:
            source = m.get("source", "")
            parts = source.split(", ")
            for part in parts:
                if part.startswith("run_"):
                    ids.add(part.replace("run_", ""))
                elif part.startswith("manual_scan_"):
                    ids.add(part.replace("manual_scan_", ""))
        return ids

    def mark_run_scanned(self, run_id: str):
        """Explicitly mark a run as scanned and persist."""
        if run_id not in self.scanned_run_ids:
            self.scanned_run_ids.add(run_id)
            self.save()

    def delete(self, memory_id: str):
        """Delete a memory and rebuild the FAISS index cleanly.
        
        Removes the memory from metadata and embeddings, then rebuilds the 
        entire FAISS index to eliminate ghost vectors.
        """
        # Find the memory to delete and its index position
        target_idx = None
        for i, m in enumerate(self.memories):
            if m["id"] == memory_id:
                target_idx = i
                break
        
        if target_idx is None:
            logger.warning(f"Memory {memory_id} not found for deletion")
            return False
        
        # Remove from metadata and embeddings
        self.memories.pop(target_idx)
        if target_idx < len(self._embeddings):
            self._embeddings.pop(target_idx)
        
        # Update faiss_id references for remaining memories
        for i, m in enumerate(self.memories):
            m["faiss_id"] = i
        
        # Rebuild FAISS index from remaining embeddings
        self._rebuild_index()
        self.save()
        
        logger.info(f"Deleted memory {memory_id} and rebuilt index ({len(self.memories)} remaining)")
        return True

    def update_text(self, memory_id: str, new_text: str, new_embedding: np.ndarray):
        """Update the text and embedding of a memory, rebuilding the index cleanly."""
        original_idx = -1
        for i, m in enumerate(self.memories):
            if m["id"] == memory_id:
                original_idx = i
                break
        
        if original_idx == -1:
            logger.warning(f"Memory {memory_id} not found for update")
            return False
        
        # Update metadata in place (preserving ID/Created At)
        self.memories[original_idx]["text"] = new_text
        self.memories[original_idx]["updated_at"] = datetime.now().isoformat()
        
        # Replace embedding at the same index
        if original_idx < len(self._embeddings):
            self._embeddings[original_idx] = new_embedding.copy()
        else:
            self._embeddings.append(new_embedding.copy())
        
        # Rebuild FAISS index cleanly (no ghost vectors)
        self._rebuild_index()
        
        # Update faiss_id references
        for i, m in enumerate(self.memories):
            m["faiss_id"] = i
        
        self.save()
        logger.info(f"Updated memory {memory_id} and rebuilt index")
        return True
