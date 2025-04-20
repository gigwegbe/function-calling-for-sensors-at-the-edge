
# Complete function descriptions for the farm control system

import json
import re
import os
import datetime
import numpy as np
import traceback
import logging
from typing import List, Dict, Optional, Union, Any, Tuple, TypedDict
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import StateGraph, START, END
from services.farm_control_service import FarmControlService
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

FUNCTION_DESCRIPTIONS = {
    "get_all_farms": {
        "description": "Get information about all farms in the system",
        "args": {"include_related": "Boolean to include related entities like fields, sensors, actuators"}
    },
    "get_farm_by_id": {
        "description": "Get information about a specific farm by ID",
        "args": {"farm_id": "ID of the farm", "include_related": "Boolean to include related entities"}
    },
    "get_all_fields": {
        "description": "Get information about all fields across all farms",
        "args": {"include_related": "Boolean to include related entities like sensors, actuators"}
    },
    "get_field_by_id": {
        "description": "Get information about a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_field_by_name": {
        "description": "Get information about a specific field by name",
        "args": {"field_name": "Name of the field", "include_related": "Boolean to include related entities"}
    },
    "get_all_sensors": {
        "description": "Get information about all sensors in the system",
        "args": {"include_related": "Boolean to include related field information"}
    },
    "get_sensor_by_id": {
        "description": "Get information about a specific sensor by ID",
        "args": {"sensor_id": "ID of the sensor", "include_related": "Boolean to include related field information"}
    },
    "get_all_actuators": {
        "description": "Get information about all actuators in the system",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_actuator_by_type": {
        "description": "Get information about actuators of a specific type",
        "args": {"actuator_type": "Type of actuator (e.g., 'water_valves', 'pump')", "include_related": "Boolean to include related entities"}
    },
    "get_actuator_by_id": {
        "description": "Get information about a specific actuator by ID",
        "args": {"actuator_id": "ID of the actuator", "include_related": "Boolean to include related entities"}
    },
    "get_all_resources": {
        "description": "Get information about all resources (water tanks, fertilizer tanks, etc.)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_resource_by_id": {
        "description": "Get information about a specific resource by ID",
        "args": {"resource_id": "ID of the resource", "include_related": "Boolean to include related entities"}
    },
    "get_actuators_by_field": {
        "description": "Get all actuators associated with a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_actuators_by_field_name": {
        "description": "Get all actuators associated with a specific field by name",
        "args": {"field_name": "Name of the field", "include_related": "Boolean to include related entities"}
    },
    "get_sensors_by_field": {
        "description": "Get all sensors in a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_active_actuators": {
        "description": "Get all actuators that are currently active (open status)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_inactive_actuators": {
        "description": "Get all actuators that are currently inactive (closed status)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_resource_levels": {
        "description": "Get current levels of all resources (water tanks, fertilizer tanks, etc.)",
        "args": {}
    },
    "update_actuator_status": {
        "description": "Update the status of an actuator (open/close). Common commands include: 'open', 'start', 'activate', 'turn on', 'switch on', 'enable', 'power on' for opening; and 'close', 'stop', 'deactivate', 'turn off', 'switch off', 'disable', 'shut down', 'power off' for closing.",
        "args": {"actuator_id": "ID of the actuator", "new_status": "New status ('open', 'close')"}
    },
    "get_resource_dependent_actuators": {
        "description": "Get all actuators that depend on a specific resource",
        "args": {"resource_id": "ID of the resource", "include_related": "Boolean to include related entities"}
    },
    "update_resource_level": {
        "description": "Update the current level of a resource",
        "args": {"resource_id": "ID of the resource", "new_level": "New level value"}
    }
}

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)
    
class EnhancedVectorSearchEngine:
    """Improved embedding-based vector search engine for RAG examples with better caching"""
    def __init__(self, api_key: str, embedding_model: str = "text-embedding-3-small"):
        self.embeddings = OpenAIEmbeddings(api_key=api_key, model=embedding_model)
        self.example_embeddings = []
        self.examples = []
        self.embedding_cache = {}  # Cache for embeddings
        
    def add_examples(self, examples: List[Dict]):
        """Add examples to the vector store with caching"""
        self.examples = examples
        
        # Extract user requests for embedding
        user_requests = [example.get("user_request", "") for example in examples]
        
        # Use cached embeddings where possible
        new_requests = []
        new_indices = []
        self.example_embeddings = [None] * len(user_requests)
        
        for i, request in enumerate(user_requests):
            if request in self.embedding_cache:
                self.example_embeddings[i] = self.embedding_cache[request]
            else:
                new_requests.append(request)
                new_indices.append(i)
        
        # Generate embeddings for new requests in batch
        if new_requests:
            new_embeddings = self.embeddings.embed_documents(new_requests)
            
            # Store in cache and result list
            for j, idx in enumerate(new_indices):
                self.example_embeddings[idx] = new_embeddings[j]
                self.embedding_cache[user_requests[idx]] = new_embeddings[j]
    
    def search(self, query: str, top_k: int = 3, threshold: float = 0.75) -> List[Dict]:
        """Search for similar examples using cosine similarity with embedding caching"""
        # Check if query is in cache, otherwise generate embedding
        if query not in self.embedding_cache:
            query_embedding = self.embeddings.embed_query(query)
            self.embedding_cache[query] = query_embedding
        else:
            query_embedding = self.embedding_cache[query]
        
        # Calculate similarities using numpy for efficiency - no need for additional embeddings
        query_embedding_array = np.array([query_embedding])
        example_embedding_array = np.array(self.example_embeddings)
        
        # Calculate cosine similarity
        similarities = cosine_similarity(query_embedding_array, example_embedding_array)[0]
        
        # Create results with scores
        results = []
        for i, score in enumerate(similarities):
            if score >= threshold:
                example = self.examples[i].copy()
                example["similarity_score"] = float(score)
                results.append(example)
        
        # Sort by similarity score (highest first)
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        logging.info(f"Found {len(results)} results with similarity >= {threshold}")    
        
        # Return top k results
        return results[:top_k]
    

class AmbiguityResolver:
    def __init__(self, system_info):
        self.components = system_info['actuators'] + system_info['sensors']
        self.fields = system_info['fields']
        
    def resolve_partial_ids(self, text: str) -> str:
        """Resolve partial component IDs in text to full IDs"""
        pattern = r"\b([A-Z]{2,4}-?\d{0,4})\b"
        for match in re.finditer(pattern, text):
            partial_id = match.group(1)
            full_id = self._find_closest_component(partial_id)
            if full_id:
                text = text.replace(partial_id, full_id)
        return text
    
    def _find_closest_component(self, partial: str) -> Optional[str]:
        """Find the closest matching component ID for a partial ID"""
        candidates = [c['id'] for c in self.components]
        matches = [c for c in candidates if partial in c]
        return matches[0] if matches else None
    
    def resolve_field_references(self, text: str) -> str:
        """Resolve ambiguous field references using known field names"""
        for field in self.fields:
            field_name = field.get('name', '')
            if field_name and field_name.lower() in text.lower():
                # Replace ambiguous references with specific field name
                text = re.sub(r'\b(field|area|section)\b', field_name, text, flags=re.IGNORECASE)
        return text

class MemoryControlAgent:
    """Farm control agent with memory and vector search capabilities"""
    def __init__(self, rag_examples_path: str, farm_control_service: Optional[FarmControlService] = None, 
                 model_name: str = "gpt-4o", temperature: float = 0.1):
        # Load RAG examples
        with open(rag_examples_path, "r") as f:
            self.rag_data = json.load(f)

        # Set up API key and models
        self.api_key = os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, model=model_name, temperature=temperature)
        self.farm_control_service = farm_control_service
        
        # Set up vector search
        self.vector_search = EnhancedVectorSearchEngine(api_key=self.api_key)
        self._prepare_vector_search()
        
        # Prefetch system information
        self.system_info = self._prefetch_system_info() if farm_control_service else {
            "farms": [], "fields": [], "actuators": [], "sensors": [], "resources": []
        }

        # Initialize memory
        self.memory = {
            "last_field": None,
            "last_actuator": None,
            "last_actuator_type": None,
            "last_actuator_name": None,
            "last_crop": None,
            "last_action": None,
            "field_focus": False,
            "crop_focus": False,
            "last_interaction_type": None,
            "conversation_history": []
        }
        self.patterns = {
        "actuator_ids": r"([A-Z]+-\d{4})",
        "field_ids": r"field\s+(\d+)|field\s+(\w+)",
        "field_names": r"([A-Za-z]+)\s+field|([A-Za-z]+ern)\s+field?|field\s+of\s+([A-Za-z]+)|([A-Za-z]+)\s+Field",
        "resource_ids": r"(RES-\d{4})",
        "open_command": r"\b(open|start|activate|turn\s+on|switch\s+on|enable|power\s+on)\b",
        "close_command": r"\b(close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off)\b",
        "status_query": r"\b(status|state|condition|what\s+is|how\s+is)\b",
        "level_query": r"\b(level|volume|amount|capacity|how\s+much)\b",
        "all_keyword": r"\b(all|every|each)\b",
        "actuator_types": r"\b(valves?|pumps?|actuators?|water\s+valves?|sensors?|equipment|machines?|devices?)\b",
        "irrigation_command": r"\b(irrigate|water|start\s+irrigation|begin\s+watering)\b",
        "irrigation_stop": r"\b(stop\s+irrigation|stop\s+watering|end\s+irrigation)\b",
        "moisture_query": r"\b(moisture|wetness|humidity|soil\s+moisture)\b",
        "temperature_query": r"\b(temperature|heat|warmth|how\s+hot|how\s+cold)\b",
        "bulk_operation": r"\b(all|every|each|multiple|several|many)\b",
        "crop_reference": r"\b(corn|wheat|soy|soybeans|barley|alfalfa|cotton|rice|potatoes|vegetables)\b"
    }

        
        self.field_actuator_map = self._build_field_actuator_map()
        self.resource_actuator_map = self._build_resource_dependencies()
        self.ambiguous_handler = AmbiguityResolver(self.system_info)

        # Build and compile graph
        self.graph = self._build_graph().compile()
        
    def batch_update_actuators(self, field_id: str, new_status: str):
        actuator_ids = self.field_actuator_map.get(field_id, [])
        return [
            self.farm_control_service.update_actuator_status(
                actuator_id=aid,
                new_status=new_status
            ) for aid in actuator_ids
        ]
        
    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract relevant entities from user request using enhanced patterns"""
        entities = {
            "actuator_ids": re.findall(self.patterns["actuator_ids"], text, re.IGNORECASE),
            "field_ids": [x[0] or x[1] for x in re.findall(self.patterns["field_ids"], text, re.IGNORECASE) if x[0] or x[1]],
            "field_names": [],  # We'll extract these from field_names pattern matches
            "resource_ids": re.findall(self.patterns["resource_ids"], text, re.IGNORECASE),
            "is_irrigation_command": bool(re.search(self.patterns["irrigation_command"], text, re.IGNORECASE)),
            "is_irrigation_stop": bool(re.search(self.patterns["irrigation_stop"], text, re.IGNORECASE)),
            "is_moisture_query": bool(re.search(self.patterns["moisture_query"], text, re.IGNORECASE)),
            "is_temperature_query": bool(re.search(self.patterns["temperature_query"], text, re.IGNORECASE)),
            "is_bulk_operation": bool(re.search(self.patterns["bulk_operation"], text, re.IGNORECASE)),
            "has_status_query": bool(re.search(self.patterns["status_query"], text, re.IGNORECASE)),
            "has_level_query": bool(re.search(self.patterns["level_query"], text, re.IGNORECASE)),
            "has_open_command": bool(re.search(self.patterns["open_command"], text, re.IGNORECASE)),
            "has_close_command": bool(re.search(self.patterns["close_command"], text, re.IGNORECASE))
        }

        # Extract field names from more complex pattern
        field_matches = re.finditer(self.patterns["field_names"], text, re.IGNORECASE)
        for match in field_matches:
            # Get the first non-None group from the match
            field_name = next((g for g in match.groups() if g is not None), None)
            if field_name:
                entities["field_names"].append(field_name)

        return entities

    def _build_field_actuator_map(self) -> Dict[str, List[str]]:
        """Build a map of field IDs to actuator IDs"""
        field_actuator_map = {}
        for field in self.system_info.get("fields", []):
            field_id = field.get("id")
            actuators = self.farm_control_service.get_actuators_by_field(field_id)
            actuator_ids = [actuator.get("id") for actuator in actuators]
            field_actuator_map[field_id] = actuator_ids
        return field_actuator_map
        
    def _build_resource_dependencies(self) -> Dict[str, List[str]]:
        """Build a map of resource IDs to actuator IDs"""
        resource_actuator_map = {}
        for resource in self.system_info.get("resources", []):
            resource_id = resource.get("id")
            actuators = self.farm_control_service.get_resource_dependent_actuators(resource_id)
            actuator_ids = [actuator.get("id") for actuator in actuators]
            resource_actuator_map[resource_id] = actuator_ids
        return resource_actuator_map
    

    def _prepare_vector_search(self):
        """Prepare vector search with RAG examples using the enhanced search engine"""
        examples = []
        try:
            # Extract all examples from categories
            for category in self.rag_data:
                category_examples = category.get("examples", [])
                # Add category tag to each example for better filtering
                for example in category_examples:
                    example["category"] = category.get("category", "unknown")
                examples.extend(category_examples)
            
            # Add examples to vector search
            self.vector_search = EnhancedVectorSearchEngine(api_key=self.api_key)
            self.vector_search.add_examples(examples)
            print(f"Vector search initialized with {len(examples)} examples")
        except Exception as e:
            print(f"Error initializing vector search: {e}")
            print(f"Stack trace: {traceback.format_exc()}")
            # Initialize with empty examples as fallback
            self.vector_search = EnhancedVectorSearchEngine(api_key=self.api_key)
            self.vector_search.add_examples([])
        
    def _prefetch_system_info(self):
        """Prefetch farm system information"""
        try:
            return {
                "farms": self.farm_control_service.get_all_farms(),
                "fields": self.farm_control_service.get_all_fields(),
                "actuators": self.farm_control_service.get_all_actuators(),
                "sensors": self.farm_control_service.get_all_sensors(),
                "resources": self.farm_control_service.get_all_resources()
            }
        except Exception as e:
            print("[System Prefetch Failed]", str(e))
            return {"farms": [], "fields": [], "actuators": [], "sensors": [], "resources": []}

    def update_memory(self, state: Dict):
        """Update agent memory based on executed functions and their results"""
        for call in state.get("function_calls", []):
            fn_name = call.get("function", "")
            args = call.get("args", {})
            result = call.get("result", {})
            
            # Update field in memory
            if fn_name == "get_field_by_name" and result:
                self.memory["last_field"] = result.get("name") if isinstance(result, dict) else None
                self.memory["field_focus"] = True
                self.memory["last_interaction_type"] = "field_info"
                
            elif fn_name == "get_field_by_id" and result:
                self.memory["last_field"] = result.get("name") if isinstance(result, dict) else None
                self.memory["field_focus"] = True
                self.memory["last_interaction_type"] = "field_info"
                
            elif fn_name == "get_all_fields" and result and isinstance(result, list) and len(result) > 0:
                # Only update if we're focusing on a specific field
                if len(result) == 1:
                    self.memory["last_field"] = result[0].get("name") if isinstance(result[0], dict) else None
                    self.memory["field_focus"] = True
                    self.memory["last_interaction_type"] = "field_info"
                else:
                    self.memory["field_focus"] = False
            
            # Update actuator in memory
            if fn_name == "get_actuator_by_id" and result:
                self.memory["last_actuator"] = result.get("id") if isinstance(result, dict) else None
                self.memory["last_actuator_name"] = result.get("name") if isinstance(result, dict) else None
                self.memory["last_actuator_type"] = result.get("type") if isinstance(result, dict) else None
                self.memory["last_interaction_type"] = "actuator_info"
                
            elif fn_name == "update_actuator_status" and args:
                self.memory["last_actuator"] = args.get("actuator_id")
                self.memory["last_action"] = args.get("new_status")
                self.memory["last_interaction_type"] = "actuator_control"
                
                # If this was a field-level operation, update the field focus
                if args.get("field_name"):
                    self.memory["last_field"] = args.get("field_name")
                    self.memory["field_focus"] = True
            
            # Extract crop info if available
            if fn_name in ["get_field_by_name", "get_field_by_id"] and result and isinstance(result, dict):
                self.memory["last_crop"] = result.get("crop_type")
                if result.get("crop_type"):
                    self.memory["crop_focus"] = True
        
        # Add request and response to conversation history (limit to last 10 exchanges)
        self.memory["conversation_history"].append({
            "request": state.get("user_request", ""),
            "response": state.get("user_response", ""),
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        # Apply temporal decay to focus flags (reduce focus over time)
        if len(self.memory["conversation_history"]) > 3:
            # After 3 exchanges, start reducing focus strength
            if self.memory.get("field_focus") is True:
                self.memory["field_focus"] = "weakening"
            elif self.memory.get("field_focus") == "weakening":
                self.memory["field_focus"] = False

            if self.memory.get("crop_focus") is True:
                self.memory["crop_focus"] = "weakening"
            elif self.memory.get("crop_focus") == "weakening":
                self.memory["crop_focus"] = False
        
        # Keep history to last 10 exchanges
        if len(self.memory["conversation_history"]) > 10:
            self.memory["conversation_history"] = self.memory["conversation_history"][-10:]
        
        return self.memory
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between two text embeddings using cache"""
        # Check cache first
        if text1 not in self.vector_search.embedding_cache:
            embedding1 = self.vector_search.embeddings.embed_query(text1)
            self.vector_search.embedding_cache[text1] = embedding1
        else:
            embedding1 = self.vector_search.embedding_cache[text1]
        
        if text2 not in self.vector_search.embedding_cache:
            embedding2 = self.vector_search.embeddings.embed_query(text2)
            self.vector_search.embedding_cache[text2] = embedding2
        else:
            embedding2 = self.vector_search.embedding_cache[text2]
            
        similarity = cosine_similarity([embedding1], [embedding2])[0][0]
        return float(similarity)
    
    def resolve_rag_example(self, user_request: str) -> Optional[Dict]:
        """
        Resolve user request against RAG examples for exact or near-exact matches
        with improved caching
        """
        # Quick check for exact match in examples first
        for category in self.rag_data:
            for example in category.get("examples", []):
                if user_request.lower() == example.get("user_request", "").lower():
                    # Exact string match - no need for embedding
                    example["similarity_score"] = 1.0
                    example["category"] = category.get("category", "unknown")
                    return example
        
        # For non-exact matches, check if we already have embedding results cached
        cached_results = self.vector_search.search(user_request, top_k=1, threshold=0.85)
        if cached_results and cached_results[0].get("similarity_score", 0) > 0.85:
            cached_results[0]["category"] = next(
                (cat.get("category", "unknown") for cat in self.rag_data 
                 if any(ex.get("user_request") == cached_results[0].get("user_request") 
                        for ex in cat.get("examples", []))),
                "unknown"
            )
            return cached_results[0]
        
        return None
    
    def resolve_user_intent(self, user_request: str) -> Dict:
        """Enhanced intent resolution using pattern matching"""
        try:
            # Extract entities first
            entities = self._extract_entities(user_request)
            
            # Determine basic intent category based on patterns
            intent_category = "other"
            if entities["has_status_query"]:
                intent_category = "status_check"
            elif entities["has_level_query"]:
                intent_category = "information_request"
            elif entities["has_open_command"] or entities["has_close_command"] or \
                entities["is_irrigation_command"] or entities["is_irrigation_stop"]:
                intent_category = "control_operation"
                
            # Build function calls based on extracted entities
            function_calls = []
            
            if intent_category == "control_operation":
                # Handle irrigation commands
                if entities["is_irrigation_command"] or entities["is_irrigation_stop"]:
                    status = "open" if entities["is_irrigation_command"] else "close"
                    
                    # If we have a specific field, use it
                    if entities["field_names"]:
                        for field_name in entities["field_names"]:
                            function_calls.append({
                                "function": "update_actuator_status",
                                "args": {
                                    "actuator_id": "field",
                                    "field_name": field_name,
                                    "new_status": status
                                }
                            })
                    else:
                        # Use last field from memory if available
                        if self.memory.get("last_field"):
                            function_calls.append({
                                "function": "update_actuator_status",
                                "args": {
                                    "actuator_id": "field",
                                    "field_name": self.memory["last_field"],
                                    "new_status": status
                                }
                            })
                        else:
                            return {
                                "intent_category": intent_category,
                                "needs_clarification": True,
                                "clarification_question": "Which field would you like to irrigate?",
                                "function_calls": []
                            }
            
            elif intent_category == "status_check":
                if entities["field_names"]:
                    function_calls.extend([
                        {"function": "get_field_by_name", "args": {"field_name": name}}
                        for name in entities["field_names"]
                    ])
                elif entities["actuator_ids"]:
                    function_calls.extend([
                        {"function": "get_actuator_by_id", "args": {"actuator_id": aid}}
                        for aid in entities["actuator_ids"]
                    ])
                    
            # Continue with existing LLM-based processing if needed
            if not function_calls:
                return super().resolve_user_intent(user_request)
                
            return {
                "source": "pattern_matching",
                "intent_category": intent_category,
                "function_calls": function_calls,
                "needs_clarification": False,
                "needs_confirmation": False
            }
                
        except Exception as e:
            print(f"Pattern matching failed: {e}")
            # Fall back to existing LLM-based intent resolution
            return super().resolve_user_intent(user_request)

    def infer_from_llm(self, user_request: str, similar_examples: List[Dict] = None) -> Dict:
        """
        Enhanced LLM-based intent inference with better prompting for farmer language
        """
        if similar_examples is None:
            similar_examples = []
        
        # Format examples for the prompt
        example_text = ""
        for i, example in enumerate(similar_examples[:2]):  # Limit to top 2 for focus
            similarity = example.get("similarity_score", 0)
            example_text += f"Example {i+1} (similarity: {similarity:.2f}):\n"
            example_text += f"User request: {example.get('user_request', '')}\n"
            
            # For high-similarity examples, include more details
            if similarity > 0.8:
                example_text += f"Category: {example.get('category', 'unknown')}\n"
                example_text += f"Intent: {example.get('intent_category', 'unknown')}\n"
                example_text += f"Function calls: {json.dumps(example.get('function_calls', []), indent=2)}\n"
            example_text += "\n"
    
        # Create improved system prompt that focuses on farmer language
        system_template = """You are a specialized farm control assistant that expertly understands how farmers naturally speak.

        PRIORITIZE understanding control operations above all else. When in doubt, assume the user wants to control something.

        Common farmer expressions and their meanings:
        - "The corn looks thirsty" = irrigate corn fields
        - "Give it a drink" = activate irrigation
        - "Shut it down" = turn off an actuator or system
        - "Hit the pumps" = activate water pumps
        - "Cut the water" = stop irrigation
        - "Give it some food" = activate fertilizer dispensers
        - "Set it for the evening" = schedule operation for evening
        - "It's looking dry out there" = fields need water
        - "The south field needs attention" = check status of south field
        - "The tomatoes don't look right" = check tomato field sensors

        Your primary goal is to convert natural language into precise system control commands, but ask for clarification if needed.

        Farm Context:
        - Current field focus: {memory_field}
        - Current crop focus: {memory_crop}
        - Last action performed: {memory_action}

        Available Farm System Information:
        Fields: {fields}
        Actuators: {actuators}

        Similar Examples:
        {examples}
    
        Convert the user request into a structured plan following this format:
        {{
            "intent_category": "control_operation" | "information_request" | "status_check" | "clarification_needed" | "other",
            "function_calls": [
                {{
                    "function": "function_name",
                    "args": {{
                        "arg_name": "value"
                    }}
                }}
            ],
            "needs_clarification": false,
            "clarification_question": "",
            "needs_confirmation": false,
            "confirmation_message": ""
        }}
        
        Return only the JSON object with no additional text."""
    
        human_template = "User request: {request}"
    
        # Create chain with proper variable mapping
        output_parser = JsonOutputParser()
        intent_chain = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template)
        ]) | self.llm | output_parser
    
        try:
            # Prepare memory context
            memory_field = self.memory.get("last_field", "None")
            memory_crop = self.memory.get("last_crop", "None")
            memory_action = self.memory.get("last_action", "None")
            
            # Invoke chain with properly mapped variables
            result = intent_chain.invoke({
                "fields": ", ".join([f"{f.get('id', '')}: {f.get('name', '')}" 
                                   for f in self.system_info.get("fields", [])]),
                "actuators": ", ".join([f"{a.get('id', '')}: {a.get('name', '')}" 
                                      for a in self.system_info.get("actuators", [])]),
                "memory_field": memory_field,
                "memory_crop": memory_crop,
                "memory_action": memory_action,
                "examples": example_text,
                "request": user_request
            })
            
            return result
    
        except Exception as e:
            print(f"LLM inference error details: {e}")
            print(f"Stack trace: {traceback.format_exc()}")
            return {
                "intent_category": "error",
                "error": str(e),
                "function_calls": [],
                "needs_clarification": True,
                "clarification_question": "I'm not quite sure what you mean. Could you tell me again what you'd like to do?",
                "needs_confirmation": False,
                "confirmation_message": ""
            }
        
    def convert_rag_to_executable(self, rag_result: Dict) -> Dict:
        """Convert potentially text-based RAG function calls to proper executable format"""
        function_calls = rag_result.get("function_calls", [])
        fixed_calls = []
        
        for call in function_calls:
            if isinstance(call, dict) and "function" in call:
                # If args is a string (like "open only irrigation-related actuators"), convert to proper args
                if isinstance(call.get("args"), str):
                    # Use LLM to parse natural language instructions into proper function args
                    fixed_args = self._parse_nl_args_with_llm(call["function"], call["args"])
                    fixed_calls.append({"function": call["function"], "args": fixed_args})
                else:
                    fixed_calls.append(call)
        
        rag_result["function_calls"] = fixed_calls
        return rag_result

    def _parse_nl_args_with_llm(self, function_name: str, args_text: str) -> Dict:
        """Use LLM to parse natural language arguments into structured function arguments"""
        # Define regex patterns
        patterns = {
            "actuator_ids": r"([A-Z]+-\d{4})",
            "field_ids": r"field\s+(\d+)|field\s+(\w+)",
            "field_names": r"([A-Za-z]+)\s+field|([A-Za-z]+ern)\s+field?|field\s+of\s+([A-Za-z]+)|([A-Za-z]+)\s+Field",
            "resource_ids": r"(RES-\d{4})",
            "open_command": r"\b(open|start|activate|turn\s+on|switch\s+on|enable|power\s+on)\b",
            "close_command": r"\b(close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off)\b",
            "actuator_types": r"\b(valves?|pumps?|actuators?|water\s+valves?|sensors?|equipment|machines?|devices?)\b",
            "irrigation_command": r"\b(irrigate|water|start\s+irrigation|begin\s+watering)\b",
            "irrigation_stop": r"\b(stop\s+irrigation|stop\s+watering|end\s+irrigation)\b",
            "bulk_operation": r"\b(all|every|each|multiple|several|many)\b"
        }
    
        try:
            # First try regex pattern matching
            if function_name == "update_actuator_status":
                # Check for actuator IDs
                actuator_ids = re.findall(patterns["actuator_ids"], args_text, re.IGNORECASE)
                if actuator_ids:
                    # Found specific actuator ID
                    actuator_id = actuator_ids[0]
                elif re.search(patterns["bulk_operation"], args_text, re.IGNORECASE):
                    # Bulk operation requested
                    actuator_id = "all"
                elif re.search(patterns["irrigation_command"], args_text, re.IGNORECASE):
                    # Irrigation-specific command
                    actuator_id = "irrigation_system_main"
                else:
                    # No specific actuator identified
                    actuator_id = None
    
                # Determine status
                if re.search(patterns["open_command"], args_text, re.IGNORECASE) or \
                   re.search(patterns["irrigation_command"], args_text, re.IGNORECASE):
                    status = "open"
                elif re.search(patterns["close_command"], args_text, re.IGNORECASE) or \
                     re.search(patterns["irrigation_stop"], args_text, re.IGNORECASE):
                    status = "close"
                else:
                    status = None
    
                if actuator_id and status:
                    return {"actuator_id": actuator_id, "new_status": status}
    
            # If regex parsing fails or for other functions, fall back to LLM
            function_schema = FUNCTION_DESCRIPTIONS.get(function_name, {})
            arg_schema = function_schema.get("args", {})
            
            args_template = ChatPromptTemplate.from_messages([
                ("system", f"""
                You are parsing natural language farm control instructions into structured function arguments.
                
                Function name: {function_name}
                Function description: {function_schema.get("description", "")}
                
                Expected arguments:
                {json.dumps(arg_schema, indent=2)}
                
                Natural language instruction: "{args_text}"
                
                Parse this into a JSON object with the proper argument names and values.
                For example, if the instruction is "open only irrigation-related actuators" for update_actuator_status,
                you might return: {{"actuator_id": "irrigation_system", "new_status": "open"}}
                
                Return only the JSON object with no explanation.
                """),
                ("human", "Parse this into structured function arguments.")
            ])
            
            output_parser = JsonOutputParser()
            args_chain = args_template | self.llm | output_parser
            
            parsed_args = args_chain.invoke({})
            return parsed_args
    
        except Exception as e:
            print(f"Error parsing arguments: {e}")
            print(f"Stack trace: {traceback.format_exc()}")
            # Fallback to simple parsing
            if function_name == "update_actuator_status":
                if any(word in args_text.lower() for word in ["open", "start", "activate", "on", "enable"]):
                    status = "open"
                else:
                    status = "close"
                    
                if "irrigation" in args_text.lower():
                    return {"actuator_id": "irrigation_system_main", "new_status": status}
                
                return {"actuator_id": "all", "new_status": status}
            
            return {}
        
    def call_functions(self, function_calls: List[Dict]) -> List[Dict]:
        """Execute function calls and return results"""
        results = []
        
        for call in function_calls:
            fn_name = call.get("function")
            args = call.get("args", {})
            
            # Skip if no farm control service available
            if not self.farm_control_service:
                results.append({
                    "function": fn_name, 
                    "args": args, 
                    "result": f"Would call {fn_name} with {args}",
                    "simulation": True
                })
                continue
                
            try:
                # Handle special case for "all" actuators with update_actuator_status
                if fn_name == "update_actuator_status" and args.get("actuator_id") == "all":
                    # Get all actuators and update them
                    actuators = self.farm_control_service.get_all_actuators()
                    batch_results = []
                    for actuator in actuators:
                        act_id = actuator.get("id")
                        act_fn = getattr(self.farm_control_service, fn_name)
                        act_result = act_fn(actuator_id=act_id, new_status=args.get("new_status"))
                        batch_results.append(act_result)
                    results.append({"function": fn_name, "args": args, "result": batch_results})
                    
                # Handle field-specific batch operations
                elif fn_name == "update_actuator_status" and args.get("actuator_id") == "field":
                    field_name = args.get("field_name") or self.memory.get("last_field")
                    if field_name:
                        # Get actuators for this field
                        field_actuators = self.farm_control_service.get_actuators_by_field_name(field_name=field_name)
                        batch_results = []
                        for actuator in field_actuators:
                            act_id = actuator.get("id")
                            act_fn = getattr(self.farm_control_service, fn_name)
                            act_result = act_fn(actuator_id=act_id, new_status=args.get("new_status"))
                            batch_results.append(act_result)
                        results.append({"function": fn_name, "args": args, "result": batch_results})
                
                # Handle specific actuator types
                elif fn_name == "update_actuator_status" and args.get("actuator_type"):
                    actuator_type = args.get("actuator_type")
                    # Get actuators of this type
                    typed_actuators = self.farm_control_service.get_actuator_by_type(
                        actuator_type=actuator_type, include_related=True)
                    batch_results = []
                    for actuator in typed_actuators:
                        act_id = actuator.get("id")
                        act_fn = getattr(self.farm_control_service, fn_name)
                        act_result = act_fn(actuator_id=act_id, new_status=args.get("new_status"))
                        batch_results.append(act_result)
                    results.append({"function": fn_name, "args": args, "result": batch_results})
                    
                # Regular function execution
                elif hasattr(self.farm_control_service, fn_name):
                    fn = getattr(self.farm_control_service, fn_name)
                    result = fn(**args)
                    results.append({"function": fn_name, "args": args, "result": result})
                else:
                    results.append({
                        "function": fn_name, 
                        "args": args, 
                        "error": "Function not found in FarmControlService"
                    })
            except Exception as e:
                results.append({
                    "function": fn_name, 
                    "args": args, 
                    "error": str(e)
                })
                
        return results
    
    def _function_to_action(self, fn_name: str, args: Dict) -> str:
        """Convert function names and args to natural language actions"""
        if fn_name == "update_actuator_status":
            actuator_id = args.get("actuator_id", "unknown")
            status = args.get("new_status", "unknown")
            
            if actuator_id == "all":
                return f"{status} all actuators"
            elif actuator_id == "field":
                field_name = args.get("field_name", "the field")
                return f"{status} all equipment in {field_name}"
            elif "irrigation" in actuator_id.lower():
                return f"{status} the irrigation system"
            else:
                return f"{status} {actuator_id}"
                
        elif fn_name == "get_field_by_name":
            return f"retrieve information about field {args.get('field_name', '')}"
            
        elif fn_name == "get_field_by_id":
            return f"retrieve information about field ID {args.get('field_id', '')}"
            
        elif fn_name == "get_all_fields":
            return "retrieve information about all fields"
            
        elif fn_name == "get_actuator_by_id":
            return f"retrieve information about actuator {args.get('actuator_id', '')}"
            
        elif fn_name == "get_actuator_by_type":
            return f"retrieve information about {args.get('actuator_type', '')} actuators"
            
        # Add more mappings as needed
        return fn_name.replace("_", " ")
    def _format_function_results(self, function_results: List[Dict]) -> str:
        """Format function results in a more readable way for the LLM"""
        if not function_results:
            return "No actions were performed."
            
        formatted = []
        for result in function_results:
            fn_name = result.get("function", "")
            args = result.get("args", {})
            outcome = result.get("result", {})
            error = result.get("error", None)
            
            # Convert function name to natural language action
            action = self._function_to_action(fn_name, args)
            
            # Format the outcome in natural language
            if error:
                formatted.append(f"Attempted to {action}, but encountered an issue: {error}")
            elif isinstance(outcome, list):
                if len(outcome) > 0:
                    formatted.append(f"Successfully {action} ({len(outcome)} items affected)")
                else:
                    formatted.append(f"Attempted to {action}, but nothing was affected")
            elif outcome:
                if isinstance(outcome, dict) and "name" in outcome:
                    formatted.append(f"Successfully {action} for {outcome.get('name')}")
                else:
                    formatted.append(f"Successfully {action}")
            else:
                formatted.append(f"Attempted to {action}, status unclear")
                
        return "\n".join(formatted)
    
    def generate_user_response(self, state: Dict) -> str:
        """Generate a more conversational user-friendly response based on function execution results"""
        user_request = state.get("user_request", "")
        intent_category = state.get("intent_category", "other")
        function_results = state.get("function_calls", [])
        
        # Format function results in a more digestible way instead of raw JSON
        formatted_results = self._format_function_results(function_results)
        
        # Extract key memory elements for contextual responses
        active_field = self.memory.get("last_field")
        active_crop = self.memory.get("last_crop")
        last_action = self.memory.get("last_action")
        last_interaction = self.memory.get("last_interaction_type")
        
        # Create a more focused system prompt
        system_message = """
            You are a friendly, helpful farming assistant named FarmHelper. Respond to the farmer's request
            in a natural, conversational way that a helpful farm manager would talk.
            
            Important guidelines:
            - Use plain language and farming terminology, not technical jargon
            - Acknowledge the farmer's request and confirm what you did
            - If action was taken, briefly confirm what was done
            - If information was provided, summarize it concisely 
            - If there were errors, explain what went wrong in practical terms
            - Refer to fields and crops by name when you know them
            - Add a small bit of relevant context or helpful tip if appropriate
            - Keep responses brief (2-4 sentences) unless detailed information was requested
            - Use contractions and casual language (e.g., "I've turned on the irrigation")
            
            The farmer is busy and wants clear, helpful responses without unnecessary detail.
        """
        
        human_message = f"""
            Farmer's request: "{user_request}"
            
            Request type: {intent_category}
            
            System actions and results: {formatted_results}
            
            Context:
            - Current field: {active_field if active_field else "None"}
            - Current crop: {active_crop if active_crop else "None"}
            - Last action: {last_action if last_action else "None"}
            - Current focus: {last_interaction if last_interaction else "None"}
            
            Special handling:
            - If clarification needed: {state.get("needs_clarification", False)}
            - Clarification question: {state.get("clarification_question", "")}
            - If confirmation needed: {state.get("needs_confirmation", False)}
            - Confirmation message: {state.get("confirmation_message", "")}

            Generate a natural, conversational response:
        """

        try:
            # Use the LLM to generate a response
            response = self.llm.invoke([{"role": "system", "content": system_message}, 
                                        {"role": "user", "content": human_message}])
            return response.content
        except Exception as e:
            print(f"Response generation error: {e}")
            print(f"Stack trace: {traceback.format_exc()}")
            # Provide a more conversational fallback response
            if intent_category == "control_operation":
                return "I've processed your request, but had some trouble confirming the details. Can you check if everything is working as expected?"
            return "I understood what you need, but ran into a small issue. Could you try again or phrase it differently?"

    def execute_planned_actions(self, state: Dict) -> Dict:
        """Execute functions and generate user response"""
        # First, make sure function calls are properly formatted (especially from RAG)
        if state.get("source") in ["RAG", "vector_search"]:
            state = self.convert_rag_to_executable(state)
        
        # If clarification is needed, don't execute functions yet
        if state.get("needs_clarification", False):
            state["user_response"] = state.get("clarification_question", "Could you please clarify your request?")
            return state
            
        # If confirmation is needed, don't execute functions yet
        if state.get("needs_confirmation", False):
            state["user_response"] = state.get("confirmation_message", "Would you like to proceed with this operation?")
            return state
            
        # Execute functions
        execution_results = self.call_functions(state.get("function_calls", []))
        state["function_calls"] = execution_results
        
        # Update memory
        self.update_memory(state)
        state["memory"] = self.memory
        
        # Generate user response
        user_response = self.generate_user_response(state)
        state["user_response"] = user_response
        
        return state
    
    def resolve_ambiguous_references(self, user_request: str) -> Tuple[str, bool]:
        """
        Enhanced version to resolve ambiguous pronouns and references in user requests based on memory
        """
        user_request_lower = user_request.lower()
        original_request = user_request
        was_resolved = False
        
        # Farm-specific ambiguous references
        farm_terms = {
            "field_refs": ["it", "that", "there", "the field", "this field", "this area", "that area"],
            "crop_refs": ["it", "them", "the crop", "the plants", "the produce", "my crop"],
            "actuator_refs": ["it", "that", "the system", "the equipment", "the machine", "this device"],
            "irrigation_refs": ["the water", "the irrigation", "the system", "the watering"],
            "fertilizer_refs": ["the food", "the nutrients", "the fertilizer"],
            "action_verbs": ["water", "irrigate", "spray", "feed", "fertilize", "open", "close", 
                            "turn on", "turn off", "start", "stop", "activate", "shut", "switch"]
        }
        
        # Check for common farmer expressions (expanded)
        farmer_expressions = {
            r"looks (thirsty|dry)": "needs irrigation for",
            r"needs a drink": "needs irrigation for",
            r"give (it|them) a drink": "start irrigation for",
            r"getting too (wet|soggy|damp)": "stop irrigation for",
            r"shut (it|everything) down": "stop all systems in",
            r"hit the pumps": "start water pumps for",
            r"cut the water": "stop irrigation for",
            r"looks hungry": "needs fertilizer for",
            r"give (it|them) some food": "apply fertilizer to",
            r"set (it|everything) for (evening|morning|tonight)": "schedule systems for later in"
        }
        
        # Replace farmer expressions
        for expression, replacement in farmer_expressions.items():
            if re.search(expression, user_request_lower):
                # Only replace if we have context about which field
                if self.memory.get("last_field") and self.memory.get("field_focus"):
                    field_name = self.memory.get("last_field")
                    user_request = re.sub(expression, f"{replacement} {field_name}", user_request, flags=re.IGNORECASE)
                    was_resolved = True
        
        # Handle ambiguous references
        has_ambiguous_ref = any(ref in user_request_lower for refs in farm_terms.values() for ref in refs)
        
        if has_ambiguous_ref:
            # Field references
            if self.memory.get("last_field") and self.memory.get("field_focus"):
                field_name = self.memory.get("last_field")
                for ref in farm_terms["field_refs"]:
                    if ref in user_request_lower:
                        # Check if there's an action verb nearby to confirm it's about the field
                        for verb in farm_terms["action_verbs"]:
                            if verb in user_request_lower:
                                user_request = re.sub(r"\b" + re.escape(ref) + r"\b", f"field {field_name}", 
                                                    user_request, flags=re.IGNORECASE)
                                was_resolved = True
                                break
            
            # Crop references
            if self.memory.get("last_crop") and self.memory.get("crop_focus"):
                crop_name = self.memory.get("last_crop")
                for ref in farm_terms["crop_refs"]:
                    if ref in user_request_lower:
                        user_request = re.sub(r"\b" + re.escape(ref) + r"\b", f"the {crop_name} crop", 
                                            user_request, flags=re.IGNORECASE)
                        was_resolved = True
            
            # Actuator references
            if self.memory.get("last_actuator_name") and self.memory.get("last_interaction_type") == "actuator_control":
                actuator_name = self.memory.get("last_actuator_name")
                for ref in farm_terms["actuator_refs"]:
                    if ref in user_request_lower:
                        user_request = re.sub(r"\b" + re.escape(ref) + r"\b", actuator_name, 
                                            user_request, flags=re.IGNORECASE)
                        was_resolved = True
            
            # Special handling for irrigation references
            if any(ref in user_request_lower for ref in farm_terms["irrigation_refs"]):
                if any(verb in user_request_lower for verb in ["on", "start", "open", "activate"]):
                    if self.memory.get("last_field"):
                        field_name = self.memory.get("last_field")
                        user_request = f"start irrigation for field {field_name}"
                        was_resolved = True
                elif any(verb in user_request_lower for verb in ["off", "stop", "close", "deactivate", "shut"]):
                    if self.memory.get("last_field"):
                        field_name = self.memory.get("last_field")
                        user_request = f"stop irrigation for field {field_name}"
                        was_resolved = True
        
        return user_request if was_resolved else original_request, was_resolved
    
    
    def find_similar_rag_examples(self, user_request: str, top_n=3) -> List[Dict]:
        """Find semantically similar examples from the RAG data"""
        # In a real implementation, you would use embeddings and vector search
        # This is a simplified example
        
        # Ideally, precompute embeddings for all examples during initialization
        examples = []
        for category in self.rag_data:
            examples.extend(category.get("examples", []))
        
        # Use a simple text similarity measure as a placeholder
        # In production, use proper embedding-based similarity
        similar_examples = []
        for example in examples:
            # Calculate similarity (placeholder)
            score = self._text_similarity(user_request, example.get("user_request", ""))
            similar_examples.append((score, example))
        
        # Sort by similarity score and return top N
        similar_examples.sort(reverse=True)
        return [example for _, example in similar_examples[:top_n]]

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity function (placeholder)"""
        # In production, use proper embedding similarity
        # For now, count word overlap as a simple heuristic
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))
        return overlap / total if total > 0 else 0

    def _build_graph(self):
        class MCPState(TypedDict, total=False):
            user_request: str
            intent_category: str
            function_calls: List[Dict]
            user_response: str
            next: str

        def parse_intent(state: MCPState):
            try:
                # Ensure input is properly handled
                state["user_request"] = state.get("user_request", "").strip()
                state["original_request"] = state["user_request"]
                
                # Clear any previous error states
                state.pop("error", None)
                
                # Use more robust error handling for intent resolution
                try:
                    llm_result = self.resolve_user_intent(state["user_request"])
                    if llm_result and isinstance(llm_result, dict):
                        # Update with new fields but preserve original keys
                        for key, value in llm_result.items():
                            state[key] = value
                        
                        # Set next node
                        state["next"] = "execute_actions"
                    else:
                        raise ValueError("Intent resolution returned invalid result")
                except Exception as e:
                    print(f"Intent resolution error: {e}")
                    state["intent_category"] = "error"
                    state["function_calls"] = []
                    state["needs_clarification"] = True
                    state["clarification_question"] = "I'm having trouble understanding. Could you please rephrase your request?"
                    state["next"] = "end"
                
                return state
            
            except Exception as e:
                print(f"Critical error in parse_intent: {e}")
                print(f"Stack trace: {traceback.format_exc()}")
                
                # Ensure we return a valid state
                state["intent_category"] = "error"
                state["function_calls"] = []
                state["user_response"] = "I encountered a system error. Please try again."
                state["next"] = "end"
                return state
    
        def handle_followup(state: MCPState):
            user_input = state["user_request"].lower()
            
            # Process confirmation response
            if state.get("awaiting_confirmation"):
                if any(word in user_input for word in ["yes", "yeah", "yep", "sure", "confirm", "ok", "okay", "proceed", "go ahead"]):
                    # User confirmed, execute the stored plan
                    state.update(state["stored_plan"])
                    state["awaiting_confirmation"] = False
                    state["next"] = "execute_actions"
                    return state
                else:
                    # User declined, cancel operation
                    state["user_response"] = "Operation cancelled. Is there something else I can help with?"
                    state["awaiting_confirmation"] = False
                    state["next"] = "end"
                    return state
            
            # Process clarification response
            if state.get("awaiting_clarification"):
                # Use LLM to process the clarification
                clarification_template = ChatPromptTemplate.from_messages([
                    ("system", f"""
                    You are analyzing a user's clarification response to update a farm control plan.
                    Original request: {state.get("original_request", "")}
                    Clarification question: {state.get("clarification_question", "")}
                    User's clarification: {user_input}

                    Return JSON:
                    {{
                    "intent_category": "control_operation" | "information_request" | "status_check" | "other",
                    "function_calls": [
                        {{"function": "function_name", "args": {{"arg_name": "value"}}}}
                    ],
                    "needs_more_clarification": false,
                    "clarification_question": ""
                    }}
                    """),
                    ("human", "Process this clarification")
                ])
                output_parser = JsonOutputParser()
                clarification_chain = clarification_template | self.llm | output_parser
                
                try:
                    # Notice we're passing an empty dict here since the template variables
                    # are already formatted into the f-string
                    clarification_result = clarification_chain.invoke({})
                    
                    # Update state with resolved clarification
                    state.update({
                        "intent_category": clarification_result.get("intent_category", "control_operation"),
                        "function_calls": clarification_result.get("function_calls", []),
                        "needs_clarification": clarification_result.get("needs_more_clarification", False),
                        "clarification_question": clarification_result.get("clarification_question", ""),
                        "awaiting_clarification": False
                    })
                    
                    state["next"] = "execute_actions"
                    return state
                    
                except Exception as e:
                    print(f"Clarification processing error: {e}")
                    print(f"Stack trace: {traceback.format_exc()}")
                    # If parsing fails, provide generic response
                    state["user_response"] = "I'm having trouble understanding. Could you rephrase your request?"
                    state["awaiting_clarification"] = False
                    state["next"] = "end"
                    return state
            
            state["next"] = "execute_actions"
            return state

        def execute_actions(state: MCPState):
            try:
                # If needs confirmation, store plan and await confirmation
                if state.get("needs_confirmation", False):
                    state["stored_plan"] = {k: v for k, v in state.items() if k != "awaiting_confirmation"}
                    state["awaiting_confirmation"] = True
                    state["user_response"] = state.get("confirmation_message", "Would you like to proceed with this operation?")
                    state["next"] = "end"
                    return state
                    
                # If needs clarification, store request and await clarification
                if state.get("needs_clarification", False):
                    state["original_request"] = state.get("user_request", "")
                    state["awaiting_clarification"] = True
                    state["user_response"] = state.get("clarification_question", "Could you please clarify your request?")
                    state["next"] = "end"
                    return state
                    
                # Otherwise, execute planned actions
                try:
                    result_state = self.execute_planned_actions(state)
                    if not result_state or not isinstance(result_state, dict):
                        raise ValueError("execute_planned_actions returned invalid result")
                        
                    # Update state with result values, but keep original state structure
                    for key, value in result_state.items():
                        state[key] = value
                        
                    state["next"] = "end"
                    return state
                except Exception as e:
                    print(f"Action execution error: {e}")
                    state["user_response"] = "I encountered an issue while executing your request. Please try again."
                    state["next"] = "end"
                    return state
                
            except Exception as e:
                print(f"Error in execute_actions: {e}")
                state["user_response"] = f"I encountered an unexpected error. Please try again."
                state["next"] = "end"
                return state

        def end_node(state: MCPState):
            # Finalize state and return user response
            state["user_response"] = state.get("user_response", "Thank you! Is there anything else I can assist you with?")
            state["next"] = "end"
            return state
        
        try:
            g = StateGraph(MCPState)
            
            # Add nodes
            g.add_node("parse_intent", parse_intent)
            g.add_node("handle_followup", handle_followup)
            g.add_node("execute_actions", execute_actions)
            g.add_node("end", end_node)
            
            # Add edges
            g.add_edge(START, "parse_intent")
            
            g.add_conditional_edges(
                "parse_intent",
                lambda x: x.get("next", "end"),  # Default to end if next is missing
                {
                    "handle_followup": "handle_followup",
                    "execute_actions": "execute_actions",
                    "end": "end"
                }
            )
            
            g.add_conditional_edges(
                "handle_followup",
                lambda x: x.get("next", "end"),
                {
                    "execute_actions": "execute_actions",
                    "end": "end"
                }
            )
            
            g.add_conditional_edges(
                "execute_actions",
                lambda x: x.get("next", "end"),
                {
                    "end": "end"
                }
            )
            
            g.add_edge("end", END)
            
            return g
        except Exception as e:
            print(f"Error building graph: {e}")
            # Return a simplified graph that just outputs an error message
            g = StateGraph(MCPState)
            
            def error_node(state):
                state["user_response"] = f"System error occurred: {e}"
                return state
                
            g.add_node("error", error_node)
            g.add_edge(START, "error")
            g.add_edge("error", END)
            
            return g
    
    def run(self, user_request: str) -> Dict:
        try:
            # Ensure we initialize with a valid state structure
            initial_state = {"user_request": user_request, "function_calls": []}
            
            # Log the start of processing
            print(f"Processing request: {user_request}")
            
            # Invoke the graph with proper state initialization
            print("Invoking graph...")
            result = self.graph.invoke(initial_state)
            
            # Validate result before proceeding
            if result is None or not isinstance(result, dict):
                print("Warning: Graph returned invalid result")
                result = {
                    "user_request": user_request,
                    "intent_category": "error",
                    "function_calls": [],
                    "user_response": "I encountered an issue processing your request. Please try again."
                }
            
            # Ensure user_response exists in result
            if "user_response" not in result:
                result["user_response"] = self.generate_user_response(result)
            
            print(f"Final result: {result.get('user_response')}")
            return result
            
        except Exception as e:
            # Handle exceptions
            error_msg = str(e)
            print(f"Error in agent.run: {error_msg}")
            print(f"Stack trace: {traceback.format_exc()}")
            
            return {
                "user_request": user_request,
                "intent_category": "error",
                "error": error_msg,
                "function_calls": [],
                "user_response": "I encountered a technical issue. Please try again with a different command."
            }