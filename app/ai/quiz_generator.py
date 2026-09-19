import os
import json
import random
import warnings
from ..schemas.quiz import QuizRequest, QuizResponse
from utils.analyzer import execute_llm

def shuffle_question_options(q):
    """
    Shuffles question options randomly so the correct answer is not always in position 'a'.
    Reassigns ids 'a', 'b', 'c', 'd' and updates correct_option_id accordingly.
    """
    options = q.get("options", [])
    if not options or len(options) < 2:
        return q

    correct_id = str(q.get("correct_option_id", "a")).lower()
    
    # Find text of the correct option before shuffling
    correct_text = None
    for opt in options:
        if isinstance(opt, dict) and str(opt.get("id", "")).lower() == correct_id:
            correct_text = opt.get("text")
            break
            
    if not correct_text and isinstance(options[0], dict):
        correct_text = options[0].get("text")

    texts = [opt.get("text") if isinstance(opt, dict) else str(opt) for opt in options]
    random.shuffle(texts)
    
    new_options = []
    new_correct_id = "a"
    for idx, txt in enumerate(texts):
        opt_id = chr(ord('a') + idx)
        new_options.append({"id": opt_id, "text": txt})
        if txt == correct_text:
            new_correct_id = opt_id

    q["options"] = new_options
    q["correct_option_id"] = new_correct_id
    return q

def generate_quiz(request: QuizRequest) -> QuizResponse:
    """
    Generates a structured JSON multiple-choice quiz based on the requested topic
    and uploaded PDF notes using RAG context if lesson_id is provided.
    """
    import re
    topic = (request.topic or "Software Development").strip()
    
    rag_context = ""
    if request.lesson_id:
        try:
            from .tutor import get_vector_store
            vs = get_vector_store()
            if vs:
                filter_dict = {"lesson_id": int(request.lesson_id)}
                try:
                    docs = vs.similarity_search(topic, k=4, filter=filter_dict)
                except Exception:
                    docs = vs.similarity_search(topic, k=4)
                if docs:
                    rag_context = "\n".join([d.page_content for d in docs if d.page_content])
        except Exception as e:
            print(f"Quiz RAG Retrieval Notice: {e}")

    rag_instruction = ""
    if rag_context:
        rag_instruction = f"""
    IMPORTANT: You must generate the quiz questions specifically based on the following uploaded PDF notes for this lesson:
    --- UPLOADED LESSON NOTES (RAG CONTEXT) ---
    {rag_context}
    --- END LESSON NOTES ---
    Ensure the questions test the exact concepts, formulas, code, and definitions from these uploaded notes.
        """

    prompt = f"""
    You are an expert technical hiring manager and computer science professor. Generate a {request.difficulty} level multiple-choice quiz about "{topic}" in {request.language}.
    {rag_instruction}
    You must generate exactly {request.num_questions} realistic, highly technical, and practical questions.
    Each question must test real code patterns, architectural logic, or API understanding of "{topic}".
    Ensure every question includes a thorough, crystal-clear 2-sentence technical explanation of why the correct option is right.
    Randomly distribute the correct answer across 'a', 'b', 'c', and 'd'.
    
    Return ONLY a valid JSON object matching this exact structure:
    {{
        "topic": "{topic}",
        "questions": [
            {{
                "question": "Clear, technically accurate question text about {topic}?",
                "options": [
                    {{"id": "a", "text": "First concrete option"}},
                    {{"id": "b", "text": "Second concrete option"}},
                    {{"id": "c", "text": "Third concrete option"}},
                    {{"id": "d", "text": "Fourth concrete option"}}
                ],
                "correct_option_id": "a",
                "explanation": "Detailed explanation explaining why this option is correct based on {topic} architecture."
            }}
        ]
    }}
    """
    
    response_text = execute_llm(prompt, system_message="You are an expert technical examiner. Always return valid JSON only.", format_json=True, temperature=0.4)
    
    if response_text:
        try:
            match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', response_text)
            json_str = match.group(0) if match else response_text
            quiz_data = json.loads(json_str)
            if "questions" in quiz_data and len(quiz_data["questions"]) > 0:
                shuffled_questions = []
                for q in quiz_data["questions"]:
                    if "options" in q and isinstance(q["options"], list):
                        norm_opts = []
                        for idx, opt in enumerate(q["options"]):
                            if isinstance(opt, str):
                                opt_id = chr(ord('a') + idx)
                                norm_opts.append({"id": opt_id, "text": opt})
                            elif isinstance(opt, dict):
                                opt_id = opt.get("id") or chr(ord('a') + idx)
                                opt_text = opt.get("text") or opt.get("option") or str(opt)
                                norm_opts.append({"id": str(opt_id).lower(), "text": str(opt_text)})
                        q["options"] = norm_opts
                    if "correct_option_id" in q:
                        q["correct_option_id"] = str(q["correct_option_id"]).lower()
                    if "explanation" not in q:
                        q["explanation"] = f"Correct answer verified for {topic} core principles."
                    shuffled_questions.append(shuffle_question_options(q))
                quiz_data["questions"] = shuffled_questions
                return QuizResponse(**quiz_data)
        except Exception as e:
            print(f"Failed to parse AI Quiz JSON: {e}\nRaw output: {response_text}")
    
    # Domain-specific rich fallback quizzes for technical skills
    tl = topic.lower()
    if "fastapi" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the primary role of Pydantic models in FastAPI request handlers?",
                "options": [
                    {"id": "a", "text": "Automatic JSON payload validation, parsing, and OpenAPI schema generation"},
                    {"id": "b", "text": "Directly compiling Python code into C++ binaries"},
                    {"id": "c", "text": "Managing PostgreSQL database connection pools"},
                    {"id": "d", "text": "Handling client-side CSS rendering"}
                ],
                "correct_option_id": "a",
                "explanation": "FastAPI uses Pydantic for data validation, type conversion, and generating OpenAPI documentation dynamically."
            },
            {
                "question": "How does FastAPI achieve asynchronous request handling?",
                "options": [
                    {"id": "a", "text": "Using Python asyncio event loop with ASGI web servers like Uvicorn"},
                    {"id": "b", "text": "By spawning a new OS thread for every single HTTP packet"},
                    {"id": "c", "text": "By executing synchronous WSGI handlers sequentially"},
                    {"id": "d", "text": "Using web workers inside the web browser"}
                ],
                "correct_option_id": "a",
                "explanation": "FastAPI is an ASGI framework built on Starlette and Pydantic, running non-blocking coroutines on the asyncio event loop."
            },
            {
                "question": "Which FastAPI feature is commonly used for authentication, database session management, and shared logic?",
                "options": [
                    {"id": "a", "text": "Dependency Injection system using Depends()"},
                    {"id": "b", "text": "Global environment variables"},
                    {"id": "c", "text": "Hardcoded request body parameters"},
                    {"id": "d", "text": "Thread-local global locks"}
                ],
                "correct_option_id": "a",
                "explanation": "FastAPI's `Depends()` allows declarative dependency injection for reusable authentication, DB sessions, and business logic."
            },
            {
                "question": "What happens when a client sends invalid JSON data to a FastAPI path operation with a Pydantic body model?",
                "options": [
                    {"id": "a", "text": "FastAPI automatically returns an HTTP 422 Unprocessable Entity error with detailed field error descriptions"},
                    {"id": "b", "text": "The server crashes immediately with an unhandled exception"},
                    {"id": "c", "text": "FastAPI silently replaces invalid fields with None and proceeds"},
                    {"id": "d", "text": "The request is redirected to the home route"}
                ],
                "correct_option_id": "a",
                "explanation": "Pydantic validation errors trigger an automatic HTTP 422 response detailing missing or mis-typed JSON fields."
            }
        ]
    elif "docker" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the key difference between CMD and ENTRYPOINT instructions in a Dockerfile?",
                "options": [
                    {"id": "a", "text": "ENTRYPOINT sets the primary executable, while CMD provides default arguments that can be overridden at runtime"},
                    {"id": "b", "text": "CMD runs at image build time, while ENTRYPOINT runs only inside Kubernetes"},
                    {"id": "c", "text": "ENTRYPOINT compiles C code, while CMD creates directory symlinks"},
                    {"id": "d", "text": "There is no functional difference; they are interchangeable aliases"}
                ],
                "correct_option_id": "a",
                "explanation": "ENTRYPOINT specifies the container's main binary, whereas CMD defines default flags/arguments that CLI commands easily override."
            },
            {
                "question": "Why are multi-stage Docker builds recommended for production deployments?",
                "options": [
                    {"id": "a", "text": "They separate build-time SDK dependencies from runtime artifacts, significantly reducing final image size"},
                    {"id": "b", "text": "They allow containers to execute on multiple CPU architectures simultaneously"},
                    {"id": "c", "text": "They automatically encrypt container volumes on host disks"},
                    {"id": "d", "text": "They bypass container image registries entirely"}
                ],
                "correct_option_id": "a",
                "explanation": "Multi-stage builds allow copying compiled binaries into lightweight base images (e.g. alpine), eliminating heavy compiler dependencies."
            },
            {
                "question": "Which command is used to inspect running Docker containers and view their status?",
                "options": [
                    {"id": "a", "text": "docker ps"},
                    {"id": "b", "text": "docker run --all"},
                    {"id": "c", "text": "docker build -t"},
                    {"id": "d", "text": "docker push"}
                ],
                "correct_option_id": "a",
                "explanation": "`docker ps` lists active running containers along with container IDs, names, status, and mapped host ports."
            },
            {
                "question": "How does Docker layer caching optimize container build times?",
                "options": [
                    {"id": "a", "text": "If a Dockerfile instruction and preceding layers haven't changed, Docker reuses cached filesystem layers"},
                    {"id": "b", "text": "It stores built containers directly inside host RAM indefinitely"},
                    {"id": "c", "text": "It downloads pre-compiled binaries from public GitHub repositories"},
                    {"id": "d", "text": "It skips executing RUN instructions during builds"}
                ],
                "correct_option_id": "a",
                "explanation": "Docker checks layer cache line-by-line; placing infrequently changed instructions (like dependency installs) first optimizes build speed."
            }
        ]
    elif "aws" in tl:
        raw_fallback_questions = [
            {
                "question": "Which AWS service provides scalable object storage accessible via HTTP/REST APIs?",
                "options": [
                    {"id": "a", "text": "Amazon S3 (Simple Storage Service)"},
                    {"id": "b", "text": "Amazon EBS (Elastic Block Store)"},
                    {"id": "c", "text": "Amazon EFS (Elastic File System)"},
                    {"id": "d", "text": "AWS ElastiCache"}
                ],
                "correct_option_id": "a",
                "explanation": "Amazon S3 is designed for highly durable, scalable cloud object storage accessed using REST APIs or SDKs."
            },
            {
                "question": "What is the primary function of AWS IAM (Identity and Access Management)?",
                "options": [
                    {"id": "a", "text": "Securely controlling authentication and authorization access permissions for AWS resources"},
                    {"id": "b", "text": "Monitoring server CPU temperature and hardware fan speeds"},
                    {"id": "c", "text": "Provisioning domain names and DNS record routing"},
                    {"id": "d", "text": "Compiling Lambda source code into machine bytecode"}
                ],
                "correct_option_id": "a",
                "explanation": "IAM enables administrators to define fine-grained policies, roles, users, and groups governing cloud resource permissions."
            },
            {
                "question": "What type of cloud computing paradigm does AWS Lambda represent?",
                "options": [
                    {"id": "a", "text": "Serverless Event-Driven Compute (FaaS)"},
                    {"id": "b", "text": "Bare-Metal Dedicated Server Hosting"},
                    {"id": "c", "text": "On-Premises Hypervisor Virtualization"},
                    {"id": "d", "text": "Manual Container Cluster Provisioning"}
                ],
                "correct_option_id": "a",
                "explanation": "AWS Lambda is a serverless compute service that automatically runs code in response to events without managing infrastructure."
            },
            {
                "question": "Which AWS networking component acts as a virtual firewall for controlling EC2 instance inbound and outbound traffic?",
                "options": [
                    {"id": "a", "text": "Security Group"},
                    {"id": "b", "text": "Route Table"},
                    {"id": "c", "text": "Internet Gateway"},
                    {"id": "d", "text": "Direct Connect Link"}
                ],
                "correct_option_id": "a",
                "explanation": "Security Groups operate as stateful virtual firewalls filtering port and IP protocol traffic at the instance interface level."
            }
        ]
    elif "postgres" in tl or "postgresql" in tl:
        raw_fallback_questions = [
            {
                "question": "What tool in PostgreSQL allows developers to analyze query execution plans and index usage?",
                "options": [
                    {"id": "a", "text": "EXPLAIN ANALYZE"},
                    {"id": "b", "text": "SHOW TABLES ALL"},
                    {"id": "c", "text": "DEBUG QUERY EXEC"},
                    {"id": "d", "text": "POSTGRES PROFILER RUN"}
                ],
                "correct_option_id": "a",
                "explanation": "EXPLAIN ANALYZE executes the statement and shows actual runtime costs, execution node timing, and index scan details."
            },
            {
                "question": "Which default index type is created in PostgreSQL for primary key and unique constraints?",
                "options": [
                    {"id": "a", "text": "B-Tree Index"},
                    {"id": "b", "text": "GiST Index"},
                    {"id": "c", "text": "GIN Index"},
                    {"id": "d", "text": "BRIN Index"}
                ],
                "correct_option_id": "a",
                "explanation": "PostgreSQL creates B-Tree indexes by default, offering O(log N) lookup time for equality and range queries."
            },
            {
                "question": "What mechanisms does PostgreSQL use to support Multi-Version Concurrency Control (MVCC)?",
                "options": [
                    {"id": "a", "text": "Tuple versioning with xmin and xmax transaction IDs on table rows"},
                    {"id": "b", "text": "Global table-level exclusive write locking"},
                    {"id": "c", "text": "Writing all updates to flat CSV files"},
                    {"id": "d", "text": "Terminating concurrent reader transactions"}
                ],
                "correct_option_id": "a",
                "explanation": "PostgreSQL MVCC maintains tuple row versions tagged with transaction IDs (xmin/xmax), allowing readers to access snapshot data without blocking writers."
            },
            {
                "question": "Which command-line utility is used to perform logical backups of a PostgreSQL database?",
                "options": [
                    {"id": "a", "text": "pg_dump"},
                    {"id": "b", "text": "postgres_backup"},
                    {"id": "c", "text": "sql_save"},
                    {"id": "d", "text": "pg_sync"}
                ],
                "correct_option_id": "a",
                "explanation": "`pg_dump` dumps a PostgreSQL database into SQL scripts or archive formats for backup and restore purposes."
            }
        ]
    elif "rag" in tl or "vector" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the primary objective of Retrieval-Augmented Generation (RAG) in AI applications?",
                "options": [
                    {"id": "a", "text": "Combining vector similarity retrieval of domain documents with LLM prompt context to eliminate hallucinations"},
                    {"id": "b", "text": "Retraining base LLM weights from scratch every 5 minutes"},
                    {"id": "c", "text": "Converting SQL databases into plain HTML web pages"},
                    {"id": "d", "text": "Compressing MP4 video streams using H.264 codecs"}
                ],
                "correct_option_id": "a",
                "explanation": "RAG retrieves relevant external text chunks using vector search and injects them into the LLM prompt to ground model answers in real facts."
            },
            {
                "question": "Which mathematical metric is most commonly used to compute distance between document vector embeddings in FAISS or ChromaDB?",
                "options": [
                    {"id": "a", "text": "Cosine Similarity / Dot Product"},
                    {"id": "b", "text": "Hamming Distance on ASCII characters"},
                    {"id": "c", "text": "Manhattan Grid Distance on integer coordinates"},
                    {"id": "d", "text": "Levenshtein String Edit Distance"}
                ],
                "correct_option_id": "a",
                "explanation": "Cosine similarity measures the angle between high-dimensional dense embedding vectors to assess semantic closeness."
            },
            {
                "question": "Why is document chunking an essential step prior to vector store indexing in a RAG pipeline?",
                "options": [
                    {"id": "a", "text": "Dense embedding models and LLMs have maximum token context windows, requiring granular semantic sections"},
                    {"id": "b", "text": "To remove all numbers and punctuation from source documents"},
                    {"id": "c", "text": "To translate English documents into binary hex streams"},
                    {"id": "d", "text": "To prevent users from reading full PDF pages"}
                ],
                "correct_option_id": "a",
                "explanation": "Chunking splits large documents into focused, semantically rich snippets that fit embedding context limits and improve retrieval precision."
            },
            {
                "question": "In a RAG architecture, what role does an Embedding Model (e.g. all-MiniLM-L6-v2) play?",
                "options": [
                    {"id": "a", "text": "Translating unstructured text strings into high-dimensional numerical vector representations"},
                    {"id": "b", "text": "Generating human-like conversational responses"},
                    {"id": "c", "text": "Parsing PDF file layouts into JPEG images"},
                    {"id": "d", "text": "Managing HTTP socket connections for REST endpoints"}
                ],
                "correct_option_id": "a",
                "explanation": "Embedding models convert text chunks into dense floating-point vectors capturing deep semantic meanings."
            }
        ]
    elif "kubernetes" in tl or "k8s" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the smallest deployable computing unit in Kubernetes?",
                "options": [
                    {"id": "a", "text": "Pod"},
                    {"id": "b", "text": "Container Cluster"},
                    {"id": "c", "text": "Worker Node"},
                    {"id": "d", "text": "Namespace"}
                ],
                "correct_option_id": "a",
                "explanation": "A Pod represents a single instance of a running process in a cluster, encapsulating one or more co-located containers."
            },
            {
                "question": "Which Kubernetes controller manages declarative updates for Pods, rolling updates, and self-healing replicas?",
                "options": [
                    {"id": "a", "text": "Deployment"},
                    {"id": "b", "text": "Ingress Controller"},
                    {"id": "c", "text": "Kubelet Service"},
                    {"id": "d", "text": "Etcd Database"}
                ],
                "correct_option_id": "a",
                "explanation": "Deployments provide declarative updates for Pods and ReplicaSets, ensuring desired replica counts and zero-downtime rollouts."
            },
            {
                "question": "What is the role of etcd in a Kubernetes Control Plane?",
                "options": [
                    {"id": "a", "text": "Strongly consistent, distributed key-value store holding cluster state metadata"},
                    {"id": "b", "text": "Load balancing HTTP traffic across external ingress routers"},
                    {"id": "c", "text": "Building Docker container images directly on worker nodes"},
                    {"id": "d", "text": "Streaming container application stdout logs"}
                ],
                "correct_option_id": "a",
                "explanation": "etcd is Kubernetes' primary database, storing cluster configuration, node state, secrets, and workload specifications."
            },
            {
                "question": "Which kubectl command retrieves real-time stdout/stderr output from a specified Pod?",
                "options": [
                    {"id": "a", "text": "kubectl logs <pod-name>"},
                    {"id": "b", "text": "kubectl get pod --output-text"},
                    {"id": "c", "text": "kubectl describe cluster"},
                    {"id": "d", "text": "kubectl exec --print"}
                ],
                "correct_option_id": "a",
                "explanation": "`kubectl logs` fetches the console logs emitted by containers inside the target pod for debugging."
            }
        ]
    elif "react" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the primary function of the Virtual DOM in React?",
                "options": [
                    {"id": "a", "text": "Minimizing expensive direct browser DOM manipulations through diffing (reconciliation)"},
                    {"id": "b", "text": "Running client-side JavaScript inside a WebAssembly sandbox"},
                    {"id": "c", "text": "Managing server-side SQL database transactions"},
                    {"id": "d", "text": "Bypassing browser CSS stylesheet rules"}
                ],
                "correct_option_id": "a",
                "explanation": "React maintains a lightweight Virtual DOM tree in memory, diffing changes against the actual DOM to perform minimal batch updates."
            },
            {
                "question": "In React functional components, which hook is used to perform side effects (e.g. data fetching, event listeners)?",
                "options": [
                    {"id": "a", "text": "useEffect"},
                    {"id": "b", "text": "useState"},
                    {"id": "c", "text": "useContext"},
                    {"id": "d", "text": "useReducer"}
                ],
                "correct_option_id": "a",
                "explanation": "useEffect handles lifecycle side-effects such as API calls, subscriptions, and DOM updates after component rendering."
            },
            {
                "question": "Why must state variables created with useState never be mutated directly (e.g. count = 5)?",
                "options": [
                    {"id": "a", "text": "Direct mutation bypasses React's state setter, failing to trigger component re-renders"},
                    {"id": "b", "text": "It throws a fatal browser syntax exception immediately"},
                    {"id": "c", "text": "It deletes the component from the DOM tree"},
                    {"id": "d", "text": "It converts numbers into string data types"}
                ],
                "correct_option_id": "a",
                "explanation": "React detects state changes via reference comparisons in setter functions; mutating state directly does not alert React to re-render."
            },
            {
                "question": "What key prop requirement must be satisfied when rendering lists of elements in React?",
                "options": [
                    {"id": "a", "text": "Each item must have a unique 'key' prop to help React identify inserted, updated, or removed items"},
                    {"id": "b", "text": "List items must all be wrapped in HTML table tags"},
                    {"id": "c", "text": "All items must have identical class names"},
                    {"id": "d", "text": "Items must be sorted alphabetically before rendering"}
                ],
                "correct_option_id": "a",
                "explanation": "Unique keys give list items a persistent identity, allowing React's reconciliation algorithm to efficiently re-order elements."
            }
        ]
    elif "node" in tl:
        raw_fallback_questions = [
            {
                "question": "Which component handles asynchronous I/O and threading under the hood in Node.js?",
                "options": [
                    {"id": "a", "text": "libuv multi-platform C library"},
                    {"id": "b", "text": "Apache HTTP Server core"},
                    {"id": "c", "text": "Direct OS kernel interrupts without abstractions"},
                    {"id": "d", "text": "V8 Garbage Collector exclusively"}
                ],
                "correct_option_id": "a",
                "explanation": "Node.js relies on libuv for its cross-platform asynchronous I/O engine, event loop, and internal worker thread pool."
            },
            {
                "question": "In the Node.js event loop, when do process.nextTick() callbacks execute?",
                "options": [
                    {"id": "a", "text": "Immediately after the current operation finishes, before any other event loop phase"},
                    {"id": "b", "text": "At the start of the next Poll phase after timers"},
                    {"id": "c", "text": "Only when the thread pool is completely idle"},
                    {"id": "d", "text": "After setImmediate callbacks are evaluated"}
                ],
                "correct_option_id": "a",
                "explanation": "process.nextTick is part of the microtask queue and runs immediately after the current script executes, before the event loop advances to the next phase."
            },
            {
                "question": "Why are Node.js Streams preferred over fs.readFile when reading massive files?",
                "options": [
                    {"id": "a", "text": "Streams process data sequentially in chunks without loading the entire file into RAM"},
                    {"id": "b", "text": "Streams automatically compile JavaScript into binary assembly"},
                    {"id": "c", "text": "Streams bypass the V8 security sandbox entirely"},
                    {"id": "d", "text": "Streams prevent multiple concurrent HTTP requests"}
                ],
                "correct_option_id": "a",
                "explanation": "Readable and Writable Streams process chunks piece by piece, keeping memory footprint low even when transferring gigabytes of data."
            },
            {
                "question": "How does Node.js cluster module achieve vertical scaling across multi-core CPUs?",
                "options": [
                    {"id": "a", "text": "It forks child processes that share the same server port and distributes incoming connections"},
                    {"id": "b", "text": "It compiles JavaScript to multi-threaded C++ at runtime"},
                    {"id": "c", "text": "It overrides the operating system scheduler with hardware microcode"},
                    {"id": "d", "text": "It disables the event loop to run synchronous loops in parallel"}
                ],
                "correct_option_id": "a",
                "explanation": "The cluster module spawns worker processes sharing the primary port, utilizing round-robin load distribution across available CPU cores."
            }
        ]
    elif "mongo" in tl:
        raw_fallback_questions = [
            {
                "question": "What is the primary binary serialization format utilized by MongoDB to store documents?",
                "options": [
                    {"id": "a", "text": "BSON (Binary JSON)"},
                    {"id": "b", "text": "Protocol Buffers (Protobuf)"},
                    {"id": "c", "text": "Raw XML string blobs"},
                    {"id": "d", "text": "MessagePack"}
                ],
                "correct_option_id": "a",
                "explanation": "MongoDB stores documents in BSON, a binary-encoded format that extends JSON with rich data types like Date and raw binary data."
            },
            {
                "question": "Which MongoDB aggregation pipeline stage is used to perform a left outer join with another collection?",
                "options": [
                    {"id": "a", "text": "$lookup"},
                    {"id": "b", "text": "$join"},
                    {"id": "c", "text": "$mergeDocuments"},
                    {"id": "d", "text": "$relate"}
                ],
                "correct_option_id": "a",
                "explanation": "The $lookup aggregation stage performs a left outer join to an unsharded collection in the same database to filter and combine documents."
            },
            {
                "question": "What does a 'COLLSCAN' stage in MongoDB explain('executionStats') output indicate?",
                "options": [
                    {"id": "a", "text": "A full collection scan occurred because no index satisfied the query"},
                    {"id": "b", "text": "The query was satisfied entirely using an in-memory index"},
                    {"id": "c", "text": "Documents were retrieved directly from the RAM buffer pool"},
                    {"id": "d", "text": "The database encountered a replica set synchronization error"}
                ],
                "correct_option_id": "a",
                "explanation": "A COLLSCAN indicates MongoDB had to scan every single document in the collection because no suitable index (IXSCAN) was available."
            },
            {
                "question": "In MongoDB Replica Sets, what is the role of the Primary node?",
                "options": [
                    {"id": "a", "text": "It accepts all write operations and writes to the oplog for secondaries to replicate"},
                    {"id": "b", "text": "It only stores configuration metadata without processing CRUD"},
                    {"id": "c", "text": "It functions solely as an arbiter during election votes"},
                    {"id": "d", "text": "It automatically fragments chunks across shard routers"}
                ],
                "correct_option_id": "a",
                "explanation": "The primary node is the only member in a replica set that receives write operations and records state changes to its operation log (oplog)."
            }
        ]
    elif "mysql" in tl or "sql" in tl:
        raw_fallback_questions = [
            {
                "question": "Which storage engine in MySQL provides full ACID transactions and foreign key referential integrity?",
                "options": [
                    {"id": "a", "text": "InnoDB"},
                    {"id": "b", "text": "MyISAM"},
                    {"id": "c", "text": "MEMORY / HEAP"},
                    {"id": "d", "text": "CSV Engine"}
                ],
                "correct_option_id": "a",
                "explanation": "InnoDB is the default MySQL storage engine featuring row-level locking, foreign key constraints, and ACID compliant crash recovery."
            },
            {
                "question": "What does the SQL command 'EXPLAIN' reveal when prepended to a SELECT query?",
                "options": [
                    {"id": "a", "text": "The optimizer's query execution plan, including table scan types, indexes used, and row estimates"},
                    {"id": "b", "text": "A natural language summary generated by an AI assistant"},
                    {"id": "c", "text": "The hard drive sector location where table data is physically written"},
                    {"id": "d", "text": "The user credentials of the connection executing the query"}
                ],
                "correct_option_id": "a",
                "explanation": "EXPLAIN provides details on how MySQL executes queries, showing indexes utilized, join types (e.g. ALL, ref, range), and estimated rows examined."
            },
            {
                "question": "Which transaction isolation level in MySQL prevents Dirty Reads, Non-Repeatable Reads, and Phantom Reads?",
                "options": [
                    {"id": "a", "text": "SERIALIZABLE"},
                    {"id": "b", "text": "READ UNCOMMITTED"},
                    {"id": "c", "text": "READ COMMITTED"},
                    {"id": "d", "text": "REPEATABLE READ"}
                ],
                "correct_option_id": "a",
                "explanation": "SERIALIZABLE is the highest isolation level that emulates serial transaction execution to eliminate dirty reads, non-repeatable reads, and phantom reads."
            },
            {
                "question": "What is the fundamental difference between WHERE and HAVING clauses in SQL?",
                "options": [
                    {"id": "a", "text": "WHERE filters individual rows before grouping; HAVING filters aggregated groups after GROUP BY"},
                    {"id": "b", "text": "WHERE can only be used on primary keys, while HAVING is used on foreign keys"},
                    {"id": "c", "text": "HAVING executes before WHERE in the logical query processing order"},
                    {"id": "d", "text": "WHERE is only supported in MySQL, whereas HAVING is ANSI SQL exclusive"}
                ],
                "correct_option_id": "a",
                "explanation": "WHERE filters rows prior to aggregation, while HAVING filters the results of aggregate functions (like SUM, COUNT, AVG) after GROUP BY."
            }
        ]
    elif "python" in tl:
        raw_fallback_questions = [
            {
                "question": "How does CPython's memory management handle cyclic object references?",
                "options": [
                    {"id": "a", "text": "It combines reference counting with a cyclic generational garbage collector"},
                    {"id": "b", "text": "It relies exclusively on manual malloc/free calls"},
                    {"id": "c", "text": "It terminates the application process when cycles occur"},
                    {"id": "d", "text": "It forces objects to live in immutable memory blocks"}
                ],
                "correct_option_id": "a",
                "explanation": "CPython uses reference counting as its primary memory manager and a generational cyclic garbage collector to detect and free reference cycles."
            },
            {
                "question": "What is the primary purpose of Python's Global Interpreter Lock (GIL)?",
                "options": [
                    {"id": "a", "text": "To prevent multiple native threads from executing CPython bytecode simultaneously, protecting reference count integrity"},
                    {"id": "b", "text": "To lock source code files from being edited while running"},
                    {"id": "c", "text": "To enforce type safety on global variable declarations"},
                    {"id": "d", "text": "To prevent network connections from timing out"}
                ],
                "correct_option_id": "a",
                "explanation": "The GIL is a mutex that protects access to Python objects, preventing multiple native threads from concurrently executing Python bytecodes."
            },
            {
                "question": "What makes Python generator functions using 'yield' memory-efficient compared to returning lists?",
                "options": [
                    {"id": "a", "text": "Generators produce items lazily one at a time on demand rather than storing the entire dataset in RAM"},
                    {"id": "b", "text": "Generators compress data into gzip archives in memory"},
                    {"id": "c", "text": "Generators execute directly on the GPU"},
                    {"id": "d", "text": "Generators bypass Python's object model and write to disk"}
                ],
                "correct_option_id": "a",
                "explanation": "Generators return an iterator that yields one value per next() iteration, maintaining state while consuming minimal RAM for huge streams."
            },
            {
                "question": "In Python asyncio, what does 'await' keyword do when called on a coroutine?",
                "options": [
                    {"id": "a", "text": "It pauses the coroutine execution and yields control back to the event loop until the awaited task completes"},
                    {"id": "b", "text": "It spawns a new operating system process in the background"},
                    {"id": "c", "text": "It locks the CPU core to execute the task synchronously"},
                    {"id": "d", "text": "It deletes the coroutine from memory if it takes longer than 1 second"}
                ],
                "correct_option_id": "a",
                "explanation": "The await keyword suspends execution of the current coroutine, allowing the event loop to run other scheduled tasks while waiting for I/O."
            }
        ]
    else:
        raw_fallback_questions = [
            {
                "question": f"Which core architectural principle is vital for enterprise applications built with {topic}?",
                "options": [
                    {"id": "a", "text": f"Modular separation of concerns, defensive error handling, and scalable execution design for {topic}"},
                    {"id": "b", "text": "Hardcoding static configuration credentials into source code files"},
                    {"id": "c", "text": "Disabling automated unit testing and logging pipelines"},
                    {"id": "d", "text": "Writing monolithic functions exceeding 5,000 lines"}
                ],
                "correct_option_id": "a",
                "explanation": f"Enterprise applications utilizing {topic} rely on clean modular boundaries, comprehensive error bounds, and scalable execution patterns."
            },
            {
                "question": f"How should high-throughput asynchronous operations be managed when implementing {topic}?",
                "options": [
                    {"id": "a", "text": f"Utilizing non-blocking async primitives, thread pooling, and structured exception boundaries tailored for {topic}"},
                    {"id": "b", "text": "Blocking the main execution thread indefinitely until disk I/O responds"},
                    {"id": "c", "text": "Executing infinite loops without timeout delays"},
                    {"id": "d", "text": "Ignoring failed network responses and continuing execution"}
                ],
                "correct_option_id": "a",
                "explanation": f"Non-blocking concurrency and structured timeout policies prevent system deadlocks and maintain system responsiveness in {topic}."
            },
            {
                "question": f"What telemetry and logging practice is required for production observability in {topic} workloads?",
                "options": [
                    {"id": "a", "text": f"Emitting structured JSON logs with correlation IDs, tracing spans, and performance metrics for {topic}"},
                    {"id": "b", "text": "Relying exclusively on unformatted console prints on production servers"},
                    {"id": "c", "text": "Disabling diagnostic logs completely to reduce disk writes"},
                    {"id": "d", "text": "Waiting for end users to report application crashes"}
                ],
                "correct_option_id": "a",
                "explanation": f"Structured logs and distributed telemetry allow engineering teams to quickly isolate bottlenecks and root causes in {topic} deployments."
            },
            {
                "question": f"When security hardening systems leveraging {topic}, which security posture is mandatory?",
                "options": [
                    {"id": "a", "text": f"Strict input validation, least-privilege authorization, and end-to-end cryptographic encryption across {topic} services"},
                    {"id": "b", "text": "Exposing internal administration ports directly to the public internet"},
                    {"id": "c", "text": "Disabling TLS/SSL encryption on external REST endpoints"},
                    {"id": "d", "text": "Storing secret keys in client-side local storage without encryption"}
                ],
                "correct_option_id": "a",
                "explanation": f"Defense-in-depth security mandates input sanitization, least-privilege access, and encrypted transport for all {topic} components."
            }
        ]

    shuffled_fallback = [shuffle_question_options(q) for q in raw_fallback_questions]

    return QuizResponse(
        topic=topic,
        questions=shuffled_fallback
    )

