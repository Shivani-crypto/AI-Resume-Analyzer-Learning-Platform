import os
import warnings
from typing import Optional, List

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")

from ..schemas.chat import ChatRequest, ChatResponse
from utils.analyzer import execute_llm

FAISS_INDEX_DIR = "faiss_index"
_embeddings = None
_vector_store = None
_initialized = False

def get_vector_store():
    global _embeddings, _vector_store, _initialized
    if not _initialized:
        _initialized = True
        try:
            import faiss
            from langchain_community.vectorstores import FAISS
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
            except ImportError:
                from langchain_community.embeddings import HuggingFaceEmbeddings

            _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            if os.path.exists(FAISS_INDEX_DIR) and os.path.exists(os.path.join(FAISS_INDEX_DIR, "index.faiss")):
                _vector_store = FAISS.load_local(FAISS_INDEX_DIR, _embeddings, allow_dangerous_deserialization=True)
                print("✅ FAISS Vector Index loaded successfully from persistent storage.")
            else:
                _vector_store = FAISS.from_texts(["Platform initialized."], embedding=_embeddings, metadatas=[{"lesson_id": 0}])
        except Exception as e:
            print(f"FAISS Init Notice: {e}")
            _embeddings = None
            _vector_store = None
    return _vector_store

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        get_vector_store()
    return _embeddings

def save_vector_store():
    v_store = get_vector_store()
    if v_store:
        try:
            os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
            v_store.save_local(FAISS_INDEX_DIR)
            print("✅ Saved FAISS index to disk.")
        except Exception as e:
            print(f"⚠️ Failed to save FAISS index: {e}")

def generate_tutor_response(request: ChatRequest) -> ChatResponse:
    """
    Retrieves relevant course notes from FAISS isolated by lesson_id metadata
    and generates an expert multilingual tutor response.
    """
    v_store = get_vector_store()
    
    context_text = ""
    if request.skill:
        context_text += f"[Target Technical Skill Course]: {request.skill.strip()}\n"
        
    docs = []
    
    if v_store:
        try:
            target_lesson = request.lesson_id
            search_kwargs = {"k": 4}
            if target_lesson is not None:
                search_kwargs["filter"] = {"lesson_id": target_lesson}

            retriever = v_store.as_retriever(search_kwargs=search_kwargs)
            docs = retriever.invoke(request.message)
            
            # Fallback if lesson filter returned empty: try general search
            if not docs and target_lesson is not None:
                retriever = v_store.as_retriever(search_kwargs={"k": 3})
                docs = retriever.invoke(request.message)

            if docs:
                context_text += "\n\n".join([f"[Source Note]: {doc.page_content}" for doc in docs if doc.page_content.strip() != "Platform initialized."])
        except Exception as e:
            print(f"RAG Retrieval Error: {e}")
            try:
                store = get_vector_store()
                if store:
                    retriever = store.as_retriever(search_kwargs={"k": 3})
                    docs = retriever.invoke(request.message)
                    if docs:
                        context_text += "\n\n".join([doc.page_content for doc in docs])
            except Exception:
                pass

    if not context_text.strip():
        context_text = "No specific course notes available for this lesson."
    
    requested_lang = request.language if (request.language and request.language.strip() and request.language.lower() != "english") else "the student's spoken/requested language (or English if neutral)"
    
    skill_hint = f"Focus your technical answer specifically on '{request.skill.strip()}'." if request.skill else ""
    
    prompt = f"""
    Verified Course Lesson Context & Skill:
    {context_text}
    
    Student Question:
    {request.message}
    
    Instructions for Multilingual AI Tutor:
    - {skill_hint}
    - Base your answer on the provided lesson/skill context. Provide deep, accurate technical details, real code examples where relevant, and clear conceptual explanations.
    - Detect the language of the student's question or requested language ({requested_lang}) and respond in THAT SAME LANGUAGE.
    - Use clean HTML formatting tags like <strong>, <code>, <pre>, <ul>, <li> for clear representation.
    """
    
    system_msg = "You are a Senior Multilingual AI Technical Tutor. Provide clear, accurate answers grounded in technical course material."
    
    result = execute_llm(prompt, system_message=system_msg, temperature=0.5)
    if not result:
        result = f"<p><strong>Hello!</strong> Regarding '<em>{request.message}</em>': Please review the lesson concepts carefully. Let me know if you have specific code or theory questions!</p>"
    
    source_docs = [doc.page_content[:200] + "..." for doc in docs if doc.page_content.strip() != "Platform initialized."] if docs else []
    
    return ChatResponse(
        response=result,
        source_documents=source_docs
    )

def ingest_pdf_to_vectorstore(file_path: str, lesson_id: Optional[int] = None):
    """
    Loads a PDF file (e.g. course notes), attaches lesson_id metadata to all document chunks,
    and persists the FAISS vector store to disk.
    """
    v_store = get_vector_store()
    emb = get_embeddings()
    if os.path.exists(file_path):
        try:
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader(file_path)
            docs = loader.load_and_split()
            
            # Attach lesson_id metadata to every chunk
            for doc in docs:
                if lesson_id is not None:
                    doc.metadata["lesson_id"] = lesson_id
                doc.metadata["file_path"] = os.path.basename(file_path)
                    
            if v_store is None:
                if emb is None:
                    emb = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                v_store = FAISS.from_documents(docs, embedding=emb)
                global _vector_store
                _vector_store = v_store
            else:
                v_store.add_documents(docs)
                
            save_vector_store()
            print(f"✅ Ingested {len(docs)} pages from {file_path} into FAISS (Lesson ID: {lesson_id}).")
        except Exception as e:
            print(f"❌ Failed to ingest PDF to FAISS: {e}")
